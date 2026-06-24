"""
Volume analysis indicators.

  - Relative Volume (RVOL)
  - Volume divergence (price vs volume)
  - Volume spread analysis (VSA)
  - Effort vs Result (Wyckoff principle)
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class VolumeSignal:
    rvol: float = 1.0                     # relative volume (current / average)
    divergence: Optional[Literal["bullish", "bearish"]] = None
    vsa_signal: Optional[str] = None      # "no_demand", "no_supply", "climax_buy", "climax_sell"
    effort_result: Optional[str] = None   # "effort_up_no_result", "effort_down_no_result"
    strength: float = 0.0


def analyse(df: pd.DataFrame, vol_ma_period: int = 20) -> VolumeSignal:
    sig = VolumeSignal()
    if len(df) < vol_ma_period + 5:
        return sig

    v  = df["tick_volume"].values.astype(float)
    c  = df["close"].values
    h  = df["high"].values
    l  = df["low"].values
    o  = df["open"].values

    vol_ma = np.convolve(v, np.ones(vol_ma_period) / vol_ma_period, mode="full")[:len(v)]

    # ── Relative volume ───────────────────────────────────────────────────────
    sig.rvol = v[-1] / (vol_ma[-1] + 1e-10)

    # ── Volume divergence (last 10 candles) ───────────────────────────────────
    recent = 10
    price_change = c[-1] - c[-recent]
    vol_change   = np.mean(v[-5:]) - np.mean(v[-recent: -5])

    if price_change > 0 and vol_change < 0:
        sig.divergence = "bearish"   # price rising but volume falling → weak move
    elif price_change < 0 and vol_change < 0:
        sig.divergence = "bullish"   # price falling but volume also falling → selling exhaustion

    # ── VSA on last candle ────────────────────────────────────────────────────
    spread = h[-1] - l[-1]
    avg_spread = np.mean(h[-vol_ma_period:] - l[-vol_ma_period:])
    high_vol = v[-1] > vol_ma[-1] * 1.5
    low_vol  = v[-1] < vol_ma[-1] * 0.7
    narrow_spread = spread < avg_spread * 0.5
    wide_spread   = spread > avg_spread * 1.5
    bullish_close = c[-1] > (h[-1] + l[-1]) / 2  # close in upper half
    bearish_close = c[-1] < (h[-1] + l[-1]) / 2  # close in lower half

    if high_vol and wide_spread and bearish_close:
        sig.vsa_signal = "climax_sell"   # bearish climax, watch for reversal
        sig.strength = 0.8
    elif high_vol and wide_spread and bullish_close:
        sig.vsa_signal = "climax_buy"
        sig.strength = 0.8
    elif low_vol and narrow_spread and bullish_close:
        sig.vsa_signal = "no_demand"     # weak up-move, likely short setup
        sig.strength = 0.6
    elif low_vol and narrow_spread and bearish_close:
        sig.vsa_signal = "no_supply"     # weak down-move, likely long setup
        sig.strength = 0.6

    # ── Effort vs Result ──────────────────────────────────────────────────────
    # Big volume (effort) but small price movement (no result)
    big_volume  = v[-1] > vol_ma[-1] * 2.0
    small_range = spread < avg_spread * 0.4

    if big_volume and small_range and bullish_close:
        sig.effort_result = "effort_up_no_result"    # absorption, bearish
    elif big_volume and small_range and bearish_close:
        sig.effort_result = "effort_down_no_result"  # absorption, bullish

    return sig
