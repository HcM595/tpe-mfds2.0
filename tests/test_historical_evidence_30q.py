#!/usr/bin/env python3
"""3.0Q: verify genuine archival raw bytes and refuse historical false positives."""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_historical_evidence_30q as H

class HistoricalEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=ROOT/'site'/'data'
  cls.index=H.load_json((cls.data/'signal_archive_index.json').read_bytes())
  cls.first=H.first_entries(cls.index)

 def test_true_first_archives_dedup_and_raw_flows(self):
  self.assertGreaterEqual(len(self.first),2)
  self.assertLess(len(self.first),len(self.index['snapshots']))
  all_rows=[]
  for day,entry in self.first:
   self.assertEqual(day,entry['source_price_dates'][0])
   rows=H.recover_archive(self.data,day,entry)
   self.assertGreater(len(rows),0)
   self.assertEqual(len(rows),len({x['stock_id'] for x in rows}))
   self.assertTrue(all(x['first_snapshot_id']==entry['snapshot_id'] for x in rows))
   self.assertTrue(all(x['raw_input_verified']=='true' for x in rows))
   self.assertTrue(all(x['eligible_for_historical_trade']=='false' for x in rows))
   self.assertTrue(all(x['first_publication_time_verified']=='false' for x in rows))
   for r in rows:
    if r['flow_5d_observation_usable']=='false':
     self.assertEqual(r['foreign_5d_shares'],'')
     self.assertEqual(r['trust_5d_shares'],'')
    if r['holder_4w_observation_usable']=='false':
     self.assertEqual(r['large400_4w_pp'],'')
     self.assertEqual(r['large1000_4w_pp'],'')
   all_rows.extend(rows)
  self.assertEqual(len(all_rows),len({(r['stock_id'],r['price_session']) for r in all_rows}))
  self.assertTrue(any(x['flow_5d_observation_usable']=='true' for x in all_rows))
  self.assertTrue(any(x['holder_4w_observation_usable']=='true' for x in all_rows))
  self.assertTrue(any(x['technical_confirmed_count'] for x in all_rows if x['tech_observation_usable']=='true'))

 def test_tampered_manifest_gzip_and_path_fail_closed(self):
  day,entry=self.first[0]
  with tempfile.TemporaryDirectory() as scratch:
   temp=Path(scratch)
   original=self.data/entry['snapshot_path']
   destination=temp/entry['snapshot_path']
   destination.parent.mkdir(parents=True)
   shutil.copytree(original.parent,destination.parent,dirs_exist_ok=True)
   self.assertGreater(len(H.recover_archive(temp,day,entry)),0)
   manifest=destination.read_bytes()
   destination.write_bytes(manifest.replace(b'"version": "2.4A"',b'"version": "3.0Q"',1))
   with self.assertRaisesRegex(ValueError,'SHA256'):
    H.recover_archive(temp,day,entry)
   destination.write_bytes(manifest)
   raw=destination.parent/'inputs'/'chip_signals.csv.gz'
   payload=raw.read_bytes()
   raw.write_bytes(payload[:-12]+b'CORRUPTEDZIP')
   with self.assertRaisesRegex(ValueError,'SHA256|corrupt'):
    H.recover_archive(temp,day,entry)
   raw.write_bytes(payload)
   self.assertTrue(H.recover_archive(temp,day,entry))
   with self.assertRaisesRegex(ValueError,'escaped|missing'):
    H.recover_archive(temp,day,{**entry,'snapshot_path':'../stolen.json'})

 def test_duplicate_price_date_uses_first_capture(self):
  day,entry=self.first[0]
  second={**entry,'snapshot_id':'second_valid_name','captured_at_utc':'2026-11-01T09:00:00Z'}
  index={'snapshots_total':2,'snapshots':[second,entry]}
  self.assertEqual(H.first_entries(index)[0][1]['snapshot_id'],entry['snapshot_id'])
  with self.assertRaisesRegex(ValueError,'duplicate'):
   H.first_entries({'snapshots_total':2,'snapshots':[entry,entry]})
  with self.assertRaisesRegex(ValueError,'count'):
   H.first_entries({'snapshots_total':20,'snapshots':[entry]})
  with self.assertRaisesRegex(ValueError,'unsafe'):
   H.first_entries({'snapshots_total':1,'snapshots':[{**entry,'snapshot_path':'../../etc/passwd'}]})

 def test_validation_never_suggests_probabilities_from_old_data(self):
  rows=H.recover_archive(self.data,*self.first[0])
  readiness=H.load_json((self.data/'research_readiness_meta.json').read_bytes())
  audit=H.gate_report(readiness,rows,len(self.first))
  self.assertFalse(audit['model_enabled'])
  self.assertEqual(audit['verified_trade_samples'],0)
  self.assertIsNone(audit['certified_win_rate'])
  self.assertFalse(audit['required_checks']['trade_execution']['passed'])
  self.assertFalse(audit['required_checks']['historical_availability']['passed'])
  self.assertFalse(audit['required_checks']['adjusted_ohlc']['passed'])
  all_true={**readiness,**{flag:True for _,flag in H.GATE_CHECKS}}
  still=H.gate_report(all_true,rows,55)
  self.assertFalse(still['model_enabled'])
  self.assertEqual(still['verified_trade_samples'],0)
  with self.assertRaisesRegex(ValueError,'re-audit'):
   H.gate_report({**readiness,'strict_performance_samples_eligible':5},rows,55)

 def test_output_rebuild_on_temp_is_deterministic_and_never_backdated(self):
  with tempfile.TemporaryDirectory() as scratch:
   folder=Path(scratch)
   index=H.load_json((self.data/'signal_archive_index.json').read_bytes())
   # Limit fixture I/O to two real archives while keeping lineage exact.
   choose=self.first[:2]
   entries=[x for _,x in choose]
   (folder/'signal_archive_index.json').write_text(
    json.dumps({'snapshots':entries,'snapshots_total':2}),encoding='utf-8')
   shutil.copy(self.data/'research_readiness_meta.json',folder/'research_readiness_meta.json')
   for _,item in choose:
    src=self.data/item['snapshot_path']
    dest=folder/item['snapshot_path']
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(src.parent,dest.parent,dirs_exist_ok=True)
   when=dt.datetime(2026,10,29,0,0,tzinfo=dt.timezone.utc)
   meta=H.build(folder,generated_at=when)
   self.assertEqual(meta['unique_first_captured_price_sessions'],2)
   self.assertEqual(meta['status'],'verified_raw_archives_model_blocked')
   self.assertFalse(meta['strict_validation']['model_enabled'])
   path=folder/'historical_evidence_30q.csv'
   first_bytes=path.read_bytes()
   with path.open(encoding='utf-8-sig',newline='') as fh:rows=list(csv.DictReader(fh))
   self.assertEqual(len(rows),meta['stock_session_observations'])
   self.assertTrue(all(x['first_captured_at_utc']>x['price_session'] for x in rows))
   self.assertTrue(all(x['eligible_for_historical_trade']=='false' for x in rows))
   H.build(folder,generated_at=when)
   self.assertEqual(path.read_bytes(),first_bytes)

if __name__=='__main__':
 unittest.main()
