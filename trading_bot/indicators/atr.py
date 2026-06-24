"""Average True Range — shared volatility measure used for SL sizing."""
import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> float:
    """Returns the latest ATR value (Wilder's smoothing approximated by SMA)."""
    if len(df) < period + 1:
        return 0.0
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    prev_close = np.roll(c, 1)
    tr = np.maximum.reduce([
        h - l,
        np.abs(h - prev_close),
        np.abs(l - prev_close),
    ])
    tr[0] = h[0] - l[0]
    return float(np.mean(tr[-period:]))
