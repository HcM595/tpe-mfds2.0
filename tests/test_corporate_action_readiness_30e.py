import csv
import json
import tempfile
import unittest
from pathlib import Path
from scripts.audit_corporate_action_readiness_30e import audit

def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator="\n")
        w.writeheader();w.writerows(rows)

def setup(root):
    d=Path(root)/"site"/"data";d.mkdir(parents=True,exist_ok=True)
    write(d/"factor_evidence_29a.csv",[
       dict(stock_id="8064",stock_name="東捷",market="上櫃",price_asof="2026-10-27"),
       dict(stock_id="3533",stock_name="嘉澤",market="上市",price_asof="2026-10-27")])
    write(d/"price_history.csv",[
       dict(stock_id="8064",date="2026-10-20",close="125"),
       dict(stock_id="8064",date="2026-10-21",close="120"),
       dict(stock_id="8064",date="2026-10-22",close="118"),
       dict(stock_id="8064",date="2026-10-27",close="122"),
       dict(stock_id="3533",date="2026-10-22",close="1585"),
       dict(stock_id="3533",date="2026-10-27",close="1590")])
    base=dict(market="上櫃",stock_id="8064",stock_name="東捷",ex_date="2026-10-22",
         event_type="息",pre_close="120",reference_price="116",
         field_semantics="reference_price_components_not_share_distribution",
         source_sha256="a"*64)
    write(d/"corporate_action_history_events.csv",[base])
    write(d/"corporate_actions_observed.csv",[
       dict(market="TPEx",stock_id="8064",ex_date="2026-10-22",event_type="息")])
    write(d/"corporate_action_history_sources.csv",[
       dict(market="上櫃",result="events_archived"),
       dict(market="上市",result="source_unverified")])
    (d/"corporate_action_history_meta.json").write_text(json.dumps(
      dict(historical_corporate_actions_complete=False,cash_or_stock_distribution_terms_verified=False,
           adjusted_ohlc_verified=False)),encoding="utf-8")
    (d/"corporate_actions_meta.json").write_text(json.dumps(
      dict(historical_corporate_actions_complete=False,adjusted_ohlc_verified=False)),encoding="utf-8")
    return d

class ActionReadinessTests(unittest.TestCase):
    def test_ex_right_reference_is_not_cash_or_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=setup(tmp)
            records,m=audit(Path(tmp))
            self.assertEqual(len(records),2)
            self.assertEqual(m["failed_or_unverified_history_source_attempts"],1)
            self.assertEqual(m["prior_raw_close_pairs_checked"],1)
            self.assertEqual(m["prior_raw_close_mismatches"],0)
            row=next(x for x in records if x["stock_id"]=="8064")
            self.assertEqual(row["last_official_prior_close"],"120")
            self.assertEqual(row["last_official_reference_price"],"116")
            self.assertEqual(row["last_observed_preceding_raw_close"],"120.0")
            self.assertEqual(row["prior_close_matches"],"1")
            self.assertEqual(row["history_events_observed"],"1")
            self.assertEqual(row["rolling_notices_observed"],"1")
            self.assertEqual(row["total_return_calculation_allowed"],"false")
            self.assertEqual(row["adjusted_ohlc_verified"],"false")
            self.assertEqual(m["prior_raw_close_mismatches"],0)
            blank=next(x for x in records if x["stock_id"]=="3533")
            self.assertEqual(blank["history_events_observed"],"0")
            self.assertIn("不得推定無",blank["research_status"])
            self.assertFalse(m["total_return_calculation_allowed"])
            self.assertFalse(m["formal_model_scores_enabled"])
            self.assertEqual(json.loads((d/"corporate_action_readiness_meta_30e.json").read_text())["stocks"],2)
            self.assertEqual(records,audit(Path(tmp))[0],"audit must be deterministic")
    def test_wrong_previous_close_is_flagged_not_adjusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=setup(tmp);p=d/"price_history.csv"
            p.write_text(p.read_text().replace("2026-10-21,120","2026-10-21,117"),encoding="utf-8")
            rows,meta=audit(Path(tmp))
            self.assertEqual(meta["prior_raw_close_mismatches"],1)
            self.assertIn("不一致",next(x for x in rows if x["stock_id"]=="8064")["research_status"])
            self.assertFalse(meta["adjusted_ohlc_verified"])
    def test_invalid_event_source_semantics_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=setup(tmp);p=d/"corporate_action_history_events.csv"
            p.write_text(p.read_text().replace(
                "reference_price_components_not_share_distribution","falsely_claims_cash_dividend"),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"Unknown ex-right"):
                audit(Path(tmp))
    def test_missing_history_and_false_completeness_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=setup(tmp)
            (d/"price_history.csv").unlink()
            with self.assertRaises(FileNotFoundError):audit(Path(tmp))
        with tempfile.TemporaryDirectory() as tmp:
            d=setup(tmp)
            (d/"corporate_action_history_meta.json").write_text(
                json.dumps(dict(historical_corporate_actions_complete=True)),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"incomplete corporate-action"):
                audit(Path(tmp))
if __name__=="__main__": unittest.main()
