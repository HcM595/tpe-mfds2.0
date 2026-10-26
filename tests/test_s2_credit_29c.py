import csv,datetime as dt,json,tempfile,unittest
from pathlib import Path
from scripts.collect_s2_credit_29c import twse_rows,tpex_rows,collect,roc,nonnegative

FIELDS=["代號","名稱","買進","賣出","現金償還","前日餘額","今日餘額","次一營業日限額","買進","賣出","現券償還","前日餘額","今日餘額","次一營業日限額","資券互抵","註記"]
def twse(n=110):
    return {"stat":"OK","date":"20261022","tables":[{"title":"信用交易統計","fields":["項目"],"data":[]},
        {"title":"融資融券彙總 (全部)","fields":FIELDS,
          "data":[[str(3000+i),f"測試{i}","1","2","0","12","9","100","0","1","0","4","5","100","0",""] for i in range(n)]}]}
def tpex(n=110):
    return [{"Date":"1151022","SecuritiesCompanyCode":str(5000+i),"CompanyName":f"測試{i}",
         "MarginPurchaseBalancePreviousDay":"20","MarginPurchaseBalance":"22",
         "ShortSaleBalancePreviousDay":"3","ShortSaleBalance":"1",
         "MarginPurchaseUtilizationRate":"10.25","ShortSaleUtilizationRate":"2.5"} for i in range(n)]
def save(path,records):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=records[0]);wr.writeheader();wr.writerows(records)
class CreditObservations29C(unittest.TestCase):
    def test_twse_strict_report_date_and_columns(self):
        master={str(3000+i):{"market":"上市"} for i in range(110)}
        rows,invalid=twse_rows(twse(),"2026-10-22",master,"sha","2026-10-26T08:00:00Z")
        self.assertEqual(len(rows),110)
        self.assertEqual(invalid,0)
        self.assertEqual(rows[0]["margin_change_units"],-3)
        self.assertEqual(rows[0]["short_change_units"],1)
        self.assertEqual(rows[0]["report_time_verified"],"false")
        with self.assertRaises(ValueError):twse_rows(twse(),"2026-10-23",master,"sha","")
        bad=twse();bad["tables"][1]["fields"][6]="未知欄"
        with self.assertRaises(ValueError):twse_rows(bad,"2026-10-22",master,"sha","")
    def test_tpex_roc_date_and_missing_not_zero(self):
        master={str(5000+i):{"market":"上櫃"} for i in range(110)}
        rows,n=tpex_rows(tpex(),master,"sha","", "2026-10-26")
        self.assertEqual(len(rows),110)
        self.assertEqual(rows[0]["report_date"],"2026-10-22")
        self.assertEqual(rows[0]["margin_change_units"],2)
        self.assertEqual(rows[0]["short_change_units"],-2)
        self.assertEqual(rows[0]["margin_utilization_pct_raw"],10.25)
        broken=tpex();broken[0]["ShortSaleBalance"]=""
        out,count=tpex_rows(broken,master,"sha","", "2026-10-26")
        self.assertEqual(len(out),109)
        self.assertEqual(count,1)
        self.assertIsNone(nonnegative(""))
        self.assertEqual(roc("1151022"),"2026-10-22")
    def test_end_to_end_no_daytrade_or_sentiment_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            save(root/"history_data"/"ordinary_stock_master.csv",
                 [{"stock_id":str(3000+i),"market":"上市"} for i in range(110)]+
                 [{"stock_id":str(5000+i),"market":"上櫃"} for i in range(110)])
            save(root/"site"/"data"/"official_snapshot.csv",
                 [{"stock_id":"3533","asof":"2026-10-22","market":"上市"},
                  {"stock_id":"8064","asof":"2026-10-22","market":"上櫃"}])
            def fake(url):
                return json.dumps(twse() if "twse.com.tw" in url else tpex(),ensure_ascii=False).encode()
            rows,meta=collect(root,fake,dt.datetime(2026,10,26,9,0,tzinfo=dt.timezone.utc))
            self.assertEqual(len(rows),220)
            self.assertEqual(meta["fresh_records"],220)
            self.assertEqual(meta["sources"]["上市"]["status"],"ok")
            self.assertEqual(meta["sources"]["上櫃"]["status"],"ok")
            self.assertFalse(meta["per_stock_daytrade_volume_available"])
            self.assertFalse(meta["stock_sentiment_factor_verified"])
            self.assertFalse(meta["probabilities_enabled"])
            self.assertTrue(all(r["retail_sentiment_factor_eligible"]=="false" for r in rows))
            self.assertTrue(list((root/"history_data"/"s2_credit_sources"/"上市").glob("*.json")))
            def unavailable(url):raise OSError("network down")
            older,second=collect(root,unavailable,dt.datetime(2026,10,27,9,0,tzinfo=dt.timezone.utc))
            self.assertEqual(len(older),220)
            self.assertEqual(second["fresh_records"],0)
            self.assertTrue(all(r["source_status"]=="stale_backup" for r in older))
    def test_future_tpex_dates_rejected(self):
        master={str(5000+i):{"market":"上櫃"} for i in range(110)}
        bad=tpex();bad[0]["Date"]="1151121"
        rows,invalid=tpex_rows(bad,master,"sha","", "2026-10-26")
        self.assertEqual(len(rows),109)
        self.assertEqual(invalid,1)
if __name__=="__main__":unittest.main()
