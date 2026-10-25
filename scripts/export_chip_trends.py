#!/usr/bin/env python3
"""2.6B - 將已封存的三大法人逐日與集保逐週資料匯出成網頁可讀CSV。
只複製真實來源日期及值；不補值、不插值、不估計股利或勝率。
"""
import csv
import json
import datetime as dt
from pathlib import Path
from collections import defaultdict
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parents[1]
ARCHIVE=BASE/'history_data'
OUT=BASE/'site'/'data'
FLOWS=('date','stock_id','market','foreign_net_shares','trust_net_shares','dealer_net_shares','source')
HOLDERS=('date','stock_id','holder400_pct','holder1000_pct','source')

def parse_number(x):
    try:
        z=float(str(x).replace(',','').strip())
        if not -1e20<z<1e20:return None
        return z
    except (ValueError,TypeError):return None

def load_file(path,fields):
    if not path.is_file():return [],'missing'
    with path.open(encoding='utf-8-sig',newline='') as h:
        rd=csv.DictReader(h)
        if not set(fields).issubset(set(rd.fieldnames or [])):return [],'invalid_schema'
        data=[]
        for row in rd:
            d=(row.get('date') or '').strip();sid=(row.get('stock_id') or '').strip()
            try:dt.date.fromisoformat(d)
            except ValueError:continue
            if not sid.isdigit() or len(sid)<4 or len(sid)>6:continue
            nums=fields[3:-1] if len(fields)==7 else fields[2:-1]
            if any(parse_number(row.get(f)) is None for f in nums):continue
            data.append({f:(row.get(f) or '').strip() for f in fields})
        return data,'ok'

def keep_last(rows,kind,n):
    dedup={}
    for row in rows:
        k=(row['stock_id'],row['date'],row.get('market','')) if kind=='flow' else (row['stock_id'],row['date'])
        dedup[k]=row
    groups=defaultdict(list)
    for row in dedup.values():groups[row['stock_id']].append(row)
    output=[]
    for sid,rr in groups.items():
        rr.sort(key=lambda r:r['date'])
        output+=rr[-n:]
    return sorted(output,key=lambda r:(r['stock_id'],r['date'],r.get('market','')))

def write_csv(path,cols,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as h:
        wr=csv.DictWriter(h,fieldnames=cols,extrasaction='ignore');wr.writeheader();wr.writerows(rows)

def main():
    rawf,sf=load_file(ARCHIVE/'institutional_daily.csv',FLOWS)
    rawh,sh=load_file(ARCHIVE/'holder_weekly.csv',HOLDERS)
    f=keep_last(rawf,'flow',120)
    h=keep_last(rawh,'holder',26)
    write_csv(OUT/'institutional_trend.csv',FLOWS,f)
    write_csv(OUT/'holder_trend.csv',HOLDERS,h)
    now=dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    meta={'version':'2.6B','generated_at_taipei':now,'flow_source_status':sf,'holder_source_status':sh,'flow_rows':len(f),'holder_rows':len(h),'flow_stocks':len(set(r['stock_id'] for r in f)),'holder_stocks':len(set(r['stock_id'] for r in h)),'flow_date_latest':max((r['date'] for r in f),default=None),'holder_date_latest':max((r['date'] for r in h),default=None),'flow_max_records_per_stock':120,'holder_max_records_per_stock':26,'historical_data_complete':False,'notes':'資料僅為已封存之實際來源日期；未補日期、未推估、非官方獨立驗證，不能據此認定模型勝率。'}
    (OUT/'chip_trend_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False))
if __name__=='__main__':main()
