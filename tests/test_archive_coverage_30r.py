#!/usr/bin/env python3
"""3.0R: real 3.0Q evidence, scheduled holiday and closure leads, fail-closed tests."""
from __future__ import annotations
import csv
import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'scripts'))
import audit_archive_coverage_30r as M

class CoverageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=BASE/'site'/'data'

 def test_real_archive_evidence_consistency(self):
  x=M.verify(self.data)
  self.assertEqual(len(x['rows']),x['meta']['stock_session_observations'])
  self.assertEqual(len(x['refs']),x['meta']['unique_first_captured_price_sessions'])
  self.assertEqual(sum(x['by_day'].values()),len(x['rows']))
  self.assertTrue(all(s in ('true','false') for r in x['rows'] for s in
         (r['flow_5d_observation_usable'],r['holder_4w_observation_usable'])))
  self.assertGreater(len(x['by_stock']),20)
  self.assertTrue(all(r['eligible_for_historical_trade']=='false' for r in x['rows']))
  self.assertFalse(x['meta']['strict_validation']['model_enabled'])
  self.assertEqual(x['meta']['strict_validation']['verified_trade_samples'],0)

 def test_calendar_and_exceptions_conservative(self):
  x=M.verify(self.data)
  cal=M.get_json(self.data/'official_session_calendar.json')
  with (self.data/'market_session_exceptions.csv').open(encoding='utf-8-sig',newline='') as f:
   leads=list(csv.DictReader(f))
  entries=M.coverage(x,cal,leads)
  self.assertTrue(entries)
  observed={(x['date'],x['market']):x for x in entries}
  for day in x['refs']:
   for market in M.MARKETS:
    self.assertEqual(observed[(day,market)]['status'],'verified_first_capture')
  self.assertNotIn(('2026-10-26','上市'),observed,'officially closed date should not be considered missing')
  if '2026-10-23' not in x['refs']:
   for market in M.MARKETS:
    self.assertEqual(observed[('2026-10-23',market)]['status'],
                     'extraordinary_closure_requires_official_source')
    self.assertNotEqual(observed[('2026-10-23',market)]['status'],
                        'unarchived_possible_session')
  no_ex=M.coverage(x,cal,[])
  if '2026-10-23' not in x['refs']:
   self.assertIn('unarchived_possible_session',[x['status'] for x in no_ex])
  self.assertTrue(all(x['status'] in (
   'verified_first_capture','extraordinary_closure_requires_official_source',
   'unarchived_possible_session') for x in entries))

 def test_snapshot_and_manifest_tampering_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   d=Path(folder)
   for name in ['historical_evidence_meta_30q.json',
                'historical_evidence_30q.csv','signal_archive_index.json']:
    shutil.copy(self.data/name,d/name)
   self.assertTrue(M.verify(d))
   p=d/'historical_evidence_30q.csv'
   original=p.read_bytes()
   p.write_bytes(original+b'\n')
   with self.assertRaisesRegex(ValueError,'row count|duplicate|invalid'):
    M.verify(d)
   p.write_bytes(original)
   obj=M.get_json(d/'historical_evidence_meta_30q.json')
   obj['strict_validation']['model_enabled']=True
   (d/'historical_evidence_meta_30q.json').write_text(json.dumps(obj),encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'unverified performance'):
    M.verify(d)
   shutil.copy(self.data/'historical_evidence_meta_30q.json',
               d/'historical_evidence_meta_30q.json')
   lines=original.decode('utf-8-sig').splitlines()
   rows=list(csv.DictReader(lines))
   rows[0]['first_snapshot_sha256']='0'*64
   import io
   out=io.StringIO(newline='')
   writer=csv.DictWriter(out,fieldnames=rows[0].keys())
   writer.writeheader();writer.writerows(rows)
   p.write_bytes(out.getvalue().encode('utf-8-sig'))
   with self.assertRaisesRegex(ValueError,'not bound'):
    M.verify(d)

 def test_extra_row_reject_and_per_stock_absence_not_data_gap(self):
  x=M.verify(self.data)
  stock=M.build_stock_coverage(x)
  self.assertEqual(len(stock),len({r['stock_id'] for r in x['rows']}))
  for r in stock:
   self.assertEqual(r['first_captured_candidate_days']+
                    r['other_archived_days_not_in_candidates'],len(x['refs']))
   self.assertFalse(r['first_publication_time_verified']=='true')
   self.assertEqual(r['verified_trade_samples'],0)
   self.assertIn('不等於行情缺漏',r['note'])
  # Same stock can disappear from the screened candidate set
  # without implying its quote itself was unavailable.

 def test_output_meta_compatibility_and_no_certified_metrics(self):
  with tempfile.TemporaryDirectory() as folder:
   d=Path(folder)
   for name in ['historical_evidence_meta_30q.json',
                'historical_evidence_30q.csv','signal_archive_index.json',
                'official_session_calendar.json','market_session_exceptions.csv']:
    shutil.copy(self.data/name,d/name)
   now=dt.datetime(2026,10,29,2,0,tzinfo=dt.timezone.utc)
   out=M.run(d,now)
   self.assertEqual(out['verified_price_days'],4)
   self.assertEqual(out['archived_stock_day_records'],297)
   self.assertFalse(out['trade_performance_enabled'])
   self.assertIsNone(out['certified_win_rate'])
   self.assertIn('source_csv_sha256',out)
   self.assertEqual(out['source_csv_sha256'],M.sha((d/'historical_evidence_30q.csv').read_bytes()))
   for f in out['outputs']:self.assertTrue((d/f).is_file())
   meta=(d/'archive_coverage_meta_30r.json').read_bytes()
   day=(d/'archive_day_coverage_30r.csv').read_bytes()
   stocks=(d/'stock_candidate_coverage_30r.csv').read_bytes()
   M.run(d,now)
   self.assertEqual(meta,(d/'archive_coverage_meta_30r.json').read_bytes())
   self.assertEqual(day,(d/'archive_day_coverage_30r.csv').read_bytes())
   self.assertEqual(stocks,(d/'stock_candidate_coverage_30r.csv').read_bytes())

if __name__=='__main__':
 unittest.main()
