import datetime as dt,io,json,tempfile,unittest,zipfile
from pathlib import Path
from scripts.collect_macro_29b import parse_ndc_zip,parse_cbc_json,ndc_resource_url,collect

def ndc_fixture():
    data={
    "景氣指標與燈號.csv":"Date,景氣對策信號綜合分數,景氣對策信號\n"+
      "\n".join(f"{y}{m:02d},{35 if m%2 else 41},{'黃紅' if m%2 else '紅'}"
               for y in (2024,2025,2026) for m in range(1,13) if (y,m)<=(2026,8)),
    "同時指標構成項目.csv":"Date,海關出口值(十億元)\n"+
      "\n".join(f"{y}{m:02d},{100+10*(y-2024)+m}"
               for y in (2024,2025,2026) for m in range(1,13) if (y,m)<=(2026,8)),
    "領先指標構成項目.csv":"Date,外銷訂單動向指數(以家數計)\n"+
      "\n".join(f"{y}{m:02d},{50+m/10}"
               for y in (2024,2025,2026) for m in range(1,13) if (y,m)<=(2026,8)),
    }
    # Source contract deliberately demands >=40 records, so add 2023 data.
    for name,body in list(data.items()):
        lines=body.splitlines()
        extra=[]
        for m in range(1,13):
            for _ in (0,):
                if "景氣指標" in name:extra.append(f"2023{m:02d},29,綠")
                elif "同時指標" in name:extra.append(f"2023{m:02d},85")
                else:extra.append(f"2023{m:02d},49.1")
        data[name]=lines[0]+"\n"+"\n".join(extra+lines[1:])
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
        for n,t in data.items():z.writestr(n,t)
    return b.getvalue()
def fx_fixture():
    d=dt.date(2026,8,1)
    entries=[{"日期":(d+dt.timedelta(days=i)).strftime("%Y%m%d"),"NTD_USD":f"{30+i*0.002:.3f}"}
        for i in range(110)]
    return json.dumps(entries).encode()
class Macro29B(unittest.TestCase):
    def test_source_whitelist(self):
        self.assertEqual(ndc_resource_url({"result":{"distribution":[{"resourceFormat":"ZIP","resourceDownloadUrl":"https://ws.ndc.gov.tw/Download.ashx?u=x"}]}}),"https://ws.ndc.gov.tw/Download.ashx?u=x")
        for url in ("http://ws.ndc.gov.tw/Download.ashx","https://example.com/Download.ashx","https://ws.ndc.gov.tw.other.test/Download.ashx"):
            with self.assertRaises(ValueError):ndc_resource_url({"result":{"distribution":[{"resourceFormat":"ZIP","resourceDownloadUrl":url}]}})
    def test_ndc_periods_score_export_yoy_and_orders_are_distinct(self):
        rows=parse_ndc_zip(ndc_fixture(),dt.date(2026,10,26))
        self.assertGreaterEqual(len(rows),40)
        last=rows[-1]
        self.assertEqual(last["period"],"202608")
        self.assertEqual(last["signal_score"],41)
        self.assertEqual(last["light"],"紅")
        self.assertGreater(last["export_yoy_pct"],0)
        self.assertGreater(last["export_order_direction_index"],0)
        self.assertNotEqual(last["export_yoy_pct"],last["export_order_direction_index"])
        self.assertEqual(parse_ndc_zip(ndc_fixture(),dt.date(2026,7,2))[-1]["period"],"202607")
    def test_fx_valid_dates_and_future_guard(self):
        fx=parse_cbc_json(fx_fixture(),dt.date(2026,10,26))
        self.assertGreater(len(fx),100)
        self.assertTrue(all(float(r["usd_twd_close"])>5 for r in fx))
        self.assertTrue(all(r["date"]<="2026-10-26" for r in fx))
    def test_archive_and_stale_provider_independence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            z=ndc_fixture();f=fx_fixture()
            api=b'{"result":{"distribution":[{"resourceFormat":"ZIP","resourceDownloadUrl":"https://ws.ndc.gov.tw/Download.ashx?u=fixture"}]}}'
            def fetch(url,*args):
                if "/api/v2/" in url:return api
                if "ws.ndc.gov.tw" in url:return z
                return f
            _,meta=collect(root,fetch,dt.datetime(2026,10,26,9,0,tzinfo=dt.timezone.utc))
            self.assertEqual(meta["status"],{"ndc":"ok","cbc":"ok"})
            self.assertEqual(meta["M1"]["composite_score"],41)
            self.assertIsNone(meta["M1"]["published_at"])
            self.assertFalse(meta["factor_scores_enabled"])
            self.assertFalse(meta["backtest_enabled"])
            self.assertFalse(meta["M2"]["export_orders_amount_yoy_verified"])
            self.assertTrue((root/"site"/"data"/"macro_ndc_history_29b.csv").is_file())
            self.assertTrue(list((root/"history_data"/"macro_sources"/"ndc").glob("*.zip")))
            def fx_offline(url,*args):
                if "cbc.gov.tw" in url:raise OSError("provider down")
                return fetch(url)
            _,later=collect(root,fx_offline,dt.datetime(2026,10,26,10,0,tzinfo=dt.timezone.utc))
            self.assertEqual(later["status"]["ndc"],"ok")
            self.assertEqual(later["status"]["cbc"],"stale_backup")
            self.assertIsNotNone(later["M3"]["usd_twd_close"])
            self.assertFalse(later["probability_enabled"])
if __name__=="__main__":unittest.main()
