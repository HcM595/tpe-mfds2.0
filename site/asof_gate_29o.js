/* TPE-MFDS 2.9O: strict historical-as-of availability gate.
   A source's report day and our first capture are NOT its publication time.
   For historical price day D, a conservative research cutoff is D 00:00 Asia/Taipei.
   This module cannot, by itself, certify model factors, adjusted prices or backtests. */
(function(root) {
  'use strict';
  function day(s) {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    const t = Date.parse(s + 'T00:00:00Z');
    return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === s;
  }
  function instant(s) {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(s)) return null;
    const ms = Date.parse(s);
    return Number.isFinite(ms) ? ms : null;
  }
  function cutoff(priceDay) { return day(priceDay) ? Date.parse(priceDay + 'T00:00:00+08:00') : null; }
  function clockGate(params) {
    const {priceDay, reportDay, firstSeen, officialPublished, sourceVerified} = params || {};
    const cut = cutoff(priceDay);
    if (cut === null) return {eligible:false, reason:'invalid_price_day'};
    if (!day(reportDay)) return {eligible:false, reason:'missing_report_day'};
    if (reportDay > priceDay) return {eligible:false, reason:'report_after_price_day'};
    const captured = instant(firstSeen);
    if (captured === null) return {eligible:false, reason:'first_seen_unverified'};
    if (captured >= cut) return {eligible:false, reason:'first_seen_after_cutoff'};
    const published = instant(officialPublished);
    if (published === null) return {eligible:false, reason:'official_publication_unverified'};
    if (published >= cut) return {eligible:false, reason:'publication_after_cutoff'};
    if (published > captured) return {eligible:false, reason:'capture_precedes_official_release'};
    if (sourceVerified !== true) return {eligible:false, reason:'source_authorization_missing'};
    return {eligible:true, reason:'clocks_precede_cutoff'};
  }
  function f2(pit, valuation, priceDay) {
    if (!pit || !pit.stock_id || !valuation || !valuation.stock_id ||
        pit.stock_id !== valuation.stock_id || pit.market !== valuation.market)
      return {eligible:false,reason:'missing_or_mismatched_source'};
    if (pit.price_asof !== priceDay || valuation.asof !== priceDay)
      return {eligible:false,reason:'source_price_day_mismatch'};
    return clockGate({priceDay,reportDay:pit.F2_source_report_date,
      firstSeen:pit.F2_observed_first_at_utc,
      officialPublished:pit.F2_publication_at_utc,
      sourceVerified:pit.F2_usable_for_backtest === 'true' && valuation.source_status === 'ok'});
  }
  function revenue(row, priceDay) {
    if (!row || !row.stock_id) return {eligible:false,reason:'missing_source'};
    // table_date is a bulk table label, never a company filing timestamp.
    return clockGate({priceDay,reportDay:row.table_date,
      firstSeen:row.first_seen_utc,officialPublished:row.verified_publication_at_utc,
      sourceVerified:row.disclosure_time_verified === 'true'});
  }
  const api = {day,instant,cutoff,clockGate,f2,revenue};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.MFDSAsOfGate = api;
})(typeof window !== 'undefined' ? window : null);
