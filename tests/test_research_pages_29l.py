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
PAGES = ("factor_gaps_29h.html", "stock_research_29i.html", "dual_engine_29j.html", "compare_29k.html")
SOURCE_FILES = (
    "factor_evidence_29a.csv", "official_snapshot.csv", "chip_signals.csv",
    "tech_crosscheck.csv", "industry_relative_28c.csv", "risk_observations_28d.csv",
    "f2_valuation_29e.csv", "revenue_snapshot_28c.csv",
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
        self.assertIn("對齊", stock)
        self.assertIn("無法判定", compare)

if __name__ == "__main__":
    unittest.main()
