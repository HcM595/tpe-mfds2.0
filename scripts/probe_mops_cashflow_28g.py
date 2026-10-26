#!/usr/bin/env python3
"""Read-only format probe for a single publicly filed MOPS cashflow statement.
No financial content is saved; log only response status and table-header/label hints.
"""
import html
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

class TrRows(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr":self.row=[]
        if tag in ("td","th") and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()));self.cell=None
        if tag=="tr" and self.row is not None:
            self.rows.append(self.row);self.row=None

def probe(stock_id="8064",year=115,quarter=2):
    url="https://mopsov.twse.com.tw/mops/web/ajax_t164sb05"
    data=urllib.parse.urlencode({
        "encodeURIComponent":"1","step":"1","firstin":"1","off":"1",
        "queryName":"co_id","inpuType":"co_id","TYPEK":"all","isnew":"false",
        "co_id":stock_id,"year":str(year),"season":f"{quarter:02d}",
    }).encode()
    req=urllib.request.Request(url,data=data,headers={
        "User-Agent":"Mozilla/5.0 (compatible; TPE-MFDS research format-verification)",
        "Content-Type":"application/x-www-form-urlencoded","Referer":"https://mopsov.twse.com.tw/mops/web/t164sb05",
    })
    with urllib.request.urlopen(req,timeout=30) as resp:
        raw=resp.read(3_000_001)
        print("MOPS HTTP",resp.status,"bytes",len(raw),"content-type",resp.headers.get("content-type"),"urlhost","mopsov.twse.com.tw")
    if len(raw)>3_000_000:raise ValueError("response too big")
    decoded=raw.decode("utf-8-sig",errors="replace")
    if decoded.count("\ufffd")>100:decoded=raw.decode("big5",errors="replace")
    p=TrRows();p.feed(decoded)
    print("HTML tables rows",len(p.rows),"likely financial content",any("現金流" in ''.join(r) for r in p.rows))
    interest=["營業活動","營運活動","現金流量","現金及約當現金","單位","公司代號","期間"]
    found=[(i," | ".join(row)[:240]) for i,row in enumerate(p.rows) if any(k in " ".join(row) for k in interest)]
    print("Matching rows",len(found))
    for i,txt in found[:18]:print("MOPSROW",i,txt)
    print("First rows",[(i," | ".join(row)[:150]) for i,row in enumerate(p.rows[:8])])
if __name__=="__main__":
    try:probe()
    except Exception as exc:print("MOPS probe unavailable:",type(exc).__name__,str(exc)[:220])
