#!/usr/bin/env python3
"""TPE-MFDS 2.2.1 chip-flow collection and conservative synchronized-increase research flag.

Official sources only; unavailable fields remain missing. This is NOT a return
forecast or trading signal. All flow quantities are shares, all TDCC ownership
ratios are PERCENT (not a 0..1 fraction), weekly delta is percentage POINTS.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
ARCHIVE = BASE / 'history_data'
SITE = BASE / 'site' / 'data'
FLOW_FILE = 'institutional_daily.csv'
HOLDER_FILE = 'holder_weekly.csv'
T86 = 'https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={day}&selectType=ALLBUT0999'
TPEX = 'https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading'
TDCC = 'https://openapi.tdcc.com.tw/v1/opendata/1-5'
LEGACY_TDCC = 'https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5'
FLOW_COLS = ['date', 'stock_id', 'market', 'foreign_net_shares', 'trust_net_shares', 'dealer_net_shares', 'source']
HOLDER_COLS = ['date', 'stock_id', 'holder400_pct', 'holder1000_pct', 'source']
SIGNAL_COLS = ['stock_id','flow_asof','holder_asof','flow_days','holder_weeks','foreign_5d_shares','trust_5d_shares','dealer_5d_shares','large400_pct','large400_4w_pp','large1000_pct','large1000_4w_pp','chip_status','chip_reason']


def request(url, accept='application/json, text/csv, */*'):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (TPE-MFDS/2.2; public-research)', 'Accept':accept})
    err=None
    for i in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r: return r.read()
        except Exception as ex:
            err=ex
            if i==0:time.sleep(2)
    raise RuntimeError(f'{type(err).__name__}: {err}')


def clean(s): return re.sub(r'[^a-z0-9\u4e00-\u9fff]+','',str(s).lower())

def number(x):
    s=str(x if x is not None else '').strip().replace(',','').replace('%','')
    if s in ('','--','---','—','-','null','None'):return None
    try:
        v=float(s)
        return v if abs(v)<1e20 and v==v else None
    except (TypeError,ValueError):return None

def date_iso(s):
    s=str(s or '').strip().replace(' ','')
    try:
        if re.fullmatch(r'\d{7}',s):return dt.date(int(s[:3])+1911,int(s[3:5]),int(s[5:])).isoformat()
        if re.fullmatch(r'\d{8}',s):return dt.date(int(s[:4]),int(s[4:6]),int(s[6:])).isoformat()
        if re.fullmatch(r'\d{3}/\d\d/\d\d',s):return dt.date(int(s[:3])+1911,int(s[4:6]),int(s[7:])).isoformat()
        return dt.date.fromisoformat(s).isoformat()
    except (ValueError,TypeError):return None

def stock_code(x):
    s=str(x or '').strip();return s if re.fullmatch(r'[1-9][0-9]{3}',s) else None

def csv_load(path):
    if not path.exists():return []
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def csv_save(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    text=io.StringIO(newline='');w=csv.DictWriter(text,fields,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(rows)
    path.write_text(text.getvalue(),encoding='utf-8-sig')

def pick_value(row,variants,forbid=()):
    """Conservative exact-name matching, with forbidden tokens for misleading aliases."""
    kv={clean(k):v for k,v in row.items() if k is not None and all(x not in clean(k) for x in forbid)}
    for k in variants:
        if clean(k) in kv:return number(kv[clean(k)])
    return None


def twse_rows(payload,day):
    if not isinstance(payload,dict) or payload.get('stat') not in ('OK',None):raise ValueError('T86 status not OK')
    fields=payload.get('fields',[]);items=payload.get('data',[])
    if not fields or not isinstance(items,list):raise ValueError('T86 fields/data missing')
    result=[]
    for cells in items:
        if not isinstance(cells,list):continue
        row=dict(zip(fields,cells))
        code=stock_code(cells[0] if cells else '')
        if not code:continue
        # Only accept named official net columns, not Buy/Sell or investor totals.
        main=pick_value(row,('外陸資買賣超股數(不含外資自營商)','外陸資買賣超股數不含外資自營商','外資及陸資買賣超股數'))
        dealer_f=pick_value(row,('外資自營商買賣超股數',))
        trust=pick_value(row,('投信買賣超股數',))
        proprietary=pick_value(row,('自營商自行買賣買賣超股數',))
        hedge=pick_value(row,('自營商避險買賣超股數',))
        # Do not construct a misleading zero from missing components.
        if main is None or trust is None:continue
        result.append(dict(date=day,stock_id=code,market='上市',foreign_net_shares=int(main+(dealer_f or 0)) if dealer_f is not None else int(main),trust_net_shares=int(trust),dealer_net_shares=int(proprietary+hedge) if proprietary is not None and hedge is not None else '',source='TWSE T86'))
    if not result:raise ValueError('TWSE T86 found no validated foreign/trust columns')
    return result


def tpex_rows(payload):
    if not isinstance(payload,list):raise ValueError('TPEx expected JSON array')
    out=[]
    for r in payload:
        if not isinstance(r,dict):continue
        c={clean(k):v for k,v in r.items()}
        code=None
        for k in ('SecuritiesCompanyCode','SecuritiesCode','Code','StockCode'):
            code=stock_code(c.get(clean(k)))
            if code:break
        if not code:continue
        day=None
        for k in ('Date','TradeDate','TradingDate'):
            day=date_iso(c.get(clean(k)))
            if day:break
        if not day:continue
        # Prefer explicitly labeled net fields. May vary by feed version.
        foreign=pick_value(r,['ForeignInvestorsNetBuySell','ForeignInvestorsIncludeMainlandAreaInvestorsDifference','ForeignInvestorsincludeMainlandAreaInvestorsForeignDealersexcludedDifference','ForeignInvestorsTotalDifference','ForeignInvestorsDifference','ForeignNetBuySell'])
        trust=pick_value(r,['SecuritiesInvestmentTrustCompaniesNetBuySell','SecuritiesInvestmentTrustCompaniesDifference','SecuritiesInvestmentTrustCompaniesTotalDifference','InvestmentTrustNetBuySell','SitcDifference'])
        if foreign is None:
            buys=pick_value(r,['ForeignInvestorsincludeMainlandAreaInvestorsForeignDealersexcludedTotalBuy','ForeignInvestorsTotalBuy','ForeignInvestorsBuy'])
            sells=pick_value(r,['ForeignInvestorsincludeMainlandAreaInvestorsForeignDealersexcludedTotalSell','ForeignInvestorsTotalSell','ForeignInvestorsSell'])
            if buys is not None and sells is not None:foreign=buys-sells
        if trust is None:
            buys=pick_value(r,['SecuritiesInvestmentTrustCompaniesTotalBuy','InvestmentTrustTotalBuy']);sells=pick_value(r,['SecuritiesInvestmentTrustCompaniesTotalSell','InvestmentTrustTotalSell'])
            if buys is not None and sells is not None:trust=buys-sells
        if foreign is None or trust is None:continue
        out.append(dict(date=day,stock_id=code,market='上櫃',foreign_net_shares=int(foreign),trust_net_shares=int(trust),dealer_net_shares='',source='TPEx openapi'))
    if not out:raise ValueError('TPEx schema unrecognized: cannot validate foreign/trust values')
    return out


def decode_csv(raw):
    for enc in ('utf-8-sig','big5','cp950'):
        try:
            x=raw.decode(enc)
            rows=list(csv.DictReader(io.StringIO(x)))
            if rows and any('證券代號' in str(k) for k in rows[0]):return rows
        except (UnicodeError,csv.Error):pass
    raise ValueError('TDCC does not contain verified CSV headers')


def tdcc_parse(raw):
    # TDCC open data may return JSON or CSV. Never guess unknown grade mapping.
    try:
        payload=json.loads(raw)
        if isinstance(payload,dict):payload=payload.get('data',payload.get('Data',[]))
        if not isinstance(payload,list):raise ValueError('TDCC JSON is not a list')
        records=payload
    except (ValueError,TypeError):records=decode_csv(raw)
    groups=defaultdict(dict)
    for row in records:
        if not isinstance(row,dict):continue
        vals={clean(k):v for k,v in row.items()}
        code=stock_code(vals.get(clean('證券代號')) or vals.get(clean('SecuritiesCode')) or vals.get(clean('stock_id')))
        day=date_iso(vals.get(clean('資料日期')) or vals.get(clean('Date')))
        level=number(vals.get(clean('持股分級')) or vals.get(clean('HoldingRangeCode')))
        proportion=number(vals.get(clean('占集保庫存數比例%')) or vals.get(clean('Proportion')) or vals.get(clean('ShareRatio')))
        if not code or not day or level is None or proportion is None:continue
        grade=int(level)
        if 1<=grade<=15 and 0<=proportion<=100:groups[(day,code)][grade]=proportion
    output=[]
    for (day,code),grades in groups.items():
        # Require every individual bucket to prevent false concentration changes.
        if len(grades)!=15:continue
        big400=sum(grades[i] for i in range(12,16));big1000=grades[15]
        if not (0<=big400<=101 and 0<=big1000<=100):continue
        output.append(dict(date=day,stock_id=code,holder400_pct=round(big400,4),holder1000_pct=round(big1000,4),source='TDCC 1-5'))
    if not output:raise ValueError('TDCC grade 1..15 missing or schema changed')
    return output


def merge_rows(old,new,columns,key_cols,limit=320):
    keyed={}
    for raw in old+new:
        if any(not raw.get(k) for k in key_cols):continue
        item={c:raw.get(c,'') for c in columns}
        if not date_iso(item.get('date')) or not stock_code(item.get('stock_id')):continue
        keyed[tuple(item[k] for k in key_cols)]=item
    latest=max((i['date'] for i in keyed.values()),default=None)
    if latest:
        cutoff=(dt.date.fromisoformat(latest)-dt.timedelta(days=limit)).isoformat()
        keyed={k:v for k,v in keyed.items() if v['date']>=cutoff}
    return sorted(keyed.values(),key=lambda x:(x['date'],x['stock_id']))


def make_signals(flows,holders,asof_date=None):
    today=dt.date.fromisoformat(asof_date) if asof_date else dt.datetime.now(ZoneInfo('Asia/Taipei')).date()
    by_stock=defaultdict(list);h_stock=defaultdict(list)
    for r in flows:by_stock[r['stock_id']].append(r)
    for r in holders:h_stock[r['stock_id']].append(r)
    output=[]
    for code in sorted(set(by_stock)|set(h_stock)):
        daily=sorted(by_stock[code],key=lambda r:r['date']); weekly=sorted(h_stock[code],key=lambda r:r['date'])
        recent=daily[-5:];cur=weekly[-1] if weekly else None
        fullflow=len(recent)==5 and len({x['date'] for x in recent})==5 and (today-dt.date.fromisoformat(recent[-1]['date'])).days<=7 and (dt.date.fromisoformat(recent[-1]['date'])-dt.date.fromisoformat(recent[0]['date'])).days<=14
        fullholder=False;prior=None
        if cur and (today-dt.date.fromisoformat(cur['date'])).days<=13:
            t=dt.date.fromisoformat(cur['date'])
            candidates=[x for x in weekly[:-1] if 24<=(t-dt.date.fromisoformat(x['date'])).days<=35]
            if candidates:prior=min(candidates,key=lambda x:abs((t-dt.date.fromisoformat(x['date'])).days-28));fullholder=True
        f5=sum(float(x['foreign_net_shares']) for x in recent) if fullflow else None
        t5=sum(float(x['trust_net_shares']) for x in recent) if fullflow else None
        d5=sum(float(x['dealer_net_shares']) for x in recent) if fullflow and all(str(x['dealer_net_shares']).strip() for x in recent) else None
        dh=float(cur['holder400_pct'])-float(prior['holder400_pct']) if fullholder else None
        dh1=float(cur['holder1000_pct'])-float(prior['holder1000_pct']) if fullholder else None
        matched=fullflow and fullholder and f5>0 and t5>0 and dh>0
        if not fullflow or not fullholder:
            status='insufficient'
            if not fullflow and not fullholder:why='缺近5個有效交易日法人資料及相隔約4週的集保資料'
            elif not fullflow:why='法人未滿5個有效交易日或日期不連續／已過期'
            else:why='集保缺少相隔約4週的有效資料'
        else:status='matched' if matched else 'not_matched';why='外資及投信近5日買超，且400張以上占比近4週增加' if matched else '未同時符合三項增持條件'
        output.append(dict(stock_id=code,flow_asof=recent[-1]['date'] if recent else '',holder_asof=cur['date'] if cur else '',flow_days=len(recent),holder_weeks=len(weekly),foreign_5d_shares=int(f5) if f5 is not None else '',trust_5d_shares=int(t5) if t5 is not None else '',dealer_5d_shares=int(d5) if d5 is not None else '',large400_pct=cur['holder400_pct'] if cur else '',large400_4w_pp=round(dh,4) if dh is not None else '',large1000_pct=cur['holder1000_pct'] if cur else '',large1000_4w_pp=round(dh1,4) if dh1 is not None else '',chip_status=status,chip_reason=why))
    return output


def execute(archive=ARCHIVE,site=SITE,fixtures=None,asof=None):
    archive.mkdir(parents=True,exist_ok=True);site.mkdir(parents=True,exist_ok=True)
    diagnostics={'version':'2.2.1','generated_at_taipei':dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),'sources':{},'notes':'同步增持僅為描述性篩選，非預測；歷史集保備份若來源為第三方鏡像須與官方最新快照交叉核對。'}
    backfill_report=site/'chip_backfill_meta.json'
    if backfill_report.exists():
        try:
            backfill=json.loads(backfill_report.read_text('utf-8'))
            diagnostics['backfill']={'asof':backfill.get('asof'),'focus':backfill.get('focus',{}),'tdcc_archive':backfill.get('tdcc_archive',{}),'market_history':backfill.get('market_history',{})}
        except (ValueError,OSError):diagnostics['backfill']={'status':'metadata_unreadable'}
    snapshot=csv_load(site/'official_snapshot.csv');dates=sorted({r.get('asof','') for r in snapshot if date_iso(r.get('asof'))});day=dates[-1] if dates else dt.datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()
    all_flows=[];all_holders=[]
    for key,fn in [('twse',lambda:twse_rows(json.loads(request(T86.format(day=day.replace('-','')))),day)),('tpex',lambda:tpex_rows(json.loads(request(TPEX))))]:
        try:
            path=(fixtures or {}).get(key)
            incoming=fn() if path is None else (twse_rows(json.loads(Path(path).read_text('utf-8')),day) if key=='twse' else tpex_rows(json.loads(Path(path).read_text('utf-8'))))
            all_flows+=incoming
            diagnostics['sources'][key]={'status':'ok','rows':len(incoming),'latest_date':max(r['date'] for r in incoming)}
        except Exception as exc:
            diagnostics['sources'][key]={'status':'error','reason':str(exc)[:180]}
    try:
        path=(fixtures or {}).get('tdcc')
        raw=Path(path).read_bytes() if path else request(TDCC)
        incoming=tdcc_parse(raw)
        all_holders+=incoming
        diagnostics['sources']['tdcc']={'status':'ok','rows':len(incoming),'latest_date':max(r['date'] for r in incoming)}
    except Exception as first:
        try:
            if fixtures is not None:raise RuntimeError('fixture failed: no network fallback')
            all_holders+=tdcc_parse(request(LEGACY_TDCC,accept='text/csv, */*'))
            diagnostics['sources']['tdcc']={'status':'ok','rows':len(all_holders),'source':'legacy CSV fallback'}
        except Exception as second:
            diagnostics['sources']['tdcc']={'status':'error','reason':f'new={str(first)[:90]}; backup={str(second)[:90]}'}
    flows=merge_rows(csv_load(archive/FLOW_FILE),all_flows,FLOW_COLS,['date','stock_id','market'])
    holders=merge_rows(csv_load(archive/HOLDER_FILE),all_holders,HOLDER_COLS,['date','stock_id'])
    csv_save(archive/FLOW_FILE,FLOW_COLS,flows);csv_save(archive/HOLDER_FILE,HOLDER_COLS,holders)
    flags=make_signals(flows,holders,asof_date=asof)
    csv_save(site/'chip_signals.csv',SIGNAL_COLS,flags)
    diagnostics.update({'flow_history_rows':len(flows),'holder_history_rows':len(holders),'stocks_with_chip_records':len(flags),'matching_stocks':sum(x['chip_status']=='matched' for x in flags),'ready_stocks':sum(x['chip_status']!='insufficient' for x in flags),'selection_rule':'5個有效法人交易日：外資淨買超>0 且投信淨買超>0；兩期集保持股相隔約28日：400張以上比例增幅>0pp；均需資料未過期。'})
    (site/'chip_meta.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Chip analysis',json.dumps(diagnostics,ensure_ascii=False))
    return flags,diagnostics

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--twse-fixture');p.add_argument('--tpex-fixture');p.add_argument('--tdcc-fixture');p.add_argument('--asof-date')
    args=p.parse_args();fx={k:getattr(args,k+'_fixture') for k in ('twse','tpex','tdcc') if getattr(args,k+'_fixture')}
    execute(fixtures=fx or None,asof=args.asof_date)
