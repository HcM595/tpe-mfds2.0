#!/usr/bin/env python3
"""Narrow public-format probe. No source values recorded in logs, only labels."""
from scripts.collect_cashflow_focus_28g import TableReader,normalized
from urllib.request import Request,urlopen
from urllib.parse import urlencode
url="https://mopsov.twse.com.tw/mops/web/ajax_t164sb04"
payload=urlencode({"encodeURIComponent":"1","step":"1","firstin":"1","off":"1","queryName":"co_id","inpuType":"co_id","TYPEK":"all","isnew":"false","co_id":"8064","year":"115","season":"02"}).encode()
r=Request(url,data=payload,headers={"User-Agent":"Mozilla/5.0 (compatible; TPE-MFDS research)","Content-Type":"application/x-www-form-urlencoded","Referer":"https://mopsov.twse.com.tw/mops/web/t164sb04"})
try:
    with urlopen(r,timeout=30) as h:
        b=h.read(1000000)
        print("status",h.status,"bytes",len(b),"type",h.headers.get("content-type"))
    s=b.decode("utf-8-sig",errors="replace")
    parser=TableReader();parser.feed(s)
    print("rows",len(parser.rows))
    for i,row in enumerate(parser.rows):
        label=" | ".join(row)
        if any(x in label for x in ["單位：","會計項目","115年","114年","淨利","季","本期稅後"]):
            # Only labels and period header strings. Never values or row bodies.
            print("LABEL",i,"first",repr(row[0][:110] if row else ""),"second-column-is-period",repr(row[1][:100] if len(row)>1 and ("年" in row[1] or "度" in row[1]) else ""), "cells",len(row))
            if i>170:break
except Exception as e:
    print("probe blocked",type(e).__name__,str(e)[:160])
