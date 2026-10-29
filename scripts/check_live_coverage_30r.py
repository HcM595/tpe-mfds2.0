#!/usr/bin/env python3
"""3.0R: independently verify the *deployed* GitHub Pages bytes after publish.

GitHub push being green is not sufficient: this checker downloads the public
site and compares the 3.0R provenance claims with the exact deployed 3.0Q
evidence, index, official calendar, and exceptional-closure lead bytes.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import time
import urllib.request
from urllib.parse import urljoin
from pathlib import Path

BASE='https://hcm595.github.io/tpe-mfds2.0/'
SOURCE_PATHS={
 'meta30r':'data/archive_coverage_meta_30r.json',
 'meta30q':'data/historical_evidence_meta_30q.json',
 'csv30q':'data/historical_evidence_30q.csv',
 'stock':'data/stock_candidate_coverage_30r.csv',
 'day':'data/archive_day_coverage_30r.csv',
 'index':'data/signal_archive_index.json',
 'calendar':'data/official_session_calendar.json',
 'exceptions':'data/market_session_exceptions.csv',
 'html':'index.html',
}
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch_all(base=BASE):
 outputs={}
 for key,path in SOURCE_PATHS.items():
  url=urljoin(base.rstrip('/')+'/',path)
  req=urllib.request.Request(url,headers={
    'User-Agent':'TPE-MFDS-public-deploy-audit/3.0R',
    'Cache-Control':'no-cache','Pragma':'no-cache'})
  with urllib.request.urlopen(req,timeout=25) as response:
   if response.status!=200:raise ValueError(f'{path}: public HTTP {response.status}')
   raw=response.read()
  if not raw:raise ValueError(path+' empty public response')
  outputs[key]=raw
 return outputs
def parse_json(raw,label):
 try:
  result=json.loads(raw.decode('utf-8-sig'))
  if not isinstance(result,dict):raise ValueError('not object')
  return result
 except (UnicodeError,ValueError) as e:
  raise ValueError(label+' invalid published JSON') from e
def count_csv(raw,label):
 try:
  reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
  if not reader.fieldnames:raise ValueError('missing header')
  return list(reader)
 except (UnicodeError,csv.Error) as e:
  raise ValueError(label+' invalid CSV') from e
def evaluate(raw):
 for name in SOURCE_PATHS:
  if name not in raw or not isinstance(raw[name],bytes):
   raise ValueError('published source missing: '+name)
 r=parse_json(raw['meta30r'],'3.0R')
 q=parse_json(raw['meta30q'],'3.0Q')
 index=parse_json(raw['index'],'archive index')
 if r.get('version')!='3.0R' or r.get('status')!='original_sources_verified_no_performance':
  raise ValueError('deployed 3.0R status/version not ready')
 if q.get('version')!='3.0Q' or q.get('strict_validation',{}).get('model_enabled') is not False:
  raise ValueError('deployed upstream model security gate not verified')
 if index.get('snapshots_total')!=q.get('snapshots_in_index'):
  raise ValueError('published upstream archive index does not match historical 3.0Q')
 linked={
   'csv30q':'source_csv_sha256',
   'meta30q':'source_historical_meta_sha256',
   'index':'source_archive_index_sha256',
   'calendar':'source_calendar_sha256',
   'exceptions':'source_market_exceptions_sha256',
 }
 for key,field in linked.items():
  if sha(raw[key])!=r.get(field):
   raise ValueError('published 3.0R '+field+' mismatches live '+SOURCE_PATHS[key])
 records=count_csv(raw['csv30q'],'historical stock rows')
 candidates=count_csv(raw['stock'],'stock candidate coverage')
 day_rows=count_csv(raw['day'],'market calendar coverage')
 if len(records)!=r.get('archived_stock_day_records') or \
    len(records)!=q.get('stock_session_observations'):
  raise ValueError('published historic record count mismatch')
 if len(candidates)!=r.get('stocks_appearing_in_any_archive'):
  raise ValueError('published security-candidate count mismatch')
 if len({x['stock_id'] for x in candidates})!=len(candidates):
  raise ValueError('duplicate published stock candidates')
 if len({x['price_session'] for x in records})!=r.get('verified_price_days'):
  raise ValueError('published price session count mismatch')
 if r.get('trade_performance_enabled') is not False or \
    r.get('verified_trade_samples')!=0 or r.get('certified_win_rate') is not None:
  raise ValueError('unverified financial outcomes published as certified')
 if not any(x['status']=='verified_first_capture' for x in day_rows):
  raise ValueError('no published verified first-seen dates')
 page=raw['html'].decode('utf-8-sig')
 if 'archive_coverage_meta_30r.json' not in page or '3.0R｜封存連續性' not in page:
  raise ValueError('public index is still an older version without 3.0R UI')
 return {'status':'pass','public_source_files_verified':len(SOURCE_PATHS),
  'stock_candidate_days':r['archived_stock_day_records'],
  'archived_price_days':r['verified_price_days'],
  'candidate_stocks':r['stocks_appearing_in_any_archive'],
  'certified_win_rate':None,'trade_performance_enabled':False}
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--base-url',default=BASE)
 parser.add_argument('--attempts',type=int,default=5)
 parser.add_argument('--output',default='live_archive_audit_30r.json')
 opts=parser.parse_args()
 if not 1<=opts.attempts<=8:raise ValueError('attempts outside [1..8]')
 last=None
 for attempt in range(opts.attempts):
  try:
   result=evaluate(fetch_all(opts.base_url))
   Path(opts.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   print('3.0R PUBLIC DEPLOY PASS '+json.dumps(result,ensure_ascii=False))
   return
  except (OSError,ValueError,TimeoutError) as e:
   last=str(e);print(f'Public deploy attempt {attempt+1}/{opts.attempts} cannot confirm: {last}')
   if attempt+1<opts.attempts:time.sleep(12)
 Path(opts.output).write_text(json.dumps({'status':'fail','reason':last},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit('Published research source verification failed: '+str(last))
if __name__=='__main__':main()
