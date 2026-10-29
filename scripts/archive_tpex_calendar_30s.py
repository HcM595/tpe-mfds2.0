#!/usr/bin/env python3
"""3.0S — independent TPEx annual calendar *document* provenance.

This is NOT a proof of every market closure. A published TPEx calendar PDF is
archived with its raw SHA256 only if it is actually downloaded and parsed.
The named dates are cross-checked as document tokens, NOT classified into
closure/trading-status rows (the PDF contains both!). Thus it never upgrades
the market-day or 2026-10-23 extraordinary-closure certification.

Failed source requests remain 'pending'; no TWSE-only fallback may be labelled
a verified TPEx original. Previously archived immutable original may be
reused only after re-verifying its bytes and recognized annual document text.
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
import urllib.request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site'/'data'
URL='https://www.tpex.org.tw/storage/eb_data/11411/114007545811-1.pdf'
ANNOUNCEMENT='https://www.tpex.org.tw/storage/eb_data/11411/11400754581.html'
YEAR=2026
ROC_YEAR=115
TIMEZONE=ZoneInfo('Asia/Taipei')
# These particular days must be mentioned in the original PDF.
# Mere mention does NOT establish that each is closed: the PDF also lists
# last trading days and first trading days. These are document identity checks.
REQUIRED_TOKENS=((1,1),(2,12),(2,13),(2,27),(4,3),(4,6),
                 (5,1),(6,19),(9,25),(9,28),(10,9),(10,26),(12,25))
VERSION='3.0S'

def sha256(data:bytes)->str:
 return hashlib.sha256(data).hexdigest()

def iso_utc(now):
 return now.astimezone(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')

def extract_pdf(raw:bytes)->str:
 if not isinstance(raw,bytes) or not raw.startswith(b'%PDF-') or len(raw)<900:
  raise ValueError('downloaded object is not a plausible original PDF')
 binary=shutil.which('pdftotext')
 if not binary:raise ValueError('pdftotext PDF text extractor is not installed')
 cp=subprocess.run([binary,'-layout','-enc','UTF-8','-','-'],
    input=raw,capture_output=True,timeout=20,check=False)
 if cp.returncode or len(cp.stdout)<100:
  raise ValueError('official PDF cannot be text-extracted reliably')
 return cp.stdout.decode('utf-8',errors='strict')

def validate_doc(text:str):
 if not isinstance(text,str):raise ValueError('calendar PDF text missing')
 clean=re.sub(r'\s+','',text).replace('（','(').replace('）',')')
 identity=(str(ROC_YEAR)+'年' in clean and '櫃檯買賣' in clean and
           '開(休)市' in clean)
 if not identity:raise ValueError('not the 115-year official TPEx annual trading calendar')
 matches=set((int(a),int(b)) for a,b in re.findall(r'(\d{1,2})月(\d{1,2})日',clean))
 missing=set(REQUIRED_TOKENS)-matches
 if missing:raise ValueError('official PDF key calendar dates missing: '+str(sorted(missing)))
 if len(matches)<18:raise ValueError('annual calendar date coverage insufficient')
 return {'roc_year':ROC_YEAR,'calendar_year':YEAR,'date_tokens_found':len(matches),
         'minimum_identity_token_checks':len(REQUIRED_TOKENS)}

def download():
 req=urllib.request.Request(URL,headers={
  'User-Agent':'Mozilla/5.0 (compatible; MFDS-Educational-Source-Audit/3.0S)',
  'Accept':'application/pdf'})
 with urllib.request.urlopen(req,timeout=20) as response:
  if response.status!=200:raise ValueError('TPEx HTTP '+str(response.status))
  body=response.read(2_200_001)
 if len(body)>2_200_000:raise ValueError('TPEx calendar PDF exceeds safety size limit')
 return body

def manifest_path(data,sha):
 return data/'tpex_calendar_sources'/('year_2026_'+sha+'.pdf')

def run(data_dir=DATA, now=None, fetch=None, extractor=None):
 data_dir=Path(data_dir)
 now=now or dt.datetime.now(dt.timezone.utc)
 if now.tzinfo is None:raise ValueError('source collection time must have UTC offset')
 text_extract=extractor or extract_pdf
 archive_root=data_dir/'tpex_calendar_sources'
 archive_root.mkdir(parents=True,exist_ok=True)
 seen=[]
 for source in sorted(archive_root.glob('year_2026_*.pdf')):
  try:
   binary=source.read_bytes()
   if source.name!='year_2026_'+sha256(binary)+'.pdf':raise ValueError('archived SHA mismatch')
   info=validate_doc(text_extract(binary))
   seen.append((source,info))
  except (OSError,ValueError,UnicodeError,subprocess.TimeoutExpired):
   raise ValueError('existing TPEx original archive failed validation: '+source.name)
 note=None
 new_saved=False
 try:
  binary=(fetch or download)()
  if not isinstance(binary,bytes):raise ValueError('source download must be raw bytes')
  info=validate_doc(text_extract(binary))
  digest=sha256(binary)
  source=manifest_path(data_dir,digest)
  if source.exists():
   if source.read_bytes()!=binary:raise ValueError('same-named source was overwritten')
  else:
   source.write_bytes(binary)
   new_saved=True
  # Existing first-seen times are separately stored in immutable manifest for
  # each sha. Never invent a capture date from the published annual date.
  seen=[x for x in seen if x[0]!=source]+[(source,info)]
 except (OSError,ValueError,UnicodeError,subprocess.TimeoutExpired) as e:
  note=type(e).__name__+': '+str(e)[:220]
 # If older validated original is already present, we can reuse its bytes.
 if seen:
  source,info=seen[-1]
  digest=sha256(source.read_bytes())
  status='archived_official_document_tokens_verified'
  archived=True
  ref=source.relative_to(data_dir).as_posix()
 else:
  status='official_original_unavailable_pending'
  digest=None
  info=None
  archived=False
  ref=None
 manifest={
   'version':VERSION,'status':status,
   'generated_at_utc':iso_utc(now),
   'market':'上櫃','year':YEAR,'roc_year':ROC_YEAR,
   'official_announcement_url':ANNOUNCEMENT,'official_pdf_url':URL,
   'official_raw_pdf_archived':archived,
   'raw_original_sha256':digest,'raw_source_file':ref,
   'document_token_validation':info,
   'official_document_download_error':note,
   'annual_market_closure_dates_independently_verified':False,
   'tpex_market_trading_sessions_independently_verified':False,
   '2026_10_23_extraordinary_closure_official_original_verified':False,
   'official_first_publication_timestamp_verified':False,
   'twse_calendar_substitution_permitted':False,
   'certified_backtest_eligible':False,
   'explanation':'只核對原始PDF身分、原始位元SHA256及年曆日期字詞；首次取得並非首次官方公布。PDF內同時有最後交易日、恢復交易日、休市日，不得僅憑日期出現就歸類為休市。上櫃與上市不能混用未驗證的行事曆，也尚未封存2026-10-23臨時停市官方原公告。'
 }
 data_dir.mkdir(parents=True,exist_ok=True)
 (data_dir/'tpex_calendar_evidence_30s.json').write_text(
    json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('3.0S TPEx annual official source: '+status+'; closure-date certification still OFF')
 return manifest

if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--data-dir',type=Path,default=DATA)
 opts=p.parse_args()
 run(opts.data_dir)
