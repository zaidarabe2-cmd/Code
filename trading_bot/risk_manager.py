"""
Risk management: position sizing, SL/TP calculation.
"""
import logging
import MetaTrader5 as mt5

from config import RISK_PER_TRADE_PCT, MIN_RR_RATIO
from mt5_connector import get_balance, get_symbol_info

logger = logging.getLogger(__name__)


def calculate_lot(symbol: str, sl_pips: float, risk_pct: float = None) -> float:
    """
    Returns lot size so that a loss of `sl_pips` equals `risk_pct` of balance.
    """
    risk_pct = risk_pct or RISK_PER_TRADE_PCT
    balance = get_balance()
    if balance <= 0:
        return 0.01

    info = get_symbol_info(symbol)
    if info is None:
        return 0.01

    risk_amount = balance * (risk_pct / 100)
    pip_value = info.trade_tick_value * (info.point / info.trade_tick_size) if info.trade_tick_size else info.trade_tick_value
    value_per_pip_per_lot = pip_value * 10  # 10 ticks per pip for most FX

    if sl_pips <= 0 or value_per_pip_per_lot <= 0:
        return 0.01

    lot = risk_amount / (sl_pips * value_per_pip_per_lot)
    lot = max(info.volume_min, min(info.volume_max, round(lot / info.volume_step) * info.volume_step))
    logger.debug("Lot calc: balance=%.2f risk=%.2f sl_pips=%.1f → %.4f lots", balance, risk_amount, sl_pips, lot)
    return lot


def calculate_sl_tp(
    entry: float,
    direction: str,          # "BUY" or "SELL"
    sl_price: float,
    rr_ratio: float = None,
) -> tuple[float, float]:
    """
    Given entry and SL price, computes TP from the RR ratio.
    Returns (sl_price, tp_price).
    """
    rr = rr_ratio or MIN_RR_RATIO
    distance = abs(entry - sl_price)
    tp = entry + distance * rr if direction == "BUY" else entry - distance * rr
    return round(sl_price, 5), round(tp, 5)


def pips_to_price(symbol: str, pips: float) -> float:
    """Converts a pip count to a price distance."""
    info = get_symbol_info(symbol)
    if info is None:
        return pips * 0.0001
    return pips * info.point * 10
