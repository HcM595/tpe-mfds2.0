import datetime as dt
import tempfile
import unittest
import csv
import json
from pathlib import Path
from scripts.build_factor_evidence_29a import (
    FACTOR_IDS,HEAD,STATES,eligibility,build_row,build
)

def prices(n=125,turnover=40_000_000,asof="2026-10-22"):
    # contiguous calendar days are deliberately NOT asserted official sessions
    end=dt.date.fromisoformat(asof)
    return [{"date":(end-dt.timedelta(days=n-i-1)).isoformat(),
             "close":str(100+i),"trade_value_twd":str(turnover)} for i in range(n)]

def sample(id="8064"):
    asof="2026-10-22"
    stock={"stock_id":id,"stock_name":"測試","market":"上櫃","asof":asof}
    master={"stock_id":id,"market":"上櫃","sector":"電子"}
    f={"stock_id":id,"asof":asof,"foreign_20d_volume_ratio_pct":"0","trust_20d_volume_ratio_pct":"0","foreign_5d_volume_ratio_pct":"0","trust_5d_volume_ratio_pct":"0","s1_5d_end":asof,
       "s1_20d_end":asof,"s3_momentum20_raw_pct":"0","s3_momentum60_raw_pct":"0"}
    industry={"stock_id":id,"asof":asof,"industry_relative20_raw_pp":"0",
              "industry_relative60_raw_pp":"1"}
    revenue={"stock_id":id,"revenue_period":"2026-09","table_date":"2026-10-17",
             "first_seen_utc":"2026-10-26T06:00:00+00:00"}
    income={"stock_id":id,"report_period":"2026Q2"}
    cash={"stock_id":id,"report_period":"2026Q2","source_status":"ok"}
    ytd={"stock_id":id,"report_period":"2026Q2","income_ytd_net_profit_raw":"123",
         "cashflow_period_matched":"true"}
    return stock,master,f,industry,revenue,income,cash,ytd

def files(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)

class OriginalFactorCoverage29A(unittest.TestCase):
    def test_eligibility_120_sessions_and_20d_mean(self):
        p=prices()
        r=eligibility(p,"2026-10-22",True)
        self.assertEqual(r["basic_data_eligible"],"true")
        self.assertEqual(r["avg20_trade_value_twd"],40_000_000)
        self.assertEqual(eligibility(p[:119],p[118]["date"],True)["basic_data_status"],"歷史資料不足")
        low=p[:];low[-1]=dict(low[-1],trade_value_twd="0")
        self.assertEqual(eligibility(low,"2026-10-22",True)["basic_data_eligible"],"true")
        below=prices(turnover=29_000_000)
        self.assertEqual(eligibility(below,"2026-10-22",True)["basic_data_status"],"流動性未達門檻")
        one_missing=p[:];one_missing[-4]=dict(one_missing[-4],trade_value_twd="")
        self.assertEqual(eligibility(one_missing,"2026-10-22",True)["basic_data_status"],"近20日成交額資料不足")
        self.assertEqual(eligibility(p,"2026-10-23",True)["basic_data_status"],"歷史資料尚未對齊最新收盤日")
        self.assertEqual(eligibility(p,"2026-10-22",False)["basic_data_eligible"],"false")
    def test_all_twelve_explicitly_present_and_no_scores(self):
        stock,master,f,industry,rev,inc,cf,ytd=sample()
        row=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,{"holder_asof":"2026-10-22"},{})
        self.assertEqual(tuple(x for x in FACTOR_IDS),("M1","M2","M3","I1","I2","I3","F1","F2","F3","S1","S2","S3"))
        self.assertEqual(row["I3_state"],"descriptive")
        self.assertEqual(row["F1_state"],"descriptive")
        self.assertEqual(row["S1_state"],"descriptive")
        self.assertEqual(row["S3_state"],"descriptive")
        self.assertEqual(row["M1_state"],"no_data")
        self.assertEqual(row["F2_state"],"no_data")
        self.assertEqual(row["model_eligible"],"false")
        self.assertEqual(row["factor_coverage_initial_60_pass"],"false")
        self.assertEqual(row["verified_factor_count"],0)
        self.assertEqual(row["source_postdates_price"],"true")
        self.assertTrue(all(row[x+"_state"] in STATES for x in FACTOR_IDS))
        self.assertEqual([k for k in HEAD if k.endswith("_state")].__len__(),12)
    def test_official_macro_observations_still_not_verified_factors(self):
        stock,master,f,industry,rev,inc,cf,ytd=sample()
        macro={"M1":{"observation_period":"202608","composite_score":41,"light":"紅"},
               "M2":{"export_period":"202608","export_yoy_pct":12.4,
                     "order_direction_index":51.8},
               "sources":{"ndc":{"first_seen_utc":"2026-10-26T08:00:00+00:00"},
                          "cbc":{"first_seen_utc":"2026-10-26T08:00:00+00:00"}}}
        row=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,{}, {},macro,
                      {"date":"2026-10-22","usd_twd_close":"30.5"})
        self.assertEqual(row["M1_state"],"descriptive")
        self.assertEqual(row["M1_asof"],"2026-08-31")
        self.assertEqual(row["M2_state"],"partial")
        self.assertEqual(row["M3_state"],"partial")
        self.assertEqual(row["M3_asof"],"2026-10-22")
        self.assertEqual(row["source_postdates_price"],"true")
        self.assertEqual(row["verified_factor_count"],0)
        self.assertEqual(row["model_eligible"],"false")
        self.assertEqual(row["prediction_enabled"],"false")
        future=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,{}, {},
                         {"M1":{"observation_period":"202611","composite_score":40,"light":"紅"}}, {})
        self.assertEqual(future["M1_state"],"no_data")

    def test_i1_requires_sector24_peers_and_no_i2_policy_beneficiary_guess(self):
        stock,master,f,industry,rev,inc,cf,ytd=sample()
        master["sector"]="24"
        breadth={"stock_id":stock["stock_id"],"market":"上櫃",
                 "sector":"24","period":"2026-09",
                 "table_date":"2026-10-17","growth_diffusion_pct":"60.0"}
        x=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,{}, {},
                    None,None,None,breadth)
        self.assertEqual(x["I1_state"],"partial")
        self.assertEqual(x["I1_asof"],"2026-10-17")
        self.assertEqual(x["I2_state"],"no_data")
        self.assertEqual(x["verified_factor_count"],0)
        self.assertEqual(x["model_eligible"],"false")
        master["sector"]="27"
        unrelated=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,{}, {},
                    None,None,None,breadth)
        self.assertEqual(unrelated["I1_state"],"no_data")
        master["sector"]="24"
        breadth["table_date"]="2026-10-27"
        future=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,{}, {},
                    None,None,None,breadth)
        self.assertEqual(future["I1_state"],"no_data")

    def test_s2_requires_dated_credit_evidence_not_holder_concentration(self):
        stock,master,f,industry,rev,inc,cf,ytd=sample()
        holder={"holder_asof":"2026-10-22"}
        row=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,holder,{})
        self.assertEqual(row["S2_state"],"no_data")
        credit={"stock_id":"8064","report_date":"2026-10-22",
                "margin_balance_units":"100","short_balance_units":"20",
                "first_seen_utc":"2026-10-26T08:00:00Z"}
        with_evidence=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,
                                holder,{},None,None,credit)
        self.assertEqual(with_evidence["S2_state"],"partial")
        self.assertEqual(with_evidence["S2_asof"],"2026-10-22")
        self.assertEqual(with_evidence["verified_factor_count"],0)
        self.assertEqual(with_evidence["model_eligible"],"false")
        credit["report_date"]="2026-10-27"
        future=build_row(stock,master,prices(),f,industry,rev,inc,cf,ytd,
                         holder,{},None,None,credit)
        self.assertEqual(future["S2_state"],"no_data")

    def test_missing_numeric_data_stays_absent_and_never_qualified(self):
        stock,master,f,ind,rev,inc,cf,ytd=sample()
        f["foreign_20d_volume_ratio_pct"]=""
        f["s3_momentum20_raw_pct"]=""
        f["s3_momentum60_raw_pct"]=""
        ind["industry_relative60_raw_pp"]=""
        ytd["cashflow_period_matched"]="false"
        out=build_row(stock,master,prices(),f,ind,rev,inc,cf,ytd,{},{})
        self.assertEqual(out["M3_state"],"no_data")
        self.assertEqual(out["I3_state"],"no_data")
        self.assertEqual(out["S3_state"],"no_data")
        self.assertEqual(out["S1_state"],"partial") # 20d missing a normalized foreign ratio
        self.assertEqual(out["F1_state"],"partial")
        self.assertEqual(out["S2_state"],"no_data")
    def test_end_to_end_with_real_manifest_contract_and_duplicate_roster(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            stock,master,f,ind,rev,inc,cf,ytd=sample()
            files(base/"site"/"data"/"official_snapshot.csv",[stock])
            files(base/"site"/"data"/"price_history.csv",[dict(p,stock_id="8064") for p in prices()])
            files(base/"history_data"/"ordinary_stock_master.csv",[master])
            for path,rows in [
                ("factor_observations_28b.csv",[f]),("industry_relative_28c.csv",[ind]),
                ("revenue_snapshot_28c.csv",[rev]),("income_snapshot_28f.csv",[inc]),
                ("cashflow_focus_28g.csv",[cf]),("mops_income_ytd_28i.csv",[ytd]),
                ("chip_signals.csv",[{"stock_id":"8064","holder_asof":"2026-10-22"}])
            ]:files(base/"site"/"data"/path,rows)
            manifest={"factors":[{"id":id,"status":"not_verified"} for id in FACTOR_IDS]}
            (base/"site"/"data"/"factor_readiness_28a.json").write_text(json.dumps(manifest),encoding="utf-8")
            rows,meta=build(base)
            self.assertEqual(len(rows),1)
            self.assertEqual(meta["stocks"],1)
            self.assertEqual(meta["basic_qualified"],1)
            self.assertEqual(meta["model_eligible_stocks"],0)
            self.assertFalse(meta["performance_probabilities_enabled"])
            manifest["factors"][0]["status"]="verified"
            (base/"site"/"data"/"factor_readiness_28a.json").write_text(json.dumps(manifest),encoding="utf-8")
            with self.assertRaises(ValueError):build(base)

if __name__=="__main__":unittest.main()
