#!/usr/bin/env python3
"""Fetch the *latest* TWSE/TPEx daily close snapshots for the dashboard.

Only public, delayed exchange data are displayed. Nothing in this script computes
prediction probabilities, buy/sell advice, large-holder ownership or 20-day averages.
"""
import argparse
import csv
import datetime as dt
import io
import html
import json
import re
import time
import urllib.request
from urllib.parse import urlencode
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'site' / 'data'
URLS = {
    '上市': 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    '上櫃': 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
}
TWSE_RWD = 'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL'
FIELDS = ['stock_id','stock_name','sector','market','close','change_pct','volume_shares',
          'trade_value_twd','avg_trade_value_twd','asof','large_holder_pct',
          'large_holder_change_pp','foreign_5d_net_twd',
          'M1','M2','M3','I1','I2','I3','F1','F2','F3','S1','S2','S3']


def number(s):
    try:
        a = str(s).strip().replace(',', '')
        if not a or a in {'--', '---', '----', 'X', '—', '－'}:
            return None
        v = float(a)
        return v if v == v and abs(v) != float('inf') else None
    except (ValueError, TypeError):
        return None


def iso_date(v):
    s = str(v or '').strip()
    try:
        if re.fullmatch(r'\d{7}', s):  # ROC YYYMMDD
            return dt.date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:])).isoformat()
        if re.fullmatch(r'\d{3}/\d\d/\d\d', s):
            return dt.date(int(s[:3]) + 1911, int(s[4:6]), int(s[7:])).isoformat()
        if re.fullmatch(r'\d{8}', s):
            return dt.date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
        return dt.date.fromisoformat(s).isoformat()
    except (ValueError, TypeError):
        return None


def is_common_four_digit(code):
    # Conservative common-stock *candidate* filter; not a security master.
    return bool(re.fullmatch(r'[1-9]\d{3}', code))


def first(row, *names):
    for key in names:
        value = row.get(key)
        if value is not None and str(value).strip() != '':
            return str(value).strip()
    return ''


def transform(records, market):
    parsed = []
    if not isinstance(records, list):
        raise ValueError('來源 JSON 並非陣列')
    for row in records:
        if not isinstance(row, dict):
            continue
        if market == '上市':
            code = first(row, 'Code'); name = first(row, 'Name')
            close = number(first(row, 'ClosingPrice'))
            amount = number(first(row, 'TradeValue'))
            day = iso_date(first(row, 'Date'))
            change = number(first(row, 'Change'))
        else:
            code = first(row, 'SecuritiesCompanyCode', 'SecuritiesCode', 'Code', 'SecuritiesNo')
            name = first(row, 'CompanyName', 'SecuritiesCompanyName', 'SecuritiesName', 'SecurityName', 'Name')
            close = number(first(row, 'Close', 'ClosingPrice', 'Closing'))
            amount = number(first(row, 'TransactionAmount', 'TradeValue', 'TradingAmount', 'TradingValue', 'TradeAmount'))
            day = iso_date(first(row, 'Date'))
            change = number(first(row, 'Change'))
        volume = number(first(row, 'TradeVolume', 'TradingShares', 'TradingVolume', 'TradeShares'))
        if not is_common_four_digit(code) or not name or close is None or close <= 0 or not day:
            continue
        # Only use an actual close and a known date. The daily trade amount is
        # not a 20-day average, which stays empty until we build history.
        out = dict.fromkeys(FIELDS, '')
        out.update(stock_id=code, stock_name=name, sector='未分類', market=market,
                   close=f'{close:.4f}'.rstrip('0').rstrip('.'), asof=day)
        if amount is not None and amount >= 0:
            out['trade_value_twd'] = str(int(amount))
        if volume is not None and volume >= 0:
            out['volume_shares'] = str(int(volume))
        # For displayed daily price % change, yesterday close = today - delta.
        # These endpoints usually supply the *point* change, not percentage.
        if change is not None and close - change > 0:
            out['change_pct'] = f'{change / (close-change) * 100:.4f}'
        parsed.append(out)
    # All records should have same latest date; avoid mixing old isolated rows.
    if parsed:
        newest = max(x['asof'] for x in parsed)
        parsed = [x for x in parsed if x['asof'] == newest]
    return parsed



def transform_twse_rwd(payload):
    """Parse TWSE official RWD all-stocks daily report using its named columns.

    Never infer the requested date: use only the date returned by the source.
    Never assume fixed column indexes, since official CSV/JSON schemas can vary.
    """
    if not isinstance(payload, dict) or payload.get('stat') != 'OK':
        raise ValueError('TWSE RWD not OK or unsupported JSON response')
    date = iso_date(payload.get('date'))
    if not date:
        raise ValueError('TWSE RWD has no valid response date')
    tables = payload.get('tables')
    blocks = tables if isinstance(tables, list) and tables else [payload]
    result = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        fields = [re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', html.unescape(str(x))))
                  for x in (block.get('fields') or [])]
        def col(*names):
            for name in names:
                norm = re.sub(r'\s+', '', name)
                if norm in fields:
                    return fields.index(norm)
            return None
        ci = col('證券代號', '證券代碼', '股票代號', '代號')
        ni = col('證券名稱', '股票名稱', '名稱')
        pi = col('收盤價', '收盤')
        ai = col('成交金額', '成交值')
        vi = col('成交股數', '成交量')
        di = col('日期', '交易日期')
        sign_i = col('漲跌(+/-)', '漲跌(+/-)', '漲跌符號')
        diff_i = col('漲跌價差', '漲跌')
        if any(v is None for v in (ci, ni, pi, ai, vi)):
            continue
        for rec in block.get('data') or []:
            if not isinstance(rec, (tuple, list)) or max(ci,ni,pi,ai,vi) >= len(rec):
                continue
            code=str(rec[ci]).strip()
            name=str(rec[ni]).strip()
            close=number(rec[pi]);volume=number(rec[vi]);amount=number(rec[ai])
            day=iso_date(rec[di]) if di is not None and di < len(rec) else date
            if not is_common_four_digit(code) or not name or not day or close is None or close<=0:
                continue
            # Safeguard: RWD response date must match each individual row date, when supplied.
            if day!=date:
                continue
            row=dict.fromkeys(FIELDS,'')
            row.update(stock_id=code,stock_name=name,market='上市',sector='未分類',
                       close=f'{close:.4f}'.rstrip('0').rstrip('.'),asof=date)
            if volume is not None and volume>=0:row['volume_shares']=str(int(volume))
            if amount is not None and amount>=0:row['trade_value_twd']=str(int(amount))
            if diff_i is not None and diff_i < len(rec):
                change=number(re.sub(r'<[^>]+>','',html.unescape(str(rec[diff_i]))))
                if change is not None:
                    if sign_i is not None and sign_i<len(rec):
                        sign=html.unescape(str(rec[sign_i]))
                        if '-' in re.sub(r'<[^>]+>','',sign):change=-abs(change)
                        elif '+' in re.sub(r'<[^>]+>','',sign):change=abs(change)
                        else:change=None  # unresolved direction, no percentage
                    if change is not None and close-change>0:
                        row['change_pct']=f'{change/(close-change)*100:.4f}'
            result.append(row)
    if len(result)<500:
        raise ValueError('TWSE RWD returned too few safely parsed stock rows: '+str(len(result)))
    return result


def rwd_url(target_date):
    dt.date.fromisoformat(target_date)
    return TWSE_RWD+'?'+urlencode({'date':target_date.replace('-',''),'response':'json'})

def get_json(url, attempts=3):
    error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; MFDS-Research-Dashboard/0.2)',
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except Exception as exc:
            error = exc
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(str(error))


def run(twse_fixture=None, tpex_fixture=None, output_dir=DATA):
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped = {}
    meta = {
        'status': 'unavailable',
        'generated_at_taipei': dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
        'markets': {},
        'sources': {**URLS, '上市盤後備援': TWSE_RWD},
        'notes': ('各市場顯示各自已驗證的收盤日期。日期不同不當作同步行情；'
                  '籌碼強度排名只在法人與股價日期一致時給分。非即時報價。'),
    }
    for market,fixture in [('上市',twse_fixture),('上櫃',tpex_fixture)]:
        try:
            records=json.loads(Path(fixture).read_text(encoding='utf-8')) if fixture else get_json(URLS[market])
            rows=transform(records,market)
            if not rows:raise ValueError('官方來源沒有有效價格與日期')
            grouped[market]=rows
            meta['markets'][market]={'status':'ok','rows':len(rows),'date':rows[0]['asof'],'source':'openapi'}
        except Exception as exc:
            meta['markets'][market]={'status':'failed','error':str(exc)[:180]}
            print('WARNING ['+market+']:',exc)

    # Official alternative: OpenAPI often lags behind TPEx. RWD has date-specific
    # reports. It must be parsed by returned named columns and actual response date.
    if not twse_fixture and not tpex_fixture:
        tw=meta['markets'].get('上市',{})
        otc=meta['markets'].get('上櫃',{})
        if otc.get('date') and (not tw.get('date') or tw['date']<otc['date']):
            target=otc['date']
            meta['twse_alternative']={'attempted':True,'requested_date':target,'url':rwd_url(target)}
            try:
                rows=transform_twse_rwd(get_json(rwd_url(target),attempts=2))
                actual=rows[0]['asof']
                meta['twse_alternative']['response_date']=actual
                if actual>=tw.get('date','') and actual<=target:
                    grouped['上市']=rows
                    meta['markets']['上市']={'status':'ok','rows':len(rows),'date':actual,'source':'rwd_official'}
                    meta['twse_alternative']['result']='selected'
                else:
                    meta['twse_alternative']['result']='not_newer'
            except Exception as exc:
                meta['twse_alternative']['result']='failed'
                meta['twse_alternative']['error']=(type(exc).__name__+': '+str(exc))[:250]
                print('WARNING [上市官方盤後備援]:',exc)

    output=[row for market in ('上市','上櫃') for row in grouped.get(market,[])]
    dates={market:items[0]['asof'] for market,items in grouped.items() if items}
    meta['market_dates']=dates
    meta['markets_included']=sorted(dates)
    meta['display_date']=max(dates.values()) if dates else None
    meta['aligned']=len(dates)==2 and len(set(dates.values()))==1
    meta['status']='ok' if meta['aligned'] else ('partial' if output else 'unavailable')
    meta['tracked_symbols_found']={code:any(r['stock_id']==code for r in output)
                                   for code in ('8064','3533','2345','2330')}
    if output:
        buf=io.StringIO(newline='')
        writer=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator='\n')
        writer.writeheader();writer.writerows(output)
        (output_dir/'official_snapshot.csv').write_text(buf.getvalue(),encoding='utf-8-sig')
    else:
        old=output_dir/'official_snapshot.csv'
        if old.exists():
            with old.open(encoding='utf-8-sig',newline='') as fh:
                oldrows=list(csv.DictReader(fh))
            if oldrows:
                meta['status']='stale'
                olddates=[x.get('asof','') for x in oldrows if iso_date(x.get('asof'))]
                meta['display_date']=max(olddates) if olddates else 'unknown'
                meta['markets_included']=sorted(set(x.get('market','') for x in oldrows))
                meta['market_dates']={market:max(x.get('asof','') for x in oldrows if x.get('market')==market)
                                      for market in meta['markets_included']}
                meta['notes']+=' 本次兩個市場皆未取到資料，保留已驗證的舊快照。'
    (output_dir/'official_meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f"Result: {meta['status']} | {len(output)} records | {meta.get('market_dates',{})}")
    return meta,output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--twse-fixture', help='Offline TWSE JSON fixture (testing only)')
    parser.add_argument('--tpex-fixture', help='Offline TPEx JSON fixture (testing only)')
    parser.add_argument('--output-dir', type=Path, default=DATA)
    args = parser.parse_args()
    run(args.twse_fixture, args.tpex_fixture, args.output_dir)
