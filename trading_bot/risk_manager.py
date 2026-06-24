"""
Risk management: position sizing, SL/TP calculation.

Position sizing uses the broker's tick_value / tick_size directly, which is
correct for ANY instrument (FX, indices, metals, crypto CFDs) — no fragile
"pips" abstraction or "10 ticks per pip" assumption.
"""
import logging

from config import RISK_PER_TRADE_PCT, MIN_RR_RATIO
from mt5_connector import get_balance, get_symbol_info

logger = logging.getLogger(__name__)


def money_at_risk_per_lot(symbol_info, sl_distance_price: float) -> float:
    """Money lost on 1.0 lot if price moves `sl_distance_price` against you."""
    tick_size  = symbol_info.trade_tick_size or symbol_info.point
    tick_value = symbol_info.trade_tick_value
    if tick_size <= 0 or tick_value <= 0:
        return 0.0
    ticks = sl_distance_price / tick_size
    return ticks * tick_value


def calculate_lot(symbol: str, sl_distance_price: float, risk_pct: float = None) -> float:
    """
    Lot size so that being stopped out (price moves `sl_distance_price`
    against the position) loses exactly `risk_pct` of the balance.
    """
    risk_pct = risk_pct if risk_pct is not None else RISK_PER_TRADE_PCT
    balance = get_balance()
    info = get_symbol_info(symbol)
    if balance <= 0 or info is None or sl_distance_price <= 0:
        return 0.0

    risk_amount = balance * (risk_pct / 100.0)
    per_lot_loss = money_at_risk_per_lot(info, sl_distance_price)
    if per_lot_loss <= 0:
        logger.error("Cannot compute per-lot loss for %s (tick_value/size missing)", symbol)
        return 0.0

    lot = risk_amount / per_lot_loss

    # Snap to the broker's volume step and clamp to min/max.
    step = info.volume_step or 0.01
    lot = round(lot / step) * step
    lot = max(info.volume_min, min(info.volume_max, lot))

    # If even the minimum lot risks more than allowed, refuse the trade.
    min_lot_risk = info.volume_min * per_lot_loss
    if min_lot_risk > risk_amount * 1.5:
        logger.warning("Min lot %.2f risks %.2f (> %.2f budget) on %s — skipping.",
                       info.volume_min, min_lot_risk, risk_amount, symbol)
        return 0.0

    logger.debug("Lot calc: bal=%.2f risk=%.2f sl_dist=%.5f per_lot_loss=%.4f → %.2f lots",
                 balance, risk_amount, sl_distance_price, per_lot_loss, lot)
    return round(lot, 2)


def calculate_tp(entry: float, sl_price: float, direction: str, rr_ratio: float = None) -> float:
    """TP from the entry/SL distance and the target R:R."""
    rr = rr_ratio if rr_ratio is not None else MIN_RR_RATIO
    distance = abs(entry - sl_price)
    tp = entry + distance * rr if direction == "BUY" else entry - distance * rr
    return round(tp, 5)


def enforce_min_stop(symbol: str, entry: float, sl_price: float, direction: str) -> float:
    """
    Ensure the SL respects the broker's minimum stop level (`trade_stops_level`)
    and the current spread. Returns a (possibly widened) SL price.
    """
    info = get_symbol_info(symbol)
    if info is None:
        return sl_price
    point = info.point or 0.00001
    min_dist = max(getattr(info, "trade_stops_level", 0), getattr(info, "spread", 0)) * point
    if min_dist <= 0:
        return sl_price

    if direction == "BUY":
        max_sl = entry - min_dist
        return min(sl_price, max_sl)
    else:
        min_sl = entry + min_dist
        return max(sl_price, min_sl)
