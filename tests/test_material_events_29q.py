import csv
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.collect_material_events_29q import (collect,parse,roc_day,speech_clock,URLS)

class MaterialDisclosureTests(unittest.TestCase):
    def test_roc_date_and_unpadded_source_time(self):
        self.assertEqual(roc_day("1151026"),"2026-10-26")
        self.assertEqual(roc_day("20261026"),"2026-10-26")
        self.assertEqual(roc_day("1150230"),"")
        self.assertEqual(speech_clock("54626"),"05:46:26")
        self.assertEqual(speech_clock("235959"),"23:59:59")
        self.assertEqual(speech_clock("246000"),"")
        self.assertEqual(speech_clock(""),"")

    def test_parse_requires_speech_time_and_never_promotes_factor(self):
        content=[{"公司代號":"8064","公司名稱":"東捷","發言日期":"1151026","發言時間":"54626",
                  "主旨 ":"公告公司重要事項"},
                 {"公司代號":"8064","公司名稱":"東捷","發言日期":"1151026","發言時間":"",
                  "主旨 ":"公告資訊時間待核"},
                 {"公司代號":"3533","公司名稱":"嘉澤","發言日期":"1151026","發言時間":"120000",
                  "主旨 ":"不在本測試市場"}]
        raw=json.dumps(content,ensure_ascii=False).encode()
        rows=parse(raw,"上櫃",hashlib.sha256(raw).hexdigest(),"2026-10-26T00:00:00+00:00",{("8064","上櫃")})
        self.assertEqual(len(rows),2)
        self.assertEqual([r["source_day_and_time_parsed"] for r in rows].count("true"),1)
        ok=next(r for r in rows if r["source_day_and_time_parsed"]=="true")
        self.assertEqual(ok["source_speech_at_taipei"],"2026-10-26T05:46:26+08:00")
        self.assertEqual(ok["event_first_publication_verified"],"false")
        self.assertEqual(ok["factor_release_time_eligible"],"false")
        self.assertEqual(ok["matched_factor"],"")
        missing=next(r for r in rows if r["source_day_and_time_parsed"]=="false")
        self.assertEqual(missing["source_speech_at_taipei"],"")
        with self.assertRaisesRegex(ValueError,"schema"):
            parse(b'[{"Date":"1151026","Code":"8064"}]',"上櫃","a"*64,"2026-10-26T00:00:00Z")

    def test_archival_version_first_seen_and_source_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=root/"site"/"data";data.mkdir(parents=True)
            with (data/"factor_evidence_29a.csv").open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["stock_id","stock_name","market"]);w.writeheader()
                w.writerow({"stock_id":"8064","stock_name":"東捷","market":"上櫃"})
                w.writerow({"stock_id":"2330","stock_name":"台積電","market":"上市"})
            twse=json.dumps([{"公司代號":"2330","公司名稱":"台積電","發言日期":"1151026",
                              "發言時間":"131500","主旨 ":"測試發布資訊"}],ensure_ascii=False).encode()
            tpex=json.dumps([{"公司代號":"8064","公司名稱":"東捷","發言日期":"1151026",
                              "發言時間":"90102","主旨 ":"測試重要事項"}],ensure_ascii=False).encode()
            payloads={URLS["上市"]:twse,URLS["上櫃"]:tpex}
            first=dt.datetime(2026,10,26,13,0,tzinfo=dt.timezone.utc)
            events,meta=collect(root,fetcher=lambda url:payloads[url],clock=first)
            self.assertEqual(len(events),2)
            self.assertEqual(meta["new_events_this_run"],2)
            self.assertEqual(meta["verified_first_publication_times"],0)
            self.assertEqual(meta["events_mapped_to_F2_F3_revenue"],0)
            self.assertFalse(meta["model_scoring_enabled"])
            self.assertTrue(all(r["factor_release_time_eligible"]=="false" for r in events))
            original={r["event_key"]:r["observed_first_at_utc"] for r in events}
            again,m2=collect(root,fetcher=lambda url:payloads[url],
                 clock=first+dt.timedelta(days=1))
            self.assertEqual(m2["new_events_this_run"],0)
            self.assertEqual({r["event_key"]:r["observed_first_at_utc"] for r in again},original)
            def fail_one(url):
                if url==URLS["上市"]:raise OSError("network disconnected")
                return payloads[url]
            stale,m3=collect(root,fetcher=fail_one,clock=first+dt.timedelta(days=2))
            self.assertEqual(len(stale),2,"source outage may not erase previously captured events")
            self.assertEqual(m3["sources"]["上市"]["status"],"unavailable")
            self.assertEqual(m3["verified_first_publication_times"],0)
            self.assertEqual(json.loads((data/"material_events_meta_29q.json").read_text())["events_captured"],2)

if __name__=="__main__": unittest.main()
