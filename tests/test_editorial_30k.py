#!/usr/bin/env python3
"""3.0K editorial UI acceptance: exactly one primary navigation with 7 roles."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]/"site"

class Sidebar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.within=False;self.depth=0;self.buttons=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="nav" and a.get("id")=="nav":
            self.within=True;self.depth=1;return
        if self.within:
            if tag=="nav":self.depth+=1
            if tag=="button" and a.get("class","").find("nav-btn")>=0:
                self.buttons.append((a.get("data-page"),a.get("data-research-tab")))
            if tag=="a":self.links.append(a.get("href"))
    def handle_endtag(self,tag):
        if tag=="nav" and self.within:
            self.depth-=1
            if self.depth==0:self.within=False

class EditorialSiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index=(SITE/"index.html").read_text(encoding="utf-8")
        cls.hub=(SITE/"research_hub_30a.html").read_text(encoding="utf-8")
        cls.css=(SITE/"editorial_30k.css").read_text(encoding="utf-8")
    def test_one_sidebar_seven_unique_routes(self):
        nav=Sidebar()
        nav.feed(self.index)
        self.assertEqual(nav.buttons,[
            ("research","overview"),("research","stock"),("chip",None),
            ("research","history"),("research","quality"),("watch",None),
            ("settings",None)
        ])
        self.assertEqual(nav.links,[])
        self.assertNotIn('id="nav-advanced"',self.index)
        self.assertNotIn('id="nav-research-tools"',self.index)
        self.assertEqual(self.index.count('id="nav"'),1)
    def test_distinct_deep_evidence_pages_not_deleted_or_repeated_in_sidebar(self):
        m=re.search(r"const evidenceHall=(.*?);\n\s*return",self.index,re.S)
        self.assertIsNotNone(m)
        library=m.group(1)
        names=[
            "research_hub_30a.html","factor_gaps_29h.html",
            "dual_engine_29j.html","compare_29k.html",
            "stock_research_29i.html","publication_review_29p.html",
            "material_events_29q.html","event_body_audit_29s.html"
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(library.count('href="./'+name+'"'),1)
                self.assertTrue((SITE/name).is_file())
        self.assertEqual(library.count("<a href="),8)
        self.assertIn("研究資料館",library)
    def test_theme_applied_to_both_index_and_deep_workbench(self):
        self.assertIn('href="./editorial_30k.css"',self.index)
        self.assertIn('href="./editorial_30k.css"',self.hub)
        self.assertIn('class="workbench-editorial"',self.hub)
        self.assertGreater(len(self.css),9000)
        for marker in (".sidebar",".r-metric",".topline",":focus-visible",
                       "@media(max-width:740px)","body.workbench-editorial"):
            self.assertIn(marker,self.css)
    def test_no_fabricated_signals_or_production_win_rates_from_design(self):
        for token in ("Premium","2024/11/08","23,529.64","428 檔","289 檔","預測勝率80%"):
            with self.subTest(token=token):
                self.assertNotIn(token,self.index)
                self.assertNotIn(token,self.hub)
        self.assertIn("獨立績效樣本",self.index) if "獨立績效樣本" in self.index else self.assertIn("禁止勝率",self.index)
        self.assertIn("未驗證",self.index)
        self.assertIn("正式模型及機率功能保持停用",self.hub)

if __name__=="__main__":
    unittest.main()
