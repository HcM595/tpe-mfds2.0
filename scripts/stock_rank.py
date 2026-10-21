#!/usr/bin/env python3
"""TPE-MFDS 2.3A/B: exchange-company universe + descriptive chip-strength percentiles.

No return forecasts or trading instructions. No guessing of stock identities,
prices, liquidity, or missing observations. Uses official current company rosters.
"""
from __future__ import annotations
import csv
import datetime as dt
import io
import json
import math
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / 'history_data'
SITE = ROOT / 'site' / 'data'
MASTER_FILE = HIST / 'ordinary_stock_master.csv'
TWSE_URL = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'
TPEX_URL = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O'
TWSE_FALLBACK = 'https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv'
TPEX_FALLBACK = 'https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv'
MASTER_COLS = ['stock_id','stock_name','market','sector','asof','source']
RANK_COLS = ['stock_id','stock_name','market','sector','ordinary_status','ordinary_reason',
             'chip_status','rank_status','rank_reason','price_asof','flow_asof','holder_asof',
             'close','avg_20d_turnover_twd','five_day_volume_shares','foreign_5d_shares',
             'trust_5d_shares','foreign_ratio_pct','trust_ratio_pct','large400_4w_pp',
             'large1000_4w_pp','mid400_999_4w_pp','p_foreign','p_trust','p_mid','p_large',
             'chip_strength_score','chip_strength_rank','ma20','close_above_ma20','technical_confirmation']
UNSUITABLE = ('etf','etn','權證','受益證券','存託憑證','存托憑證','tdr','特別股','債券','交換債')


def now_taipei():return dt.datetime.now(ZoneInfo('Asia/Taipei'))

def fetch_bytes(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; TPE-MFDS research/2.3)','Accept':'application/json,text/csv,*/*'})
    with urllib.request.urlopen(req,timeout=35) as resp:return resp.read()

def text_decode(raw):
    for charset in ('utf-8-sig','utf-8','cp950'):
        try:return raw.decode(charset)
        except UnicodeDecodeError:pass
    raise ValueError('CSV encoding unrecognized')

def csv_load(path):
    if not path.exists():return []
    with path.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def csv_save(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def number(v):
    s=str(v if v is not None else '').replace(',','').replace('%','').strip()
    if not s or s in ('-','--','—','null','None'):return None
    try:
        x=float(s)
        return x if math.isfinite(x) else None
    except ValueError:return None

def iso_date(v):
    s=str(v or '').strip()
    try:
        if re.fullmatch(r'\d{7}',s):return dt.date(int(s[:3])+1911,int(s[3:5]),int(s[5:])).isoformat()
        if re.fullmatch(r'\d{3}/\d\d/\d\d',s):return dt.date(int(s[:3])+1911,int(s[4:6]),int(s[7:])).isoformat()
        if re.fullmatch(r'\d{4}-\d\d-\d\d',s):return dt.date.fromisoformat(s).isoformat()
    except ValueError:pass
    return ''

def norm_key(s):return re.sub(r'[\s_\-.]+','',str(s).lower())

def pick(row, names):
    r={norm_key(k):v for k,v in row.items()}
    for n in names:
        if norm_key(n) in r and str(r[norm_key(n)] or '').strip():return str(r[norm_key(n)]).strip()
    return ''

def profile_rows(payload,market,source):
    if not isinstance(payload,list):raise ValueError('official company roster is not JSON array')
    out=[]
    for r in payload:
        if not isinstance(r,dict):continue
        code=pick(r,['公司代號','SecuritiesCompanyCode','CompanyCode','Code'])
        name=pick(r,['公司簡稱','CompanyAbbreviation','CompanyShortName','公司名稱','CompanyName'])
        sector=pick(r,['產業別','SecuritiesIndustryCode','IndustryCode']) or '未分類'
        if not re.fullmatch(r'[0-9]{4}',code) or not name:continue
        if any(word in (name+' '+pick(r,['公司名稱','CompanyName'])).lower() for word in UNSUITABLE):continue
        asof=iso_date(pick(r,['出表日期','Date'])) or now_taipei().date().isoformat()
        out.append(dict(stock_id=code,stock_name=name,market=market,sector=sector,asof=asof,source=source))
    if len(out)<100:raise ValueError('official company master unexpectedly short: '+str(len(out)))
    return out

def load_official_master():
    errors=[];selected=[];by_market={}
    for market,url in [('上市',TWSE_URL),('上櫃',TPEX_URL)]:
        try:
            rows=profile_rows(json.loads(text_decode(fetch_bytes(url))),market,url)
            selected+=rows;by_market[market]='ok'
        except Exception as ex:
            errors.append(market+': '+type(ex).__name__+': '+str(ex))
            fallback = TPEX_FALLBACK if market=='上櫃' else TWSE_FALLBACK
            try:
                body=text_decode(fetch_bytes(fallback));reader=list(csv.DictReader(io.StringIO(body)))
                rows=profile_rows(reader,market,fallback)
                selected+=rows;by_market[market]='ok_csv_fallback';continue
            except Exception as ex2:errors.append(market+'備援: '+type(ex2).__name__+': '+str(ex2))
            by_market[market]='failed'
    cached=csv_load(MASTER_FILE)
    # Safe cache only when official master still recent; older rosters must not silently masquerade as current.
    today=now_taipei().date()
    if cached:
        age=[]
        for r in cached:
            try:age.append((today-dt.date.fromisoformat(r['asof'])).days)
            except (ValueError,KeyError):age.append(9999)
        fresh_cache=(max(age)<=14)
        if fresh_cache:
            for market in ('上市','上櫃'):
                if by_market.get(market)=='failed':
                    selected += [r for r in cached if r.get('market')==market]
                    by_market[market]='cached_recent'
    selected_by_key={}
    for r in selected:selected_by_key[(r['stock_id'],r['market'])]=r
    selected=list(selected_by_key.values())
    # If a code is attributed to both markets, withhold both from eligible list.
    codes=Counter(r['stock_id'] for r in selected)
    selected=[r for r in selected if codes[r['stock_id']]==1]
    if selected:csv_save(MASTER_FILE,MASTER_COLS,sorted(selected,key=lambda x:x['stock_id']))
    return selected,{'source_status':by_market,'errors':errors,'count':len(selected),'conflicting_ids':[c for c,n in codes.items() if n>1]}

def price_index(rows):
    grouped=defaultdict(dict)
    for r in rows:
        date=iso_date(r.get('date'));close=number(r.get('close'));vol=number(r.get('volume_shares'));turn=number(r.get('trade_value_twd'));code=r.get('stock_id','')
        if not date or not re.fullmatch(r'[0-9]{4}',code) or close is None or close<=0:continue
        grouped[code][date]=dict(date=date,close=close,vol=vol,turn=turn)
    return {k:sorted(v.values(),key=lambda x:x['date']) for k,v in grouped.items()}

def percentiles(rows,key):
    """0-100 empirical mid-ranks, ties assigned identical scores; 1 sample -> 50."""
    vals=sorted(float(r[key]) for r in rows)
    unique={}
    for i,v in enumerate(vals):unique.setdefault(v,[]).append(i)
    for v,ix in unique.items():
        score=50.0 if len(vals)==1 else (sum(ix)/len(ix))/(len(vals)-1)*100
        unique[v]=round(score,4)
    return {r['stock_id']:unique[float(r[key])] for r in rows}

def rank_candidates(signals, master, snapshot, prices):
    roster={r['stock_id']:r for r in master}
    snap={r.get('stock_id',''):r for r in snapshot}
    px=price_index(prices)
    results=[]
    for sig in signals:
        code=sig.get('stock_id','')
        if sig.get('chip_status')!='matched':continue
        row={k:'' for k in RANK_COLS};row['stock_id']=code;row['chip_status']='matched';row['flow_asof']=sig.get('flow_asof','');row['holder_asof']=sig.get('holder_asof','')
        mr=roster.get(code);sr=snap.get(code)
        reasons=[]
        if not mr:
            row['ordinary_status']='待確認';row['ordinary_reason']='不在本次可用的上市櫃公司官方名錄';reasons.append('普通股身分待確認')
        else:
            row.update(stock_name=mr['stock_name'],market=mr['market'],sector=mr.get('sector',''))
            row['ordinary_status']='已核對公司名錄';row['ordinary_reason']='公司資料來自官方上市櫃公司名錄，非完整證券種類保證'
            if not sr or sr.get('market')!=mr['market']:
                reasons.append('行情不存在或市場別不相符')
            elif iso_date(sr.get('asof'))!=iso_date(sig.get('flow_asof')):
                reasons.append('法人日期與最新收盤行情日期不同')
        points=[p for p in px.get(code,[]) if p['date']<=sig.get('flow_asof','')]
        if not points:reasons.append('缺歷史價格');row['price_asof']=''
        else:
            row['price_asof']=points[-1]['date'];row['close']=round(points[-1]['close'],4)
            if row['price_asof']!=sig.get('flow_asof',''):reasons.append('法人日期與價格日期不同')
            if len(points)<20 or any(p['turn'] is None or p['turn']<=0 for p in points[-20:]):reasons.append('20日成交額資料不足')
            else:
                avg=mean(p['turn'] for p in points[-20:]);row['avg_20d_turnover_twd']=round(avg)
                if avg<30_000_000:reasons.append('20日平均成交額不足3000萬元')
                row['ma20']=round(mean(p['close'] for p in points[-20:]),4)
                row['close_above_ma20']='是' if points[-1]['close']>number(row['ma20']) else '否'
            if len(points)<5 or any(p['vol'] is None or p['vol']<=0 for p in points[-5:]):reasons.append('近5日成交股數不足')
            else:row['five_day_volume_shares']=int(sum(p['vol'] for p in points[-5:]))
        if not iso_date(sig.get('holder_asof')) or not iso_date(sig.get('flow_asof')):
            reasons.append('籌碼日期不完整')
        else:
            day_gap=(dt.date.fromisoformat(sig['flow_asof'])-dt.date.fromisoformat(sig['holder_asof'])).days
            if day_gap<0 or day_gap>14:reasons.append('大戶週資料過期或日期異常')
        foreign=number(sig.get('foreign_5d_shares'));trust=number(sig.get('trust_5d_shares'))
        l400=number(sig.get('large400_4w_pp'));l1000=number(sig.get('large1000_4w_pp'))
        row['foreign_5d_shares']=sig.get('foreign_5d_shares','');row['trust_5d_shares']=sig.get('trust_5d_shares','')
        row['large400_4w_pp']=sig.get('large400_4w_pp','');row['large1000_4w_pp']=sig.get('large1000_4w_pp','')
        if foreign is None or trust is None or l400 is None or l1000 is None:reasons.append('籌碼指標資料不足')
        else:row['mid400_999_4w_pp']=round(l400-l1000,4)
        if row['five_day_volume_shares']!='' and foreign is not None and trust is not None:
            total=row['five_day_volume_shares'];row['foreign_ratio_pct']=round(foreign/total*100,6);row['trust_ratio_pct']=round(trust/total*100,6)
        row['rank_status']='可排名' if not reasons else '未納入'
        row['rank_reason']='；'.join(reasons) if reasons else '普通股候選、日期一致、流動性及資料品質初步通過'
        row['technical_confirmation']='通過' if row['close_above_ma20']=='是' else ('未通過' if row['close_above_ma20']=='否' else '資料不足')
        results.append(row)
    eligible=[r for r in results if r['rank_status']=='可排名']
    for key,score_field in [('foreign_ratio_pct','p_foreign'),('trust_ratio_pct','p_trust'),('mid400_999_4w_pp','p_mid'),('large1000_4w_pp','p_large')]:
        lookup=percentiles(eligible,key)
        for r in eligible:r[score_field]=lookup[r['stock_id']]
    for r in eligible:
        r['chip_strength_score']=round(.25*r['p_foreign']+.25*r['p_trust']+.20*r['p_mid']+.30*r['p_large'],2)
    eligible.sort(key=lambda r:(-r['chip_strength_score'],r['stock_id']))
    for index,r in enumerate(eligible,1):r['chip_strength_rank']=index
    results.sort(key=lambda r:(r['rank_status']!='可排名',-float(r['chip_strength_score'] or 0),r['stock_id']))
    return results

def run():
    SITE.mkdir(parents=True,exist_ok=True)
    signals=csv_load(SITE/'chip_signals.csv')
    prices=csv_load(SITE/'price_history.csv')
    snapshot=csv_load(SITE/'official_snapshot.csv')
    if not signals:raise RuntimeError('chip_signals.csv missing or empty')
    if not prices:raise RuntimeError('price_history.csv missing or empty')
    if not snapshot:raise RuntimeError('official_snapshot.csv missing or empty')
    master,ms=load_official_master()
    if not master:print('WARNING: company roster unavailable. All candidate identities remain unverified; no scores.',file=sys.stderr)
    results=rank_candidates(signals,master,snapshot,prices)
    csv_save(SITE/'stock_universe.csv',MASTER_COLS,sorted(master,key=lambda x:x['stock_id']))
    csv_save(SITE/'chip_rank.csv',RANK_COLS,results)
    today=now_taipei().isoformat()
    audit={
        'version':'2.3A+B','generated_at_taipei':today,'status':('unavailable' if not master else 'ok' if all(x in ('ok','ok_csv_fallback') for x in ms['source_status'].values()) else 'partial'),
        'master':ms,'original_chip_matches':sum(s.get('chip_status')=='matched' for s in signals),
        'candidate_rows':len(results),'eligible_ranked':sum(r['rank_status']=='可排名' for r in results),
        'excluded_or_pending':dict(Counter(r['rank_reason'] for r in results if r['rank_status']!='可排名')),
        'min_20d_avg_turnover_twd':30000000,'min_trade_days':20,'alignment':'price_asof must equal flow_asof',
        'score_weights':{'foreign_flow_ratio':.25,'trust_flow_ratio':.25,'mid400_999_4w_delta':.20,'holder1000_4w_delta':.30},
        'notes':['非預測勝率；各項因子用當次可排名名單的百分位數評分。',
                 '普通股判定基於公司名錄與市場別；異常證券種類仍須抽樣核對。',
                 '集保歷史來源可能含非官方鏡像，建議人工核對異常4週變化。',
                 '無法取得官方公司名錄時不得用4位代碼直接推定普通股。']}
    (SITE/'chip_rank_meta.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('2.3 ranked',audit['eligible_ranked'],'/',len(results),'matched; roster',len(master),'sources',ms['source_status'])
    if not any(r['rank_status']=='可排名' for r in results):
        print('NOTICE: no eligible ranking due to market alignment/master coverage/data sufficiency; no fabricated scores')

if __name__=='__main__':
    try:run()
    except Exception as exc:
        print('TPE-MFDS 2.3 error:',exc,file=sys.stderr);sys.exit(1)
