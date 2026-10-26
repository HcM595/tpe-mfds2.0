#!/usr/bin/env python3
"""Read-only schema probe of official Taiwan stock sentiment endpoints."""
import json,urllib.request
urls={
"twse_margin":"https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
"twse_daytrade":"https://openapi.twse.com.tw/v1/exchangeReport/TWTB4U",
"tpex_margin":"https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance",
"tpex_daytrade":"https://www.tpex.org.tw/openapi/v1/tpex_intraday_trading_statistics"}
for name,url in urls.items():
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS/2.9C official data schema research","Accept":"application/json"})
  with urllib.request.urlopen(req,timeout=28) as response:
   raw=response.read(4_000_001);print(name,"HTTP",response.status,"content_type",response.headers.get("content-type"),"bytes",len(raw))
  obj=json.loads(raw.decode("utf-8-sig"))
  print(name,"type",type(obj).__name__,"count",len(obj) if hasattr(obj,"__len__") else "-")
  if isinstance(obj,list):
   for i,row in enumerate(obj[:3]):
    print(name,"row",i,"keys",list(row)[:35] if isinstance(row,dict) else "non-dict")
    if isinstance(row,dict):
     print(name,"row",i,"sample",str({k:str(v)[:45] for k,v in row.items() if any(c in str(k).lower() for c in ["date","日期","證券代號","股票代號","代號","code","融資","融券","當沖","date"])})[:1400])
  if isinstance(obj,dict):print(name,"root_keys",list(obj)[:35])
 except Exception as e: print(name,"FAILED",type(e).__name__,str(e)[:180])

# Explicitly dated TWSE historical statement; unlike latest OpenAPI, it has a day label.
for chosen in ("20261022",):
 try:
  url="https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date="+chosen+"&selectType=ALL&response=json"
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS/2.9C","Accept":"application/json"})
  with urllib.request.urlopen(req,timeout=30) as r: info=json.loads(r.read(5_000_001))
  print("twse_dated","keys",list(info),"date",info.get("date"),"stat",info.get("stat"))
  for t in info.get("tables",[]):
   print("twse_dated table",str(t.get("title",""))[:90],"fields",str(t.get("fields",[]))[:550],"rows",len(t.get("data",[])))
   for row in t.get("data",[]):
    if row and str(row[0]).strip() in ("3533","2345","2330","2308"):
     print("twse_dated focus",row[:19])
 except Exception as e: print("twse_dated FAILED",type(e).__name__,str(e)[:180])
