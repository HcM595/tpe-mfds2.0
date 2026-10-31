#!/usr/bin/env python3
"""3.0W: real local provenance and injected remote mixed-version failures."""
from __future__ import annotations
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import release_receipt_30w as R

class ReleaseReceiptTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.now=dt.datetime(2026,10,31,8,0,tzinfo=dt.timezone.utc)
  cls.report=R.build(R.SITE,now=cls.now)
  cls.files={R.MANIFEST:(R.SITE/R.MANIFEST).read_bytes()}
  for f in cls.report['source_files']:
   cls.files[f['path']]=(R.SITE/f['path']).read_bytes()

 def test_local_genuine_official_sources_and_perf_gate(self):
  x=R.validate(R.SITE)
  self.assertEqual(x['version'],'3.0W')
  self.assertGreaterEqual(len(x['source_files']),13)
  self.assertEqual(x['source_file_count'],len(x['source_files']))
  self.assertTrue(any(z['path'].endswith('.pdf') for z in x['source_files']))
  self.assertEqual(x['official_source_status']['TPEX_2026_10_23_full_notice'],
      'pending_independent_full_original')
  self.assertEqual(x['certified_trade_samples'],0)
  self.assertIsNone(x['certified_win_rate'])
  self.assertFalse(x['trade_model_enabled'])
  self.assertFalse(x['cash_market_closure_both_independently_verified'])

 def remote(self,files=None,expected=None):
  obj=files if files is not None else self.files
  return R.validate_live('https://example.invalid/',expected=expected,
    fetch=lambda name:obj[name])

 def test_public_validation_uses_exact_original_bytes(self):
  r=self.remote(expected=R.SITE/R.MANIFEST)
  self.assertEqual(r['status'],'pass')
  self.assertEqual(r['release'],'3.0W')
  self.assertEqual(r['public_files_verified'],len(self.report['source_files']))
  self.assertEqual(r['certified_trade_samples'],0)
  self.assertIsNone(r['certified_win_rate'])

 def test_stale_or_mixed_version_public_site_is_rejected(self):
  body=dict(self.files)
  body['index.html']=body['index.html'].replace(b'3.0W',b'3.0V')
  with self.assertRaisesRegex(ValueError,'byte mismatch'):
   self.remote(body)
  body=dict(self.files)
  key='data/official_source_readiness_30v.json'
  body[key]=body[key].replace(b'verified_source_readiness_performance_blocked',b'unknown')
  with self.assertRaisesRegex(ValueError,'byte mismatch'):
   self.remote(body)
  body=dict(self.files)
  pdf=next(p for p in body if p.endswith('.pdf'))
  body[pdf]=body[pdf]+b'TAMPER'
  with self.assertRaisesRegex(ValueError,'byte mismatch'):
   self.remote(body)
  body=dict(self.files)
  del body[pdf]
  with self.assertRaises(KeyError):
   self.remote(body)

 def test_snapshot_cannot_claim_model_or_both_markets_verified(self):
  m=copy.deepcopy(self.report)
  for key,val in [('trade_model_enabled',True),('certified_trade_samples',3),
                  ('certified_win_rate',.89),('cash_market_closure_both_independently_verified',True),
                  ('official_first_publication_timestamp_verified',True)]:
   doc=copy.deepcopy(m);doc[key]=val
   files=dict(self.files)
   files[R.MANIFEST]=(json.dumps(doc,ensure_ascii=False)+'\n').encode()
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,'falsely certifies'):
    self.remote(files)

 def test_missing_or_duplicate_receipt_entries_fails(self):
  m=copy.deepcopy(self.report);m['source_files'].pop()
  files=dict(self.files);files[R.MANIFEST]=(json.dumps(m)+'\n').encode()
  with self.assertRaisesRegex(ValueError,'lacks declared'):
   self.remote(files)
  m=copy.deepcopy(self.report);m['source_files'].append(m['source_files'][-1])
  m['source_file_count']=len(m['source_files'])
  files[R.MANIFEST]=(json.dumps(m)+'\n').encode()
  with self.assertRaisesRegex(ValueError,'duplicate'):
   self.remote(files)
  m=copy.deepcopy(self.report);m['source_files'][0]['path']='../../etc/passwd'
  files[R.MANIFEST]=(json.dumps(m)+'\n').encode()
  with self.assertRaisesRegex(ValueError,'unsafe'):
   self.remote(files)

 def test_local_archive_byte_tamper_rejected(self):
  # Isolate only the exact declared dependencies (no backfill or network).
  with tempfile.TemporaryDirectory() as scratch:
   root=Path(scratch)
   for k,v in self.files.items():
    dest=root/k;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(v)
   self.assertEqual(R.validate(root)['version'],'3.0W')
   p=root/'data'/'official_source_readiness_30v.json'
   p.write_bytes(p.read_bytes()+b'\n')
   with self.assertRaisesRegex(ValueError,'byte mismatch'):
    R.validate(root)

if __name__=='__main__':unittest.main()
