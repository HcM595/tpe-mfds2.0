#!/usr/bin/env python3
"""3.0T: independently archive first-party CASH-market closure source *leads*.

Only market-owned page bytes may be called original. A dated headline on an
official LISTING is not the original full closure announcement, and a futures
notice is not an equity or TPEx cash-market order. A website that cannot be
fetched/checked stays pending. This process NEVER marks the session as
officially proven closed or allows use in performance validation.

Existing raw snapshots are immutable, content-addressed, and re-verified
before reuse. 3.0R's archived-day audit is left unchanged until distinct
dated, full original notices can actually be verified for both cash markets.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site'/'data'
VERSION='3.0T'
DATE='2026-10-23'
URLS={
 'TWSE': 'https://investoredu.twse.com.tw/pages/TWSE_HotNews.aspx',
 'TPEX': 'https://www.tpex.org.tw/zh-tw/announce/market/announce.html',
}
ALLOWED={
 'TWSE':frozenset({'investoredu.twse.com.tw'}),
 'TPEX':frozenset({'www.tpex.org.tw'}),
}
ALIASES={
 'TWSE':('臺灣證券交易所','證交所','集中交易市場'),
 'TPEX':('櫃買中心','證券櫃檯買賣中心','櫃檯買賣'),
}
MAX_BYTES=950_000

def sha(raw):return hashlib.sha256(raw).hexdigest()
def utc(now):return now.astimezone(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
class Text(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.text=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style','svg'):self.skip+=1
 def handle_endtag(self,tag):
  if tag in ('script','style','svg'):self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip:self.text.append(data)

def text_content(raw):
 if not isinstance(raw,bytes) or not raw:raise ValueError('source raw HTML missing')
 if len(raw)>MAX_BYTES:raise ValueError('official source exceeds size limit')
 if not re.search(br'<html\b|<!doctype\s+html',raw[:4000],re.I):
  raise ValueError('downloaded source is not HTML')
 try:html=raw.decode('utf-8-sig','strict')
 except UnicodeError as e:raise ValueError('official source HTML cannot be decoded') from e
 parser=Text();parser.feed(html)
 return re.sub(r'\s+','', ''.join(parser.text)).replace('（','(').replace('）',')')

def verify_host(exchange, url):
 if exchange not in URLS:raise ValueError('unrecognized cash exchange')
 u=urllib.parse.urlsplit(url)
 if u.scheme!='https' or u.hostname not in ALLOWED[exchange] or u.username or u.password or u.port not in (None,443):
  raise ValueError('non-official or redirected hostname rejected')
 return True

def analyze(exchange,raw):
 clean=text_content(raw)
 if len(clean)<80:raise ValueError('official page does not have sufficient readable content')
 authority=any(x in clean for x in ALIASES[exchange])
 # Only describe proof from words actually on that particular page.
 dated=bool(re.search(r'115年10月23日|2026年10月23日|2026/10/23|2026-10-23|115/10/23',clean))
 closure=bool(re.search(r'休市(?:一天|一日|1天|1日)?|停止交易',clean))
 # This is a source LISTING / announcement search form, not the full dated notice.
 mention=authority and dated and closure
 return {'authority_tokens_present':authority,'date_token_present':dated,
    'closure_token_present':closure,
    'dated_notice_listing_mention':mention,
    'full_first_party_closure_notice_verified':False,
    'date_covered':DATE,
    'source_kind':'official_headline_listing' if exchange=='TWSE' else 'official_announcement_search_index'}

def download(exchange):
 url=URLS[exchange];verify_host(exchange,url)
 req=urllib.request.Request(url,headers={
  'User-Agent':'Mozilla/5.0 (compatible; MFDS-Official-Source-Verification/3.0T)',
  'Accept':'text/html','Cache-Control':'no-cache'})
 with urllib.request.urlopen(req,timeout=17) as response:
  if response.status!=200:raise ValueError('official source HTTP '+str(response.status))
  final=response.geturl()
  verify_host(exchange,final)
  kind=(response.headers.get('Content-Type') or '').lower()
  if kind and not ('text/html' in kind or 'application/xhtml+xml' in kind):
   raise ValueError('official source returned unexpected content type')
  raw=response.read(MAX_BYTES+1)
 if len(raw)>MAX_BYTES:raise ValueError('official source size cap exceeded')
 return raw,final

def raw_path(data_dir,exchange,digest):
 return data_dir/'cash_market_closure_sources_30t'/(exchange.lower()+'_'+digest+'.html')

def run(data_dir=DATA,now=None,fetch=None):
 data_dir=Path(data_dir)
 now=now or dt.datetime.now(dt.timezone.utc)
 if now.tzinfo is None:raise ValueError('collection time must contain timezone')
 archive_dir=data_dir/'cash_market_closure_sources_30t'
 archive_dir.mkdir(parents=True,exist_ok=True)
 records={}
 for exchange,url in URLS.items():
  cached=[]
  # Validate ALL prior content-addressed entries. A tampered existing snapshot
  # must never quietly be replaced or overlooked.
  for p in sorted(archive_dir.glob(exchange.lower()+'_*.html')):
   raw=p.read_bytes()
   if p!=raw_path(data_dir,exchange,sha(raw)):
    raise ValueError('tampered immutable official-source archive: '+p.name)
   evidence=analyze(exchange,raw)
   cached.append((p,evidence))
  error=None;fresh=None;final=url
  try:
   body,final=(fetch or download)(exchange)
   verify_host(exchange,final)
   evidence=analyze(exchange,body)
   digest=sha(body)
   p=raw_path(data_dir,exchange,digest)
   if p.exists() and p.read_bytes()!=body:raise ValueError('same digest filename has different content')
   if not p.exists():p.write_bytes(body)
   fresh=(p,evidence)
  except (OSError,UnicodeError,ValueError,TimeoutError) as e:
   error=type(e).__name__+': '+str(e)[:180]
  # Favor freshly verified original bytes. Re-using an immutable older listing
  # is permitted but does NOT prove an as-of publication timestamp.
  used=fresh or (cached[-1] if cached else None)
  if used:
   p,evidence=used
   digest=sha(p.read_bytes())
   status='dated_listing_mention_not_original' if evidence['dated_notice_listing_mention'] else 'official_index_only_no_event'
   file_ref=p.relative_to(data_dir).as_posix()
  else:
   status='official_listing_unavailable_pending'
   digest=None;file_ref=None
   evidence=None
  records[exchange]={
   'market':'上市' if exchange=='TWSE' else '上櫃',
   'official_source_url':url,
   'last_fetch_url':final,
   'status':status,'source_file':file_ref,'source_sha256':digest,
   'source_validation':evidence,'last_fetch_error':error,
   'source_bytes_verified':bool(used),
   'full_first_party_closure_notice_verified':False,
   'official_publication_timestamp_verified':False,
   'cash_market_session_closed_certified':False}
 result={
  'version':VERSION,'generated_at_utc':utc(now),
  'date':DATE,
  'status':'source_listing_research_pending_original_notices',
  'sources':records,
  'independent_cash_market_originals_verified':False,
  'official_closure_date_certified_for_both_markets':False,
  'trade_performance_enabled':False,
  'verified_trade_samples':0,'certified_win_rate':None,
  'why':'上市與上櫃須各自具備當日完整官方原始公告，不能只用官網新聞標題、行事曆、期交所公告或轉述。首度取得本站頁面不等於官網當時首次公開。'
 }
 data_dir.mkdir(parents=True,exist_ok=True)
 (data_dir/'cash_market_closure_evidence_30t.json').write_text(
   json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('3.0T: '+', '.join(k+'='+v['status'] for k,v in records.items())+
       '; closure/trading gate remains OFF')
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--data-dir',type=Path,default=DATA)
 args=p.parse_args()
 run(args.data_dir)
