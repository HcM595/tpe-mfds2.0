import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from scripts.collect_cashflow_focus_28g import parse_html,collect,HEAD

def html(year=115,end_month="06",current="196,004",prior="309,863"):
    end_day="30" if end_month!="03" else "31"
    return f"""<html><table>
    <tr><th>會計項目</th><th>{year}年01月01日至{year}年{end_month}月{end_day}日</th><th>{year-1}年01月01日至{year-1}年{end_month}月{end_day}日</th></tr>
    <tr><td>金額</td><td></td><td></td></tr>
    <tr><td>營業活動之現金流量－間接法</td><td></td><td></td></tr>
    <tr><td>營業活動之淨現金流入（流出）</td><td>{current}</td><td>{prior}</td></tr>
    </table></html>""".encode("utf-8")

def save(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)

class OfficialCashflow28G(unittest.TestCase):
    def test_cumulative_period_and_current_prior_values(self):
        data=parse_html(html(),2026,2)
        self.assertEqual(data["start"],"2026-01-01")
        self.assertEqual(data["end"],"2026-06-30")
        self.assertEqual(data["current"],"196004")
        self.assertEqual(data["prior"],"309863")
    def test_official_exact_unit_header_proves_only_cashflow_units(self):
        unit=html().replace("<tr><td>金額".encode("utf-8"), "<tr><th>單位：新台幣仟元</th></tr><tr><td>金額".encode("utf-8"))
        record=parse_html(unit,2026,2)
        self.assertTrue(record["unit_verified"])
        self.assertEqual(record["unit"],"新台幣千元")
        self.assertEqual(record["unit_source_text"],"單位：新台幣仟元")
        self.assertFalse(parse_html(html(),2026,2)["unit_verified"])
        mismatch=html().replace("<tr><td>金額".encode("utf-8"), "<tr><th>單位：美元</th></tr><tr><td>金額".encode("utf-8"))
        self.assertFalse(parse_html(mismatch,2026,2)["unit_verified"])

    def test_actual_mops_unclosed_th_unit_header(self):
        # Archived MOPS examples render <th>單位：新台幣仟元</tr> without </th>.
        # This is valid source evidence despite the imperfect HTML.
        raw=html().replace("<tr><td>金額".encode("utf-8"),
            "<tr><th class='tblHead' colspan='7'>單位：新台幣仟元</tr><tr><td>金額".encode("utf-8"))
        parsed=parse_html(raw,2026,2)
        self.assertEqual(parsed["unit_source_text"],"單位：新台幣仟元")
        self.assertEqual(parsed["unit"],"新台幣千元")
        self.assertTrue(parsed["unit_verified"])

    def test_incremental_batch_keeps_previous_rows_and_freshness(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            companies=[{"stock_id":str(5000+i),"market":"上市"} for i in range(16)]
            income=[{"stock_id":r["stock_id"],"stock_name":"測試股","market":"上市",
                     "report_period":"2026Q2","fiscal_year":"2026","fiscal_quarter":"2"}
                    for r in companies]
            save(base/"history_data"/"ordinary_stock_master.csv",companies)
            save(base/"site"/"data"/"income_snapshot_28f.csv",income)
            official=html().replace("<tr><td>金額".encode("utf-8"),"<tr><th>單位：新台幣仟元</th></tr><tr><td>金額".encode())
            records,m=collect(base,lambda *_:official,dt.datetime(2026,10,26,tzinfo=dt.timezone.utc))
            self.assertEqual(m["fresh_observations"],10)
            self.assertEqual(m["unit_verified_observations"],10)
            self.assertEqual(m["fresh_unit_verified"],10)
            self.assertEqual(len(records),10)
            records2,m2=collect(base,lambda *_:official,dt.datetime(2026,10,27,tzinfo=dt.timezone.utc))
            self.assertEqual(len(records2),16)
            self.assertEqual(m2["fresh_observations"],6)
            self.assertEqual(m2["unit_verified_observations"],16)
            self.assertEqual(sum(1 for r in records2 if r["source_status"]=="not_checked_this_run"),10)
            self.assertFalse(m2["factor_F1_eligible"])
            self.assertFalse(m2["cashflow_to_netincome_ratio_enabled"])
    def test_reject_wrong_period_and_non_numeric(self):
        with self.assertRaises(ValueError):parse_html(html(end_month="09"),2026,2)
        with self.assertRaises(ValueError):parse_html(html(year=114),2026,2)
        with self.assertRaises(ValueError):parse_html(html(current="--"),2026,2)
        with self.assertRaises(ValueError):parse_html(html()+b"x"*3000000,2026,2)
    def test_archive_and_preserve_backup_with_all_scores_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            save(base/"history_data"/"ordinary_stock_master.csv",
                 [{"stock_id":"8064","market":"上櫃"},{"stock_id":"3533","market":"上市"}])
            save(base/"site"/"data"/"income_snapshot_28f.csv",
                 [{"stock_id":"8064","stock_name":"東捷","market":"上櫃","report_period":"2026Q2","fiscal_year":"2026","fiscal_quarter":"2"},
                  {"stock_id":"3533","stock_name":"嘉澤","market":"上市","report_period":"2026Q2","fiscal_year":"2026","fiscal_quarter":"2"}])
            called=[]
            def fake(sid,year,quarter):
                called.append((sid,year,quarter));return html()
            data,meta=collect(base,fake,dt.datetime(2026,10,26,tzinfo=dt.timezone.utc),focus=("8064","3533"))
            self.assertEqual(len(data),2)
            self.assertEqual(meta["fresh_observations"],2)
            self.assertEqual(called,[("8064",2026,2),("3533",2026,2)])
            self.assertTrue(all(d["cashflow_netincome_ratio"]=="" and d["factor_F1_eligible"]=="false" for d in data))
            self.assertEqual(data[0]["cashflow_ytd_operating_raw"],"196004")
            self.assertEqual(data[0]["amount_unit_verified"],"false")
            self.assertFalse(meta["filing_timestamps_verified"])
            self.assertFalse(meta["cashflow_to_netincome_ratio_enabled"])
            self.assertEqual(len(list((base/"history_data"/"cashflow_sources"/"8064").glob("*.html"))),1)
            def broken(*args):raise OSError("temporarily unavailable")
            old,mm=collect(base,broken,dt.datetime(2026,10,27,tzinfo=dt.timezone.utc),focus=("8064","3533"))
            self.assertEqual(len(old),2)
            self.assertEqual(mm["fresh_observations"],0)
            self.assertEqual(old[0]["source_status"],"stale_backup")
    def test_no_fabricated_missing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            save(base/"history_data"/"ordinary_stock_master.csv",[{"stock_id":"8064","market":"上櫃"}])
            save(base/"site"/"data"/"income_snapshot_28f.csv",
                 [{"stock_id":"8064","stock_name":"東捷","market":"上櫃","report_period":"2026Q2","fiscal_year":"2026","fiscal_quarter":"2"}])
            data,meta=collect(base,lambda *_:html(current="-"),dt.datetime(2026,10,26,tzinfo=dt.timezone.utc),focus=("8064",))
            self.assertEqual(data,[])
            self.assertEqual(meta["fresh_observations"],0)
            self.assertEqual(meta["per_stock"]["8064"]["status"],"unavailable")

if __name__=="__main__":unittest.main()
