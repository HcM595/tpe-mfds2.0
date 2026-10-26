#!/usr/bin/env python3
"""2.9E: official TWSE/TPEx snapshot valuation and chair/CEO overlap.

P/E, P/B, dividend yield are descriptive quote ratios, NOT cheapness or forward
consensus estimates. Chair/CEO concurrent status is a factual disclosure and
NOT a proven governance quality factor. Cross-sector/market peer comparison
is forbidden; snapshots are not independently verified public-at time.
"""
import csv,datetime as dt,hashlib,json,math,statistics,urllib.request
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
URLS={
 "上市":{"valuation":"https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
         "governance":"https://openapi.twse.com.tw/v1/opendata/t187ap33_L"},
 "上櫃":{"valuation":"https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
         "governance":"https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap33_O"},
}
FIELD={
 ("上市","valuation"):("Date","Code","Name","PEratio","PBratio","DividendYield"),
 ("上櫃","valuation"):("Date","SecuritiesCompanyCode","CompanyName","PriceEarningRatio","PriceBookRatio","YieldRatio"),
 ("上市","governance"):("出表日期","公司代號","公司名稱","董事長是否兼任總經理"),
 ("上櫃","governance"):("Date","SecuritiesCompanyCode","CompanyName","董事長是否兼任總經理")
}
VALUE_COLUMNS=["stock_id","stock_name","market","sector","asof","pe_ratio","pb_ratio",
 "dividend_yield_pct","pe_peer_median","pb_peer_median","pe_peer_sample","pb_peer_sample",
 "source_status","source_url","source_sha256","first_seen_utc","quote_publication_at_verified",
 "earnings_period_verified","peer_f2_ready","factor_F2_eligible"]
GOV_COLUMNS=["stock_id","stock_name","market","sector","source_asof",
 "chairman_is_general_manager","chairman_general_manager_disclosure",
 "source_status","source_url","source_sha256","first_seen_utc",
 "per_company_disclosure_time_verified","governance_quality_verified","factor_F3_eligible"]
MIN_PEERS=5
def load(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader();w.writerows(rows)
def number(v):
    try:
        if v is None or str(v).strip() in ("","-","--","NA","N/A"):return None
        n=float(str(v).replace(",","").strip())
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None
def positive(v):
    n=number(v)
    return round(n,5) if n is not None and n>0 else ""
def yield_pct(v):
    n=number(v)
    return round(n,5) if n is not None and 0<=n<=100 else ""
def roc(s):
    s=str(s or "").strip()
    if len(s)!=7 or not s.isdigit():return ""
    try:return dt.date(int(s[:3])+1911,int(s[3:5]),int(s[5:])).isoformat()
    except ValueError:return ""
def fetch(url):
    request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS official fundamental archive","Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=40) as r:
        content=r.read(3_500_001)
    if len(content)>3_500_000:raise ValueError("official payload exceeded bound")
    return content
def parse(raw,market,kind,master,today,sha,first_seen):
    rows=json.loads(raw.decode("utf-8-sig"))
    fields=FIELD[(market,kind)]
    if not isinstance(rows,list) or len(rows)<100 or not isinstance(rows[0],dict):
        raise ValueError("official dataset unexpectedly sparse or non-tabular")
    if not set(fields).issubset(rows[0]):raise ValueError("official header schema changed")
    seen=set();out=[]
    for row in rows:
        if not isinstance(row,dict):continue
        day=roc(row.get(fields[0]))
        sid=str(row.get(fields[1],"")).strip()
        co=master.get(sid)
        if not day or day>today.isoformat() or not co or co["market"]!=market:
            continue
        if sid in seen:continue
        seen.add(sid)
        common={"stock_id":sid,"stock_name":str(row.get(fields[2],"")),
                "market":market,"sector":co.get("sector",""),
                "source_status":"ok","source_url":URLS[market][kind],
                "source_sha256":sha,"first_seen_utc":first_seen}
        if kind=="valuation":
            pe=positive(row.get(fields[3]))
            pb=positive(row.get(fields[4]))
            y=yield_pct(row.get(fields[5]))
            if pe=="" and pb=="" and y=="":continue
            out.append(dict(common,asof=day,pe_ratio=pe,pb_ratio=pb,
               dividend_yield_pct=y,pe_peer_median="",pb_peer_median="",
               pe_peer_sample=0,pb_peer_sample=0,
               quote_publication_at_verified="false",
               earnings_period_verified="false",peer_f2_ready="false",
               factor_F2_eligible="false"))
        else:
            concurrent=str(row.get(fields[3],"")).strip()
            if concurrent not in ("兼任","未兼任"):continue
            out.append(dict(common,source_asof=day,
               chairman_is_general_manager="true" if concurrent=="兼任" else "false",
               chairman_general_manager_disclosure=concurrent,
               per_company_disclosure_time_verified="false",
               governance_quality_verified="false",factor_F3_eligible="false"))
    if len(out)<100:raise ValueError("too few confirmed ordinary-stock records")
    return out
def peer_medians(valuation):
    peers=defaultdict(list)
    for row in valuation:
        peers[(row["market"],row["sector"],row["asof"])].append(row)
    for group in peers.values():
        for field,label in (("pe_ratio","pe"),("pb_ratio","pb")):
            entries=[number(row.get(field)) for row in group]
            entries=[v for v in entries if v is not None and v>0]
            median=round(statistics.median(entries),5) if len(entries)>=MIN_PEERS else ""
            for row in group:
                row[f"{label}_peer_sample"]=len(entries)
                row[f"{label}_peer_median"]=median
        for row in group:
            row["peer_f2_ready"]="true" if (row["pe_ratio"]!="" and
                row["pb_ratio"]!="" and row["pe_peer_median"]!="" and
                row["pb_peer_median"]!="") else "false"
def archive(root,market,kind,raw,clock):
    sha=hashlib.sha256(raw).hexdigest()
    folder=root/"history_data"/"f2f3_official_sources"/market/kind
    folder.mkdir(parents=True,exist_ok=True)
    name=folder/(sha+".json");first=folder/(sha+".first_seen")
    if not name.is_file():
        name.write_bytes(raw)
        first.write_text(clock.isoformat(timespec="seconds")+"\n",encoding="utf-8")
    return sha, first.read_text(encoding="utf-8").strip() if first.is_file() else ""
def collect(root=ROOT,fetcher=fetch,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    today=clock.astimezone(ZoneInfo("Asia/Taipei")).date()
    data=root/"site"/"data";data.mkdir(parents=True,exist_ok=True)
    master={r["stock_id"]:r for r in load(root/"history_data"/"ordinary_stock_master.csv") if r.get("stock_id")}
    kinds=(("valuation","f2_valuation_29e.csv",VALUE_COLUMNS),
           ("governance","f3_governance_29e.csv",GOV_COLUMNS))
    output={};provenance={}
    for kind,destname,columns in kinds:
        path=data/destname
        prev={r["stock_id"]:r for r in load(path)}
        stored={}
        for market in ("上市","上櫃"):
            url=URLS[market][kind]
            try:
                raw=fetcher(url)
                digest=hashlib.sha256(raw).hexdigest()
                first=clock.isoformat(timespec="seconds")
                parsed=parse(raw,market,kind,master,today,digest,first)
                digest,first=archive(root,market,kind,raw,clock)
                for row in parsed:row["first_seen_utc"]=first
                stored[market]=parsed
                provenance[f"{market}_{kind}"]={
                    "status":"ok","rows":len(parsed),"source_sha256":digest,
                    "source_url":url,
                    "source_dates":sorted(set(row["asof"] if kind=="valuation" else row["source_asof"] for row in parsed))}
            except (OSError,ValueError,UnicodeError,KeyError,TypeError,json.JSONDecodeError) as e:
                stored[market]=[dict(r,source_status="stale_backup") for r in prev.values()
                                if r.get("market")==market]
                provenance[f"{market}_{kind}"]={"status":"stale_backup" if stored[market] else "unavailable",
                     "source_url":url,"rows":len(stored[market]),"reason":str(e)[:200]}
        entries=sorted((r for group in stored.values() for r in group),
                        key=lambda r:(r["market"],r["stock_id"]))
        if kind=="valuation":peer_medians(entries)
        if entries:write(path,columns,entries)
        output[kind]=entries
    vals=output["valuation"];gov=output["governance"]
    meta={
      "version":"2.9E","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
      "valuation_stocks":len(vals),"valuation_peer_comparable":sum(r["peer_f2_ready"]=="true" for r in vals),
      "governance_stocks":len(gov),"chair_ceo_concurrent_count":sum(r["chairman_is_general_manager"]=="true" for r in gov),
      "sources":provenance,"min_same_sector_peer_sample":MIN_PEERS,
      "cross_market_peers_mixed":False,"F2_expected_earnings_surprise_verified":False,
      "F2_valuation_quality_factor_verified":False,"F3_governance_quality_factor_verified":False,
      "historical_announcement_time_verified":False,"factor_scores_enabled":False,
      "backtested_probabilities_enabled":False,
      "notes":[
       "本益比、淨值比、殖利率為官方目前觀察，不等於便宜或昂貴，沒有分析師一致預期與EPS公告時點",
       "同市場／同產業／同日期，且至少5檔有效比率才計算同業中位數；不混合跨市場樣本",
       "本益比為負或無法計算時保持缺值，不補0；本益比可能因虧損而不存在",
       "董事長是否兼任總經理是事實揭露，無法僅憑兼任與否評價公司治理好壞",
       "本版不具獨立官方發布時分、最新資料修訂時分或歷史除權息後EPS一致性，因此F2/F3只提供部分資料，不啟用模型計分"
      ]}
    (data/"company_f2f3_meta_29e.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("2.9E official valuation/governance",meta["valuation_stocks"],meta["governance_stocks"],meta["valuation_peer_comparable"],provenance)
    return output,meta
if __name__=="__main__":collect()
