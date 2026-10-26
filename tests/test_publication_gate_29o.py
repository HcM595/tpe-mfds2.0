import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.audit_publication_gate_29o import build,check,instant

class PublicationGateTests(unittest.TestCase):
    def test_time_boundaries_and_release_authorization(self):
        d="2026-10-22"
        early="2026-10-21T15:59:59+00:00"
        late="2026-10-21T16:00:00+00:00"
        self.assertTrue(check(d,d,early,early,True)[0])
        self.assertFalse(check(d,d,early,early,False)[0])
        self.assertIn("source_authorization_missing",check(d,d,early,early,False)[1])
        self.assertIn("first_seen_after_cutoff",check(d,d,late,early,True)[1])
        self.assertIn("publication_after_cutoff",check(d,d,early,late,True)[1])
        self.assertIn("official_publication_unverified",check(d,d,early,"",True)[1])
        self.assertIn("report_after_price_day",check(d,"2026-10-23",early,early,True)[1])
        self.assertIn("invalid_price_day",check("2026-02-30",d,early,early,True)[1])
        self.assertIsNone(instant("2026-10-22"))
        self.assertIn("first_seen_after_cutoff",check(d,d,"2026-10-22T00:00:00+08:00",early,True)[1])

    def test_csv_audit_preserves_unverified_times_and_closes_model(self):
        def write(p,records):
            p.parent.mkdir(parents=True,exist_ok=True)
            with p.open("w",encoding="utf-8",newline="") as fp:
                w=csv.DictWriter(fp,fieldnames=records[0].keys());w.writeheader();w.writerows(records)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            site=root/"site"/"data"
            write(site/"factor_evidence_29a.csv",[
                {"stock_id":"8064","stock_name":"東捷","market":"上櫃","price_asof":"2026-10-22"},
                {"stock_id":"2330","stock_name":"台積電","market":"上市","price_asof":"2026-10-22"}])
            write(site/"pit_f2f3_stock_29f.csv",[
                {"stock_id":"8064","market":"上櫃","price_asof":"2026-10-22",
                 "F2_source_report_date":"2026-10-22","F2_observed_first_at_utc":"2026-10-26T01:00:00Z",
                 "F2_publication_at_utc":"","F2_source_status":"ok","F2_usable_for_backtest":"false",
                 "F3_source_report_date":"2026-10-25","F3_observed_first_at_utc":"2026-10-26T01:00:00Z",
                 "F3_publication_at_utc":"","F3_source_status":"ok","F3_usable_for_backtest":"false"}])
            write(site/"revenue_snapshot_28c.csv",[
                {"stock_id":"8064","market":"上櫃","table_date":"2026-10-17",
                 "first_seen_utc":"2026-10-26T01:00:00Z",
                 "disclosure_time_verified":"false","source_sha256":"test","verified_publication_at_utc":""}])
            rows,meta=build(root)
            self.assertEqual(len(rows),2)
            row=rows[0]
            self.assertEqual(row["F2_asof_clock_pass"],"false")
            self.assertIn("official_publication_unverified",row["F2_blockers"])
            self.assertIn("report_after_price_day",row["F3_blockers"])
            self.assertIn("first_seen_after_cutoff",row["REVENUE_blockers"])
            self.assertEqual(row["REVENUE_verified_publication_utc"],"")
            self.assertEqual(meta["strict_backtest_eligible"],0)
            self.assertFalse(meta["model_scoring_enabled"])
            self.assertFalse(meta["probability_enabled"])
            self.assertEqual(meta["clock_gate_pass"],{"F2":0,"F3":0,"REVENUE":0})
            self.assertTrue((site/"publication_gate_29o.csv").is_file())
            self.assertEqual(json.loads((site/"publication_gate_meta_29o.json").read_text())["universe_stocks"],2)

if __name__=="__main__":
    unittest.main()
