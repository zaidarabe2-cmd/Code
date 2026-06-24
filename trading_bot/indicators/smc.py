"""
Smart Money Concepts (SMC) indicators.

Concepts implemented:
  - Swing Highs / Swing Lows
  - Break of Structure (BOS) and Change of Character (CHoCH)
  - Order Blocks (OB) – bullish and bearish
  - Fair Value Gaps (FVG) – bullish and bearish
  - Liquidity pools (equal highs / equal lows)
  - Inducement levels
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Literal


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SwingPoint:
    index: int
    price: float
    kind: Literal["high", "low"]


@dataclass
class OrderBlock:
    index: int
    top: float
    bottom: float
    kind: Literal["bullish", "bearish"]  # bullish OB = potential buy zone
    violated: bool = False


@dataclass
class FairValueGap:
    index: int          # middle candle index
    top: float
    bottom: float
    kind: Literal["bullish", "bearish"]
    filled: bool = False


@dataclass
class LiquidityPool:
    price: float
    kind: Literal["buy_side", "sell_side"]  # buy-side = above EQH, sell-side = below EQL
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
    last_bos: StructureEvent = None
    last_choch: StructureEvent = None


# ── Swing detection ───────────────────────────────────────────────────────────

def find_swings(df: pd.DataFrame, window: int = 5) -> list[SwingPoint]:
    """Detect swing highs and lows using a rolling window."""
    swings = []
    highs = df["high"].values
    lows  = df["low"].values
    n = len(df)

    for i in range(window, n - window):
        # swing high: highest in [i-window, i+window]
        if highs[i] == np.max(highs[i - window: i + window + 1]):
            swings.append(SwingPoint(i, highs[i], "high"))
        # swing low: lowest in [i-window, i+window]
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
    BOS: price breaks in the direction of the existing trend.
    CHoCH: price breaks against the existing trend (first sign of reversal).
    Returns a list of events and the current structural trend.
    """
    events: list[StructureEvent] = []
    if len(swings) < 4:
        return events, "ranging"

    highs = [s for s in swings if s.kind == "high"]
    lows  = [s for s in swings if s.kind == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return events, "ranging"

    # Determine trend: higher highs + higher lows = bullish, else bearish
    recent_highs = sorted(highs[-3:], key=lambda s: s.index)
    recent_lows  = sorted(lows[-3:],  key=lambda s: s.index)

    hh = recent_highs[-1].price > recent_highs[0].price
    hl = recent_lows[-1].price  > recent_lows[0].price
    ll = recent_lows[-1].price  < recent_lows[0].price
    lh = recent_highs[-1].price < recent_highs[0].price

    if hh and hl:
        current_trend = "bullish"
    elif ll and lh:
        current_trend = "bearish"
    else:
        current_trend = "ranging"

    close = df["close"].values
    n = len(df)

    # Scan last `lookback` candles for structure breaks
    prev_swing_high = highs[-2].price if len(highs) >= 2 else None
    prev_swing_low  = lows[-2].price  if len(lows) >= 2 else None

    for i in range(max(0, n - lookback), n):
        c = close[i]
        if prev_swing_high and c > prev_swing_high:
            kind = "BOS_up" if current_trend == "bullish" else "CHoCH_up"
            events.append(StructureEvent(i, c, kind))
            prev_swing_high = c
        if prev_swing_low and c < prev_swing_low:
            kind = "BOS_down" if current_trend == "bearish" else "CHoCH_down"
            events.append(StructureEvent(i, c, kind))
            prev_swing_low = c

    return events, current_trend


# ── Order Blocks ──────────────────────────────────────────────────────────────

def find_order_blocks(df: pd.DataFrame, lookback: int = 50) -> list[OrderBlock]:
    """
    Bullish OB: last bearish (red) candle before a strong bullish impulse that broke structure.
    Bearish OB: last bullish (green) candle before a strong bearish impulse that broke structure.
    """
    obs: list[OrderBlock] = []
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(df)
    start = max(0, n - lookback)

    for i in range(start + 2, n - 1):
        body = abs(c[i] - o[i])
        avg_body = np.mean(np.abs(c[start:i] - o[start:i])) + 1e-10

        # Strong impulse: body at least 1.5× average
        if body < 1.5 * avg_body:
            continue

        bullish_candle = c[i] > o[i]
        bearish_candle = c[i] < o[i]

        if bullish_candle:
            # Look back for the last bearish candle before this impulse
            for j in range(i - 1, max(start, i - 5), -1):
                if c[j] < o[j]:
                    obs.append(OrderBlock(j, high=h[j], low=l[j],
                                         top=max(o[j], c[j]),
                                         bottom=min(o[j], c[j]),
                                         kind="bullish"))
                    break

        if bearish_candle:
            for j in range(i - 1, max(start, i - 5), -1):
                if c[j] > o[j]:
                    obs.append(OrderBlock(j, high=h[j], low=l[j],
                                         top=max(o[j], c[j]),
                                         bottom=min(o[j], c[j]),
                                         kind="bearish"))
                    break

    # Mark violated OBs (price closed through the OB body)
    current_close = c[-1]
    for ob in obs:
        if ob.kind == "bullish" and current_close < ob.bottom:
            ob.violated = True
        elif ob.kind == "bearish" and current_close > ob.top:
            ob.violated = True

    return obs


# Fix: OrderBlock dataclass needs high/low fields too
@dataclass
class OrderBlock:
    index: int
    top: float
    bottom: float
    high: float
    low: float
    kind: Literal["bullish", "bearish"]
    violated: bool = False


# ── Fair Value Gaps ───────────────────────────────────────────────────────────

def find_fvgs(df: pd.DataFrame, min_gap_pct: float = 0.01) -> list[FairValueGap]:
    """
    Bullish FVG: candle[i-1].high < candle[i+1].low  (gap filled upward)
    Bearish FVG: candle[i-1].low  > candle[i+1].high (gap filled downward)
    """
    fvgs: list[FairValueGap] = []
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(df)

    for i in range(1, n - 1):
        mid_price = c[i]
        min_gap = mid_price * min_gap_pct

        # Bullish FVG
        gap_bottom = h[i - 1]
        gap_top    = l[i + 1]
        if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_gap:
            fvgs.append(FairValueGap(i, top=gap_top, bottom=gap_bottom, kind="bullish"))

        # Bearish FVG
        gap_top    = l[i - 1]
        gap_bottom = h[i + 1]
        if gap_top > gap_bottom and (gap_top - gap_bottom) >= min_gap:
            fvgs.append(FairValueGap(i, top=gap_top, bottom=gap_bottom, kind="bearish"))

    # Mark filled FVGs
    current_low  = l[-1]
    current_high = h[-1]
    for fvg in fvgs:
        if fvg.kind == "bullish" and current_low <= fvg.bottom:
            fvg.filled = True
        elif fvg.kind == "bearish" and current_high >= fvg.top:
            fvg.filled = True

    return fvgs


# ── Liquidity pools ───────────────────────────────────────────────────────────

def find_liquidity_pools(
    df: pd.DataFrame,
    lookback: int = 30,
    tolerance_pct: float = 0.002,
) -> list[LiquidityPool]:
    """
    Buy-side liquidity: equal highs (EQH) — stops cluster above.
    Sell-side liquidity: equal lows  (EQL) — stops cluster below.
    """
    pools: list[LiquidityPool] = []
    h = df["high"].values[-lookback:]
    l = df["low"].values[-lookback:]
    n = len(h)

    def near(a, b, tol):
        return abs(a - b) / ((a + b) / 2 + 1e-10) < tol

    # Equal highs
    for i in range(n):
        for j in range(i + 1, n):
            if near(h[i], h[j], tolerance_pct):
                pools.append(LiquidityPool(price=(h[i] + h[j]) / 2, kind="buy_side"))
                break  # one pool per swing high

    # Equal lows
    for i in range(n):
        for j in range(i + 1, n):
            if near(l[i], l[j], tolerance_pct):
                pools.append(LiquidityPool(price=(l[i] + l[j]) / 2, kind="sell_side"))
                break

    # Deduplicate pools that are too close together
    unique_pools = []
    for p in pools:
        if not any(near(p.price, u.price, tolerance_pct) and p.kind == u.kind
                   for u in unique_pools):
            unique_pools.append(p)

    # Mark swept pools
    current_high = df["high"].values[-1]
    current_low  = df["low"].values[-1]
    for pool in unique_pools:
        if pool.kind == "buy_side"  and current_high > pool.price:
            pool.touched = True
        if pool.kind == "sell_side" and current_low  < pool.price:
            pool.touched = True

    return unique_pools


# ── Main SMC analysis ─────────────────────────────────────────────────────────

def analyse(df: pd.DataFrame, cfg: dict) -> SMCSignals:
    """Run full SMC analysis on a DataFrame with OHLCV columns."""
    sig = SMCSignals()

    swings = find_swings(df, window=5)
    sig.swings = swings

    events, trend = detect_structure(df, swings, lookback=cfg.get("BOS_LOOKBACK", 20))
    sig.structure_events = events
    sig.trend = trend

    if events:
        bos_events   = [e for e in events if "BOS"   in e.kind]
        choch_events = [e for e in events if "CHoCH" in e.kind]
        sig.last_bos   = bos_events[-1]   if bos_events   else None
        sig.last_choch = choch_events[-1] if choch_events else None

    sig.order_blocks    = find_order_blocks(df, lookback=cfg.get("OB_LOOKBACK", 50))
    sig.fvgs            = find_fvgs(df, min_gap_pct=cfg.get("FVG_MIN_GAP_PCT", 0.01))
    sig.liquidity_pools = find_liquidity_pools(df, lookback=cfg.get("LIQUIDITY_LOOKBACK", 30))

    return sig
