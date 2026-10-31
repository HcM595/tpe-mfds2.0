#!/usr/bin/env python3
"""3.0W: a byte-exact public Pages release receipt for a stock research site.

Before publication: verify all material provenance and output files then record
their relative paths, lengths, SHA256 and conservative certification flags.
After publication: fetch the actual public bytes and compare with the receipt,
including the original TWSE/TPEx official PDFs. A GitHub Actions green job is
not proof that GitHub Pages served the same data; this makes them testable.

Never claim to prove the PDF's first official release time, a historical PIT
trading eligibility, matured investment returns, or a prediction win rate.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import time
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
DATA=SITE/'data'
LIVE='https://hcm595.github.io/tpe-mfds2.0/'
VERSION='3.0W'
RELEASE='3.0W'
MANIFEST='data/release_receipt_30w.json'
SOURCES=[
 'index.html','editorial_30k.css',
 'data/historical_evidence_meta_30q.json',
 'data/historical_evidence_30q.csv',
 'data/archive_coverage_meta_30r.json',
 'data/archive_day_coverage_30r.csv',
 'data/stock_candidate_coverage_30r.csv',
 'data/signal_archive_index.json',
 'data/official_session_calendar.json',
 'data/market_session_exceptions.csv',
 'data/tpex_calendar_evidence_30s.json',
 'data/official_closure_notice_evidence_30u.json',
 'data/official_source_readiness_30v.json',
]
MAX_FILE_BYTES=20_000_000

def sha(data):return hashlib.sha256(data).hexdigest()

def clean_rel(name):
 if not isinstance(name,str) or not name or '\\' in name or '?' in name or '#' in name:
  raise ValueError('unsafe release file path')
 p=PurePosixPath(name)
 if (p.is_absolute() or '..' in p.parts or '.' in p.parts or
     p.as_posix()!=name or p.parts[0] not in ('data','index.html','editorial_30k.css')):
  raise ValueError('unsafe or unexpected release file path')
 return name

def bytes_from_site(site,rel):
 clean_rel(rel)
 site=Path(site).resolve()
 path=(site/rel).resolve()
 if not path.is_relative_to(site) or not path.is_file():
  raise ValueError('missing or escaped release file: '+rel)
 b=path.read_bytes()
 if not b or len(b)>MAX_FILE_BYTES:
  raise ValueError('release source size missing or exceeds limit: '+rel)
 return b

def metadata(raw,kind):
 try: m=json.loads(raw.decode('utf-8-sig'))
 except (ValueError,UnicodeError) as e:raise ValueError(kind+' invalid JSON') from e
 if not isinstance(m,dict):raise ValueError(kind+' expected JSON object')
 return m

def source_paths(site):
 tpex=metadata(bytes_from_site(site,'data/tpex_calendar_evidence_30s.json'),'TPEx original')
 twse=metadata(bytes_from_site(site,'data/official_closure_notice_evidence_30u.json'),'TWSE original')
 tp_state=tpex.get('status')
 tw=twse.get('sources',{}).get('TWSE',{})
 paths=list(SOURCES)
 if tp_state=='archived_official_document_tokens_verified':
  src=tpex.get('raw_source_file')
  check='data/tpex_calendar_sources/year_2026_'+str(tpex.get('raw_original_sha256'))+'.pdf'
  if src!='tpex_calendar_sources/year_2026_'+str(tpex.get('raw_original_sha256'))+'.pdf':
   raise ValueError('TPEx verified original has inconsistent path/digest')
  paths.append('data/'+src)
 elif tp_state!='official_original_unavailable_pending':
  raise ValueError('TPEx status not recognized')
 if tw.get('status')=='verified_full_original_pdf':
  src=tw.get('source_file')
  if src!='official_closure_originals_30u/twse_20261023_'+str(tw.get('source_sha256'))+'.pdf':
   raise ValueError('TWSE verified original has inconsistent path/digest')
  paths.append('data/'+src)
 elif tw.get('status')!='official_original_pending':
  raise ValueError('TWSE status not recognized')
 return paths

def evaluate(site):
 """Check offline repository sources before writing receipt. No network."""
 import sys
 sys.path.insert(0,str(ROOT/'scripts'))
 import check_live_coverage_30r as old
 import audit_official_source_readiness_30v as audit
 store={k:bytes_from_site(site,v) for k,v in old.SOURCE_PATHS.items()}
 old.evaluate(store)
 srcmeta=metadata(bytes_from_site(site,'data/official_source_readiness_30v.json'),'3.0V')
 s30=metadata(bytes_from_site(site,'data/tpex_calendar_evidence_30s.json'),'3.0S')
 u30=metadata(bytes_from_site(site,'data/official_closure_notice_evidence_30u.json'),'3.0U')
 tpex=audit.verify_tpex(Path(site)/'data',s30)
 twse=audit.verify_twse(Path(site)/'data',u30)
 if srcmeta.get('version')!='3.0V' or srcmeta.get('pdf_extractor_present') is not True:
  raise ValueError('3.0V official source readiness is not verified')
 if srcmeta.get('source_manifest_sha256')!={'tpex_30s':sha(bytes_from_site(site,'data/tpex_calendar_evidence_30s.json')),
            'twse_30u':sha(bytes_from_site(site,'data/official_closure_notice_evidence_30u.json'))}:
  raise ValueError('official 3.0V attestations do not match the original source manifests')
 checks=[
  (srcmeta.get('markets',{}).get('TWSE_listed_cash_closure_2026_10_23',{}).get('status')==twse['status'],
   'TWSE proof status mismatch'),
  (srcmeta.get('markets',{}).get('TPEX_otc_annual_calendar_2026',{}).get('status')==tpex['status'],
   'TPEx annual proof status mismatch'),
  (srcmeta.get('markets',{}).get('TPEX_otc_full_closure_notice_2026_10_23',{}).get('status')=='pending_independent_full_original',
   'TPEx single-event full announcement not independently verified'),
  (srcmeta.get('certified_trade_outcomes')==0 and srcmeta.get('trade_model_enabled') is False and
   srcmeta.get('certified_win_rate') is None,'unverified performance was enabled'),
  (srcmeta.get('official_closure_proven_for_both_markets') is False,'two cash-market originals not both proven'),
  (srcmeta.get('official_first_publication_timestamp_verified') is False,
   'official first-published timestamp not independently established'),
 ]
 for valid,msg in checks:
  if not valid:raise ValueError(msg)
 html=bytes_from_site(site,'index.html').decode('utf-8-sig')
 if '<title>TPE-MFDS '+RELEASE+'｜台股整合研究中心</title>' not in html or \
     'release_receipt_30w.json' not in html or '3.0W｜' not in html:
  raise ValueError('new release page/title is not deployed to local source')
 return {'twse':twse,'tpex':tpex,'readiness':srcmeta}

def build(site=SITE,now=None):
 site=Path(site)
 now=now or dt.datetime.now(dt.timezone.utc)
 if now.tzinfo is None:raise ValueError('receipt clock must be timezone aware')
 proven=evaluate(site)
 paths=source_paths(site)
 files=[]
 for name in sorted(set(paths)):
  b=bytes_from_site(site,name)
  files.append({'path':name,'sha256':sha(b),'bytes':len(b)})
 report={
  'version':VERSION,'status':'source_bytes_attested_not_trade_certified',
  'issued_at_utc':now.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z'),
  'site_release':RELEASE,'source_files':files,'source_file_count':len(files),
  'official_source_status':{
   'TWSE_2026_10_23':proven['twse']['status'],
   'TPEX_annual_2026':proven['tpex']['status'],
   'TPEX_2026_10_23_full_notice':'pending_independent_full_original'},
  'official_first_publication_timestamp_verified':False,
  'cash_market_closure_both_independently_verified':False,
  'trade_model_enabled':False,'certified_trade_samples':0,
  'certified_win_rate':None,
  'notes':['對照此收據可檢驗部署位元完整性，但不是GitHub Pages已上線的自我認證。',
   '不代表每檔股票歷史數據完整，也不構成官方首次公布時分的驗證。',
   '上市事件原文與上櫃年度年曆已分別核對；上櫃10/23完整事件仍待獨立原公告。']
 }
 out=site/MANIFEST
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('3.0W release receipt created: '+str(len(files))+' sources, trade outcomes locked at 0')
 return report

def validate(site,report=None):
 site=Path(site)
 doc=report or metadata(bytes_from_site(site,MANIFEST),'3.0W release receipt')
 if doc.get('version')!=VERSION or doc.get('status')!='source_bytes_attested_not_trade_certified' or \
    doc.get('site_release')!=RELEASE:
  raise ValueError('incorrect release receipt version/status')
 if doc.get('certified_trade_samples')!=0 or doc.get('certified_win_rate') is not None or \
    doc.get('trade_model_enabled') is not False or \
    doc.get('cash_market_closure_both_independently_verified') is not False or \
    doc.get('official_first_publication_timestamp_verified') is not False:
  raise ValueError('release receipt claims unverified investment performance')
 listed=doc.get('source_files')
 if not isinstance(listed,list) or len(listed)!=doc.get('source_file_count'):
  raise ValueError('receipt file count invalid')
 names=[r.get('path') for r in listed]
 if len(names)!=len(set(names)) or sorted(names)!=names:
  raise ValueError('receipt source rows duplicate or not deterministically ordered')
 if set(names)!=set(source_paths(site)):
  raise ValueError('release receipt missing or added critical source files')
 for row in listed:
  b=bytes_from_site(site,row['path'])
  if sha(b)!=row['sha256'] or len(b)!=row['bytes']:
   raise ValueError('release receipt byte mismatch: '+row['path'])
 evaluate(site)
 return doc

def get_live(base,rel,limit=MAX_FILE_BYTES):
 clean_rel(rel)
 req=Request(urljoin(base.rstrip('/')+'/',rel),headers={
  'User-Agent':'TPE-MFDS-public-release-integrity/3.0W',
  'Cache-Control':'no-cache','Pragma':'no-cache'})
 with urlopen(req,timeout=22) as res:
  if res.status!=200:raise ValueError('public file HTTP status not 200: '+rel)
  b=res.read(limit+1)
 if not b or len(b)>limit:raise ValueError('public file empty or exceeded size cap: '+rel)
 return b

def validate_live(base=LIVE,expected=None,fetch=None):
 """Verify public bytes and optionally strict exact parity with GitHub main."""
 get=fetch or (lambda rel:get_live(base,rel))
 raw=get(MANIFEST)
 doc=metadata(raw,'public release receipt')
 if doc.get('version')!=VERSION or doc.get('site_release')!=RELEASE or \
    doc.get('status')!='source_bytes_attested_not_trade_certified':
  raise ValueError('public site has stale or invalid 3.0W release')
 if expected is not None:
  if raw!=Path(expected).read_bytes():
   raise ValueError('public release receipt differs from current GitHub published receipt')
 files=doc.get('source_files')
 if not isinstance(files,list) or len(files)!=doc.get('source_file_count'):
  raise ValueError('public receipt lacks declared source files')
 if sorted(f['path'] for f in files)!=[f['path'] for f in files] or \
    len({f['path'] for f in files})!=len(files):
  raise ValueError('public receipt has duplicate or disordered source rows')
 if doc.get('trade_model_enabled') is not False or doc.get('certified_trade_samples')!=0 or \
    doc.get('certified_win_rate') is not None or \
    doc.get('cash_market_closure_both_independently_verified') is not False or \
    doc.get('official_first_publication_timestamp_verified') is not False:
  raise ValueError('public release falsely certifies trades or both cash markets')
 for item in files:
  name=clean_rel(item['path'])
  b=get(name)
  if sha(b)!=item['sha256'] or len(b)!=item['bytes']:
   raise ValueError('public source byte mismatch: '+name)
  if name=='index.html':
   if ('<title>TPE-MFDS '+RELEASE+'｜台股整合研究中心</title>').encode() not in b:
    raise ValueError('public site title not matching release version')
 if not {'data/tpex_calendar_evidence_30s.json','data/official_closure_notice_evidence_30u.json',
          'data/official_source_readiness_30v.json','data/archive_coverage_meta_30r.json'}.issubset(
              {f['path'] for f in files}):
  raise ValueError('public original-source chain incomplete')
 return {'status':'pass','public_files_verified':len(files),'release':doc['site_release'],
  'published_issue_utc':doc['issued_at_utc'],'trade_model_enabled':False,
  'certified_trade_samples':0,'certified_win_rate':None}

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--site-dir',type=Path,default=SITE)
 p.add_argument('--mode',choices=('build','verify','live'),default='build')
 p.add_argument('--base-url',default=LIVE)
 p.add_argument('--attempts',type=int,default=5)
 p.add_argument('--report-file',type=Path,default=Path('live_source_receipt_30w.json'))
 args=p.parse_args()
 if args.mode=='build':
  build(args.site_dir)
  validate(args.site_dir)
 elif args.mode=='verify':
  validate(args.site_dir)
 else:
  if not 1<=args.attempts<=8:raise ValueError('attempts must be 1-8')
  err=None
  for n in range(args.attempts):
   try:
    result=validate_live(args.base_url,expected=args.site_dir/MANIFEST)
    args.report_file.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('3.0W PUBLIC RELEASE VERIFIED '+json.dumps(result,ensure_ascii=False))
    return
   except (OSError,ValueError,TimeoutError) as e:
    err=str(e)
    print(f'3.0W public validation attempt {n+1}/{args.attempts}: {err}')
    if n<args.attempts-1:time.sleep(12)
  args.report_file.write_text(json.dumps({'status':'fail','reason':err},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  raise SystemExit('3.0W public release did not pass exact source verification: '+str(err))
if __name__=='__main__':main()
