import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.audit_event_bodies_29s import build,revenue_period_candidate

FIRST="2026-10-27T00:28:39+00:00"
def event_key(market,row):
    import hashlib
    return hashlib.sha256("|".join((market,row["公司代號"],row["發言日期"],row["發言時間"],row["主旨 "])).encode()).hexdigest()[:32]
def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator="\n")
        w.writeheader();w.writerows(rows)
def official_event(title,body):
    return {"公司代號":"8064","公司名稱":"東捷","發言日期":"1151026",
        "發言時間":"170320","主旨 ":title,"符合條款":"第10款",
        "事實發生日":"1151026","說明":body}
def setup_case(folder,title,body):
    root=Path(folder);data=root/"site"/"data";data.mkdir(parents=True)
    rawrow=official_event(title,body)
    content=json.dumps([rawrow],ensure_ascii=False).encode()
    sha=hashlib.sha256(content).hexdigest()
    source=root/"history_data"/"material_event_sources_29q"/"上櫃"/(sha+".json")
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_bytes(content)
    source.with_suffix(".first_seen").write_text(FIRST+"\n",encoding="utf-8")
    ev=dict(event_key=event_key("上櫃",rawrow),stock_id="8064",stock_name="東捷",market="上櫃",
        source_speech_at_taipei="2026-10-26T17:03:20+08:00",
        event_title=title,source_payload_sha256=sha,observed_first_at_utc=FIRST)
    write_csv(data/"material_events_29q.csv",[ev])
    return root,source,ev

class BodyEvidenceTests(unittest.TestCase):
    def test_revenue_period_text_not_release_proof(self):
        self.assertEqual(revenue_period_candidate("公告115年9月合併月營收","1.本月營業收入情形"),
                         ("2026-09","text_only_period_not_verified"))
        self.assertEqual(revenue_period_candidate("公告月營收","1.115年9月營收；2.115年8月營收"),
                         ("","ambiguous_multiple_months"))
        self.assertEqual(revenue_period_candidate("公告取得設備","1.最近期財務報表115年9月"),
                         ("","reporting_period_missing"))
        self.assertEqual(revenue_period_candidate("公告月營收","未列資料期間"),
                         ("","reporting_period_missing"))

    def test_exact_archived_raw_body_and_factor_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            title="公告本公司115年9月合併月營收"
            body="1.115年9月營業收入 123,456仟元。2.資料另行公告。"
            root,source,ev=setup_case(tmp,title,body)
            entries,meta=build(root)
            self.assertEqual(len(entries),1)
            e=entries[0]
            self.assertEqual(e["body_archive_status"],"original_payload_validated")
            self.assertEqual(e["body_sha256"],hashlib.sha256(body.encode()).hexdigest())
            self.assertEqual(e["event_clause"],"第10款")
            self.assertEqual(e["fact_date_in_source"],"1151026")
            self.assertEqual(e["revenue_period_candidate"],"2026-09")
            self.assertEqual(e["related_financial_factor"],"REVENUE")
            self.assertEqual(e["body_variants_seen"],"1")
            self.assertEqual(e["financial_value_equivalence_verified"],"false")
            self.assertEqual(e["independent_first_publication_verified"],"false")
            self.assertEqual(e["history_eligible"],"false")
            self.assertEqual(meta["independently_verified_first_publications"],0)
            self.assertFalse(meta["model_scores_enabled"])
            again,_=build(root)
            self.assertEqual(entries,again,"unchanged input must render same audit")

    def test_asset_statement_with_financial_numbers_is_not_financial_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,source,ev=setup_case(tmp,"公告取得機器設備",
                "本公司於115年10月26日取得機器設備，共占最近期財務報表20%；"
                "月營收增長為市場推測，非本次申報事項")
            rows,meta=build(root)
            self.assertEqual(rows[0]["related_financial_factor"],"")
            self.assertEqual(rows[0]["revenue_period_candidate"],"")
            self.assertEqual(meta["explicit_subject_candidates"],0)
            self.assertEqual(meta["verified_financial_payload_equivalences"],0)

    def test_archive_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,source,ev=setup_case(tmp,"公告重大訊息","說明")
            source.write_bytes(b'[{"changed":true}]')
            with self.assertRaisesRegex(ValueError,"tampered archived"):
                build(root)

    def test_missing_first_seen_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,source,ev=setup_case(tmp,"公告重大訊息","說明")
            source.with_suffix(".first_seen").unlink()
            with self.assertRaisesRegex(ValueError,"lacks first_seen"):
                build(root)

    def test_original_version_mismatch_and_different_body_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,source,ev=setup_case(tmp,"公告本公司115年9月合併月營收",
                                     "115年9月營業收入 123,456仟元")
            # An archived later version with same event identity but changed body
            body2="115年9月營業收入 999,999仟元（更正版本）"
            changed=official_event(ev["event_title"],body2)
            raw=json.dumps([changed],ensure_ascii=False).encode()
            sha=hashlib.sha256(raw).hexdigest()
            later=source.with_name(sha+".json")
            later.write_bytes(raw)
            later.with_suffix(".first_seen").write_text("2026-10-28T00:00:00+00:00\n",encoding="utf-8")
            rows,meta=build(root)
            self.assertEqual(rows[0]["body_variants_seen"],"2")
            self.assertIn("same_event_multiple_body_versions",rows[0]["review_blockers"])
            self.assertEqual(meta["same_event_revisions"],1)
            self.assertEqual(rows[0]["history_eligible"],"false")
            # Modify original event's first-seen metadata; never silently recover.
            data=root/"site"/"data"/"material_events_29q.csv"
            write_csv(data,[{**ev,"observed_first_at_utc":"2026-10-24T00:00:00+00:00"}])
            rows,_=build(root)
            self.assertEqual(rows[0]["body_archive_status"],"first_seen_version_mismatch")
            self.assertEqual(rows[0]["financial_value_equivalence_verified"],"false")
if __name__=="__main__":
    unittest.main()
