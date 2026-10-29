#!/usr/bin/env python3
"""3.0U — fetch and attest the 2026-10-23 TWSE original closure PDF.

ONLY a literal investor-education TWSE host PDF with its actual bytes,
SHA256 and document text proving issuer, release day, event date, exchange,
and market-wide closure can raise the *TWSE* documentary proof flag.

TPEx is a distinct cash market. Its trading-day status remains pending
unless its own complete original official release is separately verified.
Neither provenance flag certifies first publication time, all trading dates,
actual executions, P&L, or a backtest win rate.

This is verification of official historical DOCUMENT CONTENT, not proof that
our crawler had the document prior to the closure itself.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site'/'data'
PDF_URL='https://investoredu.twse.com.tw/FileSystem/FileUpload/c91c7dff-afb0-42cc-9949-9f072bece31d.pdf'
EXCHANGE='TWSE'
EVENT_DAY='2026-10-23'
RELEASE_DAY='2026-10-22'
PDF_MIN_BYTES=750
PDF_MAX_BYTES=1_800_000
VERSION='3.0U'

def digest(b):return hashlib.sha256(b).hexdigest()
def utc(now):return now.astimezone(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')

def verify_url(url):
 u=urllib.parse.urlsplit(url)
 if (u.scheme!='https' or u.hostname!='investoredu.twse.com.tw' or
     u.username or u.password or u.port not in (None,443) or
     not re.fullmatch(r'/FileSystem/FileUpload/[a-f0-9-]{36}\.pdf',u.path,re.I) or u.query or u.fragment):
  raise ValueError('original TWSE PDF URL must remain on known first-party host and file path')
 return True

def validate_pdf_bytes(original):
 if not isinstance(original,bytes) or not original.startswith(b'%PDF-'):
  raise ValueError('downloaded TWSE notice is not a PDF')
 if not PDF_MIN_BYTES<=len(original)<=PDF_MAX_BYTES:
  raise ValueError('TWSE original PDF length outside bounds')

def pdf_text(original):
 validate_pdf_bytes(original)
 binary=shutil.which('pdftotext')
 if binary is None:raise ValueError('pdftotext not installed; original cannot be independently checked')
 result=subprocess.run([binary,'-layout','-enc','UTF-8','-','-'],
    input=original,capture_output=True,timeout=22,check=False)
 if result.returncode:
  raise ValueError('pdftotext rejected TWSE original PDF')
 try:return result.stdout.decode('utf-8',errors='strict')
 except UnicodeError as e:raise ValueError('cannot decode PDF text') from e

def verify_original_text(content):
 if not isinstance(content,str):raise ValueError('TWSE PDF text unavailable')
 text=re.sub(r'\s+','',content).replace('臺','台')
 if '台灣證券交易所' not in text:raise ValueError('PDF does not identify TWSE issuer')
 if '集中交易市場' not in text:raise ValueError('PDF does not identify listed cash trading market')
 if '交易部' not in text:raise ValueError('TWSE issuer department missing')
 if '115年10月22日' not in text:raise ValueError('TWSE release day absent')
 if '115年10月23日' not in text:raise ValueError('specific closure date absent')
 if '全日休市' not in text and '休市一天' not in text and '休市一日' not in text:
  raise ValueError('PDF does not state market-wide closure')
 if '交割' not in text:raise ValueError('official settlement handling absent')
 # A date string and market words appearing in an unrelated news index do not pass.
 if len(text)<75 or len(text)>15_000:raise ValueError('official document text implausible')
 return {'issuer':'臺灣證券交易所','issuer_division':'交易部',
  'market':'上市現貨集中交易市場','released_on_document':RELEASE_DAY,
  'effective_closed_date':EVENT_DAY,'closure_scope':'集中市場全日',
  'settlement_handling_mentioned':True,
  'official_first_publication_timestamp_verified':False}

def download():
 verify_url(PDF_URL)
 req=urllib.request.Request(PDF_URL,headers={
  'User-Agent':'Mozilla/5.0 (compatible; MFDS-Original-TWSE-PDF-Research/3.0U)',
  'Accept':'application/pdf','Cache-Control':'no-cache'})
 with urllib.request.urlopen(req,timeout=22) as response:
  if response.status!=200:raise ValueError('original PDF HTTP '+str(response.status))
  verify_url(response.geturl())
  typ=response.headers.get('Content-Type','').lower()
  if typ and 'application/pdf' not in typ and 'application/octet-stream' not in typ:
   raise ValueError('official PDF unexpected content type')
  b=response.read(PDF_MAX_BYTES+1)
 if len(b)>PDF_MAX_BYTES:raise ValueError('PDF exceeds size cap')
 return b,PDF_URL

def file_path(data,digest_value):
 return data/'official_closure_originals_30u'/('twse_20261023_'+digest_value+'.pdf')

def check_local(data,manifest,extractor=None):
 """Verify actual immutable PDF, not just a self-declared JSON success flag."""
 r=manifest.get('sources',{}).get('TWSE',{})
 if r.get('full_original_document_verified') is not True:return False
 path=r.get('source_file')
 sha=r.get('source_sha256')
 if not path or not re.fullmatch(r'[0-9a-f]{64}',str(sha)):
  raise ValueError('certified document lacks source SHA256 and file')
 source=file_path(Path(data),sha)
 if source.resolve()!=(Path(data)/path).resolve() or not source.is_file():
  raise ValueError('document path not immutable or file is missing')
 raw=source.read_bytes()
 if digest(raw)!=sha:raise ValueError('certified PDF SHA256 mismatch')
 proof=verify_original_text((extractor or pdf_text)(raw))
 if r.get('event_date')!=proof['effective_closed_date'] or \
    r.get('document_released_on')!=proof['released_on_document']:
  raise ValueError('PDF event/release dates do not agree with verified text')
 if r.get('first_publication_timestamp_verified') is not False:
  raise ValueError('publication time cannot be invented from capture clock')
 return True

def run(data_dir=DATA,now=None,fetch=None,extractor=None):
 data=Path(data_dir)
 now=now or dt.datetime.now(dt.timezone.utc)
 if now.tzinfo is None:raise ValueError('observation clock must be timezone-aware')
 get_text=extractor or pdf_text
 root=data/'official_closure_originals_30u'
 root.mkdir(parents=True,exist_ok=True)
 previous=[]
 for existing in sorted(root.glob('twse_20261023_*.pdf')):
  raw=existing.read_bytes()
  if existing!=file_path(data,digest(raw)):
   raise ValueError('immutable historical TWSE PDF changed: '+existing.name)
  validate_pdf_bytes(raw)
  proof=verify_original_text(get_text(raw))
  previous.append((existing,proof))
 error=None;fresh=None
 try:
  raw,url=(fetch or download)()
  verify_url(url)
  validate_pdf_bytes(raw)
  proof=verify_original_text(get_text(raw))
  d=digest(raw)
  dest=file_path(data,d)
  if dest.exists():
   if dest.read_bytes()!=raw:raise ValueError('cached official original changed')
  else:
   dest.write_bytes(raw)
  fresh=(dest,proof)
 except (OSError,ValueError,UnicodeError,subprocess.TimeoutExpired) as e:
  error=type(e).__name__+': '+str(e)[:240]
 used=fresh or (previous[-1] if previous else None)
 if used:
  src,proof=used
  sha=digest(src.read_bytes())
  twse={'market':'上市','status':'verified_full_original_pdf',
        'full_original_document_verified':True,
        'source_url':PDF_URL,'source_file':src.relative_to(data).as_posix(),
        'source_sha256':sha,'document_released_on':RELEASE_DAY,
        'event_date':EVENT_DAY,'document_proof':proof,
        'retrieved_this_run_at_utc':utc(now) if fresh else None,
        'first_publication_timestamp_verified':False,'fetch_error':error}
 else:
  twse={'market':'上市','status':'official_original_pending',
        'full_original_document_verified':False,'source_url':PDF_URL,
        'source_file':None,'source_sha256':None,
        'document_released_on':None,'event_date':EVENT_DAY,
        'document_proof':None,'retrieved_this_run_at_utc':None,
        'first_publication_timestamp_verified':False,'fetch_error':error}
 tpex={'market':'上櫃','status':'independent_complete_original_pending',
       'full_original_document_verified':False,'source_url':None,
       'source_file':None,'source_sha256':None,
       'event_date':EVENT_DAY,'first_publication_timestamp_verified':False,
       'explanation':'3.0T只有櫃買中心公告索引，非2026/10/23完整原始官方事件公告'}
 result={'version':VERSION,'date':EVENT_DAY,'generated_at_utc':utc(now),
   'status':'one_market_document_possible_other_pending',
   'sources':{'TWSE':twse,'TPEX':tpex},
   'both_cash_markets_official_originals_verified':False,
   'all_trading_sessions_independently_verified':False,
   'official_first_publication_timestamp_verified':False,
   'verified_trade_samples':0,'certified_win_rate':None,'trade_performance_enabled':False,
   'explanation':'僅在PDF原始SHA256、issuer、發布日期、事件日期及市場範圍全數核實後，得標示上市單一事件官方原文已證實。上櫃現貨需另行核對櫃買中心原公告。PDF文件內的日期不是本站可在當時使用資料的PIT時間，也不能推導勝率。'}
 data.mkdir(parents=True,exist_ok=True)
 output=data/'official_closure_notice_evidence_30u.json'
 output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 # Gate on the very same original PDF bytes about to be persisted.
 if twse['full_original_document_verified'] and not check_local(data,result,get_text):
  raise ValueError('official TWSE document cannot pass independent local gate')
 print('3.0U TWSE original='+twse['status']+'; TPEx original=pending; both-market and model qualification OFF')
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,default=DATA)
 args=p.parse_args();run(args.data_dir)
