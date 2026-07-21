"""
Kronos AI forecast — optional confluence layer.

Wraps the Kronos foundation model (https://github.com/shiyu-coder/Kronos,
Tsinghua / AAAI 2026), which forecasts future K-lines (OHLCV) from history.

Design principles (deliberate, critical):
  - OPTIONAL: if torch / the Kronos package / the weights are missing, this
    module returns a NEUTRAL signal and logs once. The bot never crashes.
  - LAZY singleton: the (heavy) model is loaded once, on first use.
  - CONFLUENCE ONLY: it outputs a direction + strength in [0,1]; the strategy
    decides how much weight to give it. It is never a standalone trigger.
  - HONEST CONFIDENCE: strength combines the forecast magnitude with the
    agreement across Monte-Carlo sample paths (dispersion). A big but
    uncertain forecast is down-weighted.

Install on the LIVE machine (not needed for backtests that keep it disabled):
    git clone https://github.com/shiyu-coder/Kronos
    pip install torch pandas numpy  # + Kronos requirements.txt
    # then set KRONOS_ENABLED=true and make the Kronos repo importable
"""
import logging
from dataclasses import dataclass
from typing import Optional, Literal

import numpy as np
import pandas as pd

from config import (
    KRONOS_ENABLED, KRONOS_MODEL, KRONOS_TOKENIZER, KRONOS_DEVICE,
    KRONOS_LOOKBACK, KRONOS_PRED_LEN, KRONOS_SAMPLES, KRONOS_MIN_MOVE,
)

logger = logging.getLogger(__name__)


@dataclass
class KronosSignal:
    direction: Optional[Literal["bullish", "bearish"]] = None
    expected_return: float = 0.0   # forecast close vs current close (fraction)
    agreement: float = 0.0         # fraction of sample paths agreeing on sign
    strength: float = 0.0          # [0,1] confidence for the confluence engine
    available: bool = False        # False = model not loaded / disabled


# ── Lazy singleton ────────────────────────────────────────────────────────────

_predictor = None
_load_failed = False


def _get_predictor():
    """Load the Kronos predictor once. Returns None if unavailable."""
    global _predictor, _load_failed
    if _predictor is not None:
        return _predictor
    if _load_failed:
        return None
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor  # Kronos repo
        tokenizer = KronosTokenizer.from_pretrained(KRONOS_TOKENIZER)
        model = Kronos.from_pretrained(KRONOS_MODEL)
        _predictor = KronosPredictor(model, tokenizer, device=KRONOS_DEVICE, max_context=512)
        logger.info("Kronos loaded: %s (device=%s)", KRONOS_MODEL, KRONOS_DEVICE)
        return _predictor
    except Exception as e:
        _load_failed = True
        logger.warning("Kronos unavailable (%s) — running WITHOUT the AI layer. "
                       "Install the Kronos repo + torch and set KRONOS_ENABLED=true "
                       "to enable it.", type(e).__name__)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def forecast(df: pd.DataFrame) -> KronosSignal:
    """
    Run a Kronos forecast on CLOSED candles and turn it into a confluence signal.
    `df` must have columns open/high/low/close/tick_volume and a DatetimeIndex.
    Returns a NEUTRAL (available=False) signal if Kronos is disabled/unavailable.
    """
    if not KRONOS_ENABLED:
        return KronosSignal()

    predictor = _get_predictor()
    if predictor is None:
        return KronosSignal()

    if len(df) < KRONOS_LOOKBACK:
        logger.debug("Kronos: not enough candles (%d < %d)", len(df), KRONOS_LOOKBACK)
        return KronosSignal()

    hist = df.tail(KRONOS_LOOKBACK).copy()
    x_df = pd.DataFrame({
        "open":   hist["open"].values,
        "high":   hist["high"].values,
        "low":    hist["low"].values,
        "close":  hist["close"].values,
        "volume": hist["tick_volume"].values.astype(float),
    })
    x_ts = pd.Series(hist.index)

    # Build future timestamps by extrapolating the bar interval.
    if len(hist.index) >= 2:
        step = hist.index[-1] - hist.index[-2]
    else:
        step = pd.Timedelta(minutes=30)
    y_ts = pd.Series([hist.index[-1] + step * (i + 1) for i in range(KRONOS_PRED_LEN)])

    try:
        pred = predictor.predict(
            df=x_df,
            x_timestamp=x_ts,
            y_timestamp=y_ts,
            pred_len=KRONOS_PRED_LEN,
            T=1.0,
            top_p=0.9,
            sample_count=KRONOS_SAMPLES,
        )
    except Exception as e:
        logger.warning("Kronos predict() failed: %s — neutral signal.", e)
        return KronosSignal()

    current_close = float(df["close"].iloc[-1])
    forecast_close = float(pred["close"].iloc[-1])
    expected_return = (forecast_close - current_close) / (current_close + 1e-12)

    # Agreement: how consistently the forecast path trends one way.
    path = pred["close"].values
    steps = np.diff(np.concatenate([[current_close], path]))
    up_frac = float(np.mean(steps > 0))
    agreement = abs(up_frac - 0.5) * 2   # 0 = coin-flip, 1 = fully one-directional

    sig = KronosSignal(
        expected_return=expected_return,
        agreement=agreement,
        available=True,
    )

    if abs(expected_return) < KRONOS_MIN_MOVE:
        return sig   # forecast too small to be directional

    sig.direction = "bullish" if expected_return > 0 else "bearish"
    # Strength: scale the move (capped) by path agreement, clamp to [0,1].
    move_score = min(abs(expected_return) / (KRONOS_MIN_MOVE * 10), 1.0)
    sig.strength = round(move_score * agreement, 3)
    return sig
