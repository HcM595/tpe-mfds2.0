#!/usr/bin/env python3
"""2.9D official MOEA IDA industry-policy event source registry.

This is an evidenced event catalogue, NOT a sector-impact mapping. Source
publication DATE is not time-of-day. No company receives a factor I2 score.
"""
import csv,datetime as dt,hashlib,json,re,urllib.parse,urllib.request
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parents[1]
EVENTS=[
 ("IDA-2026-09-01-AIWAN","2026-09-01","亞灣智慧網通國際拓點與服務應用示範研發計畫",
  "https://www.ida.gov.tw/ctlr?PRO=policy.PolicyView&id=12053"),
 ("IDA-2026-09-14-MINERALS","2026-09-14","關鍵礦物應用高值化推動計畫",
  "https://www.ida.gov.tw/ctlr?PRO=policy.PolicyView&id=12054")
]
OFFICIAL_FALLBACKS={
 "IDA-2026-09-01-AIWAN":("https://www.ida.gov.tw/ctlr?PRO=grant.DisclosureView&id=17246",)
}
COLUMNS=["event_id","official_publication_date","event_short_title","official_url",
         "source_status","raw_source_sha256","first_seen_utc","policy_relevance_to_stock_verified",
         "sector_causal_impact_verified","available_for_backtest",
         "source_note"]
class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,part):self.parts.append(part)
def fetch(url):
    u=urllib.parse.urlsplit(url)
    if u.scheme!="https" or u.hostname!="www.ida.gov.tw" or u.path!="/ctlr":
        raise ValueError("untrusted policy domain")
    request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS/2.9D public policy archive"})
    with urllib.request.urlopen(request,timeout=30) as response:
        raw=response.read(2_000_001)
        if response.geturl() and urllib.parse.urlsplit(response.geturl()).hostname!="www.ida.gov.tw":
            raise ValueError("policy source redirected outside official domain")
    if len(raw)>2_000_000:raise ValueError("official page too large")
    return raw
def prove(raw,title,date):
    if not isinstance(raw,bytes) or len(raw)<80 or len(raw)>2_000_000:return False
    text=raw.decode("utf-8-sig",errors="replace")
    parser=Text();parser.feed(text)
    clean=re.sub(r"\s+"," "," ".join(parser.parts))
    return title in clean and date in clean and "發布日期" in clean
def read(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def collect(root=BASE,fetcher=fetch,clock=None,events=EVENTS):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    today=clock.astimezone(ZoneInfo("Asia/Taipei")).date()
    data=root/"site"/"data";data.mkdir(parents=True,exist_ok=True)
    dest=data/"industry_policy_events_29d.csv"
    past={r["event_id"]:r for r in read(dest)}
    archived=root/"history_data"/"industry_policy_sources"
    out=[];statuses={}
    for eid,day,title,url in events:
        if dt.date.fromisoformat(day)>today:
            statuses[eid]="future_not_allowed";continue
        row={k:"" for k in COLUMNS}
        row.update(event_id=eid,official_publication_date=day,
                   event_short_title=title,official_url=url,
                   source_status="unavailable",policy_relevance_to_stock_verified="false",
                   sector_causal_impact_verified="false",
                   available_for_backtest="false",
                   source_note="僅是經濟部產業發展署正式公告事件；沒有實證的個別上市櫃公司受惠或當日可知時間，不計入I2分數")
        try:
            raw=None
            matched_url=""
            last_error=""
            for candidate in (url,)+OFFICIAL_FALLBACKS.get(eid,()):
                try:
                    payload=fetcher(candidate)
                    if not prove(payload,title,day):
                        raise ValueError("title and official publication date not both verified")
                    raw=payload
                    matched_url=candidate
                    break
                except (OSError,ValueError,UnicodeError) as ex:
                    last_error=str(ex)[:150]
            if raw is None:
                raise ValueError("no official event mirror passed source validation: "+last_error)
            digest=hashlib.sha256(raw).hexdigest()
            folder=archived/eid;folder.mkdir(parents=True,exist_ok=True)
            path=folder/(digest+".html")
            first=folder/(digest+".first_seen")
            if not path.is_file():
                path.write_bytes(raw)
                first.write_text(clock.isoformat(timespec="seconds")+"\n",encoding="utf-8")
            row.update(source_status="ok",official_url=matched_url,raw_source_sha256=digest,
                       first_seen_utc=first.read_text(encoding="utf-8").strip())
            statuses[eid]="ok"
        except (OSError,ValueError,UnicodeError) as ex:
            if eid in past and past[eid].get("source_status") in ("ok","stale_backup"):
                row.update(raw_source_sha256=past[eid].get("raw_source_sha256",""),
                           first_seen_utc=past[eid].get("first_seen_utc",""),
                           source_status="stale_backup")
            statuses[eid]=row["source_status"]
        out.append(row)
    with dest.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS,lineterminator="\n");writer.writeheader();writer.writerows(out)
    meta={
      "version":"2.9D","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
      "official_listings_checked":len(out),"source_verified_this_run":sum(r["source_status"]=="ok" for r in out),
      "status_by_event":statuses,"official_agency":"經濟部產業發展署",
      "mapping_company_sector_impact_verified":False,
      "publication_time_of_day_verified":False,"I2_factor_eligible":False,
      "policy_event_scores_enabled":False,"historic_backtest_enabled":False,
      "warning":"本版本只列出可核對的官方政策公告及來源；未核實個股符合申請資格、實際資金流入或受惠效果。日期不代表交易日開盤前已知，禁止據此加分或宣稱勝率。"}
    (data/"industry_policy_meta_29d.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("2.9D official industry policy events",meta["source_verified_this_run"],"of",len(out))
    return out,meta
if __name__=="__main__":collect()
