#!/usr/bin/env python3
"""TPE-MFDS 2.5B: bounded, conservative TWSE/TPEx ex-right calculation-result archival.

Events can be observed without establishing complete historical coverage.
Never compute returns, adjustment factors, or publication-time eligibility.
Unknown/empty/error data fail closed. Archived blobs never get overwritten.
"""
from __future__ import annotations
import argparse
import calendar
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site' / 'data'
ARCHIVE = ROOT / 'history_data' / 'corporate_action_history' / 'raw'
VERSION = '2.5B.1'
TZ = ZoneInfo('Asia/Taipei')
LEDGER = ['market','year_month','query_start','query_end','attempted_at_taipei',
          'result','event_rows','sha256','archive_path','url','diagnostic']
EVENT = ['market','stock_id','stock_name','ex_date','event_type',
         'pre_close','reference_price','cash_dividend','stock_dividend_value',
         'source_year_month','source_sha256','official_source','validation']
STOCK = ['market','stock_id','stock_name','cohort_observations',
         'official_events_seen','historical_completeness_verified',
         'adjusted_ohlc_verified','return_calculation_allowed','state']
URLS = {
 '上市':'https://www.twse.com.tw/rwd/zh/exRight/TWT49U',
 '上櫃':'https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ'
}


def read_csv(path):
    if not path.exists(): return []
    with path.open(encoding='utf-8-sig',newline='') as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=cols,extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def dump_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def strict_day(s):
    d=dt.date.fromisoformat(str(s))
    if str(d)!=str(s): raise ValueError('日期必須為 YYYY-MM-DD')
    return d


def day_roc(d): return f'{d.year-1911}/{d.month:02d}/{d.day:02d}'


def parse_roc(s):
    s=re.sub(r'<[^>]*>','',str(s)).strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',s): return dt.date.fromisoformat(s).isoformat()
    m=re.fullmatch(r'(\d{2,3})\s*[年/]\s*(\d{1,2})\s*[月/]\s*(\d{1,2})\s*日?',s)
    if m:
        y=int(m[1]); return dt.date(y+1911 if y<1911 else y,int(m[2]),int(m[3])).isoformat()
    m=re.fullmatch(r'(\d{3})(\d{2})(\d{2})',s)
    if m: return dt.date(int(m[1])+1911,int(m[2]),int(m[3])).isoformat()
    raise ValueError('未知的民國日期：'+s[:35])


def clean(v):
    return html.unescape(re.sub(r'<[^>]*>','',str(v))).replace('\u00a0',' ').strip()


def numeric(v):
    s=clean(v).replace(',','')
    if not s or s in ('-','--','N/A'): return ''
    try:
        val=float(s)
        if not -1e7 < val < 1e7: raise ValueError('數值不合理')
        return s
    except ValueError: raise ValueError('非數值欄位：'+s[:35])


def query(market,start,end):
    if market=='上市':
        params={'response':'json','startDate':start.strftime('%Y%m%d'), 'endDate':end.strftime('%Y%m%d')}
    else:
        params={'response':'json','startDate':start.strftime('%Y/%m/%d'), 'endDate':end.strftime('%Y/%m/%d')}
    return URLS[market]+'?'+urllib.parse.urlencode(params)


def request_json(url,timeout=18):
    req=urllib.request.Request(url,headers={
      'User-Agent':'Mozilla/5.0 (compatible; TPE-MFDS-Research/2.5B)',
      'Accept':'application/json,text/plain,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        data=response.read(6_000_001)
        if len(data)>6_000_000: raise ValueError('source response larger than 6 MB')
        charset=response.headers.get_content_charset() or 'utf-8'
    try: parsed=json.loads(data.decode(charset,'replace').lstrip('\ufeff'))
    except ValueError: raise ValueError('provider did not return valid JSON')
    if not isinstance(parsed,dict): raise ValueError('provider JSON is not an object')
    return data,parsed


def safe_provider_diagnostic(data):
    """Describe only bounded structure; never treat a provider error as an empty month."""
    keys = ','.join(sorted(str(k)[:40] for k in data.keys())[:16])
    details = []
    for k in ('stat','status','message','msg','title','date'):
        v = data.get(k)
        if isinstance(v, (str,int,float)):
            details.append(f'{k}={clean(str(v))[:75]}')
    for k in ('tables','data','aaData'):
        v = data.get(k)
        if isinstance(v,list): details.append(f'{k}_count={len(v)}')
    return f"provider_keys=[{keys}] " + '; '.join(details)


def tpex_table_to_rows(data):
    """Handle new TPEx table wrapper only when every required named column is present."""
    tables = data.get('tables')
    if not isinstance(tables,list): return None
    necessary = ('除權息日期','代號','名稱','除權息前收盤價','除權息參考價')
    for table in tables:
        if not isinstance(table,dict): continue
        rawcols = table.get('fields',table.get('columns',[]))
        rows = table.get('data')
        if not isinstance(rawcols,list) or not isinstance(rows,list): continue
        cols = [clean(c.get('title', c.get('name','')) if isinstance(c,dict) else c) for c in rawcols]
        if not all(k in cols for k in necessary): continue
        if not all(isinstance(r,list) and len(r)==len(cols) for r in rows):
            raise ValueError('TPEx named table column length changed')
        def pick(r,key): return r[cols.index(key)] if key in cols else ''
        normalized=[]
        for r in rows:
            normalized.append([pick(r,'除權息日期'),pick(r,'代號'),pick(r,'名稱'),
             pick(r,'除權息前收盤價'),pick(r,'除權息參考價'),pick(r,'權值'),
             pick(r,'息值'),pick(r,'權值+息值') or pick(r,'權值加息值'),
             pick(r,'權/息') or pick(r,'權或息'),pick(r,'漲停價'),
             pick(r,'跌停價'),pick(r,'開始交易基準價'),
             pick(r,'減除股利參考價'),pick(r,'現金股利')])
        return normalized
    return None


def normalize(data,market,start,end,ym,sha):
    # Require actual historical calculation result table, never a rolling preview feed.
    if market=='上市':
        fields=data.get('fields'); rows=data.get('data')
        if not isinstance(fields,list) or not isinstance(rows,list):
            raise ValueError('TWSE fields/data schema absent; '+safe_provider_diagnostic(data))
        cols=[clean(x) for x in fields]
        def idx(key):
            if key not in cols: raise ValueError('TWSE missing column '+key)
            return cols.index(key)
        indices=[idx(x) for x in ('資料日期','股票代號','股票名稱','除權息前收盤價','除權息參考價')]
        kind=cols.index('權/息') if '權/息' in cols else None
        money=cols.index('權值+息值') if '權值+息值' in cols else None
        parsed=[]
        for row in rows:
            if not isinstance(row,list) or len(row)!=len(cols): raise ValueError('TWSE column length changed')
            sid=clean(row[indices[1]])
            if not re.fullmatch(r'\d{4}',sid): continue  # ordinary shares only
            date=parse_roc(row[indices[0]])
            if not start.isoformat() <= date <= end.isoformat(): raise ValueError('TWSE returned date outside request range')
            pre=numeric(row[indices[3]]); ref=numeric(row[indices[4]])
            if not pre or not ref or float(pre)<=0 or float(ref)<=0: raise ValueError('TWSE missing reference price')
            parsed.append(dict(market=market,stock_id=sid,stock_name=clean(row[indices[2]]),ex_date=date,
                event_type=clean(row[kind]) if kind is not None else '',pre_close=pre,
                reference_price=ref,cash_dividend='',stock_dividend_value=numeric(row[money]) if money is not None else '',
                source_year_month=ym,source_sha256=sha,official_source=URLS[market],validation='historical_event_observed_not_complete'))
    else:
        rows=data.get('aaData')
        if not isinstance(rows,list): rows=tpex_table_to_rows(data)
        if not isinstance(rows,list): raise ValueError('TPEx aaData/named tables schema absent; '+safe_provider_diagnostic(data))
        parsed=[]
        for row in rows:
            if not isinstance(row,list) or len(row)<14: raise ValueError('TPEx historical columns changed')
            sid=clean(row[1]);
            if not re.fullmatch(r'\d{4}',sid): continue
            date=parse_roc(row[0])
            if not start.isoformat() <= date <= end.isoformat(): raise ValueError('TPEx returned date outside request range')
            pre=numeric(row[3]); ref=numeric(row[4])
            if not pre or not ref or float(pre)<=0 or float(ref)<=0: raise ValueError('TPEx missing reference price')
            parsed.append(dict(market=market,stock_id=sid,stock_name=clean(row[2]),ex_date=date,
                event_type=clean(row[8]),pre_close=pre,reference_price=ref,
                cash_dividend=numeric(row[13]),stock_dividend_value=numeric(row[5]),
                source_year_month=ym,source_sha256=sha,official_source=URLS[market],validation='historical_event_observed_not_complete'))
    # Never equate an empty response to a corporate-action-free month.
    if not rows: raise ValueError('empty provider result: not proof of no corporate actions')
    return parsed


def window(month, cutoff):
    y, m=map(int,(month[:4],month[5:]));
    st=dt.date(y,m,1)
    en=min(cutoff,dt.date(y,m,calendar.monthrange(y,m)[1]))
    return st,en


def months(start,end):
    ym=(end.year,end.month); current=(start.year,start.month)
    result=[]
    while current<=ym:
        result.append(f'{current[0]:04d}-{current[1]:02d}')
        current=(current[0]+(current[1]==12),current[1]%12+1)
    return result[::-1]


def get_cutoff(data_dir):
    doc=json.loads((data_dir/'official_meta.json').read_text(encoding='utf-8-sig'))
    if doc.get('status')!='ok' or doc.get('aligned') is not True: raise ValueError('official daily market data not aligned')
    d1=doc.get('market_dates')
    if not isinstance(d1,dict): raise ValueError('market_dates absent')
    dates=[strict_day(v) for v in d1.values()]
    if len(dates)<2 or len(set(dates))!=1: raise ValueError('TWSE/TPEx quote dates differ')
    return dates[0]


def process(data_dir=SITE,archive_dir=ARCHIVE,start_date='2026-01-01',months_per_run=2,
            now=None, fetcher=request_json):
    data_dir=Path(data_dir); archive_dir=Path(archive_dir)
    now=now or dt.datetime.now(TZ)
    start=strict_day(start_date)
    problems=[]
    try: cutoff=get_cutoff(data_dir)
    except Exception as ex: cutoff=None; problems.append('行情截止日期不可驗證：'+str(ex)[:120])
    ledger_path=data_dir/'corporate_action_history_sources.csv'
    ledger=read_csv(ledger_path)
    by_key=defaultdict(list)
    for l in ledger: by_key[(l.get('market'),l.get('year_month'))].append(l)
    chosen=[]
    if cutoff and cutoff>=start:
        for ym in months(start,cutoff):
            remaining=[]
            for market in ('上市','上櫃'):
                old=by_key[(market,ym)]
                if any(o.get('result')=='events_archived' and o.get('query_end','')>=window(ym,cutoff)[1].isoformat() for o in old): continue
                # Failed requests need retry, but no more than once every 3 calendar days.
                if old:
                    try: age=(now.date()-dt.date.fromisoformat(old[-1]['attempted_at_taipei'][:10])).days
                    except ValueError: age=3
                    if age<3 and any('v2.5B.1' in x.get('diagnostic','') for x in old): continue
                    # Permit exactly one schema-diagnostic recheck after v2.5B upgrade.
                    # Historical failures remain archived; routine 3-day cooldown resumes.
                remaining.append(market)
            if remaining:
                chosen.append((ym,remaining))
            if len(chosen)>=months_per_run: break
    elif cutoff: problems.append('資料日期早於回補起點')
    for ym,markets in chosen:
        a,b=window(ym,cutoff)
        for market in markets:
            url=query(market,a,b); result='request_failed'; diag=''; sha=''; archive=''; n=0
            try:
                blob,obj=fetcher(url)
                sha=hashlib.sha256(blob).hexdigest()
                events=normalize(obj,market,a,b,ym,sha)
                # A returned result proves some events are observable; it does NOT prove complete coverage.
                rawfile=archive_dir/f'{"twse" if market=="上市" else "tpex"}_{ym.replace("-","")}_{sha[:16]}.json'
                archive=str(rawfile.relative_to(ROOT)) if rawfile.is_relative_to(ROOT) else str(rawfile)
                rawfile.parent.mkdir(parents=True,exist_ok=True)
                if rawfile.exists() and rawfile.read_bytes()!=blob: raise ValueError('immutable raw archive conflict')
                if not rawfile.exists(): rawfile.write_bytes(blob)
                result='events_archived'; n=len(events)
                if not events: diag='provider returned rows but none matched ordinary shares'
            except Exception as ex:
                result='source_unverified'; diag=f'v2.5B.1 {type(ex).__name__}: {str(ex)[:280]}'
                sha=''; archive=''
            ledger.append(dict(market=market,year_month=ym,query_start=a.isoformat(),query_end=b.isoformat(),
                attempted_at_taipei=now.astimezone(TZ).isoformat(timespec='seconds'),
                result=result,event_rows=n,sha256=sha,archive_path=archive,url=url,diagnostic=diag))
            print('2.5B',ym,market,result,n,diag[:90])
            if fetcher is request_json: time.sleep(.4)
    # Cross-check stored official raw hashes at EVERY run before extracting event history.
    all_events=[]; seen_blob=set(); bad_archives=[]
    for row in ledger:
        if row.get('result')!='events_archived': continue
        key=(row.get('market'),row.get('year_month'),row.get('sha256'))
        if key in seen_blob: continue
        seen_blob.add(key)
        try:
            rel=Path(row['archive_path'])
            target=(ROOT/rel).resolve()
            if not target.is_relative_to(archive_dir.resolve()): raise ValueError('unsafe archive path')
            blob=target.read_bytes()
            if hashlib.sha256(blob).hexdigest()!=row['sha256']: raise ValueError('raw SHA256 mismatch')
            obj=json.loads(blob.decode('utf-8-sig'))
            a=strict_day(row['query_start']); b=strict_day(row['query_end'])
            all_events.extend(normalize(obj,row['market'],a,b,row['year_month'],row['sha256']))
        except Exception as ex:
            bad_archives.append(f"{row.get('market')} {row.get('year_month')}: {type(ex).__name__}")
    if bad_archives: problems.extend(bad_archives)
    # A later partial-month fetch may return the same event with new source SHA.
    # Collapse to the latest seen version only for the summary; retain immutable raw
    # source hashes and a per-revision report for audit and point-in-time research.
    by_event=defaultdict(list)
    for r in all_events:
        key=(r['market'],r['stock_id'],r['ex_date'],r['event_type'])
        by_event[key].append(r)
    revisions=[]; event_list=[]
    for key, versions in sorted(by_event.items()):
        seen_sha={v['source_sha256']:v for v in versions}
        distinct_versions=list(seen_sha.values())
        latest_event=distinct_versions[-1]
        event_list.append(latest_event)
        signatures={(v['pre_close'],v['reference_price'],v['cash_dividend'],v['stock_dividend_value']) for v in distinct_versions}
        if len(signatures)>1:
            revisions.append({'market':key[0],'stock_id':key[1],'ex_date':key[2],
                'event_type':key[3], 'source_versions':len(distinct_versions),
                'source_sha256s':';'.join(sorted(seen_sha)),
                'status':'values_disagree_manual_reconciliation_required'})
    if revisions: problems.append(f'存在 {len(revisions)} 個官方歷史事件來源版本數值不同，需人工核對')
    observations=read_csv(data_dir/'corporate_action_gap_audit.csv')
    if not observations: problems.append('2.5A 觀察清單缺失')
    universe={}
    for row in observations:
        key=(row.get('market','').strip(),row.get('stock_id','').strip())
        if not (key[0] in ('上市','上櫃') and re.fullmatch(r'\d{4}',key[1])):
            problems.append('觀察清單股票識別欄位異常'); continue
        entry=universe.setdefault(key,{'stock_name':row.get('stock_name','').strip(),'count':0})
        entry['count']+=1
    event_counts=defaultdict(int)
    for r in event_list: event_counts[(r['market'],r['stock_id'])]+=1
    stock_list=[]
    for (market,sid),item in sorted(universe.items()):
        cnt=event_counts[(market,sid)]
        stock_list.append(dict(market=market,stock_id=sid,stock_name=item['stock_name'],
            cohort_observations=item['count'],official_events_seen=cnt,
            historical_completeness_verified='否',adjusted_ohlc_verified='否',
            return_calculation_allowed='否',
            state='已觀察部分官方歷史事件_覆蓋未驗證' if cnt else '未能確認歷史事件_不代表沒有除權息'))
    write_csv(ledger_path,ledger,LEDGER)
    write_csv(data_dir/'corporate_action_history_events.csv',event_list,EVENT)
    write_csv(data_dir/'corporate_action_history_revisions.csv',revisions,
              ['market','stock_id','ex_date','event_type','source_versions','source_sha256s','status'])
    write_csv(data_dir/'corporate_action_history_universe.csv',stock_list,STOCK)
    attempted={(x.get('market'),x.get('year_month')) for x in ledger}
    attempted_failures=sum(1 for x in ledger if x.get('result')!='events_archived')
    if attempted_failures: problems.append(f'歷史來源曾有 {attempted_failures} 次失敗或無法證明空結果，需後續重試')
    requested=len(months(start,cutoff))*2 if cutoff and cutoff>=start else 0
    confirmed={ (x.get('market'),x.get('year_month')) for x in ledger if x.get('result')=='events_archived'}
    meta={'version':VERSION,'status':'audit_warnings' if problems else 'observations_only_not_complete',
        'generated_at_taipei':now.astimezone(TZ).isoformat(timespec='seconds'),
        'start_date':start.isoformat(),'price_cutoff':cutoff.isoformat() if cutoff else None,
        'requested_market_month_pairs':requested, 'attempted_market_month_pairs':len(attempted),
        'market_month_pairs_with_observed_events':len(confirmed),
        'observed_historical_event_rows':len(event_list),'distinct_stocks_in_observations':len(stock_list),
        'stocks_with_at_least_one_observed_historical_event':sum(event_counts[k]>0 for k in universe),
        'requested_new_month_windows':len(chosen),
        'archive_sha256_failures':len(bad_archives),'source_attempts_unverified':attempted_failures,
        'event_revision_conflicts':len(revisions),'warnings':problems,
        'historical_corporate_actions_complete':False,'adjusted_ohlc_verified':False,
        'source_publication_times_verified':False,'sample_independence_verified':False,
        'performance_metrics_enabled':False,'strict_performance_samples_eligible':0,
        'important':'事件有記錄≠區間已完整驗證；沒有事件≠確認無事件；不計算還原價格與報酬',
        'outputs':['corporate_action_history_meta.json','corporate_action_history_sources.csv',
                   'corporate_action_history_events.csv','corporate_action_history_universe.csv',
                   'corporate_action_history_revisions.csv']}
    dump_json(data_dir/'corporate_action_history_meta.json',meta)
    print('2.5B',meta['status'],'events',len(event_list),'stocks',len(stock_list),'NO RETURNS')
    return meta


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',type=Path,default=SITE)
    p.add_argument('--archive-dir',type=Path,default=ARCHIVE)
    p.add_argument('--start-date',default=os.environ.get('CORP_HISTORY_START','2026-01-01'))
    p.add_argument('--months-per-run',type=int,default=2)
    args=p.parse_args()
    if not 1<=args.months_per_run<=4: p.error('--months-per-run must be 1..4')
    process(args.data_dir,args.archive_dir,args.start_date,args.months_per_run)

if __name__=='__main__':main()
