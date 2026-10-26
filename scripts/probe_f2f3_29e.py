#!/usr/bin/env python3
"""2.9E probe official exchanges F2 valuation and F3 governance raw fields."""
import urllib.request,json
URLS={
 "twse_valuation":"https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
 "tpex_valuation":"https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
 "twse_governance":"https://openapi.twse.com.tw/v1/opendata/t187ap33_L",
 "tpex_governance":"https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap33_O",
 "twse_directors":"https://openapi.twse.com.tw/v1/opendata/t187ap09_L",
 "tpex_directors":"https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap09_O",
}
for name,url in URLS.items():
 try:
  request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS research 2.9E","Accept":"application/json"})
  with urllib.request.urlopen(request,timeout=35) as response:
   raw=response.read(3_500_000)
   print(name,"HTTP",response.status,"bytes",len(raw),"type",response.headers.get("Content-Type"))
  items=json.loads(raw.decode("utf-8-sig"))
  print(name,"shape",type(items).__name__,"count",len(items) if hasattr(items,"__len__") else "?")
  if isinstance(items,list) and items:
   print(name,"keys",list(items[0])[:40])
   for r in items[:1]:
    print(name,"sample",str(r)[:850])
 except Exception as e:print(name,"FAILED",type(e).__name__,str(e)[:220])
