#!/usr/bin/env python3
"""Public official macro schema probe: only first-record fields and shapes."""
import json,urllib.request,zipfile,io,csv
URLS=[
 ("cbc","https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day"),
 ("ndc-metadata","https://data.gov.tw/api/v2/rest/dataset/6099"),
 ("ndc-metadata-v1","https://data.gov.tw/api/v1/rest/dataset/6099"),
]
for name,url in URLS:
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS academic-research","Accept":"application/json,text/csv,application/zip,*/*"})
  with urllib.request.urlopen(req,timeout=20) as f:
   data=f.read(3_000_001);ct=f.headers.get("content-type","");status=f.status;final=f.geturl()
  print(name,"status",status,"size",len(data),"mime",ct,"location",final[:140])
  try:
   obj=json.loads(data.decode("utf-8-sig"))
   print(name,"JSON shape",type(obj).__name__,len(obj) if hasattr(obj,"__len__") else "n/a")
   if isinstance(obj,list) and obj:
    print(name,"first item keys",list(obj[0])[:25],"first item",str(obj[0])[:500])
   if isinstance(obj,dict):
    print(name,"root keys",list(obj)[:30])
    if name=="ndc-metadata":
     result=obj.get("result"); print("NDC result type",type(result).__name__)
     if isinstance(result,dict):
      print("NDC result keys",list(result)[:35]);print("NDC distribution",str(result.get("distribution",result.get("resource",{})))[:1800])
    for k,v in obj.items():
     if isinstance(v,list) and v and isinstance(v[0],dict):
      print(name,k,"first keys",list(v[0])[:30])
      if k in ("distribution","resources","resource"):print("distribution first",str(v[0])[:1100])
  except Exception as e:
   print(name,"non-JSON",type(e).__name__,"head",data[:90])
 except Exception as e:print(name,"failed",type(e).__name__,str(e)[:200])
