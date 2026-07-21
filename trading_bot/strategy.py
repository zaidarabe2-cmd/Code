"""
Main strategy: SMC + Wyckoff + Volume + Price Action confluence.

Entry logic:
  BUY  when:
    - SMC trend is bullish (BOS up or CHoCH up)
    - Price is at or near a bullish Order Block or bullish FVG
    - Wyckoff phase is accumulation (Spring/LPS/SOS)
    - Volume confirms (no_supply, climax_sell, or high RVOL on up-move)
    - Price action shows bullish pattern OR EMA trend is bullish

  SELL when the mirror conditions hold.

Additional filters:
  - No trade if an open trade for this symbol already exists (MAGIC)
  - Minimum R:R ratio enforced in risk_manager
"""
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Literal, Optional

from indicators import smc, wyckoff, volume, price_action, kronos_signal
from indicators.atr import atr
from config import KRONOS_ENABLED, KRONOS_WEIGHT
from config import OB_LOOKBACK, FVG_MIN_GAP_PCT, LIQUIDITY_LOOKBACK, BOS_LOOKBACK
from config import WYCKOFF_LOOKBACK, VOLUME_MA_PERIOD, SWING_WINDOW
from config import MIN_CONFLUENCE_SCORE, ATR_PERIOD, SL_ATR_MULT, SL_ATR_BUFFER
from config import ALLOWED_SESSIONS_UTC

logger = logging.getLogger(__name__)

CFG = {
    "OB_LOOKBACK":        OB_LOOKBACK,
    "FVG_MIN_GAP_PCT":    FVG_MIN_GAP_PCT,
    "LIQUIDITY_LOOKBACK": LIQUIDITY_LOOKBACK,
    "BOS_LOOKBACK":       BOS_LOOKBACK,
    "SWING_WINDOW":       SWING_WINDOW,
}


def _in_allowed_session(ts: pd.Timestamp) -> bool:
    """Returns False outside the configured trading sessions (UTC hours)."""
    if not ALLOWED_SESSIONS_UTC:
        return True
    h = ts.hour
    return any(start <= h < end for start, end in ALLOWED_SESSIONS_UTC)


@dataclass
class TradeSignal:
    direction: Optional[Literal["BUY", "SELL"]] = None
    entry:  float = 0.0
    sl:     float = 0.0
    tp:     float = 0.0
    reason: str   = ""
    score:  float = 0.0    # confluence score 0–1


def analyse(df: pd.DataFrame, symbol: str) -> TradeSignal:
    """
    Runs all indicator modules and produces a TradeSignal (or no-signal).
    `df` must have columns: open, high, low, close, tick_volume
    and be sorted oldest → newest.
    """
    if len(df) < 60:
        logger.warning("Not enough data (%d candles) for %s", len(df), symbol)
        return TradeSignal()

    # Session filter — XAUUSD and NAS100 have best institutional flow 07-17 UTC
    last_ts = df.index[-1]
    if not _in_allowed_session(last_ts):
        logger.debug("Outside trading session (%s UTC) — skipping %s", last_ts.hour, symbol)
        return TradeSignal()

    # ── Run indicator modules ─────────────────────────────────────────────────
    smc_sig = smc.analyse(df, CFG)
    wyk_sig = wyckoff.detect_phase(df, lookback=WYCKOFF_LOOKBACK, vol_ma_period=VOLUME_MA_PERIOD)
    vol_sig = volume.analyse(df, vol_ma_period=VOLUME_MA_PERIOD)
    pa_sig  = price_action.analyse(df)

    current_close = df["close"].iloc[-1]
    current_low   = df["low"].iloc[-1]
    current_high  = df["high"].iloc[-1]

    logger.info("[%s] Trend=%s | Wyckoff=%s(%s) | VSA=%s | PA=%s | RVOL=%.2f",
                symbol, smc_sig.trend, wyk_sig.phase, wyk_sig.sub_event,
                vol_sig.vsa_signal, pa_sig.pattern, vol_sig.rvol)

    # ── Score BUY confluence ──────────────────────────────────────────────────
    buy_score  = 0.0
    sell_score = 0.0
    buy_reasons  = []
    sell_reasons = []

    # 1. SMC structural trend
    if smc_sig.trend == "bullish":
        buy_score += 0.2
        buy_reasons.append("BOS bullish")
    elif smc_sig.trend == "bearish":
        sell_score += 0.2
        sell_reasons.append("BOS bearish")

    # 2. Recent CHoCH (reversal signal – highest weight)
    if smc_sig.last_choch:
        if "up" in smc_sig.last_choch.kind:
            buy_score  += 0.25
            buy_reasons.append("CHoCH bullish")
        else:
            sell_score += 0.25
            sell_reasons.append("CHoCH bearish")

    # 3. Price at Order Block
    active_bull_obs = [ob for ob in smc_sig.order_blocks if ob.kind == "bullish" and not ob.violated]
    active_bear_obs = [ob for ob in smc_sig.order_blocks if ob.kind == "bearish" and not ob.violated]

    for ob in active_bull_obs:
        if ob.bottom <= current_close <= ob.top:
            buy_score += 0.20
            buy_reasons.append(f"In bullish OB ({ob.bottom:.5f}–{ob.top:.5f})")
            break

    for ob in active_bear_obs:
        if ob.bottom <= current_close <= ob.top:
            sell_score += 0.20
            sell_reasons.append(f"In bearish OB ({ob.bottom:.5f}–{ob.top:.5f})")
            break

    # 4. Price at Fair Value Gap
    open_bull_fvgs = [f for f in smc_sig.fvgs if f.kind == "bullish" and not f.filled]
    open_bear_fvgs = [f for f in smc_sig.fvgs if f.kind == "bearish" and not f.filled]

    for fvg in open_bull_fvgs[-3:]:
        if fvg.bottom <= current_close <= fvg.top:
            buy_score += 0.15
            buy_reasons.append(f"In bullish FVG ({fvg.bottom:.5f}–{fvg.top:.5f})")
            break

    for fvg in open_bear_fvgs[-3:]:
        if fvg.bottom <= current_close <= fvg.top:
            sell_score += 0.15
            sell_reasons.append(f"In bearish FVG ({fvg.bottom:.5f}–{fvg.top:.5f})")
            break

    # 5. Wyckoff phase
    if wyk_sig.phase == "accumulation":
        buy_score += wyk_sig.strength * 0.15
        buy_reasons.append(f"Wyckoff accum ({wyk_sig.sub_event})")
    elif wyk_sig.phase == "markup":
        buy_score += wyk_sig.strength * 0.10
        buy_reasons.append("Wyckoff markup (SOS)")
    elif wyk_sig.phase == "distribution":
        sell_score += wyk_sig.strength * 0.15
        sell_reasons.append(f"Wyckoff dist ({wyk_sig.sub_event})")
    elif wyk_sig.phase == "markdown":
        sell_score += wyk_sig.strength * 0.10
        sell_reasons.append("Wyckoff markdown (SOW)")

    # 6. Volume signals
    if vol_sig.vsa_signal in ("no_supply", "climax_sell"):
        buy_score += 0.10
        buy_reasons.append(f"VSA: {vol_sig.vsa_signal}")
    if vol_sig.vsa_signal in ("no_demand", "climax_buy"):
        sell_score += 0.10
        sell_reasons.append(f"VSA: {vol_sig.vsa_signal}")
    if vol_sig.divergence == "bullish":
        buy_score += 0.05
        buy_reasons.append("Vol divergence bullish")
    if vol_sig.divergence == "bearish":
        sell_score += 0.05
        sell_reasons.append("Vol divergence bearish")

    # 7. Price action pattern
    if pa_sig.direction == "bullish":
        buy_score += pa_sig.strength * 0.10
        buy_reasons.append(f"PA: {pa_sig.pattern}")
    elif pa_sig.direction == "bearish":
        sell_score += pa_sig.strength * 0.10
        sell_reasons.append(f"PA: {pa_sig.pattern}")

    # 8. EMA trend confirmation
    if pa_sig.ema_trend == "bullish":
        buy_score += 0.05
    elif pa_sig.ema_trend == "bearish":
        sell_score += 0.05

    # 9. Kronos AI forecast (optional — neutral if disabled/unavailable)
    if KRONOS_ENABLED:
        k_sig = kronos_signal.forecast(df)
        if k_sig.available and k_sig.direction == "bullish":
            buy_score += k_sig.strength * KRONOS_WEIGHT
            buy_reasons.append(f"Kronos +{k_sig.expected_return*100:.2f}% (conf {k_sig.strength:.2f})")
        elif k_sig.available and k_sig.direction == "bearish":
            sell_score += k_sig.strength * KRONOS_WEIGHT
            sell_reasons.append(f"Kronos {k_sig.expected_return*100:.2f}% (conf {k_sig.strength:.2f})")

    # ── Decide signal ─────────────────────────────────────────────────────────
    MIN_SCORE = MIN_CONFLUENCE_SCORE   # configurable confluence threshold

    best_direction = None
    best_score = 0.0
    best_reasons = []

    if buy_score >= MIN_SCORE and buy_score > sell_score:
        best_direction = "BUY"
        best_score = buy_score
        best_reasons = buy_reasons
    elif sell_score >= MIN_SCORE and sell_score > buy_score:
        best_direction = "SELL"
        best_score = sell_score
        best_reasons = sell_reasons
    else:
        logger.debug("No signal – BUY=%.2f SELL=%.2f (need %.2f)", buy_score, sell_score, MIN_SCORE)
        return TradeSignal()

    # ── SL placement ──────────────────────────────────────────────────────────
    # Base SL at the relevant structure level (OB extreme / recent swing), then
    # floor the distance at SL_ATR_MULT * ATR so it is never tighter than the
    # market's noise — this is what keeps lot sizing and stop survival sane.
    atr_val = atr(df, ATR_PERIOD)
    min_dist = atr_val * SL_ATR_MULT
    buffer   = atr_val * SL_ATR_BUFFER

    if best_direction == "BUY":
        ob_lows = [ob.low for ob in active_bull_obs if ob.low < current_close]
        struct_sl = min(ob_lows) if ob_lows else current_low
        struct_sl -= buffer
        sl = min(struct_sl, current_close - min_dist)   # widen if structure is too tight
    else:
        ob_highs = [ob.high for ob in active_bear_obs if ob.high > current_close]
        struct_sl = max(ob_highs) if ob_highs else current_high
        struct_sl += buffer
        sl = max(struct_sl, current_close + min_dist)

    return TradeSignal(
        direction=best_direction,
        entry=current_close,
        sl=round(sl, 5),
        tp=0.0,             # filled by risk_manager
        reason=" | ".join(best_reasons),
        score=round(best_score, 3),
    )
