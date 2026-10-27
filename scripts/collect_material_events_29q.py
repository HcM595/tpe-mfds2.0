#!/usr/bin/env python3
"""2.9Q official material-disclosure observations, separate from F2/F3/revenue.

The two official daily material-information API tables may contain a company
speech DATE and TIME. Those fields are labeled as the source's speech time;
they are NOT independently verified first-publication times for the figures
in F2 valuation, F3 governance or company monthly revenue.
Failure and schema drift are exposed, not replaced with inferred events.
"""
import csv
import datetime as dt
import hashlib
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Taipei")
URLS={
    "上市":"https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
    "上櫃":"https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O",
}
FIELDS=["event_key","stock_id","stock_name","market","source_speech_day",
        "source_speech_clock","source_speech_at_taipei","event_title",
        "source_url","source_payload_sha256","observed_first_at_utc",
        "source_day_and_time_parsed","event_first_publication_verified",
        "matched_factor","factor_release_time_eligible","notes"]
MAX_BYTES=7_000_000
NEEDED={"stock_id":("公司代號","SecuritiesCompanyCode","Code"),
        "stock_name":("公司名稱","CompanyName","Name"),
        "speech_day":("發言日期","SpeechDate"),
        "speech_time":("發言時間","SpeechTime"),
        "title":("主旨","主旨 ","Subject")}
def read(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator="\n",extrasaction="ignore")
        w.writeheader();w.writerows(rows)
def roc_day(raw):
    s=str(raw or "").strip()
    if not s.isdigit() or len(s) not in (7,8):return ""
    try:
        y=int(s[:3])+1911 if len(s)==7 else int(s[:4])
        day=s[-4:]
        parsed=dt.date(y,int(day[:2]),int(day[2:]))
        return parsed.isoformat()
    except ValueError:return ""
def speech_clock(raw):
    s=str(raw or "").strip()
    # Source time may be unpadded; reject ambiguity beyond six digits.
    if not s.isdigit() or len(s)>6 or not s:return ""
    s=s.zfill(6)
    try:
        h,m,sec=int(s[:2]),int(s[2:4]),int(s[4:6])
        dt.time(h,m,sec)
    except ValueError:return ""
    return f"{h:02d}:{m:02d}:{sec:02d}"
def key_value(row,which):
    for field in NEEDED[which]:
        if field in row:return str(row[field] or "").strip()
    return ""
def parse(raw,market,payload_sha,first_seen,known=None):
    try:data=json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError,ValueError) as exc:raise ValueError("official JSON decoding failed") from exc
    if not isinstance(data,list):raise ValueError("material event API must return an array")
    if data and not isinstance(data[0],dict):raise ValueError("material event API rows must be objects")
    # Empty official daily results are permitted but marked no events in meta.
    if data and not all(any(k in data[0] for k in opts) for opts in NEEDED.values()):
        raise ValueError("official daily material-event API schema changed")
    output={}
    for row in data:
        if not isinstance(row,dict):continue
        sid=key_value(row,"stock_id")
        if not (sid.isdigit() and 4<=len(sid)<=6):continue
        if known is not None and (sid,market) not in known:continue
        name=key_value(row,"stock_name")
        title=key_value(row,"title")
        report=key_value(row,"speech_day")
        shown=key_value(row,"speech_time")
        day=roc_day(report)
        clock=speech_clock(shown)
        # A missing or unparseable speech time is preserved as missing; do
        # not derive it from the date, our first observation or current time.
        at=f"{day}T{clock}+08:00" if day and clock else ""
        identity="|".join((market,sid,report,shown,title))
        event_key=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        output[event_key]=dict(event_key=event_key,stock_id=sid,
            stock_name=name,market=market,source_speech_day=day,
            source_speech_clock=clock,source_speech_at_taipei=at,
            event_title=title[:360],source_url=URLS[market],
            source_payload_sha256=payload_sha,observed_first_at_utc=first_seen,
            source_day_and_time_parsed=str(bool(at)).lower(),
            event_first_publication_verified="false",matched_factor="",
            factor_release_time_eligible="false",
            notes="來源發言時刻僅供事件對照；未證明F2/F3/月營收財務版本首次公布時分")
    return sorted(output.values(),key=lambda x:(x["market"],x["stock_id"],x["source_speech_day"],x["source_speech_clock"],x["event_key"]))
def fetch(url):
    u=urllib.parse.urlsplit(url)
    if u.scheme!="https" or (u.hostname or "") not in ("openapi.twse.com.tw","www.tpex.org.tw") or not u.path.strip("/"):
        raise ValueError("untrusted material event origin")
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS material archive","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=35) as response:
        redirected=urllib.parse.urlsplit(response.geturl())
        if redirected.scheme!="https" or redirected.hostname!=u.hostname:
            raise ValueError("material API redirect outside source host")
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("material API payload above max bytes")
    return raw
def collect(root=ROOT,fetcher=fetch,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    if clock.tzinfo is None:raise ValueError("clock must include timezone")
    clock=clock.astimezone(dt.timezone.utc)
    data=root/"site"/"data";data.mkdir(parents=True,exist_ok=True)
    universe={(r.get("stock_id",""),r.get("market","")) for r in read(data/"factor_evidence_29a.csv")}
    if len(universe)<1:raise ValueError("missing stock universe")
    archive=root/"history_data"/"material_event_sources_29q"
    previous=read(data/"material_events_29q.csv")
    ledger={r["event_key"]:r for r in previous if r.get("event_key")}
    state={}
    new_count=0
    for market,url in URLS.items():
        try:
            raw=fetcher(url)
            if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise ValueError("invalid official response")
            digest=hashlib.sha256(raw).hexdigest()
            folder=archive/market
            source=folder/(digest+".json")
            captured_path=folder/(digest+".first_seen")
            if source.exists():
                # Existing same SHA must use originally captured timestamp.
                if not captured_path.is_file():
                    raise ValueError("immutable source version exists without first_seen timestamp")
                observed=captured_path.read_text(encoding="utf-8").strip()
                if not observed:raise ValueError("missing archived first capture")
            else:observed=clock.isoformat(timespec="seconds")
            parsed=parse(raw,market,digest,observed,universe)
            folder.mkdir(parents=True,exist_ok=True)
            if not source.is_file():
                source.write_bytes(raw)
                captured_path.write_text(observed+"\n",encoding="utf-8")
            for r in parsed:
                old=ledger.get(r["event_key"])
                if old is None:
                    ledger[r["event_key"]]=r
                    new_count+=1
                elif old["source_speech_day"]!=r["source_speech_day"] or old["source_speech_clock"]!=r["source_speech_clock"] or old["event_title"]!=r["event_title"]:
                    raise ValueError("event identity collision; manual review required")
                # Never rewrite original capture, title or event proof status.
            state[market]={"status":"ok","latest_events":len(parsed),"source_sha256":digest,"source_url":url}
        except (OSError,ValueError,UnicodeError,KeyError,TypeError) as exc:
            state[market]={"status":"unavailable","latest_events":0,"source_url":url,"reason":str(exc)[:220]}
    output=sorted(ledger.values(),key=lambda r:(r["market"],r["stock_id"],r["source_speech_day"],r["source_speech_clock"],r["event_key"]))
    write(data/"material_events_29q.csv",output)
    counts=Counter(r["market"] for r in output)
    meta={"version":"2.9Q","generated_at_taipei":clock.astimezone(TZ).isoformat(timespec="seconds"),
          "events_captured":len(output),"new_events_this_run":new_count,
          "events_by_market":dict(counts),"sources":state,
          "parseable_source_speech_clock":sum(r["source_day_and_time_parsed"]=="true" for r in output),
          "verified_first_publication_times":0,
          "events_mapped_to_F2_F3_revenue":0,"historical_factor_eligible":0,
          "model_scoring_enabled":False,"probability_enabled":False,
          "time_semantics":"發言日期／發言時間是官方重大訊息來源欄位；不得當作估值、公司治理或營收資料版本的獨立首次公布證明。",
          "archive_policy":"以來源原始位元組SHA256建不可覆寫版本，首次取得UTC獨立保存；遇來源或格式失敗不捏造資料。"}
    (data/"material_events_meta_29q.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return output,meta
if __name__=="__main__":
    a,m=collect()
    print("2.9Q material events",len(a),"new",m["new_events_this_run"],"source statuses",m["sources"])
