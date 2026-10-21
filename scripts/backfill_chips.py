#!/usr/bin/env python3
"""TPE-MFDS 2.2.1 — historical chip backfill.

No paid API or secrets. Historical flows are requested from TWSE/TPEx by date.
Historical TDCC snapshots are an UNOFFICIAL PUBLIC ARCHIVE of TDCC CSVs:
https://github.com/wirelessr/tdcc-opendata-archive
Source provenance is retained. No absent data are invented.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import io
import json
import re
import time
import urllib.error
import urllib.parse
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from chip_pipeline import (
        ARCHIVE, SITE, FLOW_FILE, HOLDER_FILE, FLOW_COLS, HOLDER_COLS,
        csv_load, csv_save, date_iso, merge_rows, request, stock_code, number,
        tdcc_parse, twse_rows,
    )
except ImportError:
    from scripts.chip_pipeline import (
        ARCHIVE, SITE, FLOW_FILE, HOLDER_FILE, FLOW_COLS, HOLDER_COLS,
        csv_load, csv_save, date_iso, merge_rows, request, stock_code, number,
        tdcc_parse, twse_rows,
    )

ARCHIVE_REPO = 'https://api.github.com/repos/wirelessr/tdcc-opendata-archive/contents/snapshots'
TDCC_RAW = 'https://raw.githubusercontent.com/wirelessr/tdcc-opendata-archive/main/snapshots/{year}/{day}.csv'
TP_EX_HIST = 'https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade'
TWSE_HIST = 'https://www.twse.com.tw/rwd/zh/fund/T86'


def asof_from_snapshot(site=SITE):
    rows=csv_load(site/'official_snapshot.csv')
    valid=[date_iso(r.get('asof')) for r in rows]
    valid=[x for x in valid if x]
    if valid:return dt.date.fromisoformat(max(valid))
    return dt.datetime.now(ZoneInfo('Asia/Taipei')).date()


def twse_url(day):
    q=urllib.parse.urlencode({'response':'json','date':day.strftime('%Y%m%d'),'selectType':'ALLBUT0999'})
    return TWSE_HIST+'?'+q


def tpex_url(day):
    roc=f'{day.year-1911}/{day.month:02d}/{day.day:02d}'
    q=urllib.parse.urlencode({'type':'Daily','sect':'EW','date':roc,'id':'','response':'json'})
    return TP_EX_HIST+'?'+q


def parse_tpex_historical(payload,day):
    """Parse 24-column dailyTrade only after accounting identity checks.

    Layout is subject to TPEx change; fail closed on any suspected schema drift.
    The mapping and identity equations are verified on each response.
    """
    if not isinstance(payload,dict):raise ValueError('TPEx history response must be JSON object')
    tables=payload.get('tables')
    if tables is None:
        tables=[payload] if 'aaData' in payload else []
    if not isinstance(tables,list):raise ValueError('TPEx history tables not list')
    parsed=[];invalid=0;seen=0
    for table in tables:
        if not isinstance(table,dict):continue
        rows=table.get('data',table.get('aaData',[]))
        if not isinstance(rows,list):continue
        for r in rows:
            if not isinstance(r,list) or len(r)<24:continue
            code=stock_code(r[0]);
            if not code:continue
            seen+=1
            vals=[number(r[i]) for i in (4,13,16,19,22,23)]
            if any(v is None for v in vals):
                invalid+=1;continue
            foreign,trust,self_dealer,hedge,dealer_total,all_total=vals
            if abs(self_dealer+hedge-dealer_total)>1 or abs(foreign+trust+dealer_total-all_total)>1:
                invalid+=1;continue
            parsed.append(dict(date=day,stock_id=code,market='上櫃',
                               foreign_net_shares=int(foreign),trust_net_shares=int(trust),
                               dealer_net_shares=int(dealer_total),source='TPEx historical dailyTrade'))
    if seen==0:return [] # trading holiday/no published table
    if not parsed or invalid > max(5,int(seen*0.05)):
        raise ValueError(f'TPEx position validation failed: valid={len(parsed)} / seen={seen}, invalid={invalid}')
    # Some envelopes provide both summary + details; one record per code expected.
    if len({x['stock_id'] for x in parsed})!=len(parsed):
        raise ValueError('TPEx duplicate securities across tables')
    return parsed


def parse_tdcc_archive(raw):
    """Reuse conservative official 15-bucket parser; source remains labeled archival."""
    records=tdcc_parse(raw)
    for row in records:row['source']='TDCC data mirrored by wirelessr (unofficial archive)'
    return records


def history_dates(asof, span=50):
    d=asof;out=[]
    for _ in range(span):
        if d.weekday()<5:out.append(d)
        d-=dt.timedelta(days=1)
    return out


def fetch_market_history(market,day,downloader=request):
    if market=='twse':
        payload=json.loads(downloader(twse_url(day)))
        # For non-trading days TWSE commonly responds stat != OK; treat as no data.
        if isinstance(payload,dict) and payload.get('stat') not in (None,'OK'):
            s=str(payload.get('stat',''))
            if '查無資料' in s or '沒有符合' in s or '很抱歉' in s:return []
            raise ValueError(f'TWSE status: {s[:100]}')
        if not payload.get('data'):return []
        return twse_rows(payload,day.isoformat())
    if market=='tpex':
        return parse_tpex_historical(json.loads(downloader(tpex_url(day))),day.isoformat())
    raise ValueError('unsupported market')


def listed_archive_dates(asof,lookback_weeks=9,downloader=request):
    years=sorted({asof.year,(asof-dt.timedelta(weeks=lookback_weeks+1)).year})
    dates=[];errors=[]
    for year in years:
        try:
            obj=json.loads(downloader(f'{ARCHIVE_REPO}/{year}'))
            if not isinstance(obj,list):raise ValueError('GitHub archive listing is not a list')
            for x in obj:
                name=str(x.get('name','')) if isinstance(x,dict) else ''
                if re.fullmatch(r'\d{4}-\d\d-\d\d\.csv',name):
                    d=dt.date.fromisoformat(name[:-4]);
                    if 0<=(asof-d).days<=lookback_weeks*7:dates.append(d)
        except Exception as e:errors.append(f'{year}: {str(e)[:110]}')
    return sorted(set(dates),reverse=True),errors


def run(archive=ARCHIVE,site=SITE,flow_days=12,holder_weeks=7,
        asof=None,downloader=request,pace=1.0,include_archive=True):
    archive=Path(archive);site=Path(site)
    archive.mkdir(parents=True,exist_ok=True);site.mkdir(parents=True,exist_ok=True)
    today=dt.date.fromisoformat(asof) if asof else asof_from_snapshot(site)
    flows=csv_load(archive/FLOW_FILE);holders=csv_load(archive/HOLDER_FILE)
    log={'version':'2.2.1','asof':today.isoformat(),'created_at_taipei':dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
         'notes':'下載空值與市場休市分別紀錄；歷史TDCC來源為非官方鏡像，非集保直接提供歷史API。',
         'market_history':{},'tdcc_archive':{},'focus':{}}
    day_rows={m:{r['date'] for r in flows if r.get('market')==market} for m,market in [('twse','上市'),('tpex','上櫃')]}
    fresh=[]
    for market in ('twse','tpex'):
        attempts=0;added=0;missing=[];errors=[];closed=[]
        for d in history_dates(today,span=52):
            if d.isoformat() in day_rows[market]:continue
            if attempts >= flow_days:break
            attempts+=1
            try:
                incoming=fetch_market_history(market,d,downloader=downloader)
                if incoming:
                    fresh.extend(incoming);added+=len(incoming)
                else:closed.append(d.isoformat())
            except Exception as e:errors.append({'date':d.isoformat(),'reason':str(e)[:170]})
            if pace:time.sleep(pace)
        log['market_history'][market]={'attempted_days':attempts,'new_rows':added,
                                        'no_data_days':closed[:20],'errors':errors[:20],
                                        'status':'ok' if added else 'no_new_data'}
    archive_rows=[];found_dates=[];archive_errors=[]
    if include_archive:
        candidates,discovery_errors=listed_archive_dates(today,lookback_weeks=12,downloader=downloader)
        archive_errors+=discovery_errors
        existing={r['date'] for r in holders}
        for d in candidates:
            if len(found_dates)>=holder_weeks:break
            if d.isoformat() in existing:continue
            try:
                raw=downloader(TDCC_RAW.format(year=d.year,day=d.isoformat()))
                rows=parse_tdcc_archive(raw)
                if not rows or any(r['date']!=d.isoformat() for r in rows):
                    raise ValueError('archive date differs from CSV published date or empty response')
                archive_rows+=rows;found_dates.append(d.isoformat())
            except Exception as e:archive_errors.append({'date':d.isoformat(),'reason':str(e)[:180]})
            if pace:time.sleep(pace)
    flows=merge_rows(flows,fresh,FLOW_COLS,['date','stock_id','market'],limit=390)
    holders=merge_rows(holders,archive_rows,HOLDER_COLS,['date','stock_id'],limit=390)
    csv_save(archive/FLOW_FILE,FLOW_COLS,flows)
    csv_save(archive/HOLDER_FILE,HOLDER_COLS,holders)
    log['tdcc_archive']={'mode':'unofficial_mirror' if include_archive else 'disabled',
                         'new_weeks':found_dates,'new_rows':len(archive_rows),
                         'errors':archive_errors[:20],
                         'repository':'https://github.com/wirelessr/tdcc-opendata-archive'}
    for code in ('8064','3533','2330','2345'):
        f=sorted({r['date'] for r in flows if r['stock_id']==code})
        h=sorted({r['date'] for r in holders if r['stock_id']==code})
        log['focus'][code]={'flow_dates':len(f),'latest_flow':f[-1] if f else None,
                            'holder_weeks':len(h),'latest_holder':h[-1] if h else None,
                            'ready_for_5d_flow':len(f)>=5,
                            'ready_for_4w_holder':bool(h and any(24<=(dt.date.fromisoformat(h[-1])-dt.date.fromisoformat(x)).days<=35 for x in h[:-1]))}
    log['flow_history_rows']=len(flows);log['holder_history_rows']=len(holders)
    (site/'chip_backfill_meta.json').write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(log,ensure_ascii=False,indent=2))
    return log


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--flow-days',type=int,default=12,help='Maximum attempted dates per market this run (1..25).')
    ap.add_argument('--holder-weeks',type=int,default=7,help='Maximum archived weeks to try importing (0..12).')
    ap.add_argument('--no-archive',action='store_true',help='Never use third party TDCC historical archive')
    args=ap.parse_args()
    run(flow_days=max(1,min(args.flow_days,25)),holder_weeks=max(0,min(args.holder_weeks,12)),include_archive=not args.no_archive)
