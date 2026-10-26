import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from scripts.collect_mops_income_ytd_28i import parse_statement,collect

def fixture(year=115,quarter=2,header_unit="新台幣仟元",ytd="105,842",single="40,862"):
    ending={1:"03月31日",2:"06月30日",3:"09月30日",4:"12月31日"}[quarter]
    head=f"""{year}年第{quarter}季</th><th>{year-1}年第{quarter}季</th>
    <th>{year}年01月01日至{year}年{ending}</th><th>{year-1}年01月01日至{year-1}年{ending}"""
    return f"""<html><table>
      <tr><th>民國{year}年第{quarter}季</tr>
      <tr><th>單位：{header_unit}</tr>
      <tr><th>會計項目</th><th>{head}</th></tr>
      <tr><th></th><th>金額</th><th>%</th><th>金額</th><th>%</th>
          <th>金額</th><th>%</th><th>金額</th><th>%</th></tr>
      <tr><td>本期淨利（淨損）</td><td>{single}</td><td>7.37</td>
          <td>-21,146</td><td>-4.12</td><td>{ytd}</td><td>8.62</td>
          <td>-121,033</td><td>-11.74</td></tr>
    </table></html>""".encode("utf-8")

def save(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

class IncomePeriod28ITests(unittest.TestCase):
    def test_exact_ytd_vs_single_quarter(self):
        r=parse_statement(fixture(),2026,2)
        self.assertEqual(r["quarter"],"40862")
        self.assertEqual(r["current"],"105842")
        self.assertEqual(r["prior"],"-121033")
        self.assertEqual(r["end"],"2026-06-30")
        self.assertTrue(r["unit_verified"])
        self.assertEqual(r["unit"],"新台幣千元")
    def test_prevent_period_confusion_and_bad_units(self):
        with self.assertRaises(ValueError):parse_statement(fixture(quarter=3),2026,2)
        with self.assertRaises(ValueError):parse_statement(fixture(ytd="--"),2026,2)
        x=parse_statement(fixture(header_unit="美元"),2026,2)
        self.assertFalse(x["unit_verified"])
        self.assertEqual(x["unit"],"")
        double=fixture().replace("單位：新台幣仟元</tr>".encode(),
            "單位：新台幣仟元</tr><tr><th>單位：新台幣仟元</tr>".encode())
        self.assertFalse(parse_statement(double,2026,2)["unit_verified"])
    def test_source_archive_alignment_and_no_f1(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            ids=["8064","3533"]
            save(base/"site"/"data"/"income_snapshot_28f.csv",
                 [dict(stock_id=sid,stock_name="測試股",market="上櫃",
                       report_period="2026Q2",fiscal_year="2026",
                       fiscal_quarter="2") for sid in ids])
            save(base/"site"/"data"/"cashflow_focus_28g.csv",
                 [dict(stock_id=sid,report_period="2026Q2",
                       cashflow_period_start="2026-01-01",
                       cashflow_period_end="2026-06-30",
                       amount_unit_verified="true",cashflow_unit="新台幣千元")
                   for sid in ids])
            rows,m=collect(base,lambda *_:fixture(),
                           dt.datetime(2026,10,26,tzinfo=dt.timezone.utc),
                           stocks=tuple(ids))
            self.assertEqual(len(rows),2)
            self.assertEqual(m["fresh_ytd_unit_period_aligned"],2)
            self.assertTrue(all(x["cashflow_period_matched"]=="true" for x in rows))
            self.assertTrue(all(x["net_profit_cf_ratio"]=="" and
                                x["factor_F1_eligible"]=="false" for x in rows))
            self.assertFalse(m["f1_factor_enabled"])
            self.assertFalse(m["point_in_time_backtest_enabled"])
            self.assertEqual(len(list((base/"history_data"/"mops_income_sources"/"8064").glob("*.html"))),1)
            stale,mm=collect(base,lambda *_:(_ for _ in ()).throw(OSError("offline")),
                dt.datetime(2026,10,27,tzinfo=dt.timezone.utc),stocks=tuple(ids))
            self.assertEqual(len(stale),2)
            self.assertEqual(mm["fresh_success"],0)
            self.assertTrue(all(x["source_status"]=="stale_backup" for x in stale))
    def test_misaligned_source_dates_and_units_do_not_pass(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            save(base/"site"/"data"/"income_snapshot_28f.csv",
                 [dict(stock_id="8064",stock_name="東捷",market="上櫃",
                       report_period="2026Q2",fiscal_year="2026",fiscal_quarter="2")])
            save(base/"site"/"data"/"cashflow_focus_28g.csv",
                 [dict(stock_id="8064",report_period="2026Q2",
                       cashflow_period_start="2026-01-01",
                       cashflow_period_end="2026-03-31",
                       amount_unit_verified="false",cashflow_unit="")])
            rows,m=collect(base,lambda *_:fixture(),
                           dt.datetime(2026,10,26,tzinfo=dt.timezone.utc),stocks=("8064",))
            self.assertEqual(rows[0]["cashflow_period_matched"],"false")
            self.assertEqual(rows[0]["net_profit_cf_ratio"],"")
            self.assertEqual(m["fresh_ytd_unit_period_aligned"],0)

if __name__=="__main__":unittest.main()
