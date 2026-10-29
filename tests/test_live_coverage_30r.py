#!/usr/bin/env python3
"""3.0R deployed-file verifier: pass exact bytes, reject stale/corrupt public files."""
from __future__ import annotations
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import check_live_coverage_30r as M
import audit_archive_coverage_30r as C

class DeployTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=ROOT/'site'

 def sources(self):
  return {k:(self.base/p).read_bytes() for k,p in M.SOURCE_PATHS.items()}

 def test_public_source_contract_locally(self):
  report=M.evaluate(self.sources())
  self.assertEqual(report['status'],'pass')
  self.assertEqual(report['public_source_files_verified'],len(M.SOURCE_PATHS))
  self.assertIsNone(report['certified_win_rate'])
  self.assertFalse(report['trade_performance_enabled'])

 def test_modified_csv_and_modified_meta_fail(self):
  x=self.sources()
  x['csv30q']+=b'\n'
  with self.assertRaisesRegex(ValueError,'mismatches'):
   M.evaluate(x)
  x=self.sources()
  meta=json.loads(x['meta30r'].decode('utf-8'))
  meta['trade_performance_enabled']=True
  x['meta30r']=json.dumps(meta).encode('utf-8')
  with self.assertRaisesRegex(ValueError,'financial outcomes'):
   M.evaluate(x)
  x=self.sources()
  q=json.loads(x['meta30q'].decode('utf-8'))
  q['strict_validation']['model_enabled']=True
  x['meta30q']=json.dumps(q).encode('utf-8')
  with self.assertRaisesRegex(ValueError,'upstream model'):
   M.evaluate(x)

 def test_stale_html_or_missing_deployment_rejected(self):
  x=self.sources()
  x['html']=b'<html><title>3.0P</title></html>'
  with self.assertRaisesRegex(ValueError,'older version'):
   M.evaluate(x)
  x=self.sources()
  del x['day']
  with self.assertRaisesRegex(ValueError,'missing'):
   M.evaluate(x)

if __name__=='__main__':unittest.main()
