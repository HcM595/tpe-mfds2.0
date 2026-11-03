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
        self.assertIn("<title>TPE-MFDS 3.0W｜進階研究資料館</title>",hub)
        parser=Elements();parser.feed(index)
        for page in PAGES:
            with self.subTest(page=page):
                self.assertTrue((SITE/page).is_file())
                if page=="research_hub_30a.html":
                    self.assertIn("./"+page, parser.links)
                elif page not in ("index.html", "event_crosscheck_29r.html"):
                    # Main research library links are assembled in JavaScript,
                    # so they do not exist as static HTMLParser anchor nodes.
                    # Require the exact relative target to remain in the page
                    # source AND require the destination file on disk.
                    self.assertIn('href="./'+page+'"', index)
                # Crosscheck is retained as an independent resource, not
                # advertised as a primary navigation item.
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
    def test_watchlist_changes_invalidate_prior_timeline_evidence(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        # A stock removed from the watchlist must not inherit the previous
        # stock's SHA256-verified archive report on the next render.
        self.assertIn("if(ui.stock!==known){", index)
        self.assertIn("ui.stock=known;ui.docs=[];ui.status='idle';ui.error='';ui.serial++;", index)
        self.assertIn("timeline.docs=[];timeline.status='idle';timeline.serial++;", index)
        self.assertIn("if(ui.docs[0]?.date!==ui.from||ui.docs.at(-1)?.date!==ui.to)return null;", index)
        # Adding one ticker cannot silently overwrite previously saved codes.
        self.assertIn("const persisted=window.MFDSWatchlist30N.ids(", index)
        self.assertIn("[...new Set([...persisted,...state.watch])]", index)

    def test_market_research_tiers_show_all_blockers(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertIn("<th>研究條件分級</th><th>缺漏／未通過原因</th>",index)
        self.assertIn("const tier=item.tier||{tier:'ineligible'",index)
        self.assertIn("c.issues.join('；')",index)
        self.assertIn("tier.confirmed}/3",index)

    def test_cross_screen_sorting_and_export_agree(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertIn('id="r-cross-sort"',index)
        self.assertIn("crossSort:'evidence'",index)
        self.assertIn("['r-cross-sort','crossSort']",index)
        self.assertEqual(index.count("if(research.crossSort==='evidence')"),2)
        self.assertIn("b.tier.confirmed-a.tier.confirmed",index)
        self.assertIn("lib.toCSV(result)",index)

    def test_archived_history_readiness_uses_distinct_price_dates(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertIn("new Set(ui.days.map(d=>d.date)).size",index)
        self.assertIn("10／20／60日研究準備度",index)
        self.assertIn("不能直接推算交易勝率",index)

    def test_history_displays_audited_performance_blockers(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertIn("readiness.strict_performance_samples_eligible",index)
        self.assertIn("readiness.performance_metrics_enabled===true",index)
        self.assertIn("readiness.source_publication_times_verified",index)
        self.assertIn("readiness.adjusted_ohlc_verified",index)
        self.assertIn("readiness.sample_independence_verified",index)
        self.assertIn("正式績效稽核：",index)

    def test_market_evidence_tier_distribution(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertIn("const tierCounts={confluence:0,partial_2:0,partial_1:0,unconfirmed:0,ineligible:0}",index)
        self.assertIn("tierCounts[item.tier.tier]++",index)
        self.assertIn("研究證據分級（目前搜尋及市場範圍）",index)
        self.assertIn("資料不合格：",index)
        self.assertIn("分級僅描述可核對條件，不代表勝率",index)

    def test_watch_chip_trend_is_archived_and_evidence_gated(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertIn("function watchChipTrendPanel()",index)
        self.assertIn("rArray('historyEvidence')",index)
        self.assertIn("raw_input_verified==='true'",index)
        self.assertIn("flow_5d_observation_usable==='true'",index)
        self.assertIn("holder_4w_observation_usable==='true'",index)
        self.assertIn("new Set(unique.map(r=>r.holder_asof)",index)
        self.assertIn("首末封存籌碼變化",index)
        self.assertIn("非持續增持、未來報酬或勝率",index)
        self.assertIn("+watchChipTrendPanel()+watchTimelinePanel()",index)

    def test_model_not_fake_enabled_by_site_shell(self):
        index=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertNotIn("預測勝率80%",index)
        self.assertIn("未驗證",index)
        for page in ("research","chip","watch","settings"):
            self.assertIn('data-page="'+page+'"',index)

if __name__=="__main__":
    unittest.main()
