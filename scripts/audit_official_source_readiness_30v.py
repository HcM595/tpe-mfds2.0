#!/usr/bin/env python3
"""3.0V source integrity verdict after 3.0S/3.0U acquisition.

Audits the exact local official PDF bytes, not merely a manifest's success
claim. The critical build fix is provisioning pdftotext in publish.yml.
A refused HTTP source stays pending, and publication timestamps are never
invented from PDF contents or this crawler's first-seen timestamp.

Annual TPEx source proof != 2026-10-23 TPEx extraordinary closure notice.
Both market source readiness != trade-grade historical backtest eligibility.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil

import archive_tpex_calendar_30s as tpex
import archive_official_closure_30u as twse

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site'/'data'
VERSION='3.0V'

def digest(b):
 return hashlib.sha256(b).hexdigest()

def read(path):
 obj=json.loads(path.read_text(encoding='utf-8-sig'))
 if not isinstance(obj,dict):raise ValueError('official source manifest is not JSON object: '+path.name)
 return obj

def error_kind(message):
 if not message:return None
 v=message.lower()
 if 'pdftotext' in v and ('not install' in v or 'not found' in v):
  return 'pdf_extractor_missing'
 if any(x in v for x in ('http error 403','http 403','forbidden','http error 401','http 401')):
  return 'source_access_denied'
 if any(x in v for x in ('urlerror','timed out','name resolution','connection')):
  return 'source_network_unavailable'
 if any(x in v for x in ('pdf','not the','identity','key calendar','first-party','original')):
  return 'source_pdf_content_not_verified'
 return 'source_unclassified_failure'

def verify_tpex(data,manifest,extractor=None):
 if manifest.get('version')!='3.0S' or manifest.get('year')!=2026 or manifest.get('market')!='上櫃':
  raise ValueError('3.0S annual market identity invalid')
 if manifest.get('official_pdf_url')!=tpex.URL:
  raise ValueError('TPEx official source URL changed')
 if manifest.get('annual_market_closure_dates_independently_verified') is not False or \
    manifest.get('2026_10_23_extraordinary_closure_official_original_verified') is not False:
  raise ValueError('TPEx annual PDF is not a complete independently certified closure calendar')
 if manifest.get('status')=='official_original_unavailable_pending':
  if manifest.get('official_raw_pdf_archived') is not False or \
     manifest.get('raw_original_sha256') is not None or \
     manifest.get('raw_source_file') is not None:
   raise ValueError('pending TPEx annual PDF claims archived raw evidence')
  return {'status':'pending','pdf_sha256':None,'reason':error_kind(manifest.get('official_document_download_error')),
          'verified_document_dates':0,'official_full_2026_10_23_notice':False}
 if manifest.get('status')!='archived_official_document_tokens_verified' or \
    manifest.get('official_raw_pdf_archived') is not True:
  raise ValueError('unrecognized official TPEx document status')
 expected=manifest.get('raw_original_sha256')
 if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):
  raise ValueError('TPEx official document hash missing')
 rel='tpex_calendar_sources/year_2026_'+expected+'.pdf'
 if manifest.get('raw_source_file')!=rel:
  raise ValueError('TPEx original path changed or left the provenance directory')
 path=data/rel
 if not path.is_file():
  raise ValueError('TPEx archived original PDF missing')
 raw=path.read_bytes()
 if digest(raw)!=expected:
  raise ValueError('TPEx original PDF SHA256 mismatch')
 tpex_doc=tpex.validate_doc((extractor or tpex.extract_pdf)(raw))
 if manifest.get('document_token_validation')!=tpex_doc:
  raise ValueError('TPEx document token proof differs from archived PDF')
 return {'status':'verified_original_annual_document','pdf_sha256':expected,
         'reason':error_kind(manifest.get('official_document_download_error')),
         'verified_document_dates':tpex_doc['date_tokens_found'],
         'official_full_2026_10_23_notice':False}

def verify_twse(data,manifest,extractor=None):
 if manifest.get('version')!='3.0U' or manifest.get('date')!='2026-10-23':
  raise ValueError('3.0U event/version identity invalid')
 source=manifest.get('sources',{})
 a,b=source.get('TWSE',{}),source.get('TPEX',{})
 if b.get('full_original_document_verified') is not False or \
    manifest.get('both_cash_markets_official_originals_verified') is not False or \
    manifest.get('trade_performance_enabled') is not False or \
    manifest.get('verified_trade_samples')!=0 or \
    manifest.get('certified_win_rate') is not None:
  raise ValueError('TWSE single closure notice cannot certify other market or backtest')
 if a.get('source_url')!=twse.PDF_URL or \
    a.get('first_publication_timestamp_verified') is not False:
  raise ValueError('TWSE provenance host/publication-time identity invalid')
 if a.get('status')=='official_original_pending':
  if a.get('full_original_document_verified') is not False or \
     a.get('source_file') is not None or a.get('source_sha256') is not None:
   raise ValueError('TWSE pending status incorrectly asserts an official original')
  return {'status':'pending','pdf_sha256':None,
          'reason':error_kind(a.get('fetch_error')),
          'event_date_certified':False,'official_publication_clock_verified':False}
 if a.get('status')!='verified_full_original_pdf' or \
    a.get('full_original_document_verified') is not True:
  raise ValueError('TWSE official source status is inconsistent')
 if not twse.check_local(data,manifest,extractor=extractor):
  raise ValueError('TWSE original PDF failed independent SHA/content check')
 return {'status':'verified_original_market_event','pdf_sha256':a['source_sha256'],
         'reason':error_kind(a.get('fetch_error')),
         'event_date_certified':True,'official_publication_clock_verified':False}

def run(data_dir=DATA,now=None,tpex_extractor=None,twse_extractor=None):
 data=Path(data_dir)
 now=now or dt.datetime.now(dt.timezone.utc)
 if now.tzinfo is None:raise ValueError('source audit timestamp must be timezone-aware')
 if shutil.which('pdftotext') is None:
  raise ValueError('pdftotext missing from publisher: PDF verification cannot proceed')
 s=read(data/'tpex_calendar_evidence_30s.json')
 u=read(data/'official_closure_notice_evidence_30u.json')
 tp=verify_tpex(data,s,tpex_extractor)
 tw=verify_twse(data,u,twse_extractor)
 result={
  'version':VERSION,
  'generated_at_utc':now.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z'),
  'status':'verified_source_readiness_performance_blocked',
  'pdf_extractor':'pdftotext',
  'pdf_extractor_present':True,
  'source_manifest_sha256':{
   'tpex_30s':digest((data/'tpex_calendar_evidence_30s.json').read_bytes()),
   'twse_30u':digest((data/'official_closure_notice_evidence_30u.json').read_bytes())},
  'markets':{
   'TWSE_listed_cash_closure_2026_10_23':tw,
   'TPEX_otc_annual_calendar_2026':tp,
   'TPEX_otc_full_closure_notice_2026_10_23':{
    'status':'pending_independent_full_original','event_date_certified':False}},
  'official_closure_proven_for_both_markets':False,
  'annual_tpex_session_classification_verified':False,
  'official_first_publication_timestamp_verified':False,
  'certified_trade_outcomes':0,
  'certified_win_rate':None,
  'trade_model_enabled':False,
  'verification_notes':[
   '現有上櫃官方年曆PDF不是2026/10/23單次臨時休市完整事件公告。',
   '官方PDF文本日期與本站首次取得日不同，也不能認定官方首次對外公開時分。',
   '來源拒絕存取時維持待核實；不採上市公告替代上櫃原文。',
   '交易績效仍需完整交易日、PIT、除權息還原、成本與樣本外檢驗。'],
  'outputs':['official_source_readiness_30v.json']
 }
 out=data/'official_source_readiness_30v.json'
 out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('3.0V: PDF extractor OK; TWSE='+tw['status']+
       '; TPEx annual='+tp['status']+'; independent TPEx event=pending; performance=OFF')
 return result

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--data-dir',type=Path,default=DATA)
 args=parser.parse_args()
 run(args.data_dir)
