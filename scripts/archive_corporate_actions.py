#!/usr/bin/env python3
"""TPE-MFDS 2.4E: immutable, source-attributed rolling ex-right/dividend notices.

Educational data audit only. Announcement feed is *not* complete historical
corporate-action coverage, fully adjusted prices, or an executable return model.
Preserve exact source JSON bytes via SHA256, record first observation timestamps,
never backdate events, and fail closed if a provider fails or changes its schema.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'site' / 'data'
UTC = dt.timezone.utc
TZ = ZoneInfo('Asia/Taipei')
VERSION = '2.4E'
SOURCES = {
    'TWSE': 'https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL',
    'TPEx': 'https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost',
}
COLUMNS = [
    'market','stock_id','stock_name','ex_date','event_type','cash_dividend_twd_per_share',
    'stock_dividend_ratio_reported','cash_status','first_observed_at_utc',
    'last_observed_at_utc','latest_observation_source_sha256','last_seen_this_run',
    'version_count','source_url','note',
]
CHANGE_COLUMNS = ['market','stock_id','stock_name','ex_date','event_type','first_observed_at_utc','latest_observed_at_utc','distinct_announced_values','issue_type','note']
COVERAGE_COLUMNS = [
    'cohort_id','stock_id','stock_name','market','observation_status',
    'source_fetch_status','rolling_notice_events_observed','notice_coverage',
    'historical_corporate_actions_complete','adjusted_ohlc_verified',
    'return_calculation_allowed','reason',
]


def sha(raw): return hashlib.sha256(raw).hexdigest()


def iso(now):
    return now.astimezone(UTC).isoformat(timespec='microseconds').replace('+00:00','Z')


def date_roc(value):
    # Date strings must be ROC YYYY? 1151027 or 115/10/27; never infer other formats.
    s = str(value or '').strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not re.fullmatch(r'\d{7}', digits):
        raise ValueError('官方日期不是7碼民國日期：'+repr(s[:35]))
    value = dt.date(int(digits[:3])+1911, int(digits[3:5]), int(digits[5:]))
    if not (2000 <= value.year <= 2100):
        raise ValueError('官方除權息年份不合理')
    return value.isoformat()


def number(value):
    if value is None: return None
    s=str(value).strip().replace(',','')
    if not s or any(word in s for word in ('尚未公告','待公告','N/A')) or s in ('-','--'):
        return None
    try: out=float(s)
    except ValueError: raise ValueError('官方股利數值格式錯誤：'+repr(s[:30]))
    if not math.isfinite(out) or out<0 or out>100000:
        raise ValueError('官方股利數值不合理')
    return out


def event_type(value):
    s=str(value or '').strip()
    if not s or ('權' not in s and '息' not in s):
        raise ValueError('未知除權息類別：'+repr(s))
    return '權息' if ('權' in s and '息' in s) else ('權' if '權' in s else '息')


def normalize(market, row):
    if not isinstance(row,dict): raise ValueError('官方公告內容不是物件')
    if market=='TWSE':
        required=('Date','Code','Name','Exdividend','CashDividend','StockDividendRatio')
        mapping=('Code','Name','Date','Exdividend')
    elif market=='TPEx':
        # Preserve the exact official field spelling, including the two r's.
        required=('ExRrightsExDividendDate','SecuritiesCompanyCode','CompanyName',
                  'ExRrightsExDividend','CashDividend','StockDividendRatio')
        mapping=('SecuritiesCompanyCode','CompanyName','ExRrightsExDividendDate','ExRrightsExDividend')
    else: raise ValueError('非法市場')
    if any(k not in row for k in required):
        raise ValueError('官方公告欄位變更／缺少：'+','.join(k for k in required if k not in row))
    code=str(row[mapping[0]]).strip()
    name=str(row[mapping[1]]).strip()
    if not re.fullmatch(r'[0-9A-Za-z]{4,8}',code) or not name or len(name)>100:
        raise ValueError('官方股票代號或名稱不合法')
    typ=event_type(row[mapping[3]])
    cash=number(row['CashDividend'])
    ratio=number(row['StockDividendRatio'])
    # A blank or zero cash amount with an ex-dividend announcement may mean
    # pending/zero depending on context. Only blank is 'pending'; zero is known 0.
    return {
        'market':market,'stock_id':code,'stock_name':name,
        'ex_date':date_roc(row[mapping[2]]),'event_type':typ,
        'cash_dividend_twd_per_share':cash,
        'stock_dividend_ratio_reported':ratio,
        'cash_status':'未公告金額' if ('息' in typ and cash is None) else
                      ('已提供金額' if cash is not None else '非現金除息'),
    }


def parse_feed(market, raw):
    if not isinstance(raw,list) or not raw or len(raw)>20000:
        raise ValueError('官方公告不是合理筆數的非空陣列；空清單不能證明當期無事件')
    entries={}
    for row in raw:
        obj=normalize(market,row)
        identity=(obj['stock_id'],obj['ex_date'],obj['event_type'])
        if identity in entries and entries[identity]!=obj:
            raise ValueError('同一公告事件出現矛盾紀錄')
        entries[identity]=obj
    if not entries: raise ValueError('官方公告沒有可核實資料')
    return sorted(entries.values(),key=lambda x:(x['ex_date'],x['stock_id'],x['event_type']))


def fetch(url):
    req=urllib.request.Request(url,headers={
        'User-Agent':'TPE-MFDS-educational-data-research/2.4E',
        'Accept':'application/json',
    })
    with urllib.request.urlopen(req,timeout=25) as resp:
        if resp.status!=200: raise RuntimeError('官方API HTTP狀態：'+str(resp.status))
        raw=resp.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('官方API資料過大')
    return raw


def source_path(root,market,digest):
    return root/market/(digest+'.json')


def read_sources(root):
    """Validate *every* archived source: an unreadable/modified file is fatal."""
    versions=[]
    for market in SOURCES:
        for path in sorted((root/market).glob('*.json')):
            obj=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(obj,dict) or obj.get('market')!=market:
                raise ValueError('除權息封存市場別損壞：'+str(path))
            if not re.fullmatch('[0-9a-f]{64}',path.stem) or path.stem!=obj.get('source_sha256'):
                raise ValueError('除權息封存雜湊檔名不符：'+str(path))
            raw=str(obj.get('raw_json','')).encode('utf-8')
            if sha(raw)!=path.stem:
                raise ValueError('除權息來源原始資料SHA256不符：'+str(path))
            ts=dt.datetime.fromisoformat(str(obj.get('first_seen_at_utc','')).replace('Z','+00:00'))
            if ts.tzinfo is None: raise ValueError('來源封存時間缺時區')
            parsed=parse_feed(market,json.loads(raw.decode('utf-8-sig')))
            if obj.get('normalized')!=parsed:
                raise ValueError('封存正規化資料不一致，拒絕覆寫')
            versions.append(obj)
    return versions


def dump_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def dump_csv(path,items,cols):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as fp:
        writer=csv.DictWriter(fp,fieldnames=cols,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(items)


def all_observations(data_dir):
    path=data_dir/'forward_observation.csv'
    if not path.exists(): raise FileNotFoundError('2.4C前瞻觀察CSV不存在，停止以免出現錯誤股票池')
    with path.open('r',encoding='utf-8-sig',newline='') as fp:
        return list(csv.DictReader(fp))


def run(data_dir=DATA,now=None,fetchers=None):
    data_dir=Path(data_dir)
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None: raise ValueError('必須提供具時區的執行時間')
    now=now.astimezone(UTC)
    root=data_dir/'corporate_action_sources'
    versions=read_sources(root)
    by_digest={(v['market'],v['source_sha256']):v for v in versions}
    fetchers=fetchers or {}
    result_status={}; newly=[]
    for market,url in SOURCES.items():
        try:
            getter=fetchers.get(market,fetch)
            received=getter(url)
            if isinstance(received,(list,dict)):
                raw=json.dumps(received,ensure_ascii=False,separators=(',',':')).encode('utf-8')
            elif isinstance(received,bytes):
                raw=received
            else:
                raise ValueError('來源測試值不是JSON/bytes')
            if len(raw)>2_000_000:raise ValueError('官方API回應超過長度限制')
            entries=parse_feed(market,json.loads(raw.decode('utf-8-sig')))
            key=(market,sha(raw))
            path=source_path(root,market,key[1])
            was_new=key not in by_digest
            if was_new:
                if path.exists():raise ValueError('同名封存損壞，不得覆寫')
                # JSON stores lossless raw UTF8 string; for unusual UTF8-BOM the
                # SHA is checked against the stored bytes on every future run.
                plain=raw.decode('utf-8')
                obj={'version':VERSION,'market':market,'source_url':url,
                     'source_sha256':key[1],'first_seen_at_utc':iso(now),
                     'raw_json':plain,'normalized':entries,
                     'coverage_statement':'僅當次滾動預告表，不代表歷史完整除權息資料'}
                dump_json(path,obj)
                versions.append(obj);by_digest[key]=obj;newly.append(path)
            result_status[market]={
                'status':'ok','rows_this_run':len(entries),
                'new_source_version_saved':was_new,'latest_sha256':key[1],
                'source_first_seen_at_utc':by_digest[key]['first_seen_at_utc'],
                'source_url':url,'error':None,
            }
        except (OSError,ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError,RuntimeError) as exc:
            result_status[market]={
                'status':'unavailable_or_invalid_fail_closed','rows_this_run':0,
                'new_source_version_saved':False,'latest_sha256':None,
                'source_first_seen_at_utc':None,'source_url':url,
                'error':type(exc).__name__+': '+str(exc)[:175],
            }
    # Verify output and archival consistency before writing mutable reports.
    versions=read_sources(root)
    current_hashes={k:v['latest_sha256'] for k,v in result_status.items() if v['status']=='ok'}
    ledger={}; histories={}; observed_values={}
    for item in sorted(versions,key=lambda o:(o['first_seen_at_utc'],o['market'],o['source_sha256'])):
        for entry in item['normalized']:
            ident=(item['market'],entry['stock_id'],entry['ex_date'],entry['event_type'])
            if ident not in ledger:
                ledger[ident]={**entry,
                    'first_observed_at_utc':item['first_seen_at_utc'],
                    'last_observed_at_utc':item['first_seen_at_utc'],
                    'latest_observation_source_sha256':item['source_sha256'],
                    'last_seen_this_run':False,'version_count':0,
                    'source_url':item['source_url'],
                    'note':'滾動官方公告快照；可能不含較早事件；未核實歷史完整性'}
                histories[ident]=set()
                observed_values[ident]=set()
            row=ledger[ident]
            row.update({
                'last_observed_at_utc':item['first_seen_at_utc'],
                'latest_observation_source_sha256':item['source_sha256'],
                'cash_dividend_twd_per_share':entry['cash_dividend_twd_per_share'],
                'stock_dividend_ratio_reported':entry['stock_dividend_ratio_reported'],
                'cash_status':entry['cash_status'],
                'stock_name':entry['stock_name'],
            })
            histories[ident].add(item['source_sha256'])
            observed_values[ident].add((entry['cash_dividend_twd_per_share'],entry['stock_dividend_ratio_reported']))
            if item['source_sha256']==current_hashes.get(item['market']):
                row['last_seen_this_run']=True
    rows=[]
    for ident,row in sorted(ledger.items()):
        row['version_count']=len(histories[ident]);rows.append(row)
    changes=[]
    for ident,values in sorted(observed_values.items()):
        if len(values)>1:
            row=ledger[ident]
            changes.append({
                'market':row['market'],'stock_id':row['stock_id'],'stock_name':row['stock_name'],
                'ex_date':row['ex_date'],'event_type':row['event_type'],
                'first_observed_at_utc':row['first_observed_at_utc'],
                'latest_observed_at_utc':row['last_observed_at_utc'],
                'distinct_announced_values':len(values),
                'issue_type':'公告金額或配股率曾變更_待核實',
                'note':'保留全部原始來源版本；最新滾動公告不等於最終確定配發資料',
            })
    observations=all_observations(data_dir)
    matched=Counter((r['market'],r['stock_id']) for r in rows)
    coverage=[]
    for cohort in observations:
        market={'上市':'TWSE','上櫃':'TPEx'}.get(cohort.get('market',''))
        code=cohort.get('stock_id','')
        count=matched.get((market,code),0)
        fetch_stat=result_status.get(market,{}).get('status','market_unknown')
        coverage.append({
            'cohort_id':cohort.get('cohort_id',''),'stock_id':code,
            'stock_name':cohort.get('stock_name',''),'market':cohort.get('market',''),
            'observation_status':cohort.get('observation_status',''),
            'source_fetch_status':fetch_stat,
            'rolling_notice_events_observed':count,
            'notice_coverage':'有已封存滾動公告' if count else '未在已取得滾動公告中找到_不代表沒有除權息',
            'historical_corporate_actions_complete':'false',
            'adjusted_ohlc_verified':'false',
            'return_calculation_allowed':'false',
            'reason':'預告表非歷史完整資料；缺全期間公司行動與還原OHLC、成本及成交規則；禁止績效計算',
        })
    report={
        'version':VERSION,'status':'ok' if all(v['status']=='ok' for v in result_status.values()) else 'partial_fail_closed',
        'generated_at_taipei':now.astimezone(TZ).isoformat(timespec='seconds'),
        'sources':result_status,'source_archive_versions_total':len(versions),
        'new_archives':len(newly),
        'rolling_events_ever_seen':len(rows),
        'event_cash_pending':sum(x['cash_status']=='未公告金額' for x in rows),
        'announced_value_revision_flags':len(changes),
        'forward_observation_rows':len(coverage),
        'forward_rows_with_any_rolling_notice':sum(int(x['rolling_notice_events_observed']>0) for x in coverage),
        'coverage_scope':'只包含執行本系統後取得的滾動官方預告；歷史空白不能推定無公司行動',
        'historical_corporate_actions_complete':False,
        'adjusted_ohlc_verified':False,'total_return_calculation_allowed':False,
        'performance_metrics_enabled':False,
        'outputs':['corporate_actions_meta.json','corporate_actions_observed.csv','corporate_action_coverage.csv','corporate_action_changes.csv','corporate_action_sources/'],
    }
    dump_csv(data_dir/'corporate_actions_observed.csv',rows,COLUMNS)
    dump_csv(data_dir/'corporate_action_coverage.csv',coverage,COVERAGE_COLUMNS)
    dump_csv(data_dir/'corporate_action_changes.csv',changes,CHANGE_COLUMNS)
    dump_json(data_dir/'corporate_actions_meta.json',report)
    print('2.4E notices:',report['status'],'archived_sources=',len(versions),
          'events=',len(rows),'cohort_rows=',len(coverage),'NO RETURNS')
    if report['status']!='ok':
        print('::warning::至少一個官方除權息來源下載或欄位驗證失敗，已保守標記；禁止解讀為資料完整')
    return report,rows,coverage


if __name__=='__main__':
    ap=argparse.ArgumentParser(description='Archive official rolling corporate-action notices; no returns')
    ap.add_argument('--data-dir',type=Path,default=DATA)
    args=ap.parse_args();run(args.data_dir)
