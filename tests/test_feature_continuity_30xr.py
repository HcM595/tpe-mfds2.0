#!/usr/bin/env python3
"""3.0X-R: prevent silent loss of visible study features after site releases."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]/"site"
PAGES=("index.html","research_hub_30a.html","factor_gaps_29h.html",
       "stock_research_29i.html","dual_engine_29j.html","compare_29k.html",
       "publication_review_29p.html","material_events_29q.html",
       "event_body_audit_29s.html","event_crosscheck_29r.html")
MODULES=("chip_tech_crossfilter_30l.js","stock_evidence_30m.js",
         "watchlist_center_30n.js","watch_history_30o.js",
         "watch_timeline_30p.js","research_core_30a.js")
DATA=("factor_evidence_29a.csv","chip_signals.csv","tech_crosscheck.csv",
      "historical_evidence_meta_30q.json","official_meta.json",
      "research_snapshot_30d.json")

class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="a" and attrs.get("href"):
            self.links.append(attrs["href"].split("#")[0].split("?")[0])

class FeatureContinuity(unittest.TestCase):
    def test_versions_and_subpages_reachable(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        hub=(SITE/"research_hub_30a.html").read_text(encoding="utf-8")
        self.assertIn("<title>TPE-MFDS 3.0W｜台股整合研究中心</title>",index)
        self.assertIn("<title>TPE-MFDS 3.0W｜研究資料館 · 3.0E 除權息事件核查</title>",hub)
        parser=Elements();parser.feed(index)
        for page in PAGES:
            with self.subTest(page=page):
                self.assertTrue((SITE/page).is_file())
                if page!="index.html" and page!="event_crosscheck_29r.html":
                    self.assertIn("./"+page,parser.links)
                # Crosscheck page is retained as a separate evidence resource;
                # it is not a required primary navigation item.
    def test_essential_scripts_and_data_cannot_disappear(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        for module in MODULES:
            with self.subTest(module=module):
                self.assertTrue((SITE/module).is_file())
                if module.startswith(("watch_","stock_evidence","chip_tech")):
                    self.assertIn("./"+module,index)
        for name in DATA:
            with self.subTest(data=name):
                self.assertTrue((SITE/"data"/name).is_file())
    def test_model_not_fake_enabled_by_site_shell(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertNotIn("預測勝率80%",index)
        self.assertIn("未驗證",index)
        for page in ("research","chip","watch","settings"):
            self.assertIn('data-page="'+page+'"',index)

if __name__=="__main__":
    unittest.main()
