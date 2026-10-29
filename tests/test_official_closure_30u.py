#!/usr/bin/env python3
"""3.0U original TWSE PDF provenance tests, no live internet in assertions."""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import archive_official_closure_30u as A

PDF=b'%PDF-1.7\n'+b'MOCK FIRST PARTY ORIGINAL PDF\n'*70
DOC='''臺灣證券交易所 新聞稿 中華民國115年10月22日 交易部
臺灣證券交易所集中交易市場115年10月23日休市一天
臺灣證券交易所表示，由於薔琵颱風來襲，臺北市政府宣布
全體公教機關停止上班，115年10月23日集中交易市場全日休市，
當日應屆交割款券順延辦理。'''

class OriginalRelease(unittest.TestCase):
 def test_original_document_requires_issuer_market_dates_and_closure(self):
  parsed=A.verify_original_text(DOC)
  self.assertEqual(parsed['effective_closed_date'],'2026-10-23')
  self.assertEqual(parsed['released_on_document'],'2026-10-22')
  self.assertEqual(parsed['market'],'上市現貨集中交易市場')
  self.assertFalse(parsed['official_first_publication_timestamp_verified'])
  for removed in ['臺灣證券交易所','集中交易市場','交易部','115年10月22日',
                  '115年10月23日','全日休市','交割']:
   sample=DOC.replace(removed,'',1)
   # The issuer, year and event-day have multiple appearances; delete all of them.
   sample=DOC.replace(removed,'')
   with self.assertRaisesRegex(ValueError,'.*'):
    A.verify_original_text(sample)
  with self.assertRaisesRegex(ValueError,'not a PDF'):
   A.validate_pdf_bytes(b'<html>not an original PDF</html>')
  with self.assertRaisesRegex(ValueError,'outside bounds'):
   A.validate_pdf_bytes(b'%PDF-1.6\nShort')

 def test_url_must_stay_on_official_pdf_host(self):
  self.assertTrue(A.verify_url(A.PDF_URL))
  for url in ['http://investoredu.twse.com.tw/FileSystem/FileUpload/c91c7dff-afb0-42cc-9949-9f072bece31d.pdf',
    'https://investoredu.twse.com.tw.evil.example/FileSystem/FileUpload/c91c7dff-afb0-42cc-9949-9f072bece31d.pdf',
    'https://cdn.example.com/c91c7dff-afb0-42cc-9949-9f072bece31d.pdf',
    'https://investoredu.twse.com.tw/Pages/TWSE_HotNews.aspx',
    'https://investoredu.twse.com.tw/FileSystem/FileUpload/c91c7dff-afb0-42cc-9949-9f072bece31d.pdf?next=evil']:
   with self.subTest(url=url),self.assertRaisesRegex(ValueError,'known first-party'):
    A.verify_url(url)

 def test_original_bytes_are_sha_bound_and_other_market_stays_blocked(self):
  with tempfile.TemporaryDirectory() as folder:
   d=Path(folder); now=dt.datetime(2026,10,29,5,0,tzinfo=dt.timezone.utc)
   r=A.run(d,now=now,fetch=lambda:(PDF,A.PDF_URL),extractor=lambda raw:DOC)
   self.assertEqual(r['sources']['TWSE']['status'],'verified_full_original_pdf')
   self.assertTrue(r['sources']['TWSE']['full_original_document_verified'])
   self.assertTrue(A.check_local(d,r,extractor=lambda raw:DOC))
   self.assertFalse(r['sources']['TPEX']['full_original_document_verified'])
   self.assertFalse(r['both_cash_markets_official_originals_verified'])
   self.assertFalse(r['trade_performance_enabled'])
   self.assertEqual(r['verified_trade_samples'],0)
   self.assertIsNone(r['certified_win_rate'])
   ref=r['sources']['TWSE']['source_file']
   self.assertEqual(A.digest((d/ref).read_bytes()),r['sources']['TWSE']['source_sha256'])
   # Reusing old verified bytes after transient failure is allowed.
   r2=A.run(d,now=now,fetch=lambda:(_ for _ in ()).throw(OSError('403')),
            extractor=lambda raw:DOC)
   self.assertTrue(r2['sources']['TWSE']['full_original_document_verified'])
   self.assertFalse(r2['both_cash_markets_official_originals_verified'])
   self.assertIsNotNone(r2['sources']['TWSE']['fetch_error'])
   saved=d/ref
   saved.write_bytes(saved.read_bytes()+b'TAMPER')
   with self.assertRaisesRegex(ValueError,'immutable historical TWSE PDF changed'):
    A.run(d,now=now,fetch=lambda:(PDF,A.PDF_URL),extractor=lambda raw:DOC)

 def test_no_download_and_forged_text_fail_closed(self):
  with tempfile.TemporaryDirectory() as folder:
   r=A.run(folder,fetch=lambda:(_ for _ in ()).throw(OSError('404')),
            extractor=lambda raw:DOC)
   self.assertEqual(r['sources']['TWSE']['status'],'official_original_pending')
   self.assertFalse(r['sources']['TWSE']['full_original_document_verified'])
   self.assertFalse(r['both_cash_markets_official_originals_verified'])
   self.assertFalse(A.check_local(folder,r,extractor=lambda raw:DOC))
  with tempfile.TemporaryDirectory() as folder:
   bad=A.run(folder,fetch=lambda:(PDF,A.PDF_URL),extractor=lambda raw:DOC.replace('全日休市','開市'))
   self.assertEqual(bad['sources']['TWSE']['status'],'official_original_pending')
   self.assertFalse(bad['sources']['TWSE']['full_original_document_verified'])
  with tempfile.TemporaryDirectory() as folder:
   bad=A.run(folder,fetch=lambda:(PDF,'https://example.com/official.pdf'),extractor=lambda raw:DOC)
   self.assertEqual(bad['sources']['TWSE']['status'],'official_original_pending')
   self.assertFalse(bad['sources']['TWSE']['full_original_document_verified'])

if __name__=='__main__':unittest.main()
