#!/usr/bin/env python3
"""Backfill exchange historical daily closing prices without fabricated observations.

1. Priority watchlist: TWSE and TPEx *per-stock monthly* official history.
2. Whole market: bounded date-by-date TWSE/TPEx quote retrieval, resumable.

Designed for GitHub Actions. Never manufacture missing dates, returns or prices.
TWSE raw quote volume is shares / value is TWD; TPEx monthly legacy endpoint
quotes volume in 1,000 shares and value in 1,000 TWD.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import io
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'history_data'
SNAPSHOT = ROOT / 'site' / 'data' / 'official_snapshot.csv'
COLUMNS = ['date','stock_id','close','volume_shares','trade_value_twd']
PRIORITY = {'8064': '上櫃', '3533': '上市', '2330': '上市', '2345': '上市'}
USER_AGENT = 'Mozilla/5.0 (TPE-MFDS-2.1.1 public market research; contact via GitHub repository)'
DAY_TWSE = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
DAY_TPEX = 'https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php'
MONTH_TWSE = 'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY'
MONTH_TPEX = 'https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php'


def num(x):
    x = re.sub(r'<[^>]*>', '', html.unescape(str(x or ''))).replace(',', '').strip()
    if x in ('', '--', '---', '----', 'X', '－', '—', '不適用'):
        return None
    try:
        v = float(x)
        return v if 0 <= abs(v) < float('inf') else None
    except (ValueError, TypeError):
        return None


def iso_date(x):
    x = str(x or '').strip()
    try:
        if re.fullmatch(r'\d{3}/\d{1,2}/\d{1,2}', x):
            y, m, d = map(int, x.split('/'))
            return dt.date(y+1911, m, d).isoformat()
        if re.fullmatch(r'\d{4}/\d{1,2}/\d{1,2}', x):
            y, m, d = map(int, x.split('/'))
            return dt.date(y, m, d).isoformat()
        if re.fullmatch(r'\d{7}', x):
            return dt.date(int(x[:3])+1911, int(x[3:5]), int(x[5:7])).isoformat()
        return dt.date.fromisoformat(x.replace('/', '-')).isoformat()
    except ValueError:
        return None


def monthly_dates(asof, num_months=13):
    date = asof.replace(day=1)
    out = []
    for _ in range(num_months):
        out.append(date)
        date = date.replace(day=1) - dt.timedelta(days=1)
        date = date.replace(day=1)
    return out


def record(day, code, close, volume=None, value=None):
    if not re.fullmatch(r'[1-9]\d{3}', str(code)) or not day or close is None or close <= 0:
        return None
    return {'date': day, 'stock_id': str(code),
            'close': f'{close:.4f}'.rstrip('0').rstrip('.'),
            'volume_shares': str(int(volume)) if volume is not None and volume >= 0 else '',
            'trade_value_twd': str(int(value)) if value is not None and value >= 0 else ''}


def twse_month(payload, symbol):
    if not isinstance(payload, dict):
        raise ValueError('TWSE month response is not JSON object')
    if payload.get('stat') not in ('OK', None):
        return []
    out=[]
    for item in payload.get('data', []):
        if len(item)<7: continue
        r=record(iso_date(item[0]),symbol,num(item[6]),num(item[1]),num(item[2]))
        if r: out.append(r)
    return out


def tpex_month(payload, symbol):
    if not isinstance(payload,dict):
        raise ValueError('TPEx month response is not JSON object')
    data = payload.get('aaData')
    if data is None:
        # Some TPEx endpoints use a tables envelope.
        tables=payload.get('tables') or []
        data=tables[0].get('data', []) if tables else []
    out=[]
    for item in data:
        if len(item)<7: continue
        r=record(iso_date(item[0]),symbol,num(item[6]),
                 num(item[1])*1000 if num(item[1]) is not None else None,
                 num(item[2])*1000 if num(item[2]) is not None else None)
        if r: out.append(r)
    return out


def column_index(fields, keywords):
    for keyword in keywords:
        for idx,field in enumerate(fields):
            if keyword in re.sub(r'<[^>]*>','',str(field)):
                return idx
    return None


def parse_full_market(payload, market, target_day):
    if not isinstance(payload,dict): raise ValueError('Full-market response not an object')
    out=[]
    tables=payload.get('tables') or []
    if not tables and payload.get('stat') in ('OK','ok'):
        raise ValueError('Exchange reported OK but returned no price table')
    if not tables and not any(k in payload for k in ('stat','tables')):
        raise ValueError('Unrecognized full-market response structure')
    for table in tables:
        fields=table.get('fields') or []
        ci=column_index(fields,['證券代號','代號'])
        close_i=column_index(fields,['收盤價','收盤'])
        vol_i=column_index(fields,['成交股數','成交量'])
        value_i=column_index(fields,['成交金額','成交值'])
        if ci is None or close_i is None: continue
        for a in table.get('data') or []:
            if not isinstance(a,(list,tuple)) or max(ci,close_i)>=len(a): continue
            code = re.sub(r'<[^>]*>','',str(a[ci])).strip()
            if not re.fullmatch(r'[1-9]\d{3}',code): continue
            c=num(a[close_i])
            # Daily source has raw shares and raw TWD, unlike monthly TPEx endpoint.
            vol=num(a[vol_i]) if vol_i is not None and vol_i<len(a) else None
            value=num(a[value_i]) if value_i is not None and value_i<len(a) else None
            r=record(target_day,code,c,vol,value)
            if r: out.append(r)
        if out:
            break
    if not out and any((t.get('data') or []) for t in tables):
        raise ValueError('Price table unavailable or schema changed')
    return out


def url(params, base):
    return base + '?' + urllib.parse.urlencode(params)


def fetch_json(addr, retries=2, sleep=time.sleep):
    err=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(addr,headers={'User-Agent':USER_AGENT,'Accept':'application/json,text/plain,*/*'})
            with urllib.request.urlopen(req,timeout=12) as rsp:
                return json.load(rsp)
        except Exception as exc:
            err=exc
            if attempt+1 < retries: sleep(2*(attempt+1))
    raise RuntimeError(str(err))


def read_rows(path):
    if not path.exists(): return []
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def write_rows(path, rows):
    path.parent.mkdir(exist_ok=True,parents=True)
    out=io.StringIO()
    w=csv.DictWriter(out,fieldnames=COLUMNS,lineterminator='\n')
    w.writeheader()
    for r in rows:
        w.writerow({c:r.get(c,'') for c in COLUMNS})
    s=out.getvalue()
    if not path.exists() or path.read_text('utf-8') != s:
        path.write_text(s,encoding='utf-8')


def get_snapshot_asof(snapshot=SNAPSHOT):
    rows=read_rows(snapshot)
    days=sorted(set(r.get('asof','') for r in rows if iso_date(r.get('asof'))))
    if not days: raise RuntimeError('無可用的官方行情日期；先執行 fetch_official.py')
    return dt.date.fromisoformat(days[-1])


def priority_backfill(asof, archive=ARCHIVE, symbols=None, request=fetch_json, sleep=time.sleep):
    """Prioritize a handful of named stocks. A failed month does not create fake data."""
    symbols=PRIORITY if symbols is None else symbols
    dest=archive/'watchlist_seed.csv'
    existing={(r['date'],r['stock_id']):r for r in read_rows(dest)}
    errors=[]
    for symbol,market in symbols.items():
        consecutive_failure=0
        observed=sum(1 for (date,code) in existing if code==symbol and date <=asof.isoformat())
        if observed>=220:
            print(f'priority {symbol}: {observed} sessions already saved; skip')
            continue
        for m in monthly_dates(asof):
            if market=='上市':
                endpoint=url({'date':m.strftime('%Y%m%d'),'stockNo':symbol,'response':'json'},MONTH_TWSE)
                parser=twse_month
            else:
                endpoint=url({'l':'zh-tw','d':f'{m.year-1911}/{m.month:02d}','stkno':symbol},MONTH_TPEX)
                parser=tpex_month
            try:
                payload=request(endpoint)
                arr=parser(payload,symbol)
                consecutive_failure=0
                for r in arr:
                    if r['date']<=asof.isoformat():existing[(r['date'],symbol)]=r
            except Exception as exc:
                consecutive_failure += 1
                errors.append(f'{symbol} {m:%Y-%m}: {str(exc)[:100]}')
                if consecutive_failure >= 2:
                    errors.append(f'{symbol}: historical source unavailable; later months not checked')
                    break
            sleep(0.7)
        print('priority',symbol, 'records',sum(c==symbol for d,c in existing))
        # Keep partial successful results, including when an endpoint times out.
        write_rows(dest,[existing[k] for k in sorted(existing)])
    return errors


def market_backfill(asof, archive=ARCHIVE, per_run=15, calendar_days=395, request=fetch_json, sleep=time.sleep):
    """Resume earliest missing calendar weekdays, bounded to per_run requests per exchange.

    State is explicit. Returns errors and counts; does not infer completeness from a green Action.
    """
    state_path=archive/'market_backfill_state.json'
    cutoff=asof-dt.timedelta(days=calendar_days)
    if state_path.exists():
        state=json.loads(state_path.read_text('utf-8'))
    else:
        state={'next_date':asof.isoformat(),'attempted_weekdays':0,'failed_dates':[],'notes':'逐日回補；交易所無資料日不產生行情'}
    cursor=dt.date.fromisoformat(state['next_date'])
    if cursor>asof:cursor=asof
    dates=[]
    while cursor>=cutoff and len(dates)<per_run:
        if cursor.weekday()<5:
            dates.append(cursor)
        cursor-=dt.timedelta(days=1)
    failure_map={item['date']:item for item in state.get('failed_dates',[]) if 'date' in item}
    # Retry two unfinished/partial dates per run before continuing the history scan.
    retry_dates=[dt.date.fromisoformat(x) for x in sorted(failure_map,reverse=True)[:2]]
    consecutive_failed_days=0
    processed_new=set()
    for d in retry_dates+dates:
        day=d.isoformat()
        path=archive/(day+'.csv')
        if path.exists() and len(read_rows(path))>0 and day not in failure_map:
            continue
        results=[]; failed=[]
        pairs=[('上市', url({'date':d.strftime('%Y%m%d'),'type':'ALLBUT0999','response':'json'},DAY_TWSE)),
               ('上櫃', url({'l':'zh-tw','d':f'{d.year-1911}/{d.month:02d}/{d.day:02d}','se':'EW','o':'json'},DAY_TPEX))]
        for market,addr in pairs:
            try:
                part=parse_full_market(request(addr),market,day)
                if part:results+=part
            except Exception as exc:
                failed.append(market+':'+str(exc)[:80])
            sleep(0.65)
        if results:
            combined={r['stock_id']:r for r in read_rows(path)}
            combined.update({r['stock_id']:r for r in results})
            write_rows(path,[combined[k] for k in sorted(combined)])
        if d in dates:
            processed_new.add(day)
        if failed:
            failure_map[day]={'date':day,'sources':failed}
            consecutive_failed_days+=1
        else:
            failure_map.pop(day,None)
            consecutive_failed_days=0
        print(f'market {day}: {len(results)} verified rows, errors: {len(failed)}')
        if consecutive_failed_days>=3:
            # Abort early if exchange providers are down; keep progress honest.
            # Preserve unattempted dates, so next job resumes correctly.
            if d in dates:
                cursor = d - dt.timedelta(days=1)
            print('WARNING: consecutive historical source failures, stopping this run')
            break
    state['next_date']=cursor.isoformat()
    state['attempted_weekdays']=state.get('attempted_weekdays',0)+len(processed_new)
    state['range_start']=cutoff.isoformat()
    state['asof']=asof.isoformat()
    state['reached_start']=cursor<cutoff
    state['failed_dates']=[failure_map[k] for k in sorted(failure_map,reverse=True)[:300]]
    state_path.parent.mkdir(parents=True,exist_ok=True)
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n','utf-8')
    return state


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',choices=['priority','market','all'],default='all')
    ap.add_argument('--per-run',type=int,default=15)
    ap.add_argument('--archive',type=Path,default=ARCHIVE)
    ap.add_argument('--snapshot',type=Path,default=SNAPSHOT)
    args=ap.parse_args()
    asof=get_snapshot_asof(args.snapshot)
    if args.mode in ('priority','all'):
        errors=priority_backfill(asof,args.archive)
        for err in errors[:12]: print('WARNING priority:',err)
        if errors: print('WARNING priority incomplete months:',len(errors))
    if args.mode in ('market','all'):
        progress=market_backfill(asof,args.archive,max(1,min(45,args.per_run)))
        print('Backfill reached earliest requested day:',progress['reached_start'])


if __name__=='__main__':main()
