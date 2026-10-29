#!/usr/bin/env python3
"""3.0V end-to-end immutable original-PDF readiness gate, no external requests."""
import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))
import archive_tpex_calendar_30s as TP
import archive_official_closure_30u as TW
import audit_official_source_readiness_30v as V
from test_tpex_calendar_30s import FIXTURE as TPEX_DOC
from test_official_closure_30u import DOC as TWSE_DOC, PDF as TWSE_PDF

TPEX_PDF=b'%PDF-1.7\n'+b'RAW TPEx official fixture bytes\n'*70
UTC=dt.datetime(2026,10,29,5,0,tzinfo=dt.timezone.utc)

class SourceReadiness(unittest.TestCase):
 def prepare(self,dir,tpex_present=False,twse_present=False):
  TP.run(dir,now=UTC,
   fetch=(lambda:TPEX_PDF) if tpex_present else
     (lambda: (_ for _ in ()).throw(OSError('HTTP Error 403: Forbidden'))),
   extractor=lambda b:TPEX_DOC)
  TW.run(dir,now=UTC,
   fetch=(lambda:(TWSE_PDF,TW.PDF_URL)) if twse_present else
     (lambda: (_ for _ in ()).throw(OSError('source unavailable'))),
   extractor=lambda b:TWSE_DOC)
 def check(self,dir):
  return V.run(dir,now=UTC,tpex_extractor=lambda b:TPEX_DOC,
               twse_extractor=lambda b:TWSE_DOC)

 def test_real_manifests_pending_stays_pending(self):
  result=V.run(ROOT/'site'/'data',now=UTC)
  self.assertEqual(result['version'],'3.0V')
  self.assertTrue(result['pdf_extractor_present'])
  self.assertEqual(result['certified_trade_outcomes'],0)
  self.assertFalse(result['official_closure_proven_for_both_markets'])
  self.assertFalse(result['trade_model_enabled'])
  self.assertIsNone(result['certified_win_rate'])

 def test_extractor_missing_requires_release_failure(self):
  with tempfile.TemporaryDirectory() as path:
   self.prepare(path)
   old=V.shutil.which
   try:
    V.shutil.which=lambda name:None
    with self.assertRaisesRegex(ValueError,'pdftotext missing'):
     self.check(path)
   finally:V.shutil.which=old

 def test_missing_sources_are_not_fabricated(self):
  with tempfile.TemporaryDirectory() as path:
   self.prepare(path)
   got=self.check(path)
   self.assertEqual(got['markets']['TPEX_otc_annual_calendar_2026']['status'],'pending')
   self.assertEqual(got['markets']['TWSE_listed_cash_closure_2026_10_23']['status'],'pending')
   self.assertEqual(got['markets']['TPEX_otc_annual_calendar_2026']['reason'],'source_access_denied')
   self.assertEqual(got['markets']['TPEX_otc_full_closure_notice_2026_10_23']['status'],
       'pending_independent_full_original')
   self.assertEqual(got['certified_trade_outcomes'],0)

 def test_annual_document_and_twse_event_are_two_different_proofs(self):
  with tempfile.TemporaryDirectory() as path:
   self.prepare(path,tpex_present=True,twse_present=True)
   got=self.check(path)
   self.assertEqual(got['markets']['TPEX_otc_annual_calendar_2026']['status'],
                    'verified_original_annual_document')
   self.assertEqual(got['markets']['TWSE_listed_cash_closure_2026_10_23']['status'],
                    'verified_original_market_event')
   self.assertFalse(got['annual_tpex_session_classification_verified'])
   self.assertFalse(got['official_closure_proven_for_both_markets'])
   self.assertFalse(got['trade_model_enabled'])
   self.assertIsNone(got['certified_win_rate'])
   self.assertTrue(Path(path,'official_source_readiness_30v.json').is_file())

 def test_tamper_raw_pdf_or_false_flags_rejected(self):
  with tempfile.TemporaryDirectory() as path:
   self.prepare(path,tpex_present=True,twse_present=True)
   data=Path(path)
   m=V.read(data/'tpex_calendar_evidence_30s.json')
   raw=data/m['raw_source_file']
   raw.write_bytes(raw.read_bytes()+b'SNEAKY TAMPERING')
   with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
    self.check(path)
  with tempfile.TemporaryDirectory() as path:
   self.prepare(path,tpex_present=True,twse_present=True)
   data=Path(path)
   m=V.read(data/'official_closure_notice_evidence_30u.json')
   m['both_cash_markets_official_originals_verified']=True
   (data/'official_closure_notice_evidence_30u.json').write_text(json.dumps(m),encoding='utf8')
   with self.assertRaisesRegex(ValueError,'cannot certify other market'):
    self.check(path)
  with tempfile.TemporaryDirectory() as path:
   self.prepare(path)
   data=Path(path)
   m=V.read(data/'tpex_calendar_evidence_30s.json')
   m['official_raw_pdf_archived']=True
   (data/'tpex_calendar_evidence_30s.json').write_text(json.dumps(m),encoding='utf8')
   with self.assertRaisesRegex(ValueError,'pending TPEx annual PDF'):
    self.check(path)

 def test_categorizes_recoverable_errors(self):
  self.assertEqual(V.error_kind('ValueError: pdftotext PDF text extractor is not installed'),
                   'pdf_extractor_missing')
  self.assertEqual(V.error_kind('HTTP Error 403: Forbidden'),'source_access_denied')
  self.assertEqual(V.error_kind('URLError timeout'),'source_network_unavailable')
  self.assertEqual(V.error_kind('PDF identity mismatch'),'source_pdf_content_not_verified')

if __name__=='__main__':unittest.main()
