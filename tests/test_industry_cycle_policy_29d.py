import csv,datetime as dt,json,tempfile,unittest
from pathlib import Path
from scripts.build_industry_cycle_29d import compute,build
from scripts.collect_policy_evidence_29d import prove,collect as policies

def master(n=10,market="上市",sector="24",start=2300):
    return [dict(stock_id=str(start+i),stock_name="測試股",market=market,sector=sector) for i in range(n)]
def rev(rows,period="2026-09",yoy=12,table="2026-10-17"):
    return [dict(stock_id=r["stock_id"],stock_name=r["stock_name"],market=r["market"],
      revenue_period=period,table_date=table,month_revenue_thousand_twd="123456",
      month_revenue_yoy_pct=str(yoy if isinstance(yoy,int) else yoy[i]),
      month_revenue_mom_pct="2.5",source_sha256="abc",first_seen_utc="2026-10-26T09:00:00Z") for i,r in enumerate(rows)]
def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

class RevenueBreadth29D(unittest.TestCase):
    def test_separate_market_and_sector_and_min_coverage(self):
        listing=master(10)
        tpex=master(8,"上櫃","24",5000)
        standard=master(5,"上市","27",6000)
        companies=listing+tpex+standard
        vals=rev(listing[:7],yoy=[10,5,-2,0,30,-6,2])+rev(tpex[:8],yoy=[-3,-5,7,8,-1,0,4,-2])+rev(standard)
        stocks,sectors,hist,revisions,skipped=compute(companies,vals,[],dt.date(2026,10,26))
        a=next(x for x in sectors if x["market"]=="上市" and x["sector"]=="24")
        b=next(x for x in sectors if x["market"]=="上櫃" and x["sector"]=="24")
        self.assertEqual(a["observed_peers"],7)
        self.assertEqual(a["observed_share"],.7)
        self.assertEqual(a["positive_yoy_peers"],4)
        self.assertEqual(a["growth_diffusion_pct"],round(400/7,2))
        self.assertEqual(b["growth_diffusion_pct"],37.5)
        self.assertEqual(a["has_inventory_evidence"],"false")
        self.assertEqual(a["cycle_phase_verified"],"false")
        self.assertEqual(len(stocks),20)
        weak,*,_=compute(companies,rev(listing[:4]),[],dt.date(2026,10,26))
        self.assertEqual(weak[0]["growth_diffusion_pct"],"")
        self.assertEqual(weak[0]["factor_I1_eligible"],"false")
    def test_wrong_period_future_and_null_yoy_never_zero(self):
        members=master(7)
        rows=rev(members)
        rows[0]["month_revenue_yoy_pct"]=""
        rows[1]["revenue_period"]="2026-11"
        rows[2]["table_date"]="2026-11-17"
        out,sectors,history,revisions,exclusions=compute(members,rows,[],dt.date(2026,10,26))
        self.assertEqual(len(out),4)
        self.assertEqual(out[0]["growth_diffusion_pct"],"")
        self.assertEqual(exclusions["missing_yoy"],1)
        self.assertEqual(exclusions["bad_or_future_month_or_table_date"],2)
    def test_history_first_seen_immutable_and_revisions_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            listing=master(6)
            write(root/"history_data"/"ordinary_stock_master.csv",listing)
            rows=rev(listing)
            write(root/"site"/"data"/"revenue_snapshot_28c.csv",rows)
            x,sector,meta=build(root,dt.datetime(2026,10,26,tzinfo=dt.timezone.utc))
            self.assertEqual(meta["revenue_archive_rows"],6)
            self.assertEqual(meta["revision_flags"],0)
            change=rev(listing,period="2026-10",table="2026-10-26")
            write(root/"site"/"data"/"revenue_snapshot_28c.csv",change)
            _,_,new=build(root,dt.datetime(2026,10,27,tzinfo=dt.timezone.utc))
            self.assertEqual(new["revenue_archive_rows"],12)
            self.assertFalse(new["industry_cycle_stage_verified"])
            hist=list(csv.DictReader(open(root/"site"/"data"/"revenue_history_29d.csv",encoding="utf-8")))
            self.assertEqual(len({r["period"] for r in hist}),2)
            change[0]["month_revenue_yoy_pct"]="99"
            change[0]["source_sha256"]="different"
            write(root/"site"/"data"/"revenue_snapshot_28c.csv",change)
            _,_,last=build(root,dt.datetime(2026,10,28,tzinfo=dt.timezone.utc))
            self.assertEqual(last["revision_flags"],1)
            retained=list(csv.DictReader(open(root/"site"/"data"/"revenue_history_29d.csv",encoding="utf-8")))
            self.assertEqual([r for r in retained if r["stock_id"]=="2300" and r["period"]=="2026-10"][0]["yoy_pct"],"12.0")
    def test_source_dates_not_model_eligibility(self):
        members=master(6)
        out,sectors,*_=compute(members,rev(members),[],dt.date(2026,10,26))
        self.assertEqual(sectors[0]["has_three_months"],"false")
        self.assertTrue(all(r["factor_I1_eligible"]=="false" for r in out))
        self.assertTrue(all(r["three_month_history"]=="false" for r in out))
class PolicyRegistry29D(unittest.TestCase):
    def test_policy_page_title_date_verified_no_stock_link(self):
        day="2026-09-01";title="亞灣智慧網通國際拓點與服務應用示範研發計畫"
        raw=("<html><body><h1>"+title+"</h1><p>發布日期："+day+"</p><p>"+("內容"*100)+"</p></body></html>").encode()
        self.assertTrue(prove(raw,title,day))
        self.assertFalse(prove(raw,title,"2026-09-14"))
        with tempfile.TemporaryDirectory() as d:
            e=[("TEST1",day,title,"https://www.ida.gov.tw/ctlr?PRO=policy.PolicyView&id=12053")]
            rows,meta=policies(Path(d),lambda _:raw,dt.datetime(2026,10,26,tzinfo=dt.timezone.utc),e)
            self.assertEqual(meta["source_verified_this_run"],1)
            self.assertEqual(rows[0]["source_status"],"ok")
            self.assertEqual(rows[0]["policy_relevance_to_stock_verified"],"false")
            self.assertFalse(meta["I2_factor_eligible"])
            self.assertFalse(meta["historic_backtest_enabled"])
            rows2,meta2=policies(Path(d),lambda _: (_ for _ in ()).throw(OSError("offline")),dt.datetime(2026,10,27,tzinfo=dt.timezone.utc),e)
            self.assertEqual(rows2[0]["source_status"],"stale_backup")
            self.assertEqual(meta2["source_verified_this_run"],0)
            future=policies(Path(d),lambda _:raw,dt.datetime(2026,10,26,tzinfo=dt.timezone.utc),
                       [("NEW","2026-11-14",title,e[0][-1])])
            self.assertEqual(future[0],[])
if __name__=="__main__":unittest.main()
