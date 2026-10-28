#!/usr/bin/env python3
"""3.0J acceptance contract for original TPE-MFDS website goals.

Static link, real nine-source data and research-safety checks.
Browser CI separately tests interactions, not the live Pages deployment.
"""
import csv
import hashlib
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SITE=Path(__file__).resolve().parents[1]/"site"
DATA=SITE/"data"
PAGES=("index.html","research_hub_30a.html","factor_gaps_29h.html",
       "stock_research_29i.html","dual_engine_29j.html","compare_29k.html",
       "publication_review_29p.html","material_events_29q.html",
       "event_body_audit_29s.html","event_crosscheck_29r.html")
SOURCES={
    "factor":"factor_evidence_29a.csv", "chip":"chip_signals.csv",
    "tech":"tech_crosscheck.csv", "industry":"industry_relative_28c.csv",
    "risk":"risk_observations_28d.csv","valuation":"f2_valuation_29e.csv",
    "revenue":"revenue_snapshot_28c.csv","publication":"publication_gate_29o.csv",
    "actions":"corporate_action_readiness_30e.csv"
}

class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self.scripts=[]
        self.ids=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if a.get("id"):self.ids.append(a["id"])
        if tag=="a" and a.get("href"):self.links.append(a["href"])
        if tag=="script" and a.get("src"):self.scripts.append(a["src"])

def readcsv(name):
    with (DATA/name).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

class OriginalGoalSiteAcceptance(unittest.TestCase):
    def test_all_entry_pages_have_valid_internal_links_and_scripts(self):
        for name in PAGES:
            page=(SITE/name).read_text(encoding="utf-8")
            d=Assets()
            d.feed(page)
            self.assertEqual(len(d.ids),len(set(d.ids)),name+" duplicate DOM IDs")
            for uri in d.links+d.scripts:
                if "$" in uri or "{{" in uri:continue
                p=urlsplit(uri)
                if p.scheme or p.netloc or not p.path or p.path=="/":continue
                target=(SITE/unquote(p.path).lstrip("./")).resolve()
                with self.subTest(page=name,link=uri):
                    self.assertTrue(target.is_relative_to(SITE.resolve()))
                    self.assertTrue(target.is_file(),"missing internal link or script: "+uri)

    def test_original_navigation_has_one_authoritative_hub_and_legacy_labels(self):
        home=(SITE/"index.html").read_text(encoding="utf-8")
        hub=(SITE/"research_hub_30a.html").read_text(encoding="utf-8")
        self.assertEqual(home.count('href="./research_hub_30a.html"'),1)
        self.assertNotIn('id="nav-advanced"',home)
        self.assertNotIn('id="nav-research-tools"',home)
        self.assertIn('href="./editorial_30k.css"',home)
        self.assertIn("研究資料館",home)
        self.assertIn("示範資料",home)
        self.assertIn("RESEARCH WORKSPACE",home)
        self.assertIn("3.0E · 研究資料總覽",home)
        self.assertIn("TPE-MFDS 3.0P ·",home)
        self.assertIn("3.0E｜發布快照與九份資料檔完整性",hub)
        self.assertNotIn("正在比對八類研究來源",hub)

    def test_main_journeys_and_stock_comparison_are_exposed(self):
        home=(SITE/"index.html").read_text(encoding="utf-8")
        hub=(SITE/"research_hub_30a.html").read_text(encoding="utf-8")
        for page in ("research","chip","watch","settings"):
            self.assertIn('data-page="'+page+'"',home)
        for tab in ("overview","stock","history","quality"):
            self.assertIn('data-research-tab="'+tab+'"',home)
        for tab in ("market","detail","compare","quality"):
            self.assertIn('id="tab-'+tab+'"',hub)
            self.assertIn('id="screen-'+tab+'"',hub)
        for link in ("factor_gaps_29h.html","stock_research_29i.html",
                     "dual_engine_29j.html","compare_29k.html"):
            self.assertIn('href="./'+link+'"',home)

    def test_nine_source_snapshot_matches_actual_published_csv(self):
        m=json.loads((DATA/"research_snapshot_30d.json").read_text(encoding="utf-8"))
        self.assertEqual(m["schema_version"],"3.0E")
        self.assertEqual(m["snapshot_source_count"],9)
        self.assertEqual(set(m["sources"]),set(SOURCES))
        self.assertIs(m["formal_model_scoring_enabled"],False)
        self.assertIs(m["performance_probabilities_enabled"],False)
        for key,name in SOURCES.items():
            d=m["sources"][key]
            raw=(DATA/name).read_bytes()
            with self.subTest(source=key):
                self.assertEqual(d["path"],"data/"+name)
                self.assertEqual(d["sha256"],hashlib.sha256(raw).hexdigest())
                self.assertEqual(d["byte_length"],len(raw))
                rows=readcsv(name)
                self.assertEqual(d["row_count"],len(rows))
                self.assertEqual(d["unique_stock_count"],
                                 len({r["stock_id"] for r in rows}))

    def test_specific_stocks_and_model_eligibility_are_not_fabricated(self):
        rows=readcsv("factor_evidence_29a.csv")
        byid={r["stock_id"]:r for r in rows}
        self.assertGreater(len(byid),1000)
        for code in ("8064","3533","2345"):
            self.assertIn(code,byid)
        self.assertTrue(all(r["prediction_enabled"]=="false" and
                            r["model_eligible"]=="false" for r in rows))
        readiness=json.loads((DATA/"research_readiness_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(readiness["strict_performance_samples_eligible"],0)
        actions=json.loads((DATA/"corporate_action_readiness_meta_30e.json").read_text(encoding="utf-8"))
        self.assertFalse(actions["total_return_calculation_allowed"])
        self.assertFalse(actions["adjusted_ohlc_verified"])

if __name__=="__main__":
    unittest.main()
