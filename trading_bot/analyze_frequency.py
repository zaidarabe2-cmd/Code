"""
ANÁLISIS CRÍTICO DE FRECUENCIA vs EXPECTATIVA
=============================================
Responde la pregunta del usuario con datos, no con opiniones:
  ¿Es posible 1-2 trades/día POR PAR manteniendo expectativa positiva con R:R 1:3?

Barre el umbral de confluencia (MIN_SCORE) y, para cada nivel, mide:
  - trades/día por instrumento
  - win rate
  - expectancy NETA de costes (R)
  - rentabilidad mensual implícita

Esto expone el trade-off real: bajar el umbral sube la frecuencia pero
hunde la calidad. El backtest dirá dónde está el punto de quiebre.
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))

import strategy
import generate_data
from backtest import simulate
from config import SYMBOLS

N_CANDLES = 8000
N_SEEDS   = 8
DAYS_PER_SEED = N_CANDLES * 30 / 60 / 24          # 8000 velas M30 → días calendario
M30_CANDLES_PER_MONTH = 240 * 4.33                # mercado 24h/5d


def sweep(instrument: str, scores: list[float], rr: float, risk: float):
    print(f"\n  [{instrument}]  ({DAYS_PER_SEED:.0f} días/seed × {N_SEEDS} seeds)")
    print(f"  {'MIN_SCORE':>9} {'trades/día':>11} {'WR':>7} {'Exp(R)':>8} {'%/mes':>8} {'verdict':>9}")
    print(f"  {'-'*56}")

    results = []
    for sc in scores:
        strategy.MIN_CONFLUENCE_SCORE = sc      # override en caliente
        all_trades = []
        for seed in range(N_SEEDS):
            df = generate_data.generate_market(N_CANDLES, instrument, seed, timeframe_minutes=30)
            all_trades.extend(simulate(df, rr=rr, instrument=instrument))

        n = len(all_trades)
        if n == 0:
            print(f"  {sc:>9.2f} {'0':>11} {'--':>7} {'--':>8} {'--':>8}")
            continue

        total_days = DAYS_PER_SEED * N_SEEDS
        trades_per_day = n / total_days
        wins = sum(1 for t in all_trades if t.won)
        wr = wins / n * 100
        exp = float(np.mean([t.r_multiple for t in all_trades]))

        trades_per_month = trades_per_day * (M30_CANDLES_PER_MONTH / (240*4.33/30.4))  # ~per month
        # Más directo: trades/mes = trades/día * días-mercado/mes (~21.7)
        trades_per_month = trades_per_day * 21.7
        gain_per_trade = exp * (risk / 100.0)
        monthly = ((1 + gain_per_trade) ** trades_per_month - 1) * 100

        verdict = "✅" if exp > 0.05 else ("⚠️" if exp > 0 else "❌")
        results.append((sc, trades_per_day, wr, exp, monthly))
        print(f"  {sc:>9.2f} {trades_per_day:>11.2f} {wr:>6.1f}% {exp:>+8.3f} {monthly:>+7.2f}% {verdict:>8}")

    return results


def main():
    rr = 3.0
    risk = 0.5
    scores = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]

    print("═"*64)
    print("  BARRIDO FRECUENCIA vs EXPECTATIVA — R:R 1:3 | riesgo 0.5%")
    print("  (objetivo del usuario: 1-2 trades/día por par)")
    print("═"*64)

    for inst in SYMBOLS:
        sweep(inst, scores, rr, risk)

    print(f"\n  {'─'*56}")
    print("  LECTURA:")
    print("  • 'trades/día' debe llegar a 1-2 para cumplir el objetivo.")
    print("  • Pero la Exp(R) NETA debe seguir > 0 o se pierde dinero más rápido.")
    print("  • Si al subir frecuencia la Exp cae a ~0 o negativo → el objetivo")
    print("    de 1-2/día es incompatible con R:R 1:3 en M30 (límite estructural).")
    print(f"  {'─'*56}\n")


if __name__ == "__main__":
    main()
