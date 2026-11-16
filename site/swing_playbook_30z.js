/* TPE-MFDS 3.0Z | conservative swing decision brief, not an order signal.
 * Sources: official_meta, chip_rank, tech_crosscheck and prior CLOSE risk reference.
 * All prices are unadjusted observation examples, NOT executable entry or stops.
 */
(function(root){
'use strict';
const DAY=/^\d{4}-\d{2}-\d{2}$/;
function day(v){
 if(typeof v!=='string'||!DAY.test(v))return null;
 const d=new Date(v+'T00:00:00Z');
 return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===v?d.getTime():null;
}
function number(v){
 if(v===null||v===undefined||typeof v==='boolean'||String(v).trim()==='')return null;
 const n=Number(v);return Number.isFinite(n)?n:null;
}
function closeEnough(a,b){
 return a!==null&&b!==null&&a>0&&b>0&&Math.abs(a-b)<=Math.max(0.01,a*0.001);
}
function evaluate({rank,tech,risk,official,check,now=Date.now(),minimumRR=2}={}){
 const notes=['僅供2週至3個月波段研究；MA20觀察區與歷史高收盤價不是支撐、成交價或預測目標'];
 const result=(state,label,extra={})=>Object.assign({
  state,label,notes,sourceDate:official?.display_date||'—',
  holderDate:rank?.holder_asof||'—',entryLow:null,entryHigh:null,
  invalidation:null,historicalHigh20:null,rewardRisk:null,
  riskVerified:false,canConsider:false,probabilityEnabled:false
 },extra);
 const priceDate=official?.display_date||'';
 const clock=day(priceDate),nowMs=number(now);
 if(clock===null||nowMs===null||nowMs<clock||
    nowMs-clock>5*86400000)
  return result('stale','資料過期／日期無效，停止判讀');
 if(official.status!=='ok'||official.aligned!==true||
    ['上市','上櫃'].some(m=>official.market_dates?.[m]!==priceDate))
  return result('source_mismatch','官方市場日期不一致，停止判讀');
 if(!rank||!tech||rank.stock_id!==tech.stock_id||
   rank.price_asof!==priceDate||rank.flow_asof!==priceDate||
   tech.price_asof!==priceDate||tech.flow_asof!==priceDate||
   tech.latest_history_date!==priceDate||tech.holder_asof!==rank.holder_asof)
  return result('source_mismatch','法人、技術與行情日期不一致');
 const lag=day(rank.holder_asof);
 if(lag===null||lag>clock||clock-lag>14*86400000)
  return result('source_mismatch','集保週資料缺漏或過期');
 const close=number(rank.close),techClose=number(tech.close),
       ma=number(tech.ma20),rankMa=number(rank.ma20),
       ma60=number(tech.ma60),rsi=number(tech.rsi14);
 if(!closeEnough(close,techClose)||!closeEnough(ma,rankMa)||ma60===null||
    ma60<=0||rsi===null)
  return result('source_mismatch','股價、均線或技術來源未完成交叉核對');
 const low=ma*0.99,high=ma*1.01,invalidation=ma*0.97;
 const detail={close,ma20:ma,ma60,rsi,entryLow:low,entryHigh:high,invalidation};
 if(!check?.ready||!check.confluence||
    check.price_asof!==priceDate||rank.rank_status!=='可排名')
  return result('not_ready','法人／大戶／技術尚未三面符合',detail);
 if(close<ma||close/ma>1.08||rsi<40||rsi>=70)
  return result('overextended','趨勢或追價風險未通過',detail);
 // Risk source must represent PRIOR 20 close days; highs are observations,
 // not the futures market's resistance levels or hypothetical trade exits.
 const riskClose=number(risk?.last_close),priorHigh=number(risk?.prior20_close_high);
 const validRisk=!!risk&&risk.stock_id===rank.stock_id&&
   risk.price_asof===priceDate&&risk.price_adjusted==='false'&&
   String(risk.risk_status||'').includes('20／60日完整')&&
   number(risk.close_sessions)>=60&&closeEnough(close,riskClose)&&
   priorHigh!==null&&priorHigh>0;
 if(!validRisk)
  return result('risk_unknown','風險來源不足，先觀察不要推估風報',detail);
 const hypotheticalRisk=high-invalidation,hypotheticalReward=priorHigh-high;
 const rr=hypotheticalRisk>0&&hypotheticalReward>0?
   hypotheticalReward/hypotheticalRisk:null;
 notes.push('近20日最高收盤 '+priorHigh+' 僅是歷史參考；風報比使用觀察區上緣計算，不能當作價格預測');
 const riskDetail={...detail,historicalHigh20:priorHigh,rewardRisk:rr,
   riskVerified:true};
 if(rr===null||rr<minimumRR)
  return result('reward_insufficient','歷史上緣／失效距離的風報門檻未達',riskDetail);
 if(close>high)return result('waiting','高於觀察區，等待回測',riskDetail);
 return result('monitor','接近觀察區，等待價量再確認',
   {...riskDetail,canConsider:true});
}
const api=Object.freeze({day,number,closeEnough,evaluate});
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.MFDSSwingPlaybook30Z=api;
})(typeof window!=='undefined'?window:null);
