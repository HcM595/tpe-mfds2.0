import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_monthly_revenue_28c import (
    SOURCES, FIELDS, parse_source, iso_month, iso_date, collect
)
from scripts.compute_industry_relative_28c import calculate

def revenue_rows(prefix,count=12):
    return [{
        FIELDS["stock_id"]:str(prefix+i),FIELDS["stock_name"]:f"公司{i}",
        FIELDS["industry"]:"產業甲",FIELDS["period"]:"11509",
        FIELDS["table_date"]:"1151017",FIELDS["revenue"]:"1,234",
        FIELDS["yoy"]:"10.2",FIELDS["mom"]:"",}
        for i in range(count)]

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as fp:
        w=csv.DictWriter(fp,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)

class Revenue28CTest(unittest.TestCase):
    def test_roc_units_and_missing_growth(self):
        self.assertEqual(iso_month("11509"),"2026-09")
        self.assertEqual(iso_date("1151017"),"2026-10-17")
        master={str(3000+i):{"market":"上櫃"} for i in range(12)}
        out,excluded=parse_source(revenue_rows(3000),"上櫃",master,"abc",
                                  "2026-10-18T00:00:00Z",dt.date(2026,10,26))
        self.assertEqual(len(out),12)
        self.assertEqual(out[0]["month_revenue_thousand_twd"],1234)
        self.assertEqual(out[0]["month_revenue_mom_pct"],"")
        self.assertEqual(out[0]["disclosure_time_verified"],"false")
        self.assertEqual(out[0]["revenue_period"],"2026-09")
        self.assertEqual(excluded,{})
    def test_archive_both_markets_and_preserve_on_failure(self):
        with tempfile.TemporaryDirectory() as x:
            base=Path(x)
            masters=[{"stock_id":str(prefix+i),"market":market}
                     for prefix,market in [(2000,"上市"),(3000,"上櫃")]
                     for i in range(12)]
            write_csv(base/"history_data"/"ordinary_stock_master.csv",masters)
            def fake(url):
                market=next(k for k,v in SOURCES.items() if v==url)
                p=2000 if market=="上市" else 3000
                rows=revenue_rows(p)
                return json.dumps(rows,ensure_ascii=False).encode(),rows
            rows,meta=collect(base,fake,dt.datetime(2026,10,26,tzinfo=dt.timezone.utc))
            self.assertEqual(len(rows),24)
            self.assertEqual(meta["markets"]["上市"]["status"],"ok")
            self.assertFalse(meta["per_stock_publication_time_verified"])
            self.assertEqual(len(list((base/"history_data"/"revenue_sources"/"上市").glob("*.json"))),1)
            def broken(_):raise OSError("provider temporarily unreachable")
            kept,meta2=collect(base,broken,dt.datetime(2026,10,27,tzinfo=dt.timezone.utc))
            self.assertEqual(len(kept),24)
            self.assertEqual(meta2["markets"]["上櫃"]["status"],"stale_backup")
    def test_reject_future_month(self):
        bad=revenue_rows(2000)
        for r in bad:r[FIELDS["period"]]="11512"
        master={str(2000+i):{"market":"上市"} for i in range(12)}
        with self.assertRaises(ValueError):
            parse_source(bad,"上市",master,"abc","",dt.date(2026,10,26))

class Industry28CTest(unittest.TestCase):
    def test_same_market_and_day_medians(self):
        master=[];obs=[]
        for i in range(60):
            code=str(1000+i)
            sector="01" if i<6 else "02"
            master.append({"stock_id":code,"market":"上市","sector":sector})
            obs.append({"stock_id":code,"stock_name":"股","market":"上市","asof":"2026-10-22",
                        "s3_momentum20_raw_pct":"10" if i<6 else "0",
                        "s3_momentum60_raw_pct":"20" if i<6 else "0"})
        out=calculate(obs,master)
        record=next(x for x in out if x["stock_id"]=="1000")
        self.assertEqual(record["industry_relative20_raw_pp"],10)
        self.assertEqual(record["industry_relative60_raw_pp"],20)
        self.assertEqual(record["industry_peers_20"],6)
        self.assertEqual(record["factor_I3_verified"],"false")
    def test_small_industry_and_wrong_day_cannot_fake_strength(self):
        master=[{"stock_id":str(1000+i),"market":"上市","sector":"01" if i<3 else "02"} for i in range(60)]
        obs=[{"stock_id":str(1000+i),"market":"上市",
              "asof":"2026-10-22" if i!=59 else "2026-10-21",
              "s3_momentum20_raw_pct":"1","s3_momentum60_raw_pct":""} for i in range(60)]
        result=calculate(obs,master)
        self.assertEqual(next(x for x in result if x["stock_id"]=="1000")["industry_relative20_raw_pp"],"")
        self.assertEqual(next(x for x in result if x["stock_id"]=="1000")["industry_relative60_raw_pp"],"")

if __name__=="__main__":unittest.main()
