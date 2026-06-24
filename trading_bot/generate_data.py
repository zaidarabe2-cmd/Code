"""
Generador de datos OHLCV realistas para backtesting.

Simula comportamiento de mercado real:
  - Volatilidad agrupada (GARCH-simple): los movimientos grandes vienen juntos
  - Regímenes: tendencia alcista, bajista, lateral (rango)
  - Order flow: impulsos seguidos de correcciones (estructura SMC)
  - Spreads y gaps propios de Forex H1
  - Tick volume correlacionado con el tamaño de las velas
"""
import numpy as np
import pandas as pd
import os


def generate_market(
    n_candles: int = 5000,
    start_price: float = 1.1000,
    seed: int = 42,
    timeframe_hours: int = 1,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # ── Volatility clustering (GARCH-like) ────────────────────────────────────
    # sigma fluctúa entre sesiones tranquilas y turbulentas
    base_vol    = 0.0005    # ~5 pips por vela H1 en EURUSD, aprox real
    vol_long_ma = base_vol
    sigma       = np.zeros(n_candles)
    sigma[0]    = base_vol

    for i in range(1, n_candles):
        # GARCH(1,1) simplificado
        shock        = rng.standard_normal()
        vol_long_ma  = 0.99 * vol_long_ma + 0.01 * base_vol
        sigma[i]     = np.sqrt(
            0.92 * sigma[i - 1] ** 2
            + 0.06 * (sigma[i - 1] * shock) ** 2
            + 0.02 * vol_long_ma ** 2
        )
        sigma[i] = np.clip(sigma[i], base_vol * 0.3, base_vol * 8)

    # ── Regime sequence ───────────────────────────────────────────────────────
    # Los regímenes son: UP_TREND, DOWN_TREND, RANGE
    regime_duration = rng.integers(60, 250, size=40)   # 40 regímenes
    regimes = rng.choice(["up", "down", "range"], size=40, p=[0.35, 0.35, 0.30])

    regime_series = []
    for r, d in zip(regimes, regime_duration):
        regime_series.extend([r] * int(d))
    regime_series = (regime_series * 5)[:n_candles]   # pad

    # Drift per candle based on regime
    drift_map = {"up": 0.00012, "down": -0.00012, "range": 0.0}

    # ── Price path ────────────────────────────────────────────────────────────
    close_prices = np.zeros(n_candles)
    close_prices[0] = start_price

    for i in range(1, n_candles):
        r = regime_series[i]
        drift = drift_map[r]
        # Add occasional impulse (news event / liquidity sweep)
        impulse = 0.0
        if rng.random() < 0.01:    # 1% chance of a big move
            impulse = rng.choice([-1, 1]) * sigma[i] * rng.uniform(3, 7)

        ret = drift + sigma[i] * rng.standard_normal() + impulse
        close_prices[i] = max(close_prices[i - 1] * (1 + ret), 0.0001)

    # ── Build OHLCV from close path ───────────────────────────────────────────
    opens  = np.zeros(n_candles)
    highs  = np.zeros(n_candles)
    lows   = np.zeros(n_candles)
    closes = close_prices.copy()
    vols   = np.zeros(n_candles, dtype=int)

    opens[0] = start_price
    for i in range(n_candles):
        if i > 0:
            opens[i] = closes[i - 1]

        # Intra-candle range ∝ sigma
        intra_range = sigma[i] * rng.uniform(1.0, 2.5) * opens[i]
        body_top    = max(opens[i], closes[i])
        body_bottom = min(opens[i], closes[i])
        wick_top    = intra_range * rng.uniform(0.1, 0.6)
        wick_bottom = intra_range * rng.uniform(0.1, 0.6)

        highs[i] = body_top    + wick_top
        lows[i]  = body_bottom - wick_bottom

        # Volume: higher on bigger candles, random baseline
        body_size = abs(closes[i] - opens[i]) / opens[i]
        vol_mult  = 1 + body_size / base_vol * 3
        vols[i]   = int(rng.integers(300, 1200) * vol_mult)

    rows = {
        "open":        opens,
        "high":        highs,
        "low":         lows,
        "close":       closes,
        "tick_volume": vols,
    }
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2022-01-03 00:00", periods=n_candles, freq=f"{timeframe_hours}h")
    df.index.name = "time"
    return df


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles",  type=int,   default=5000,  help="Número de velas")
    ap.add_argument("--price",    type=float, default=1.10,  help="Precio inicial")
    ap.add_argument("--seed",     type=int,   default=42,    help="Semilla aleatoria")
    ap.add_argument("--out",      default="data/EURUSD_H1_synthetic.csv")
    args = ap.parse_args()

    df = generate_market(args.candles, args.price, args.seed)
    os.makedirs("data", exist_ok=True)
    df.to_csv(args.out)
    print(f"Generado: {args.out} ({len(df)} velas)")
    print(f"Precio inicial: {df['open'].iloc[0]:.5f} | Final: {df['close'].iloc[-1]:.5f}")
    print(f"Rango total: {df['low'].min():.5f} – {df['high'].max():.5f}")


if __name__ == "__main__":
    main()
