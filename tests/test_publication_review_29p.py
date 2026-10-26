import csv
import json
import tempfile
import unittest
from pathlib import Path
from scripts.build_publication_review_29p import build,official_endpoint,checksum,captured

SHA="a"*64
TIME="2026-10-26T03:42:17+00:00"
def rows(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=data[0].keys(),lineterminator="\n")
        writer.writeheader();writer.writerows(data)

class PublicationQueueTests(unittest.TestCase):
    def test_official_domain_and_provenance_must_be_strict(self):
        self.assertTrue(official_endpoint("https://openapi.twse.com.tw/v1/opendata/t187ap05_L"))
        self.assertTrue(official_endpoint("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"))
        self.assertFalse(official_endpoint("http://openapi.twse.com.tw/v1/a"))
        self.assertFalse(official_endpoint("https://openapi.twse.com.tw.evil.example/v1/a"))
        self.assertFalse(official_endpoint("https://www.tpex.org.tw@evil.example/v1/a"))
        self.assertFalse(official_endpoint("https://www.tpex.org.tw/"))
        self.assertTrue(checksum(SHA))
        self.assertFalse(checksum("b"*63))
        self.assertTrue(captured(TIME))
        self.assertFalse(captured("2026-10-22"))
        self.assertFalse(captured("2026-10-22T10:00:00"))

    def test_three_candidates_and_no_auto_release_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            site=root/"site"/"data"
            key={"stock_id":"8064","market":"上櫃"}
            rows(site/"factor_evidence_29a.csv",[
                {**key,"stock_name":"東捷","price_asof":"2026-10-22"}])
            rows(site/"publication_gate_29o.csv",[{**key,
                "F2_source_report_day":"2026-10-22","F2_first_seen_utc":TIME,
                "F2_asof_clock_pass":"false","F2_blockers":"official_publication_unverified;first_seen_after_cutoff",
                "F3_source_report_day":"2026-10-25","F3_first_seen_utc":TIME,
                "F3_asof_clock_pass":"false","F3_blockers":"report_after_price_day",
                "REVENUE_source_report_day":"2026-10-17",
                "REVENUE_first_seen_utc":TIME,
                "REVENUE_asof_clock_pass":"false","REVENUE_blockers":"official_publication_unverified"}])
            rows(site/"f2_valuation_29e.csv",[{**key,"source_url":"https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis","source_sha256":SHA,"source_status":"ok","first_seen_utc":TIME}])
            rows(site/"f3_governance_29e.csv",[{**key,"source_url":"https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap33_O","source_sha256":SHA,"source_status":"ok","first_seen_utc":TIME}])
            rows(site/"revenue_snapshot_28c.csv",[{**key,"source_url":"https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O","source_sha256":SHA,"source_status":"ok","first_seen_utc":TIME}])
            q,meta=build(root)
            self.assertEqual(len(q),3)
            self.assertEqual(meta["universe_stocks"],1)
            self.assertEqual(set(x["factor"] for x in q),{"F2","F3","REVENUE"})
            self.assertTrue(all(x["raw_provenance_complete"]=="true" for x in q))
            self.assertTrue(all(x["verified_company_publication_utc"]=="" for x in q))
            self.assertTrue(all(x["publication_time_verified"]=="false" for x in q))
            self.assertTrue(all(x["historical_clock_eligible"]=="false" for x in q))
            self.assertTrue(all(x["review_status"]=="awaiting_independent_publication_proof" for x in q))
            self.assertEqual(meta["strict_backtest_eligible"],0)
            self.assertFalse(meta["model_scoring_enabled"])
            self.assertFalse(meta["performance_probabilities_enabled"])
            for factor in ("F2","F3","REVENUE"):
                self.assertEqual(meta["factors"][factor]["raw_provenance_complete"],1)
                self.assertEqual(meta["factors"][factor]["verified_company_release_time"],0)
            self.assertTrue((site/"publication_review_queue_29p.csv").exists())
            self.assertEqual(json.loads((site/"publication_review_meta_29p.json").read_text())["candidate_rows"],3)
            same,_=build(root)
            self.assertEqual(q,same,"regenerating an unchanged snapshot must be deterministic")

    def test_source_mismatch_is_quarantined(self):
        with tempfile.TemporaryDirectory() as temp:
            site=Path(temp)/"site"/"data"
            key={"stock_id":"8064","market":"上櫃"}
            rows(site/"factor_evidence_29a.csv",[{**key,"stock_name":"東捷","price_asof":"2026-10-22"}])
            rows(site/"publication_gate_29o.csv",[{**key,"F2_first_seen_utc":"2026-10-21T00:00:00Z"}])
            rows(site/"f2_valuation_29e.csv",[{**key,"source_url":"https://openapi.twse.com.tw.evil.invalid/foo","source_sha256":SHA,
                "source_status":"ok","first_seen_utc":TIME}])
            q,_=build(Path(temp))
            f2=next(x for x in q if x["factor"]=="F2")
            self.assertEqual(f2["raw_provenance_complete"],"false")
            self.assertIn("archive_first_seen_disagrees_with_29o",f2["blocker_codes"])
            self.assertIn("unverified_official_endpoint",f2["blocker_codes"])
            self.assertIn("individual_company_publication_time_unverified",f2["blocker_codes"])

if __name__=="__main__":
    unittest.main()
