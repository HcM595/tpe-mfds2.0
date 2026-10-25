/* Run with: node tests/chip_trends_26b.test.js
 * No external packages; tests the pure, non-rendering integrity checks.
 */
const assert = require('node:assert/strict');
const model = require('../site/chip_trends_26b.js');
const fields = ['foreign_net_shares','trust_net_shares','dealer_net_shares'];
const row = (date, a=1000) => ({date, stock_id:'8064', foreign_net_shares:String(a),trust_net_shares:'100',dealer_net_shares:'-200',source:'archived'});
const days = ['2026-10-12','2026-10-13','2026-10-14','2026-10-15','2026-10-16'];
const price = days.map(date=>({date,close:100}));
let valid = model.entries(days.map(d=>row(d)), '8064', fields, false);
assert.equal(valid.records.length,5);
let sum=model.flowWindow(valid.records,5,price);
assert.equal(sum.ok,true);
assert.deepEqual(sum.sums,[5000,500,-1000]);
assert.equal(model.flowWindow(valid.records,10,price).ok,false);
valid=model.entries([row(days[0]),row(days[0]),row('2026-10-13',''),row('bad-date'),{...row(days[2]),stock_id:'2345'}],'8064',fields,false);
assert.equal(valid.duplicate,1);
assert.equal(valid.invalid,2);
assert.equal(valid.records.length,1);
valid=model.entries(days.filter(d=>d!==days[2]).map(d=>row(d)),'8064',fields,false);
assert.equal(model.flowWindow(valid.records,5,price).ok,false);
assert.equal(model.validDate('2026-02-30'),false);
assert.equal(model.validDate('2026-10-22'),true);
const holders=model.entries([{date:'2026-10-22',stock_id:'8064',holder400_pct:'105',holder1000_pct:'50'},
 {date:'2026-10-15',stock_id:'8064',holder400_pct:'52',holder1000_pct:'30'}],'8064',['holder400_pct','holder1000_pct'],true);
assert.equal(holders.invalid,1);
assert.equal(holders.records.length,1);
console.log('2.6B chip history unit tests passed');
