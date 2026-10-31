import csv,datetime as dt,json,tempfile,unittest
from pathlib import Path
from scripts.collect_f2f3_29e import parse,collect,peer_medians,roc

def master():
    return {str(3000+i):{"stock_id":str(3000+i),"market":"上市","sector":"24"} for i in range(110)} | {
            str(5000+i):{"stock_id":str(5000+i),"market":"上櫃","sector":"24"} for i in range(110)}
def fixture(market,kind,n=110):
    out=[]
    for i in range(n):
        if kind=="valuation" and market=="上市":
            out.append(dict(Date="1151022",Code=str(3000+i),Name="上市測試",PEratio=str(10+i/10),
                            PBratio=str(1+i/100),DividendYield="2.2"))
        elif kind=="valuation":
            out.append(dict(Date="1151022",SecuritiesCompanyCode=str(5000+i),CompanyName="上櫃測試",
                            PriceEarningRatio=str(20+i/10),PriceBookRatio=str(2+i/100),YieldRatio="1.5"))
        elif market=="上市":
            out.append({"出表日期":"1151025","公司代號":str(3000+i),"公司名稱":"上市測試",
                        "董事長是否兼任總經理":"兼任" if i%2 else "未兼任"})
        else:
            out.append({"Date":"1151025","SecuritiesCompanyCode":str(5000+i),"CompanyName":"上櫃測試",
                        "董事長是否兼任總經理":"兼任" if i%2 else "未兼任"})
    return out
def save(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

class OfficialF2F329ETests(unittest.TestCase):
    def test_roc_date_and_strict_valuation_and_peers(self):
        m=master()
        self.assertEqual(roc("1151022"),"2026-10-22")
        a=fixture("上市","valuation")
        a[0]["PEratio"]=""
        a[1]["PEratio"]="-3"
        a[2]["PBratio"]=""
        vals=parse(json.dumps(a,ensure_ascii=False).encode(),"上市","valuation",m,dt.date(2026,10,26),"sha","first")
        self.assertEqual(len(vals),110)
        self.assertEqual(vals[0]["pe_ratio"],"")
        self.assertEqual(vals[1]["pe_ratio"],"")
        self.assertEqual(vals[2]["pb_ratio"],"")
        peer_medians(vals)
        self.assertEqual(vals[0]["pe_peer_sample"],108)
        self.assertTrue(vals[0]["pb_peer_median"]>0)
        self.assertEqual(vals[0]["peer_f2_ready"],"false")
        self.assertEqual(vals[3]["peer_f2_ready"],"true")
        self.assertEqual(vals[3]["factor_F2_eligible"],"false")
        future=fixture("上市","valuation")
        for z in future:z["Date"]="1151122"
        with self.assertRaises(ValueError):
            parse(json.dumps(future,ensure_ascii=False).encode(),"上市","valuation",m,dt.date(2026,10,26),"sha","")
    def test_governance_factual_only_not_quality_score(self):
        m=master()
        governance=parse(json.dumps(fixture("上櫃","governance"),ensure_ascii=False).encode(),
            "上櫃","governance",m,dt.date(2026,10,26),"sha","first")
        self.assertEqual(len(governance),110)
        self.assertEqual(governance[0]["chairman_is_general_manager"],"false")
        self.assertEqual(governance[1]["chairman_is_general_manager"],"true")
        self.assertTrue(all(x["governance_quality_verified"]=="false" and
                            x["factor_F3_eligible"]=="false" for x in governance))
        bad=fixture("上櫃","governance")
        bad[0]["董事長是否兼任總經理"]="未知"
        self.assertEqual(len(parse(json.dumps(bad,ensure_ascii=False).encode(),
             "上櫃","governance",m,dt.date(2026,10,26),"sha","")),109)
    def test_full_archive_and_independent_stale_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            save(root/"history_data"/"ordinary_stock_master.csv",list(master().values()))
            def fetch(url):
                market="上市" if "twse.com.tw" in url else "上櫃"
                kind="governance" if "t187ap33" in url else "valuation"
                return json.dumps(fixture(market,kind),ensure_ascii=False).encode()
            vals,meta=collect(root,fetch,dt.datetime(2026,10,26,12,tzinfo=dt.timezone.utc))
            self.assertEqual(meta["valuation_stocks"],220)
            self.assertEqual(meta["governance_stocks"],220)
            self.assertEqual(meta["valuation_peer_comparable"],220)
            self.assertEqual(meta["chair_ceo_concurrent_count"],110)
            self.assertFalse(meta["F2_expected_earnings_surprise_verified"])
            self.assertFalse(meta["F3_governance_quality_factor_verified"])
            self.assertFalse(meta["backtested_probabilities_enabled"])
            self.assertTrue(list((root/"history_data"/"f2f3_official_sources"/"上市"/"valuation").glob("*.json")))
            self.assertEqual(vals["governance"][0]["source_status"],"ok")
            def fail_governance(url):
                if "t187ap33" in url:raise OSError("provider unavailable")
                return fetch(url)
            result,nextmeta=collect(root,fail_governance,
                dt.datetime(2026,10,27,12,tzinfo=dt.timezone.utc))
            self.assertEqual(nextmeta["sources"]["上市_governance"]["status"],"stale_backup")
            self.assertEqual(nextmeta["sources"]["上櫃_governance"]["status"],"stale_backup")
            self.assertEqual(nextmeta["sources"]["上市_valuation"]["status"],"ok")
            self.assertTrue(all(x["source_status"]=="stale_backup" for x in result["governance"]))
    def test_truncated_official_snapshot_retains_clearly_stale_archived_evidence(self):
        # A 110-row response after a 310-stock official source must not silently
        # overwrite hundreds of original date-stamped observations.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            m=master()
            for i in range(110,310):
                m[str(3000+i)]={"stock_id":str(3000+i),"market":"上市","sector":"24"}
                m[str(5000+i)]={"stock_id":str(5000+i),"market":"上櫃","sector":"24"}
            save(root/"history_data"/"ordinary_stock_master.csv",list(m.values()))
            def fetch_full(url):
                market="上市" if "twse.com.tw" in url else "上櫃"
                kind="governance" if "t187ap33" in url else "valuation"
                return json.dumps(fixture(market,kind,310),ensure_ascii=False).encode()
            original,first=collect(root,fetch_full,dt.datetime(2026,10,28,5,tzinfo=dt.timezone.utc))
            self.assertEqual(first["valuation_stocks"],620)
            oldest={r["stock_id"]:(r["asof"],r["source_sha256"],r["first_seen_utc"])
                    for r in original["valuation"]}
            def fetch_short(url):
                market="上市" if "twse.com.tw" in url else "上櫃"
                kind="governance" if "t187ap33" in url else "valuation"
                return json.dumps(fixture(market,kind,110),ensure_ascii=False).encode()
            output,meta=collect(root,fetch_short,dt.datetime(2026,10,29,5,tzinfo=dt.timezone.utc))
            self.assertEqual(meta["valuation_stocks"],620)
            self.assertEqual(meta["governance_stocks"],620)
            for market in ("上市","上櫃"):
                reason=meta["sources"][market+"_valuation"]
                self.assertEqual(reason["status"],"partial_official_source_stale_backup")
                self.assertEqual(reason["fresh_parsed_rows"],110)
            self.assertTrue(all(r["source_status"]=="stale_backup" for r in output["valuation"]))
            self.assertEqual({r["stock_id"]:(r["asof"],r["source_sha256"],r["first_seen_utc"])
                 for r in output["valuation"]},oldest)
            self.assertFalse(meta["F2_expected_earnings_surprise_verified"])
            self.assertFalse(meta["backtested_probabilities_enabled"])

if __name__=="__main__":unittest.main()
