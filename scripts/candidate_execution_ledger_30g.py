"""3.0G synthetic execution ledger, NOT an authenticated production backtest.

A corporate-action reference price is never a dividend or an adjustment
multiplier. All fills, cash distributions, fees, taxes and share changes must
be explicitly evidenced *outside* this calculator before use.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def amount(value, label, *, allow_zero=True):
    if isinstance(value, bool) or value is None or isinstance(value, float):
        raise ValueError(label + " must be a finite decimal string or integer, not float")
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError) as err:
        raise ValueError("Invalid " + label) from err
    if not v.is_finite() or (v < 0 if allow_zero else v <= 0):
        raise ValueError("Negative, zero, or non-finite " + label)
    return v


def utc(value, label):
    if not isinstance(value, str):
        raise ValueError(label + " missing timezone")
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise ValueError(label + " invalid date") from err
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(label + " missing UTC offset")
    return ts.astimezone(timezone.utc)


def decimal_text(v):
    """Plain decimal form for stable receipts, without meaningless trailing zeros."""
    result = format(v, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def candidate_trade_ledger(trade):
    """Calculate one hypothetical *executed* round trip from explicit inputs.

    Multipliers apply in event order; cash is paid on shares held immediately
    before each event. Fractional shares require independent cash-in-lieu
    certification and are rejected by this engine.
    """
    if not isinstance(trade, dict):
        raise ValueError("Missing trade ledger")
    horizon = trade.get("horizon_sessions")
    if horizon not in (10, 20, 60) or isinstance(horizon, bool):
        raise ValueError("Horizon must be one of 10/20/60 sessions")
    index_a, index_b = trade.get("entry_session_index"), trade.get("exit_session_index")
    if (type(index_a) is not int or type(index_b) is not int or
            index_a < 0 or index_b-index_a != horizon):
        raise ValueError("Exit must occur at the prespecified trading session")
    open_at = utc(trade.get("entry_at_utc"), "entry")
    close_at = utc(trade.get("exit_at_utc"), "exit")
    if close_at <= open_at:
        raise ValueError("Exit must follow entry")
    observed = utc(trade.get("signal_first_observed_at_utc"), "signal")
    public = utc(trade.get("official_signal_publication_at_utc"), "publication")
    if open_at <= max(observed, public):
        raise ValueError("Execution precedes full public and archived signal availability")
    shares = trade.get("entry_shares")
    if type(shares) is not int or shares <= 0:
        raise ValueError("Shares must be a positive integer")
    entry = amount(trade.get("entry_price_twd"), "entry price", allow_zero=False)
    exit_price = amount(trade.get("exit_price_twd"), "exit price", allow_zero=False)
    fee_buy = amount(trade.get("entry_fee_twd"), "entry fee")
    fee_sell = amount(trade.get("exit_fee_twd"), "exit fee")
    tax = amount(trade.get("exit_tax_twd"), "exit tax")
    slip = amount(trade.get("additional_slippage_twd"), "additional slippage")
    events = trade.get("distribution_events")
    if not isinstance(events, list):
        raise ValueError("Distribution event ledger must be explicitly supplied")
    cash = Decimal("0")
    effective_previous = open_at
    held = Decimal(shares)
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Invalid distribution event")
        effective = utc(event.get("effective_at_utc"), "corporate action")
        if effective <= effective_previous or effective > close_at:
            raise ValueError("Event ordering or date invalid")
        effective_previous = effective
        dividend = amount(event.get("cash_per_share_twd"), "cash per held share")
        ratio = amount(event.get("share_multiplier"), "share multiplier", allow_zero=False)
        cash += held * dividend
        held *= ratio
        if held != held.to_integral_value():
            raise ValueError("Fractional share entitlement requires independently audited cash-in-lieu")
    if trade.get("exit_shares") != int(held) or type(trade.get("exit_shares")) is not int:
        raise ValueError("Exit shares contradict corporate actions")
    cash_in_lieu = amount(trade.get("cash_in_lieu_twd"), "cash-in-lieu")
    if cash_in_lieu:
        raise ValueError("Cash-in-lieu is not supported until independently verified")
    cost = entry * shares + fee_buy
    proceeds = exit_price * held + cash - fee_sell - tax - slip
    net = proceeds-cost
    if cost <= 0:
        raise ValueError("Invalid entry capital")
    return {
        "status": "synthetic_or_unauthenticated_candidate_only",
        "horizon_sessions": horizon,
        "entry_debit_twd": decimal_text(cost),
        "exit_credit_including_distributions_twd": decimal_text(proceeds),
        "cash_distributions_twd": decimal_text(cash),
        "final_shares": int(held),
        "net_profit_twd": decimal_text(net),
        "candidate_net_total_return": decimal_text(net/cost),
        "candidate_positive_return": net > 0,
        "production_usable": False,
        "warning": "No official source receipts are authenticated by this calculator. Never treat candidate outcomes as real returns.",
    }
