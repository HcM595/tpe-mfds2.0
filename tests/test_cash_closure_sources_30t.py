#!/usr/bin/env python3
"""3.0T regression: source origin, strict market identity and fail-closed notice gate."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import archive_cash_closure_sources_30t as A

TWSE_PAGE=('<html lang="zh"><head><title>臺灣證券交易所 新聞公告</title></head><body>'
'<h1>臺灣證券交易所</h1><p>2026年10月22日 新聞列表</p>'
'<a>臺灣證券交易所集中交易市場115年10月23日休市一天</a>'
'<p>新聞列表 日期、標題、公告內容與官方網頁資料查詢</p></body></html>').encode()
TPEX_INDEX=('<!doctype html><html><head><title>證券櫃檯買賣中心</title></head>'
'<body><h1>櫃買中心市場公告</h1>'
'<p>上櫃公告查詢：請輸入發文日期、文件類別、公告類別與主旨</p>'
'<div>公開公告資料每日上午查詢，並非完整的某日休市原始公告。</div>'
'</body></html>').encode()
FUTURES=('<html><body>臺灣期貨交易所 115年10月23日休市一天 '
         '期貨市場之一般及盤後交易停止，相關期貨結算業務暫停。</body></html>').encode()

class AuditTests(unittest.TestCase):
 def test_official_origin_and_listing_disambiguation(self):
  self.assertTrue(A.verify_host('TWSE',A.URLS['TWSE']))
  self.assertTrue(A.verify_host('TPEX',A.URLS['TPEX']))
  for url in ('http://investoredu.twse.com.tw/pages/TWSE_HotNews.aspx',
              'https://evil.example/twse/notice','https://investoredu.twse.com.tw.evil.example/'):
   with self.assertRaisesRegex(ValueError,'non-official'):A.verify_host('TWSE',url)
  with self.assertRaisesRegex(ValueError,'non-official'):
   A.verify_host('TPEX',A.URLS['TWSE'])
  info=A.analyze('TWSE',TWSE_PAGE)
  self.assertTrue(info['dated_notice_listing_mention'])
  self.assertFalse(info['full_first_party_closure_notice_verified'])
  info=A.analyze('TPEX',TPEX_INDEX)
  self.assertFalse(info['dated_notice_listing_mention'])
  self.assertFalse(info['full_first_party_closure_notice_verified'])
  with self.assertRaisesRegex(ValueError,'not HTML'):
   A.analyze('TWSE',b'%PDF-1.6'+b'x'*200)
  with self.assertRaisesRegex(ValueError,'does not have sufficient'):
   A.analyze('TWSE',b'<html>ok</html>')
  with self.assertRaisesRegex(ValueError,'cannot be decoded'):
   A.analyze('TWSE',b'<html>'+b'\xff'*500+b'</html>')

 def test_dated_futures_announcement_never_recognized_as_cash_market(self):
  self.assertFalse(A.analyze('TWSE',FUTURES)['dated_notice_listing_mention'])
  self.assertFalse(A.analyze('TPEX',FUTURES)['dated_notice_listing_mention'])

 def test_independent_original_bytes_first_seen_and_model_disabled(self):
  at=dt.datetime(2026,10,29,5,0,tzinfo=dt.timezone.utc)
  def source(exchange):
   return (TWSE_PAGE if exchange=='TWSE' else TPEX_INDEX),A.URLS[exchange]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   result=A.run(root,now=at,fetch=source)
   self.assertEqual(result['sources']['TWSE']['status'],'dated_listing_mention_not_original')
   self.assertEqual(result['sources']['TPEX']['status'],'official_index_only_no_event')
   self.assertFalse(result['official_closure_date_certified_for_both_markets'])
   self.assertFalse(result['trade_performance_enabled'])
   self.assertEqual(result['verified_trade_samples'],0)
   self.assertIsNone(result['certified_win_rate'])
   for market in A.URLS:
    row=result['sources'][market]
    raw=(root/row['source_file']).read_bytes()
    self.assertEqual(A.sha(raw),row['source_sha256'])
    self.assertFalse(row['cash_market_session_closed_certified'])
   result2=A.run(root,now=at,fetch=lambda _:(_ for _ in ()).throw(OSError('403')))
   self.assertEqual(result2['sources']['TWSE']['status'],'dated_listing_mention_not_original')
   self.assertIsNotNone(result2['sources']['TWSE']['last_fetch_error'])
   self.assertFalse(result2['independent_cash_market_originals_verified'])
   # If previously archived raw bytes are modified in place, stop publication.
   p=root/result2['sources']['TWSE']['source_file']
   p.write_bytes(p.read_bytes()+b'INJECT')
   with self.assertRaisesRegex(ValueError,'tampered immutable'):
    A.run(root,now=at,fetch=source)

 def test_no_source_both_fail_pending_and_redirect_rejection(self):
  at=dt.datetime(2026,10,29,5,0,tzinfo=dt.timezone.utc)
  with tempfile.TemporaryDirectory() as tmp:
   def failed(exchange):raise OSError(exchange+' official website unavailable')
   data=A.run(tmp,now=at,fetch=failed)
   self.assertEqual({r['status'] for r in data['sources'].values()},
        {'official_listing_unavailable_pending'})
   self.assertFalse(data['independent_cash_market_originals_verified'])
   self.assertFalse(data['official_closure_date_certified_for_both_markets'])
  with tempfile.TemporaryDirectory() as tmp:
   data=A.run(tmp,now=at,fetch=lambda x:(TWSE_PAGE,'https://evil.example/'))
   self.assertTrue(all(x['status']=='official_listing_unavailable_pending'
                       for x in data['sources'].values()))

if __name__=='__main__':unittest.main()
