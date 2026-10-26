import datetime as dt
import math
import unittest

from scripts.compute_risk_observations_28d import evaluate, max_drawdown_from_closes

class Risk28DTest(unittest.TestCase):
    def setUp(self):
        self.days=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(68)]
        self.prices=[{"date":day,"close":str(100+i)} for i,day in enumerate(self.days)]
    def run_case(self,prices=None,days=None,asof=None,revenue=None):
        return evaluate("8064","東捷","上櫃",asof or self.days[-1],days or self.days,
                        prices if prices is not None else self.prices,
                        revenue if revenue is not None else {"8064"})
    def test_actual_prior_high_excludes_today(self):
        r=self.run_case()
        self.assertEqual(r["prior20_close_high"],166)
        self.assertEqual(r["prior20_close_low"],147)
        self.assertEqual(r["prior60_close_high"],166)
        self.assertEqual(r["risk_status"],"20／60日完整（未還原收盤）")
        self.assertGreater(r["distance_prior20_high_pct"],0)
        self.assertEqual(r["max_close_drawdown20_pct"],0)
        self.assertEqual(r["atr_available"],"false")
        self.assertEqual(r["f1_cashflow_profit_verified"],"false")
    def test_one_missing_close_blocks_all_windows_if_recent(self):
        r=self.run_case(prices=[x for x in self.prices if x["date"]!=self.days[-4]])
        self.assertEqual(r["prior20_close_high"],"")
        self.assertEqual(r["max_close_drawdown60_pct"],"")
        self.assertEqual(r["risk_status"],"歷史價格或日期缺漏，不產生20／60日參考價")
    def test_market_sessions_do_not_include_future(self):
        r=self.run_case(asof=self.days[-2])
        self.assertEqual(r["price_asof"],self.days[-2])
        self.assertEqual(r["last_close"],166)
    def test_missing_latest_market_calendar(self):
        r=self.run_case(days=self.days[:-1])
        self.assertEqual(r["last_close"],"")
        self.assertEqual(r["risk_status"],"市場日期未涵蓋本股價格快照日")
    def test_max_drawdown_is_peak_to_later_trough(self):
        self.assertEqual(max_drawdown_from_closes([100,120,90,110,88]),round((88/120-1)*100,4))
        self.assertEqual(max_drawdown_from_closes([50,60,70,80]),0)
    def test_no_revenue_coverage_is_not_false_f1(self):
        r=self.run_case(revenue=set())
        self.assertEqual(r["f1_revenue_available"],"false")
        self.assertEqual(r["f2_valuation_verified"],"false")

if __name__=="__main__":unittest.main()
