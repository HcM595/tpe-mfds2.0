import csv
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_research_snapshot_30d import SOURCES,build,describe
class SnapshotReceiptTests(unittest.TestCase):
    def setup_sources(self,root):
        folder=Path(root)/"site"/"data";folder.mkdir(parents=True,exist_ok=True)
        for key,(name,asof) in SOURCES.items():
            size=1001 if key=="factor" else 2
            with (folder/name).open("w",encoding="utf-8-sig",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=["stock_id",asof,"market"],lineterminator="\n")
                writer.writeheader()
                for idx in range(size):
                    writer.writerow({"stock_id":str(1000+idx),"market":"上市",asof:"2026-10-27"})
        return folder
    def test_exact_bytes_and_reproducible_explicit_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.setup_sources(tmp)
            clock=dt.datetime(2026,10,28,1,2,tzinfo=dt.timezone.utc)
            m=build(Path(tmp),clock)
            self.assertEqual(m["snapshot_source_count"],9)
            self.assertEqual(m["sources"]["factor"]["row_count"],1001)
            self.assertFalse(m["formal_model_scoring_enabled"])
            self.assertFalse(m["performance_probabilities_enabled"])
            first=(folder/"research_snapshot_30d.json").read_bytes()
            self.assertEqual(m,build(Path(tmp),clock))
            self.assertEqual(first,(folder/"research_snapshot_30d.json").read_bytes())
            a=(folder/"chip_signals.csv").read_bytes()
            self.assertEqual(m["sources"]["chip"]["sha256"],hashlib.sha256(a).hexdigest())
            (folder/"chip_signals.csv").write_bytes(a+b"\n")
            second=describe((folder/"chip_signals.csv").read_bytes(),
                            "chip_signals.csv","flow_asof")
            self.assertNotEqual(second["sha256"],m["sources"]["chip"]["sha256"])
    def test_fails_closed_on_duplicate_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.setup_sources(tmp)
            p=folder/"chip_signals.csv"
            original=p.read_text(encoding="utf-8-sig")
            p.write_text(original+original.splitlines()[1]+"\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"duplicated stock_id"):
                build(Path(tmp))
    def test_bad_source_day_and_missing_table_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.setup_sources(tmp)
            p=folder/"revenue_snapshot_28c.csv"
            p.write_text(p.read_text(encoding="utf-8-sig").replace("2026-10-27","2026-02-30"),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"invalid table_date"):build(Path(tmp))
            p.unlink()
            with self.assertRaises(FileNotFoundError):build(Path(tmp))
    def test_naive_generation_clock_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_sources(tmp)
            with self.assertRaisesRegex(ValueError,"timezone"):
                build(Path(tmp),dt.datetime(2026,10,28,9,30))
if __name__=="__main__":
    unittest.main()
