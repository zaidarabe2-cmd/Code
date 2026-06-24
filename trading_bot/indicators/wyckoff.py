"""
Wyckoff Method phase detection.

Phases detected:
  Accumulation: PS → SC → AR → ST → Spring → SOS → LPS → Markup
  Distribution: PSY → BC → AR → UT → UTAD → SOW → LPSY → Markdown

Simplified approach: detects accumulation vs. distribution ranges
and the critical Spring/Upthrust events using volume + price structure.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class WyckoffPhase:
    phase: Literal[
        "accumulation", "distribution",
        "markup", "markdown",
        "unknown"
    ] = "unknown"
    sub_event: Optional[str] = None   # Spring, Upthrust, SOS, SOW, etc.
    range_high: Optional[float] = None
    range_low:  Optional[float] = None
    strength: float = 0.0             # 0–1 confidence


def _volume_ma(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    ma = np.convolve(volumes, np.ones(period) / period, mode="full")
    return ma[:len(volumes)]


def _is_high_volume(vol: float, vol_ma: float, threshold: float = 1.5) -> bool:
    return vol > vol_ma * threshold


def _is_low_volume(vol: float, vol_ma: float, threshold: float = 0.7) -> bool:
    return vol < vol_ma * threshold


def detect_phase(df: pd.DataFrame, lookback: int = 100, vol_ma_period: int = 20) -> WyckoffPhase:
    """
    Detects the current Wyckoff phase from the last `lookback` candles.
    """
    data = df.tail(lookback).copy().reset_index(drop=True)
    if len(data) < vol_ma_period + 10:
        return WyckoffPhase()

    o = data["open"].values
    h = data["high"].values
    l = data["low"].values
    c = data["close"].values
    v = data["tick_volume"].values.astype(float)

    vol_ma = _volume_ma(v, vol_ma_period)
    n = len(data)

    # ── Define trading range ──────────────────────────────────────────────────
    # Use middle third for range definition (avoids extremes)
    mid_start = n // 3
    mid_end   = 2 * n // 3
    range_high = np.max(h[mid_start:mid_end])
    range_low  = np.min(l[mid_start:mid_end])
    range_size = range_high - range_low

    if range_size < 1e-8:
        return WyckoffPhase()

    current_close = c[-1]
    current_vol   = v[-1]
    current_vol_ma = vol_ma[-1]

    # ── Detect Spring (Accumulation) ──────────────────────────────────────────
    # Price dips below range_low then closes back inside on declining volume
    spring_detected = False
    for i in range(max(0, n - 10), n):
        if (l[i] < range_low                      # penetrates below support
                and c[i] > range_low              # closes back above
                and _is_low_volume(v[i], vol_ma[i])):  # weak selling = no supply
            spring_detected = True
            break

    # ── Detect Upthrust (Distribution) ───────────────────────────────────────
    upthrust_detected = False
    for i in range(max(0, n - 10), n):
        if (h[i] > range_high                     # penetrates above resistance
                and c[i] < range_high             # closes back below
                and _is_high_volume(v[i], vol_ma[i])):  # high selling volume = no demand
            upthrust_detected = True
            break

    # ── Price position relative to range ─────────────────────────────────────
    range_position = (current_close - range_low) / (range_size + 1e-10)

    # ── Volume trend ──────────────────────────────────────────────────────────
    early_vol = np.mean(v[: n // 3])
    late_vol  = np.mean(v[2 * n // 3:])
    volume_contracting = late_vol < early_vol * 0.8  # volume drying up in range

    # ── Classify phase ────────────────────────────────────────────────────────
    phase = WyckoffPhase(range_high=range_high, range_low=range_low)

    if spring_detected:
        # Classic accumulation spring: expect markup
        phase.phase     = "accumulation"
        phase.sub_event = "Spring"
        phase.strength  = 0.8

    elif upthrust_detected:
        phase.phase     = "distribution"
        phase.sub_event = "Upthrust"
        phase.strength  = 0.8

    elif volume_contracting and range_position < 0.35:
        # Price at bottom of range, volume drying up → potential accumulation
        phase.phase     = "accumulation"
        phase.sub_event = "ST/LPS"
        phase.strength  = 0.6

    elif volume_contracting and range_position > 0.65:
        # Price at top of range, volume drying up → potential distribution
        phase.phase     = "distribution"
        phase.sub_event = "LPSY"
        phase.strength  = 0.6

    elif current_close > range_high and _is_high_volume(current_vol, current_vol_ma):
        # Breakout above range on high volume → markup
        phase.phase     = "markup"
        phase.sub_event = "SOS"
        phase.strength  = 0.75

    elif current_close < range_low and _is_high_volume(current_vol, current_vol_ma):
        # Breakdown below range on high volume → markdown
        phase.phase     = "markdown"
        phase.sub_event = "SOW"
        phase.strength  = 0.75

    else:
        phase.phase    = "unknown"
        phase.strength = 0.0

    return phase
