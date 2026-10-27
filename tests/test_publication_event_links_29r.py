import csv
import json
import tempfile
import unittest
from pathlib import Path
from scripts.reconcile_publication_events_29r import build,category

def write(p,items):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=items[0].keys(),lineterminator="\n")
        w.writeheader();w.writerows(items)
def reviews(stock,market):
    return [dict(stock_id=stock,stock_name="測試公司",market=market,price_asof="2026-10-22",
                 factor=f,evidence_key=f+"-id",source_sha256="f"*64,
                 source_first_seen_utc="2026-10-26T00:00:00Z",
                 review_status="awaiting_independent_publication_proof") for f in ("F2","F3","REVENUE")]
def event(k,stock,market,title):
    return dict(event_key=k,stock_id=stock,stock_name="測試公司",market=market,
       source_speech_day="2026-10-26",source_speech_clock="13:00:00",
       source_speech_at_taipei="2026-10-26T13:00:00+08:00",
       event_title=title,source_payload_sha256="a"*64,
       observed_first_at_utc="2026-10-27T01:00:00Z",
       event_first_publication_verified="false",factor_release_time_eligible="false")

class EventReconciliationTests(unittest.TestCase):
    def test_no_dividends_earnings_or_asset_disposals_automatically_promoted(self):
        self.assertEqual(category("公告本公司115年9月合併月營收"),
                         ("explicit_monthly_revenue_topic","REVENUE"))
        self.assertEqual(category("公告董事長不兼任總經理"),
                         ("explicit_chair_ceo_overlap_topic","F3"))
        for subject in ("公告調整現金股利配息率","代子公司取得機器設備",
                        "公告子公司財報盈利警告","公告每股盈餘資訊","本公司更名"):
            self.assertEqual(category(subject)[1],"",subject)
        self.assertEqual(category("公告總經理異動")[1],"","different manager is not verified chair/CEO overlap")
        self.assertEqual(category("公告本公司2026年9月月營收 2億")[1],"REVENUE")

    def test_company_market_and_explicit_topic_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/"site"/"data"
            write(d/"publication_review_queue_29p.csv",
                  reviews("8064","上櫃")+reviews("3533","上市"))
            events=[
              event("rev-a","8064","上櫃","公告本公司115年9月合併營收"),
              event("gov-a","8064","上櫃","公告董事長兼任總經理"),
              event("fin-a","8064","上櫃","代子公司公告盈利警告"),
              event("other-a","8064","上櫃","取得機器設備"),
              event("wrong-market","8064","上市","公告本公司月營收"),
              event("wrong-security","3533","上市","本公司董事會通過現金股利")
            ]
            write(d/"material_events_29q.csv",events)
            candidates,typed,meta=build(Path(tmp))
            self.assertEqual(len(candidates),6)
            self.assertEqual(meta["subject_only_candidate_links"],2)
            self.assertEqual(meta["verified_event_to_factor_value_links"],0)
            self.assertEqual(meta["official_first_publication_verified"],0)
            self.assertFalse(meta["model_scoring_enabled"])
            key={(r["stock_id"],r["market"],r["factor"]):r for r in candidates}
            self.assertEqual(key[("8064","上櫃","REVENUE")]["topic_candidate_count"],"1")
            self.assertEqual(key[("8064","上櫃","F3")]["topic_event_keys"],"gov-a")
            self.assertEqual(key[("8064","上櫃","F2")]["topic_candidate_count"],"0")
            self.assertEqual(key[("3533","上市","REVENUE")]["topic_candidate_count"],"0")
            self.assertEqual(key[("8064","上櫃","REVENUE")]["candidate_after_price_cutoff"],"true")
            self.assertTrue(all(r["historical_clock_eligible"]=="false" and
                                r["release_time_verified"]=="false" and
                                r["event_and_factor_payload_identical"]=="false"
                                for r in candidates))
            self.assertTrue(all(r["factor_release_proof"]=="false" for r in typed))
            self.assertEqual(meta["archived_events"],len(events))
            self.assertEqual(json.loads((d/"publication_event_links_meta_29r.json").read_text())["historical_factor_eligible"],0)
            self.assertEqual(candidates,build(Path(tmp))[0],"reconciliation must be repeatable")

    def test_duplicate_event_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/"site"/"data"
            write(d/"publication_review_queue_29p.csv",reviews("8064","上櫃"))
            e=event("same-key","8064","上櫃","公告本公司月營收")
            write(d/"material_events_29q.csv",[e,e])
            with self.assertRaisesRegex(ValueError,"duplicated"):
                build(Path(tmp))

if __name__=="__main__":
    unittest.main()
