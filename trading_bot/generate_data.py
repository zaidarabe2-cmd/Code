"""
Generador de datos OHLCV realistas para backtesting.

Soporta perfiles de instrumento específicos:
  XAUUSD — Gold:     precio ~$2300, ATR M30 ~$5-6
  NAS100 — Nasdaq:   precio ~$19000, ATR M30 ~$60-80
  EURUSD — FX:       precio ~$1.10, ATR M30 ~0.0004

Simula comportamiento de mercado real:
  - Volatilidad agrupada (GARCH-simple)
  - Regímenes: tendencia alcista, bajista, lateral
  - Impulsos institucionales (news / liquidation events)
  - Tick volume correlacionado con el tamaño de la vela
"""
import numpy as np
import pandas as pd
import os

from config import INSTRUMENT_PROFILES


def generate_market(
    n_candles: int = 5000,
    instrument: str = "XAUUSD",
    seed: int = 42,
    timeframe_minutes: int = 30,
) -> pd.DataFrame:
    profile = INSTRUMENT_PROFILES.get(instrument.upper(), INSTRUMENT_PROFILES["XAUUSD"])
    start_price = profile["start_price"]
    base_vol    = profile["base_vol_m30"]

    rng = np.random.default_rng(seed)

    # ── GARCH-style volatility clustering ─────────────────────────────────────
    sigma = np.zeros(n_candles)
    sigma[0] = base_vol
    vol_long_ma = base_vol

    for i in range(1, n_candles):
        shock = rng.standard_normal()
        vol_long_ma = 0.99 * vol_long_ma + 0.01 * base_vol
        sigma[i] = np.sqrt(
            0.90 * sigma[i - 1] ** 2
            + 0.08 * (sigma[i - 1] * shock) ** 2
            + 0.02 * vol_long_ma ** 2
        )
        sigma[i] = np.clip(sigma[i], base_vol * 0.25, base_vol * 10)

    # ── Regime sequence: UP / DOWN / RANGE ────────────────────────────────────
    # M30 regime durations: shorter than H1 (more transitions visible per day)
    regime_lengths = rng.integers(40, 180, size=50)
    regime_types   = rng.choice(["up", "down", "range"], size=50, p=[0.35, 0.35, 0.30])
    regime_series  = []
    for r, d in zip(regime_types, regime_lengths):
        regime_series.extend([r] * int(d))
    regime_series = (regime_series * 5)[:n_candles]

    drift_map = {"up": base_vol * 0.15, "down": -base_vol * 0.15, "range": 0.0}

    # ── Price path ─────────────────────────────────────────────────────────────
    close_prices = np.zeros(n_candles)
    close_prices[0] = start_price

    for i in range(1, n_candles):
        drift = drift_map[regime_series[i]]
        impulse = 0.0
        if rng.random() < 0.008:    # ~0.8% chance of institutional impulse
            impulse = rng.choice([-1, 1]) * sigma[i] * rng.uniform(4, 9)
        ret = drift + sigma[i] * rng.standard_normal() + impulse
        close_prices[i] = max(close_prices[i - 1] * (1 + ret), start_price * 0.1)

    # ── Build OHLCV ────────────────────────────────────────────────────────────
    opens  = np.zeros(n_candles)
    highs  = np.zeros(n_candles)
    lows   = np.zeros(n_candles)
    vols   = np.zeros(n_candles, dtype=int)
    opens[0] = start_price

    for i in range(n_candles):
        if i > 0:
            opens[i] = close_prices[i - 1]
        o, c = opens[i], close_prices[i]
        intra = sigma[i] * rng.uniform(1.0, 2.5) * o
        top_wick    = intra * rng.uniform(0.1, 0.55)
        bottom_wick = intra * rng.uniform(0.1, 0.55)
        highs[i] = max(o, c) + top_wick
        lows[i]  = min(o, c) - bottom_wick
        body_pct = abs(c - o) / (o + 1e-10)
        vol_mult = 1 + body_pct / (base_vol + 1e-10) * 2
        vols[i]  = int(rng.integers(200, 1500) * vol_mult)

    df = pd.DataFrame({
        "open":        opens,
        "high":        highs,
        "low":         lows,
        "close":       close_prices,
        "tick_volume": vols,
    })
    df.index = pd.date_range(
        "2022-01-03 07:00", periods=n_candles, freq=f"{timeframe_minutes}min"
    )
    df.index.name = "time"
    return df


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default="XAUUSD",  help="XAUUSD, NAS100, EURUSD")
    ap.add_argument("--candles",    type=int, default=8000, help="Número de velas")
    ap.add_argument("--seed",       type=int, default=42)
    ap.add_argument("--out",        default="")
    args = ap.parse_args()

    df = generate_market(args.candles, args.instrument, args.seed, timeframe_minutes=30)
    os.makedirs("data", exist_ok=True)
    out = args.out or f"data/{args.instrument}_M30_synthetic.csv"
    df.to_csv(out)
    profile = INSTRUMENT_PROFILES.get(args.instrument.upper(), {})
    print(f"Generado: {out} ({len(df)} velas M30)")
    print(f"Instrumento : {args.instrument} — {profile.get('description','')}")
    print(f"Precio ini  : {df['open'].iloc[0]:.4f}")
    print(f"Precio final: {df['close'].iloc[-1]:.4f}")
    print(f"Rango total : {df['low'].min():.4f} – {df['high'].max():.4f}")


if __name__ == "__main__":
    main()
