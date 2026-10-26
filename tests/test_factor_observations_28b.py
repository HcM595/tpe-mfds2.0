import unittest
import datetime as dt
from scripts.compute_factor_observations_28b import summarize_stock, number

class Observations28B(unittest.TestCase):
    def setUp(self):
        self.days=[(dt.date(2026, 1, 1)+dt.timedelta(days=i)).isoformat() for i in range(65)]
        self.prices=[{"date":d,"close":str(100+i),"volume_shares":"1000"}
                     for i,d in enumerate(self.days)]
        self.flows=[{"date":d,"foreign_net_shares":"100","trust_net_shares":"-50"}
                    for d in self.days]
    def calc(self, **kwargs):
        return summarize_stock("8064","東捷","上櫃",self.days[-1],kwargs.get("days",self.days),
                               kwargs.get("prices",self.prices),kwargs.get("flows",self.flows))
    def test_all_present(self):
        r=self.calc()
        self.assertEqual(r["s1_5d_end"],self.days[-1])
        self.assertEqual(r["s1_20d_end"],self.days[-1])
        self.assertAlmostEqual(r["foreign_20d_volume_ratio_pct"],10.0)
        self.assertAlmostEqual(r["trust_5d_volume_ratio_pct"],-5.0)
        self.assertEqual(r["s3_ma20_raw"],sum(range(145,165))/20)
        self.assertAlmostEqual(r["s3_momentum20_raw_pct"],(164/144-1)*100,places=4)
        self.assertTrue(r["s3_momentum60_raw_pct"]!="")
        self.assertEqual(r["risk_notes"].find("除權息調整")>=0,True)
    def test_missing_one_flow_day_blocks_20_day_and_5_day(self):
        r=self.calc(flows=[x for x in self.flows if x["date"]!=self.days[-2]])
        self.assertEqual(r["s1_5d_end"],"")
        self.assertEqual(r["s1_20d_end"],"")
        self.assertEqual(r["foreign_20d_volume_ratio_pct"],"")
    def test_missing_price_day_blocks_momentum(self):
        r=self.calc(prices=[x for x in self.prices if x["date"]!=self.days[-5]])
        self.assertEqual(r["s3_ma20_raw"],"")
        self.assertEqual(r["s3_momentum20_raw_pct"],"")
        self.assertEqual(r["s3_momentum60_raw_pct"],"")
    def test_stale_market_archive_blocks_results(self):
        r=self.calc(days=self.days[:-1])
        self.assertEqual(r["s1_status"],"市場日期參考未覆蓋快照日")
        self.assertEqual(r["s3_ma20_raw"],"")
    def test_missing_volume_does_not_become_zero(self):
        vals=[dict(p) for p in self.prices]
        vals[-1]["volume_shares"]=""
        r=self.calc(prices=vals)
        self.assertEqual(r["s1_5d_end"],"")
        self.assertTrue(r["s3_momentum20_raw_pct"]!="")
    def test_no_guess_on_bad_number(self):
        self.assertIsNone(number(""))
        self.assertIsNone(number("NaN"))

if __name__=="__main__":
    unittest.main()
