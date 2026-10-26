import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.audit_f2f3_pit_29f import capture,audit_row,utc_instant

UTC=dt.timezone.utc
def save(path,items):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=items[0]);wr.writeheader();wr.writerows(items)
def sample(root):
    data=root/"site"/"data"
    save(data/"official_snapshot.csv",[
        dict(stock_id="8064",stock_name="東捷",market="上櫃",asof="2026-10-22"),
        dict(stock_id="3533",stock_name="嘉澤",market="上市",asof="2026-10-22")])
    v=dict(stock_id="8064",market="上櫃",asof="2026-10-22",
       pe_ratio="12",pb_ratio="2",dividend_yield_pct="1.5",source_status="ok",
       source_sha256="a"*64,source_url="https://example.org/valuation",
       first_seen_utc="2026-10-26T12:00:00+00:00")
    f=dict(stock_id="8064",market="上櫃",source_asof="2026-10-25",
       chairman_is_general_manager="false",source_status="ok",
       source_sha256="b"*64,source_url="https://example.org/governance",
       first_seen_utc="2026-10-26T12:01:00Z")
    save(data/"f2_valuation_29e.csv",[v])
    save(data/"f3_governance_29e.csv",[f])
    return v,f

class PITAudit29F(unittest.TestCase):
    def test_three_clocks_never_inferred(self):
        clock=dt.datetime(2026,10,26,14,tzinfo=UTC)
        old={"_report_day":"2026-10-22","source_status":"ok",
             "first_seen_utc":"2026-10-26T12:00:00Z"}
        self.assertEqual(audit_row(old,"2026-10-22",clock),"first_observed_after_price_cutoff")
        old["_report_day"]="2026-10-25"
        self.assertEqual(audit_row(old,"2026-10-22",clock),"source_report_after_price")
        old["_report_day"]="2026-10-20";old["first_seen_utc"]="2026-10-21T08:00:00Z"
        self.assertEqual(audit_row(old,"2026-10-22",clock),"official_publication_time_unverified")
        old["first_seen_utc"]="2026-11-03T10:00:00Z"
        self.assertEqual(audit_row(old,"2026-10-22",clock),"capture_time_in_future")
        self.assertIsNone(utc_instant("2026-10-26T08:00:00")) # No implied timezone
        self.assertEqual(audit_row({},"2026-10-22",clock),"no_source")
    def test_end_to_end_archive_first_seen_and_revision_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            v,f=sample(root)
            clock=dt.datetime(2026,10,26,14,tzinfo=UTC)
            records,versions,meta=capture(root,clock)
            self.assertEqual(len(records),2)
            self.assertEqual(len(versions),2)
            self.assertEqual(meta["new_versions_this_run"],2)
            self.assertEqual(meta["strict_backtest_eligible"],0)
            focus=next(x for x in records if x["stock_id"]=="8064")
            self.assertEqual(focus["F2_pit_status"],"first_observed_after_price_cutoff")
            self.assertEqual(focus["F3_pit_status"],"source_report_after_price")
            self.assertEqual(focus["F2_usable_for_backtest"],"false")
            self.assertEqual(focus["F2_publication_at_utc"],"")
            self.assertEqual(focus["F2_observed_first_at_utc"],"2026-10-26T12:00:00+00:00")
            missing=next(x for x in records if x["stock_id"]=="3533")
            self.assertEqual(missing["F2_pit_status"],"no_source")
            self.assertEqual(missing["F3_pit_status"],"no_source")
            records2,versions2,meta2=capture(root,clock)
            self.assertEqual(len(versions2),2)
            self.assertEqual(meta2["new_versions_this_run"],0)
            # Later official source version must append rather than overwrite.
            v["pe_ratio"]="22"
            v["source_sha256"]="c"*64
            v["first_seen_utc"]="2026-10-27T01:00:00Z"
            save(root/"site"/"data"/"f2_valuation_29e.csv",[v])
            rows3,history3,meta3=capture(root,dt.datetime(2026,10,27,12,tzinfo=UTC))
            self.assertEqual(len(history3),3)
            self.assertEqual(meta3["new_versions_this_run"],1)
            old_ver=[x for x in history3 if x["factor"]=="F2" and x["raw_source_sha256"]=="a"*64][0]
            self.assertEqual(json.loads(old_ver["observed_value_json"])["pe_ratio"],"12")
            self.assertEqual(old_ver["observed_first_at_utc"],"2026-10-26T12:00:00+00:00")
            self.assertEqual(sum(x["historical_backtest_eligible"]=="true" for x in history3),0)
            self.assertTrue((root/"site"/"data"/"pit_f2f3_meta_29f.json").is_file())
            # Source failure retains the ledger and labels the latest record stale.
            v["source_status"]="stale_backup"
            save(root/"site"/"data"/"f2_valuation_29e.csv",[v])
            records4,old_history,meta4=capture(root,dt.datetime(2026,10,28,12,tzinfo=UTC))
            self.assertEqual(meta4["new_versions_this_run"],0)
            self.assertEqual(len(old_history),3)
            self.assertEqual(next(x for x in records4 if x["stock_id"]=="8064")["F2_pit_status"],"stale_or_unverified_snapshot")
    def test_same_sha_conflicting_value_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);v,_=sample(root)
            clock=dt.datetime(2026,10,26,14,tzinfo=UTC)
            capture(root,clock)
            v["pe_ratio"]="88"
            save(root/"site"/"data"/"f2_valuation_29e.csv",[v])
            with self.assertRaisesRegex(ValueError,"conflicting raw values"):
                capture(root,clock)
    def test_wrong_first_seen_cannot_be_asof_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);v,f=sample(root)
            v["first_seen_utc"]="2026-11-09T12:00:00Z"
            save(root/"site"/"data"/"f2_valuation_29e.csv",[v])
            rows,history,m=capture(root,dt.datetime(2026,10,26,14,tzinfo=UTC))
            self.assertEqual(m["factors"]["F2"]["record_future_first_seen"],1)
            self.assertEqual(len(history),1) # F3 still archived, future F2 not accepted
            self.assertEqual(next(x for x in rows if x["stock_id"]=="8064")["F2_pit_status"],"capture_time_in_future")

if __name__=="__main__":unittest.main()
