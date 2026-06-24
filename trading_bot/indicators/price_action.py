"""
Price action patterns and key level detection.

  - Engulfing candles
  - Pin bars (hammer / shooting star)
  - Inside bars
  - Key support / resistance levels
  - Trend via EMA
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class PriceActionSignal:
    pattern: Optional[str] = None        # e.g. "bullish_engulfing", "pin_bar_high"
    direction: Optional[Literal["bullish", "bearish"]] = None
    ema_trend: Literal["bullish", "bearish", "ranging"] = "ranging"
    key_levels: list = field(default_factory=list)
    strength: float = 0.0


# ── EMA helpers ───────────────────────────────────────────────────────────────

def _ema(series: np.ndarray, period: int) -> np.ndarray:
    k = 2 / (period + 1)
    ema = np.zeros_like(series, dtype=float)
    ema[0] = series[0]
    for i in range(1, len(series)):
        ema[i] = series[i] * k + ema[i - 1] * (1 - k)
    return ema


def _trend_from_emas(c: np.ndarray) -> Literal["bullish", "bearish", "ranging"]:
    fast = _ema(c, 21)
    slow = _ema(c, 50)
    if fast[-1] > slow[-1] and fast[-3] < slow[-3]:
        return "bullish"
    if fast[-1] < slow[-1] and fast[-3] > slow[-3]:
        return "bearish"
    if fast[-1] > slow[-1]:
        return "bullish"
    if fast[-1] < slow[-1]:
        return "bearish"
    return "ranging"


# ── Candlestick patterns ──────────────────────────────────────────────────────

def _pin_bar(o, h, l, c, min_wick_ratio: float = 2.0):
    """Returns 'pin_bar_low' (bullish), 'pin_bar_high' (bearish), or None."""
    body   = abs(c - o)
    top_wick    = h - max(o, c)
    bottom_wick = min(o, c) - l
    if body < 1e-10:
        return None
    if bottom_wick >= min_wick_ratio * body and top_wick < body:
        return "pin_bar_low"    # hammer → bullish
    if top_wick >= min_wick_ratio * body and bottom_wick < body:
        return "pin_bar_high"   # shooting star → bearish
    return None


def _engulfing(o1, c1, o2, c2):
    """Detects engulfing pattern between two consecutive candles."""
    bull = c1 < o1 and c2 > o2 and c2 > o1 and o2 < c1  # bullish engulfing
    bear = c1 > o1 and c2 < o2 and c2 < o1 and o2 > c1  # bearish engulfing
    if bull:
        return "bullish_engulfing"
    if bear:
        return "bearish_engulfing"
    return None


def _inside_bar(h1, l1, h2, l2):
    return h2 < h1 and l2 > l1  # candle 2 is inside candle 1's range


# ── Key levels ────────────────────────────────────────────────────────────────

def find_key_levels(df: pd.DataFrame, lookback: int = 50, tolerance_pct: float = 0.001) -> list[float]:
    """Simple support/resistance from pivot highs and lows."""
    h = df["high"].values[-lookback:]
    l = df["low"].values[-lookback:]
    n = len(h)
    levels = []

    for i in range(1, n - 1):
        if h[i] > h[i - 1] and h[i] > h[i + 1]:
            levels.append(h[i])
        if l[i] < l[i - 1] and l[i] < l[i + 1]:
            levels.append(l[i])

    # Merge close levels
    unique = []
    for lvl in sorted(levels):
        if not unique or abs(lvl - unique[-1]) / (unique[-1] + 1e-10) > tolerance_pct:
            unique.append(lvl)

    return unique


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyse(df: pd.DataFrame) -> PriceActionSignal:
    sig = PriceActionSignal()
    if len(df) < 52:
        return sig

    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    sig.ema_trend  = _trend_from_emas(c)
    sig.key_levels = find_key_levels(df)

    # Check last candle for pin bar
    pin = _pin_bar(o[-1], h[-1], l[-1], c[-1])
    if pin:
        sig.pattern   = pin
        sig.direction = "bullish" if pin == "pin_bar_low" else "bearish"
        sig.strength  = 0.65
        return sig

    # Check last two candles for engulfing
    if len(o) >= 2:
        eng = _engulfing(o[-2], c[-2], o[-1], c[-1])
        if eng:
            sig.pattern   = eng
            sig.direction = "bullish" if "bullish" in eng else "bearish"
            sig.strength  = 0.70
            return sig

    # Inside bar on the previous candle
    if len(h) >= 3 and _inside_bar(h[-3], l[-3], h[-2], l[-2]):
        # Inside bar breakout direction determined by current candle
        if c[-1] > h[-2]:
            sig.pattern   = "inside_bar_breakout_up"
            sig.direction = "bullish"
            sig.strength  = 0.60
        elif c[-1] < l[-2]:
            sig.pattern   = "inside_bar_breakout_down"
            sig.direction = "bearish"
            sig.strength  = 0.60

    return sig
