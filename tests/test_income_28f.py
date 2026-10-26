import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_income_28f import parse_rows, parse_date, collect, SOURCES

def items(prefix=2000,n=15):
    return [{"公司代號":str(prefix+i),"公司名稱":f"測試{i}","年度":"115","季別":"2",
             "出表日期":"1150817","本期淨利（淨損）":f"{120-i:,}"} for i in range(n)]

def masterfile(root):
    p=root/"history_data"/"ordinary_stock_master.csv"
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["stock_id","market"]);writer.writeheader()
        writer.writerows([{"stock_id":str((2000 if m=="上市" else 3000)+i),"market":m}
            for m in ("上市","上櫃") for i in range(15)])

class ProfitAudit28F(unittest.TestCase):
    def test_report_period_is_roc_and_not_filing_date(self):
        market={str(2000+i):{"market":"上市"} for i in range(15)}
        rows,issues=parse_rows(items(), "上市",market,"hash","2026-10-26T00:00:00Z",dt.date(2026,10,26))
        self.assertEqual(len(rows),15)
        self.assertEqual(rows[0]["report_period"],"2026Q2")
        self.assertEqual(rows[0]["table_date"],"2026-08-17")
        self.assertEqual(rows[0]["per_company_filing_time_verified"],"false")
        self.assertEqual(rows[0]["operating_cashflow_source_value"],"")
        self.assertEqual(rows[0]["cashflow_netincome_ratio"],"")
        self.assertEqual(rows[0]["amount_unit_verified"],"false")
        self.assertEqual(issues,{})
    def test_actual_tpex_english_identity_columns(self):
        master={str(3000+i):{"market":"上櫃"} for i in range(15)}
        rows=[{"Date":"1151026","Year":"115","Season":"2",
               "SecuritiesCompanyCode":str(3000+i),"CompanyName":f"上櫃公司{i}",
               "本期淨利（淨損）":"-1234.00"} for i in range(15)]
        observed,excluded=parse_rows(rows,"上櫃",master,"sha","2026-10-26T06:00:00Z",dt.date(2026,10,26))
        self.assertEqual(len(observed),15)
        self.assertEqual(observed[0]["report_period"],"2026Q2")
        self.assertEqual(observed[0]["table_date"],"2026-10-26")
        self.assertEqual(observed[0]["net_profit_source_value"],"-1234.00")
        self.assertEqual(excluded,{})
    def test_reject_conflicting_chinese_and_english_alias(self):
        master={str(3000+i):{"market":"上櫃"} for i in range(15)}
        rows=[{"Date":"1151026","出表日期":"1151025",
               "Year":"115","Season":"2","SecuritiesCompanyCode":str(3000+i),
               "CompanyName":f"股{i}","本期淨利（淨損）":"100"} for i in range(15)]
        with self.assertRaises(ValueError):
            parse_rows(rows,"上櫃",master,"sha","",dt.date(2026,10,26))

    def test_reject_untrusted_schema_and_future(self):
        market={str(2000+i):{"market":"上市"} for i in range(15)}
        with self.assertRaises(ValueError):
            parse_rows([{"公司代號":"2000"}],"上市",market,"sha","",dt.date(2026,10,26))
        future=items()
        for row in future:row["年度"]="118"
        with self.assertRaises(ValueError):
            parse_rows(future,"上市",market,"sha","",dt.date(2026,10,26))
        self.assertIsNone(parse_date("1150230"))
    def test_network_failure_retains_previous_validated_rows(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);masterfile(root)
            def fake(url):
                key=next(k for k,v in SOURCES.items() if v==url)
                rows=items(prefix=2000 if key=="上市" else 3000)
                return json.dumps(rows,ensure_ascii=False).encode("utf-8"),rows
            rows,meta=collect(root,fake,dt.datetime(2026,10,26,tzinfo=dt.timezone.utc))
            self.assertEqual(len(rows),30)
            self.assertEqual(meta["markets"]["上市"]["status"],"ok")
            self.assertFalse(meta["f1_factor_eligible"])
            self.assertFalse(meta["f1_cashflow_profit_ratio_enabled"])
            def offline(_):raise OSError("network temporarily unavailable")
            retained,m2=collect(root,offline,dt.datetime(2026,10,27,tzinfo=dt.timezone.utc))
            self.assertEqual(len(retained),30)
            self.assertEqual(m2["markets"]["上櫃"]["status"],"stale_backup")
    def test_missing_profit_never_imputed(self):
        master={str(2000+i):{"market":"上市"} for i in range(15)}
        records=items()
        records[0]["本期淨利（淨損）"]=""
        out,excluded=parse_rows(records,"上市",master,"sha","",dt.date(2026,10,26))
        self.assertEqual(len(out),14)
        self.assertEqual(excluded["missing_net_profit"],1)

if __name__=="__main__":unittest.main()
