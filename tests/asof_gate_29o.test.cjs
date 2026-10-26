const assert=require('node:assert/strict');
const G=require('../site/asof_gate_29o.js');
assert.equal(G.day('2026-02-29'),false);
assert.equal(G.day('2024-02-29'),true);
assert.equal(G.instant('2026-10-22'),null,'date labels are not release instants');
assert.equal(G.instant('2026-10-21T16:00:00'),null,'timezone-less publication is not proof');
assert.equal(G.cutoff('2026-10-22'),Date.parse('2026-10-21T16:00:00Z'));
const priceDay='2026-10-22';
const before='2026-10-21T15:59:59Z',after='2026-10-21T16:00:00Z';
const p={priceDay,reportDay:priceDay,firstSeen:before,officialPublished:before,sourceVerified:true};
assert.deepEqual(G.clockGate(p),{eligible:true,reason:'clocks_precede_cutoff'});
function fail(changes, reason){const r=G.clockGate({...p,...changes});assert.equal(r.eligible,false);assert.equal(r.reason,reason)}
fail({reportDay:'2026-10-23'},'report_after_price_day');
fail({firstSeen:after},'first_seen_after_cutoff');
fail({officialPublished:after},'publication_after_cutoff');
fail({officialPublished:''},'official_publication_unverified');
fail({sourceVerified:false},'source_authorization_missing');
fail({priceDay:'2026-02-30'},'invalid_price_day');
fail({reportDay:'2026-13-01'},'missing_report_day');
fail({firstSeen:'2026-10-21'},'first_seen_unverified');
const pit={stock_id:'8064',market:'上櫃',price_asof:priceDay,
 F2_source_report_date:priceDay,F2_observed_first_at_utc:before,
 F2_publication_at_utc:before,F2_usable_for_backtest:'true'};
const v={stock_id:'8064',market:'上櫃',asof:priceDay,source_status:'ok'};
assert.equal(G.f2(pit,v,priceDay).eligible,true,'synthetic fully-proven case should be distinguishable');
assert.equal(G.f2({...pit,F2_usable_for_backtest:'false'},v,priceDay).eligible,false);
assert.equal(G.f2({...pit,F2_publication_at_utc:''},v,priceDay).eligible,false);
assert.equal(G.f2(pit,{...v,stock_id:'3533'},priceDay).eligible,false);
const rev={stock_id:'8064',table_date:priceDay,first_seen_utc:before,
 disclosure_time_verified:'true'};
assert.equal(G.revenue(rev,priceDay).eligible,false,
 'bulk table date must never replace actual company release timestamp');
assert.equal(G.revenue({...rev,verified_publication_at_utc:before},priceDay).eligible,true);
assert.equal(G.revenue({...rev,verified_publication_at_utc:before,disclosure_time_verified:'false'},priceDay).eligible,false);
console.log('PASS 2.9O: strict Taipei cutoff, all three clocks, source authorization and no date-only release proof');
