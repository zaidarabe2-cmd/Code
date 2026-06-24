"""
Smart Money Concepts (SMC) indicators.

Concepts implemented:
  - Swing Highs / Swing Lows
  - Break of Structure (BOS) and Change of Character (CHoCH)
  - Order Blocks (OB) – bullish and bearish
  - Fair Value Gaps (FVG) – bullish and bearish
  - Liquidity pools (equal highs / equal lows)

NOTE: all functions assume `df` contains only CLOSED candles, sorted
oldest → newest. The caller is responsible for dropping the live candle.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Literal, Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SwingPoint:
    index: int
    price: float
    kind: Literal["high", "low"]


@dataclass
class OrderBlock:
    index: int                # candle index where the OB formed
    top: float                # top of the OB body
    bottom: float             # bottom of the OB body
    high: float               # full candle high (for mitigation/SL)
    low: float                # full candle low
    kind: Literal["bullish", "bearish"]   # bullish OB = potential buy zone
    violated: bool = False


@dataclass
class FairValueGap:
    index: int                # middle candle index
    top: float
    bottom: float
    kind: Literal["bullish", "bearish"]
    filled: bool = False


@dataclass
class LiquidityPool:
    price: float
    kind: Literal["buy_side", "sell_side"]
    touched: bool = False


@dataclass
class StructureEvent:
    index: int
    price: float
    kind: Literal["BOS_up", "BOS_down", "CHoCH_up", "CHoCH_down"]


@dataclass
class SMCSignals:
    trend: Literal["bullish", "bearish", "ranging"] = "ranging"
    swings: list = field(default_factory=list)
    order_blocks: list = field(default_factory=list)
    fvgs: list = field(default_factory=list)
    liquidity_pools: list = field(default_factory=list)
    structure_events: list = field(default_factory=list)
    last_bos: Optional[StructureEvent] = None
    last_choch: Optional[StructureEvent] = None


# ── Swing detection ───────────────────────────────────────────────────────────

def find_swings(df: pd.DataFrame, window: int = 5) -> list[SwingPoint]:
    """Detect fractal swing highs/lows using a centered window.

    A swing at index i is only confirmed `window` bars later, so the most
    recent `window` candles are intentionally excluded (no look-ahead).
    """
    swings = []
    highs = df["high"].values
    lows  = df["low"].values
    n = len(df)

    for i in range(window, n - window):
        if highs[i] == np.max(highs[i - window: i + window + 1]):
            swings.append(SwingPoint(i, highs[i], "high"))
        if lows[i] == np.min(lows[i - window: i + window + 1]):
            swings.append(SwingPoint(i, lows[i], "low"))

    return sorted(swings, key=lambda s: s.index)


# ── Break of Structure / Change of Character ──────────────────────────────────

def detect_structure(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    lookback: int = 20,
) -> tuple[list[StructureEvent], Literal["bullish", "bearish", "ranging"]]:
    """
    Walks confirmed swing points in order and labels each break:
      BOS   – break that continues the prevailing trend
      CHoCH – break against the prevailing trend (first reversal sign)

    The trend is maintained incrementally from the swing sequence rather than
    guessed from the last 3 swings, which is far more stable.
    """
    events: list[StructureEvent] = []
    if len(swings) < 4:
        return events, "ranging"

    close = df["close"].values
    n = len(df)

    # Track the most recent confirmed swing high/low as we walk forward.
    last_high = None        # (index, price)
    last_low = None
    trend = "ranging"

    cutoff = max(0, n - lookback)

    for sw in swings:
        if sw.kind == "high":
            # A close above the previous confirmed swing high = bullish break
            if last_high is not None and sw.price > last_high[1]:
                kind = "BOS_up" if trend == "bullish" else "CHoCH_up"
                trend = "bullish"
                if sw.index >= cutoff:
                    events.append(StructureEvent(sw.index, sw.price, kind))
            last_high = (sw.index, sw.price)
        else:  # low
            if last_low is not None and sw.price < last_low[1]:
                kind = "BOS_down" if trend == "bearish" else "CHoCH_down"
                trend = "bearish"
                if sw.index >= cutoff:
                    events.append(StructureEvent(sw.index, sw.price, kind))
            last_low = (sw.index, sw.price)

    return events, trend


# ── Order Blocks ──────────────────────────────────────────────────────────────

def find_order_blocks(df: pd.DataFrame, lookback: int = 50) -> list[OrderBlock]:
    """
    Bullish OB: last down candle before a strong up-impulse.
    Bearish OB: last up candle before a strong down-impulse.

    An OB is marked `violated` if price has CLOSED beyond its body at any
    point AFTER it formed (not just on the final candle).
    """
    obs: list[OrderBlock] = []
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(df)
    start = max(0, n - lookback)

    for i in range(start + 2, n):
        body = abs(c[i] - o[i])
        avg_body = np.mean(np.abs(c[start:i] - o[start:i])) + 1e-10
        if body < 1.5 * avg_body:          # require an impulsive candle
            continue

        if c[i] > o[i]:                    # bullish impulse → look for last red candle
            for j in range(i - 1, max(start - 1, i - 6), -1):
                if c[j] < o[j]:
                    obs.append(OrderBlock(j, top=max(o[j], c[j]), bottom=min(o[j], c[j]),
                                          high=h[j], low=l[j], kind="bullish"))
                    break
        elif c[i] < o[i]:                  # bearish impulse → look for last green candle
            for j in range(i - 1, max(start - 1, i - 6), -1):
                if c[j] > o[j]:
                    obs.append(OrderBlock(j, top=max(o[j], c[j]), bottom=min(o[j], c[j]),
                                          high=h[j], low=l[j], kind="bearish"))
                    break

    # Mark violation by scanning candles AFTER formation.
    for ob in obs:
        after = c[ob.index + 1:]
        if len(after) == 0:
            continue
        if ob.kind == "bullish" and np.any(after < ob.bottom):
            ob.violated = True
        elif ob.kind == "bearish" and np.any(after > ob.top):
            ob.violated = True

    return obs


# ── Fair Value Gaps ───────────────────────────────────────────────────────────

def find_fvgs(df: pd.DataFrame, min_gap_pct: float = 0.0005) -> list[FairValueGap]:
    """
    Bullish FVG: high[i-1] < low[i+1]   (imbalance to the upside)
    Bearish FVG: low[i-1]  > high[i+1]  (imbalance to the downside)

    A gap is `filled` if price traded back into it at any point after it
    formed (checked against the highs/lows of all subsequent candles).
    """
    fvgs: list[FairValueGap] = []
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(df)

    for i in range(1, n - 1):
        min_gap = c[i] * min_gap_pct

        gap_bottom = h[i - 1]
        gap_top    = l[i + 1]
        if gap_top - gap_bottom >= min_gap:
            fvgs.append(FairValueGap(i, top=gap_top, bottom=gap_bottom, kind="bullish"))

        gap_top    = l[i - 1]
        gap_bottom = h[i + 1]
        if gap_top - gap_bottom >= min_gap:
            fvgs.append(FairValueGap(i, top=gap_top, bottom=gap_bottom, kind="bearish"))

    for fvg in fvgs:
        # subsequent candles start at i+2 (i+1 is the third forming candle)
        lows_after  = l[fvg.index + 2:]
        highs_after = h[fvg.index + 2:]
        if len(lows_after) == 0:
            continue
        if fvg.kind == "bullish" and np.any(lows_after <= fvg.bottom):
            fvg.filled = True
        elif fvg.kind == "bearish" and np.any(highs_after >= fvg.top):
            fvg.filled = True

    return fvgs


# ── Liquidity pools ───────────────────────────────────────────────────────────

def find_liquidity_pools(
    df: pd.DataFrame,
    lookback: int = 30,
    tolerance_pct: float = 0.0008,
    swing_window: int = 3,
) -> list[LiquidityPool]:
    """
    Buy-side liquidity = equal swing highs (stops rest above).
    Sell-side liquidity = equal swing lows (stops rest below).
    Only genuine swing points are compared (not arbitrary adjacent candles).
    """
    sub = df.tail(lookback).reset_index(drop=True)
    swings = find_swings(sub, window=swing_window)
    swing_highs = [s for s in swings if s.kind == "high"]
    swing_lows  = [s for s in swings if s.kind == "low"]

    def near(a, b):
        return abs(a - b) / ((a + b) / 2 + 1e-10) < tolerance_pct

    pools: list[LiquidityPool] = []

    for i in range(len(swing_highs)):
        for j in range(i + 1, len(swing_highs)):
            if near(swing_highs[i].price, swing_highs[j].price):
                pools.append(LiquidityPool((swing_highs[i].price + swing_highs[j].price) / 2, "buy_side"))
                break
    for i in range(len(swing_lows)):
        for j in range(i + 1, len(swing_lows)):
            if near(swing_lows[i].price, swing_lows[j].price):
                pools.append(LiquidityPool((swing_lows[i].price + swing_lows[j].price) / 2, "sell_side"))
                break

    unique = []
    for p in pools:
        if not any(near(p.price, u.price) and p.kind == u.kind for u in unique):
            unique.append(p)

    cur_high = df["high"].values[-1]
    cur_low  = df["low"].values[-1]
    for pool in unique:
        if pool.kind == "buy_side" and cur_high > pool.price:
            pool.touched = True
        if pool.kind == "sell_side" and cur_low < pool.price:
            pool.touched = True

    return unique


# ── Main SMC analysis ─────────────────────────────────────────────────────────

def analyse(df: pd.DataFrame, cfg: dict) -> SMCSignals:
    """Run full SMC analysis on a DataFrame of CLOSED OHLCV candles."""
    sig = SMCSignals()

    swing_window = cfg.get("SWING_WINDOW", 5)
    swings = find_swings(df, window=swing_window)
    sig.swings = swings

    events, trend = detect_structure(df, swings, lookback=cfg.get("BOS_LOOKBACK", 20))
    sig.structure_events = events
    sig.trend = trend

    if events:
        bos = [e for e in events if "BOS" in e.kind]
        cho = [e for e in events if "CHoCH" in e.kind]
        sig.last_bos = bos[-1] if bos else None
        sig.last_choch = cho[-1] if cho else None

    sig.order_blocks    = find_order_blocks(df, lookback=cfg.get("OB_LOOKBACK", 50))
    sig.fvgs            = find_fvgs(df, min_gap_pct=cfg.get("FVG_MIN_GAP_PCT", 0.0005))
    sig.liquidity_pools = find_liquidity_pools(df, lookback=cfg.get("LIQUIDITY_LOOKBACK", 30))

    return sig
