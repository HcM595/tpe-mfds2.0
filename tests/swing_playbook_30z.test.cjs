const assert=require('node:assert/strict');
const P=require('../site/swing_playbook_30z.js');
const date='2026-11-13';
const now=Date.parse('2026-11-14T02:00:00Z');
const official={status:'ok',aligned:true,display_date:date,
 market_dates:{上市:date,上櫃:date}};
const rank={stock_id:'4105',market:'上市',price_asof:date,flow_asof:date,
 holder_asof:'2026-11-07',rank_status:'可排名',close:'105',ma20:'100'};
const tech={stock_id:'4105',data_status:'可驗證',price_asof:date,
 flow_asof:date,holder_asof:'2026-11-07',latest_history_date:date,
 close:'105',ma20:'100',ma60:'98',rsi14:'58'};
const risk={stock_id:'4105',price_asof:date,last_close:'105',
 prior20_close_high:'120',risk_status:'20／60日完整（未還原收盤）',
 price_adjusted:'false',close_sessions:'160'};
const check={ready:true,confluence:true,price_asof:date};
const evaluate=(args={})=>P.evaluate({rank,tech,risk,official,check,now,...args});
let d=evaluate();
assert.equal(d.state,'waiting');
assert.equal(d.canConsider,false,'even strong historical risk reward cannot be an entry instruction');
assert.equal(d.riskVerified,true);
assert.equal(d.probabilityEnabled,false);
assert.equal(d.entryLow,99);
assert.equal(d.entryHigh,101);
assert.equal(d.invalidation,97);
assert.equal(d.historicalHigh20,120);
assert.equal(d.rewardRisk,4.75);
assert(d.notes.join(' ').includes('不是支撐'));
const near=evaluate({rank:{...rank,close:'100'},tech:{...tech,close:'100'},
 risk:{...risk,last_close:'100'}});
assert.equal(near.state,'monitor');
assert.equal(near.canConsider,true);
assert.equal(evaluate({official:{...official,aligned:false}}).state,'source_mismatch');
assert.equal(evaluate({official:{...official,market_dates:{上市:date,上櫃:'2026-11-12'}}}).state,'source_mismatch');
assert.equal(evaluate({now:Date.parse('2026-11-25T00:00:00Z')}).state,'stale');
assert.equal(evaluate({tech:{...tech,close:'106'}}).state,'source_mismatch');
assert.equal(evaluate({tech:{...tech,ma20:'102'}}).state,'source_mismatch');
assert.equal(evaluate({risk:{...risk,price_asof:'2026-11-12'}}).state,'risk_unknown');
assert.equal(evaluate({risk:{...risk,price_adjusted:'true'}}).state,'risk_unknown');
assert.equal(evaluate({risk:{...risk,last_close:'100'}}).state,'risk_unknown');
assert.equal(evaluate({risk:{...risk,prior20_close_high:''}}).state,'risk_unknown');
assert.equal(evaluate({risk:{...risk,prior20_close_high:'104'}}).state,'risk_unfavorable');
assert.equal(evaluate({risk:{...risk,prior20_close_high:'99'}}).rewardRisk,null);
assert.equal(evaluate({rank:{...rank,holder_asof:'2026-10-20'}}).state,'source_mismatch');
assert.equal(evaluate({check:{...check,confluence:false}}).state,'not_ready');
assert.equal(evaluate({tech:{...tech,rsi14:'75'}}).state,'overextended');
assert.equal(evaluate({rank:{...rank,close:'110'},tech:{...tech,close:'110'},
 risk:{...risk,last_close:'110'}}).state,'overextended');
assert.equal(evaluate({rank:{...rank,close:'100'},tech:{...tech,close:'100'},
 risk:{...risk,last_close:'100',prior20_close_high:'106'}}).state,'risk_unfavorable');
// No trade-ready result is possible without source, institutional, large-holder and risk evidence.
for(const candidate of [null,{},undefined]){
 const p=evaluate({risk:candidate});
 assert.equal(p.state,'risk_unknown');
 assert.equal(p.canConsider,false);
}
console.log('PASS 3.0Z swing playbook: date gates, exact sources, no chasing, MA20 observation, historical-close RR and no win-rate');
