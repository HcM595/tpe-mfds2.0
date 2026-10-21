#!/usr/bin/env python3
"""Combine daily archival snapshots and backfilled verified priority watchlist.

Outputs one deduplicated CSV consumed by the existing TPE-MFDS site and a
coverage report. Values are *unadjusted* exchange closing prices.
"""
import argparse
import csv
import datetime as dt
import io
import json
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
ARCHIVE=BASE/'history_data'
SITE_DATA=BASE/'site'/'data'
COLUMNS=('date','stock_id','close','volume_shares','trade_value_twd')
KEEP_DAYS=310


def valid_date(s):
    try:dt.date.fromisoformat(s);return True
    except (ValueError,TypeError):return False


def read_csv(path):
    if not path.exists():return []
    with path.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def row_clean(row):
    date=row.get('date') or row.get('asof','')
    if not valid_date(date):return None
    code=str(row.get('stock_id','')).strip()
    if not (len(code)==4 and code.isdigit() and code[0]!='0'):return None
    try:
        close=float(str(row.get('close','')).replace(',',''))
        if close<=0 or close!=close or close==float('inf'):return None
    except (ValueError,TypeError):return None
    return {'date':date,'stock_id':code,
            'close':str(row['close']),
            'volume_shares':row.get('volume_shares',''),
            'trade_value_twd':row.get('trade_value_twd','')}


def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf,fieldnames=COLUMNS,lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    data=buf.getvalue()
    if not path.exists() or path.read_text(encoding='utf-8')!=data:
        path.write_text(data,encoding='utf-8')
        return True
    return False


def build(snapshot,archive=ARCHIVE,site_data=SITE_DATA,keep=KEEP_DAYS):
    archive.mkdir(parents=True,exist_ok=True)
    site_data.mkdir(parents=True,exist_ok=True)
    incoming=[r for x in read_csv(snapshot) if (r:=row_clean(x))]
    if incoming and len(set(r['date'] for r in incoming))==1:
        day=incoming[0]['date']
        path=archive/(day+'.csv')
        previous={r['stock_id']:r for x in read_csv(path) if (r:=row_clean(x))}
        previous.update({r['stock_id']:r for r in incoming})
        write_csv(path,[previous[k] for k in sorted(previous)])
    dates=sorted(p for p in archive.glob('????-??-??.csv') if valid_date(p.stem))
    for path in dates[:-keep]:path.unlink()
    dates=dates[-keep:]
    # Priority history used as fallback; verified daily market archive wins on conflict.
    keyed={}
    for x in read_csv(archive/'watchlist_seed.csv'):
        r=row_clean(x)
        if r:keyed[(r['date'],r['stock_id'])]=r
    for path in dates:
        for x in read_csv(path):
            r=row_clean(x)
            if r:keyed[(r['date'],r['stock_id'])]=r
    ordered=[keyed[k] for k in sorted(keyed)]
    write_csv(site_data/'price_history.csv',ordered)
    coverage={}
    for r in ordered:
        code=r['stock_id'];a=coverage.setdefault(code,{'rows':0,'earliest':r['date'],'latest':r['date']})
        a['rows']+=1;a['latest']=r['date']
    state={}
    state_path=archive/'market_backfill_state.json'
    if state_path.exists():
        try:state=json.loads(state_path.read_text('utf-8'))
        except (OSError,ValueError):state={}
    meta={'note':'實際官方收盤價格，尚未還原除權息；回補有缺口則不計入不存在的價格。',
          'total_stocks':len(coverage),'total_rows':len(ordered),
          'market_archive_dates':len(dates),
          'market_backfill_progress':{'attempted_weekdays':state.get('attempted_weekdays',0),
              'reached_start':state.get('reached_start',False),
              'all_checked_without_errors':bool(state.get('reached_start',False) and not state.get('failed_dates',[])),
              'failed_days':len(state.get('failed_dates',[])),
              'range_start':state.get('range_start',''),
              'next_date':state.get('next_date','')},
          'featured':{code:coverage.get(code,{'rows':0,'earliest':None,'latest':None})
                      for code in ['8064','3533','2330','2345']}}
    (site_data/'history_coverage.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'History built: {len(ordered):,} rows; {len(coverage):,} stock IDs; {len(dates)} archived exchange days')
    for code,row in meta['featured'].items():print('Featured',code,row)
    return ordered


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--snapshot',type=Path,default=SITE_DATA/'official_snapshot.csv')
    p.add_argument('--archive',type=Path,default=ARCHIVE)
    p.add_argument('--site-data',type=Path,default=SITE_DATA)
    args=p.parse_args()
    build(args.snapshot,args.archive,args.site_data)
