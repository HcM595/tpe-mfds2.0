#!/usr/bin/env python3
"""2.9L: integrity checks for published research screens and underlying data."""
import csv
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DATA = SITE / "data"
PAGES = ("factor_gaps_29h.html", "stock_research_29i.html", "dual_engine_29j.html", "compare_29k.html", "publication_review_29p.html", "material_events_29q.html")
SOURCE_FILES = (
    "factor_evidence_29a.csv", "official_snapshot.csv", "chip_signals.csv",
    "tech_crosscheck.csv", "industry_relative_28c.csv", "risk_observations_28d.csv",
    "f2_valuation_29e.csv", "revenue_snapshot_28c.csv", "pit_f2f3_stock_29f.csv",
    "publication_gate_29o.csv", "publication_review_queue_29p.csv",
)

def read_rows(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

class ResearchPageHealth(unittest.TestCase):
    def test_pages_present_and_reachable_from_navigation(self):
        home = (SITE / "index.html").read_text(encoding="utf-8")
        for name in PAGES:
            with self.subTest(page=name):
                page = (SITE / name).read_text(encoding="utf-8")
                self.assertIn("</html>", page.lower())
                self.assertIn("./data/", page)
                self.assertIn(name, home)

    def test_source_contract_and_stock_keys(self):
        evidence = read_rows("factor_evidence_29a.csv")
        self.assertGreater(len(evidence), 1000)
        ids = [r["stock_id"] for r in evidence]
        self.assertEqual(len(ids), len(set(ids)), "duplicate factor stock_id")
        for file in SOURCE_FILES:
            with self.subTest(file=file):
                rows = read_rows(file)
                self.assertGreater(len(rows), 0)
                self.assertIn("stock_id", rows[0])
                self.assertFalse(any(not r.get("stock_id") for r in rows))
                self.assertTrue(set(r["stock_id"] for r in rows).intersection(ids))

    def test_no_unverified_model_claims(self):
        meta = json.loads((DATA / "factor_evidence_meta_29a.json").read_text(encoding="utf-8"))
        self.assertFalse(meta["model_scores_enabled"])
        self.assertFalse(meta["performance_probabilities_enabled"])
        self.assertEqual(meta["count_verified_factors"], 0)
        for row in read_rows("factor_evidence_29a.csv"):
            self.assertEqual(row["model_eligible"], "false")
            self.assertEqual(row["prediction_enabled"], "false")

    def test_page_contracts(self):
        factor = (SITE / PAGES[0]).read_text(encoding="utf-8")
        stock = (SITE / PAGES[1]).read_text(encoding="utf-8")
        dual = (SITE / PAGES[2]).read_text(encoding="utf-8")
        compare = (SITE / PAGES[3]).read_text(encoding="utf-8")
        for page in (factor, stock, dual, compare):
            self.assertIn("cache:'no-store'", page)
            self.assertIn("function ", page)
        self.assertIn("observed_factor_count", factor)
        self.assertIn("source_postdates_price", stock)
        self.assertIn("basic_data_eligible", dual)
        self.assertIn("available", compare)
        self.assertIn("日期不同", stock)
        self.assertIn("無法判定", compare)
        self.assertIn("pit_clock_29n.js", factor)
        self.assertIn("pit_clock_29n.js", stock)
        self.assertIn("pit_f2f3_stock_29f.csv", dual)
        self.assertIn("pit_f2f3_stock_29f.csv", compare)
        self.assertIn("publication_gate_29o.csv", stock)
        events=(SITE / "material_events_29q.html").read_text(encoding="utf-8")
        self.assertIn("material_events_29q.csv",events)
        meta_events=json.loads((DATA / "material_events_meta_29q.json").read_text(encoding="utf-8"))
        self.assertEqual(meta_events["verified_first_publication_times"],0)
        self.assertEqual(meta_events["events_mapped_to_F2_F3_revenue"],0)
        self.assertFalse(meta_events["model_scoring_enabled"])
        self.assertTrue((DATA / "material_events_29q.csv").exists())
        links_html=(SITE / "event_crosscheck_29r.html").read_text(encoding="utf-8")
        self.assertIn("publication_event_links_29r.csv",links_html)
        self.assertIn("event_crosscheck_29r.html",(SITE / "material_events_29q.html").read_text(encoding="utf-8"))
        self.assertIn("event_crosscheck_29r.html",(SITE / "publication_review_29p.html").read_text(encoding="utf-8"))
        cross_meta=json.loads((DATA / "publication_event_links_meta_29r.json").read_text(encoding="utf-8"))
        self.assertEqual(cross_meta["verified_event_to_factor_value_links"],0)
        self.assertEqual(cross_meta["historical_factor_eligible"],0)
        self.assertFalse(cross_meta["model_scoring_enabled"])
        self.assertTrue((DATA / "publication_event_links_29r.csv").exists())
        self.assertTrue((DATA / "material_event_topics_29r.csv").exists())
        review=(SITE / "publication_review_29p.html").read_text(encoding="utf-8")
        self.assertIn("publication_review_queue_29p.csv",review)
        meta_review=json.loads((DATA / "publication_review_meta_29p.json").read_text(encoding="utf-8"))
        self.assertEqual(meta_review["candidate_rows"],meta_review["universe_stocks"]*3)
        self.assertEqual(meta_review["strict_backtest_eligible"],0)
        self.assertFalse(meta_review["model_scoring_enabled"])
        self.assertIn("asof_gate_29o.js", dual)
        self.assertIn("asof_gate_29o.js", compare)
        clock = json.loads((DATA / "publication_gate_meta_29o.json").read_text(encoding="utf-8"))
        self.assertEqual(clock["strict_backtest_eligible"], 0)
        self.assertFalse(clock["model_scoring_enabled"])
        self.assertFalse(clock["probability_enabled"])

if __name__ == "__main__":
    unittest.main()
