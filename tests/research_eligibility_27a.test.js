const assert=require('node:assert/strict');
const {evaluate}=require('../site/research_eligibility_27a.js');
function sample(n){return Array.from({length:n},(_,i)=>({date:new Date(Date.UTC(2026,0,1+i)).toISOString().slice(0,10),close:100,trade_value_twd:40000000}));}
let x=sample(120),asof=x.at(-1).date;
assert.equal(evaluate(x,asof).eligible,true);
assert.equal(evaluate(x.slice(1),asof).eligible,false);
assert.equal(evaluate(x,asof+'x').eligible,false);
assert.equal(evaluate(x.map(p=>({...p,trade_value_twd:20000000})),asof).status,'流動性未達門檻');
assert.equal(evaluate(x.map((p,i)=>i===119?{...p,trade_value_twd:''}:p),asof).turnover,null);
assert.equal(evaluate(x,asof).factorEligible,false);
// 2.9G: a later price must not lift the 120-session screen or pollute 20-day liquidity.
const later={date:'2026-12-31',close:200,trade_value_twd:9000000000};
assert.equal(evaluate([...x.slice(1),later],asof).eligible,false);
assert.equal(evaluate([...x,later],asof).eligible,true);
assert.equal(evaluate([...x,later],asof).count,120);
assert.equal(evaluate([...x,later],asof).latest,asof);
assert.equal(evaluate([...x,later],asof).turnover,40000000);
// Future observations must not turn insufficient historical turnover into a pass.
assert.equal(evaluate([...x.slice(0,-1),later],asof).eligible,false);
assert.equal(evaluate([...x,later],asof+'x').eligible,false);
assert.equal(evaluate(x,'2026-01-01').eligible,false);
assert.equal(evaluate(x,asof).factorEligible,false);
console.log('2.7A original eligibility tests passed');
