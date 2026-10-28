"""3.0G tests use actual repository observations and explicit synthetic fills."""
import csv
import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.audit_trade_outcomes_30g import DATA, inspect, publish
from scripts.candidate_execution_ledger_30g import candidate_trade_ledger
from scripts.prediction_readiness_30f import REQUIRED

T = datetime(2026, 10, 28, 1, tzinfo=timezone.utc)

def fixture_dir(dest):
    dest = Path(dest)
    manifest = json.loads((DATA/"research_snapshot_30d.json").read_text(encoding="utf-8"))
    names = ["research_snapshot_30d.json", "forward_observation_meta.json",
             "forward_observation.csv", "research_readiness_meta.json",
             "corporate_action_readiness_meta_30e.json"]
    names += [manifest["sources"][k]["path"].split("/")[-1] for k in REQUIRED]
    for name in names:
        shutil.copy2(DATA/name, dest/name)
    return dest

def trade():
    return {
        "horizon_sessions": 10, "entry_session_index": 100, "exit_session_index": 110,
        "signal_first_observed_at_utc": "2026-10-05T09:00:00+08:00",
        "official_signal_publication_at_utc": "2026-10-05T08:00:00+08:00",
        "entry_at_utc": "2026-10-06T09:00:00+08:00",
        "exit_at_utc": "2026-10-21T13:20:00+08:00",
        "entry_shares": 1000, "exit_shares": 1100,
        "entry_price_twd": "100", "exit_price_twd": "100",
        "entry_fee_twd": "100", "exit_fee_twd": "100",
        "exit_tax_twd": "330", "additional_slippage_twd": "100",
        "cash_in_lieu_twd": "0",
        "distribution_events": [{
            "effective_at_utc": "2026-10-12T09:00:00+08:00",
            "share_multiplier": "1.1", "cash_per_share_twd": "2",
        }],
    }

class OutcomeGateTests(unittest.TestCase):
    def test_real_sample_maturity_only_and_zero_outcomes(self):
        x=inspect(DATA,T)
        self.assertEqual(x["version"],"3.0G")
        self.assertEqual(x["status"],"verified_trade_outcomes_unavailable")
        self.assertEqual(x["observations"],387)
        self.assertEqual(x["cohort_count"],5)
        self.assertFalse(x["production_prediction_allowed"])
        for item in x["per_horizon"].values():
            self.assertEqual(item["registered"],387)
            self.assertEqual(item["valid_label_samples"],0)
            self.assertEqual(item["verified_total_returns"],0)
            self.assertEqual(sum(item[k] for k in ("matured_but_unverified","tracking",
                         "awaiting_reference","excluded")),387)
    def test_report_is_auditable_and_fails_on_changed_forward_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            data=fixture_dir(folder)
            report=publish(data)
            self.assertEqual(report["input_forward_csv_sha256"],
                             inspect(data)["input_forward_csv_sha256"])
            publish(data,verify_only=True)
            p=data/"forward_observation.csv"
            old=p.read_text(encoding="utf-8-sig")
            self.assertIn("觀察中_無績效",old)
            p.write_text(old.replace("觀察中_無績效","觀察期已走完_報酬尚未驗證",1),
                         encoding="utf-8")
            with self.assertRaises((ValueError,KeyError)):
                publish(data,verify_only=True)
    def test_invalid_horizon_progress_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            data=fixture_dir(folder)
            path=data/"forward_observation.csv"
            rows=list(csv.DictReader(path.open(encoding="utf-8-sig",newline="")))
            rows[0]["h10_observed_sessions"]="11"
            with path.open("w",encoding="utf-8-sig",newline="") as fp:
                w=csv.DictWriter(fp,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            with self.assertRaisesRegex(ValueError,"Progress out"):
                inspect(data)

class ExecutionLedgerTests(unittest.TestCase):
    def test_verified_assumption_arithmetic_still_not_real(self):
        r=candidate_trade_ledger(trade())
        self.assertEqual(r["final_shares"],1100)
        self.assertEqual(r["cash_distributions_twd"],"2000")
        self.assertEqual(r["entry_debit_twd"],"100100")
        self.assertEqual(r["exit_credit_including_distributions_twd"],"111470")
        self.assertEqual(r["net_profit_twd"],"11370")
        self.assertFalse(r["production_usable"])
        self.assertTrue(r["candidate_positive_return"])
    def test_bad_inputs_rejected(self):
        changes=[
            ("entry_fee_twd","-1"),("entry_fee_twd","nan"),
            ("entry_price_twd",0),("additional_slippage_twd",None),
            ("entry_shares",0),("exit_shares",1000),
            ("horizon_sessions",30),("exit_session_index",111),
            ("official_signal_publication_at_utc","2026-10-22T02:00:00Z"),
            ("entry_at_utc","2026-10-06T09:00:00"),
            ("cash_in_lieu_twd","10"),
        ]
        for key,invalid in changes:
            value=trade();value[key]=invalid
            with self.subTest(key=key,invalid=invalid),self.assertRaises(ValueError):
                candidate_trade_ledger(value)
    def test_noninteger_bonus_shares_and_future_distribution_block(self):
        x=trade(); x["distribution_events"][0]["share_multiplier"]="1.0001"
        with self.assertRaisesRegex(ValueError,"Fractional"):
            candidate_trade_ledger(x)
        x=trade();x["distribution_events"][0]["effective_at_utc"]="2026-10-30T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"date invalid"):
            candidate_trade_ledger(x)
    def test_missing_distribution_ledger_cannot_silently_assume_no_actions(self):
        x=trade(); x.pop("distribution_events")
        with self.assertRaisesRegex(ValueError,"ledger"):
            candidate_trade_ledger(x)
        x=trade(); x["distribution_events"]=[];x["exit_shares"]=1000
        r=candidate_trade_ledger(x)
        self.assertEqual(r["cash_distributions_twd"],"0")
        self.assertFalse(r["production_usable"])

if __name__=="__main__":
    unittest.main()
