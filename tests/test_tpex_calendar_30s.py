#!/usr/bin/env python3
"""3.0S: require first-party TPEx source identity; never infer holidays from mere mentions."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import archive_tpex_calendar_30s as T

FIXTURE=("財團法人中華民國證券櫃檯買賣中心 中華民國115年"
 "有價證券櫃檯買賣市場開（休）市日期表 "+
 ' '.join(f'{m}月{d}日' for m,d in T.REQUIRED_TOKENS)+
 " 1月2日 2月10日 2月11日 2月15日 2月16日 2月17日 2月18日 2月19日 "
 "2月20日 2月23日 2月28日 4月4日 4月5日 10月10日 10月25日")

def fake_pdf():
 return b'%PDF-1.7\n'+b'fake original fixture'*100

class TPExAudit(unittest.TestCase):
 def test_official_url_and_identity(self):
  self.assertIn('tpex.org.tw',T.URL)
  valid=T.validate_doc(FIXTURE)
  self.assertEqual(valid['roc_year'],115)
  self.assertGreaterEqual(valid['date_tokens_found'],18)
  with self.assertRaisesRegex(ValueError,'not the'):
   T.validate_doc(FIXTURE.replace('櫃檯買賣','證券交易所'))
  with self.assertRaisesRegex(ValueError,'key calendar dates'):
   T.validate_doc(FIXTURE.replace('12月25日','12月26日'))
  with self.assertRaisesRegex(ValueError,'not the'):
   T.validate_doc(FIXTURE.replace('115年','114年'))

 def test_pending_when_download_unavailable_no_false_certification(self):
  with tempfile.TemporaryDirectory() as folder:
   def unavailable():
    raise OSError('HTTP 403 on original source')
   r=T.run(folder,now=dt.datetime(2026,10,29,tzinfo=dt.timezone.utc),fetch=unavailable,
       extractor=lambda raw:FIXTURE)
   self.assertEqual(r['status'],'official_original_unavailable_pending')
   self.assertFalse(r['official_raw_pdf_archived'])
   self.assertIsNone(r['raw_original_sha256'])
   self.assertFalse(r['annual_market_closure_dates_independently_verified'])
   self.assertFalse(r['2026_10_23_extraordinary_closure_official_original_verified'])
   self.assertFalse(r['certified_backtest_eligible'])

 def test_actual_downloaded_bytes_are_digest_bound_and_reusable(self):
  with tempfile.TemporaryDirectory() as folder:
   d=Path(folder)
   now=dt.datetime(2026,10,29,tzinfo=dt.timezone.utc)
   r=T.run(d,now=now,fetch=fake_pdf,extractor=lambda _:FIXTURE)
   self.assertTrue(r['official_raw_pdf_archived'])
   self.assertTrue(r['raw_original_sha256'])
   self.assertFalse(r['tpex_market_trading_sessions_independently_verified'])
   raw=d/r['raw_source_file']
   self.assertEqual(T.sha256(raw.read_bytes()),r['raw_original_sha256'])
   result=T.run(d,now=now,fetch=lambda: (_ for _ in ()).throw(OSError('403')),
                extractor=lambda _:FIXTURE)
   self.assertEqual(result['status'],'archived_official_document_tokens_verified')
   self.assertFalse(result['annual_market_closure_dates_independently_verified'])
   raw.write_bytes(b'MALICIOUS EDIT')
   with self.assertRaisesRegex(ValueError,'existing TPEx original archive'):
    T.run(d,now=now,fetch=fake_pdf,extractor=lambda _:FIXTURE)

 def test_existing_untrusted_pdf_not_silently_accepted(self):
  with tempfile.TemporaryDirectory() as folder:
   d=Path(folder)/'tpex_calendar_sources'
   d.mkdir(parents=True)
   (d/'year_2026_'+'0'*64+'.pdf').write_bytes(fake_pdf())
   with self.assertRaisesRegex(ValueError,'existing TPEx original archive'):
    T.run(Path(folder),fetch=lambda: (_ for _ in ()).throw(OSError('403')),
          extractor=lambda _:FIXTURE)
if __name__=='__main__':unittest.main()
