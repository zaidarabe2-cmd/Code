"""
Análisis completo de backtesting:
  1. Genera 8 conjuntos de datos con distintas semillas (diversidad de regímenes)
  2. Corre el backtest en cada uno con R:R 1:3 y 1:2
  3. Agrega estadísticas y muestra diagnóstico completo

Esto da una muestra estadísticamente significativa (objetivo: 100+ trades)
antes de arriesgar capital en la cuenta demo.
"""
import sys
import os
import numpy as np
import pandas as pd
import argparse

# Aseguramos que el path correcto esté en sys.path
sys.path.insert(0, os.path.dirname(__file__))

import generate_data
from backtest import simulate, report

os.makedirs("data", exist_ok=True)


def run_batch(n_candles: int, rr: float, risk: float, balance: float,
              n_seeds: int = 8, verbose: bool = True):
    all_trades = []
    equity_curves = []
    seed_results = []

    for seed in range(n_seeds):
        df = generate_data.generate_market(n_candles=n_candles, seed=seed)
        trades = simulate(df, rr=rr)
        all_trades.extend(trades)
        if verbose:
            wins = sum(1 for t in trades if t.won)
            n = len(trades)
            pf_num = sum(t.r_multiple for t in trades if t.won) * risk
            pf_den = abs(sum(t.r_multiple for t in trades if not t.won)) * risk
            pf = (pf_num / pf_den) if pf_den > 0 else float("inf")
            wr = wins / n * 100 if n > 0 else 0
            print(f"  Semilla {seed:2d}: {n:3d} trades | WR {wr:5.1f}% | PF {pf:.2f}")
        seed_results.append(trades)

    return all_trades, seed_results


def aggregate_report(all_trades, balance: float, risk: float, rr: float):
    if not all_trades:
        print("Sin trades.")
        return {}

    wins = [t for t in all_trades if t.won]
    losses = [t for t in all_trades if not t.won]
    n = len(all_trades)
    win_rate = len(wins) / n * 100
    r_values = [t.r_multiple for t in all_trades]
    expectancy_r = float(np.mean(r_values))
    gross_win  = sum(rr for t in wins)
    gross_loss = abs(sum(-1.0 for t in losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")

    # Fixed-fractional equity curve
    equity = balance
    peak = balance
    max_dd = 0.0
    max_consec_losses = 0
    cur_losses = 0
    for t in all_trades:
        pnl = t.r_multiple * equity * (risk / 100.0)
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
        if t.won:
            cur_losses = 0
        else:
            cur_losses += 1
            max_consec_losses = max(max_consec_losses, cur_losses)

    bars_per_trade = float(np.mean([t.bars_held for t in all_trades]))
    ret_pct = (equity - balance) / balance * 100
    be_wr = 1 / (1 + rr) * 100

    print("\n" + "═" * 60)
    print("          BACKTEST AGREGADO (múltiples regímenes)")
    print("═" * 60)
    print(f"  Total de operaciones        : {n}")
    print(f"  Win rate                    : {win_rate:5.1f}%  (break-even: {be_wr:.0f}%)")
    print(f"  Profit factor               : {profit_factor:5.2f}      (quieres > 1.3)")
    print(f"  Expectancy por trade        : {expectancy_r:+5.3f} R  (debe ser > 0)")
    print(f"  Máx drawdown                : {max_dd:5.1f}%")
    print(f"  Máx pérdidas consecutivas   : {max_consec_losses}")
    print(f"  Duración media de trade     : {bars_per_trade:.1f} velas")
    print(f"  Balance inicial             : {balance:,.2f}")
    print(f"  Balance final               : {equity:,.2f}   ({ret_pct:+.1f}%)")
    print("─" * 60)

    edge_ok = expectancy_r > 0 and profit_factor > 1.0
    statistically_ok = n >= 100
    verdict_parts = []
    if not statistically_ok:
        verdict_parts.append(f"muestra insuficiente ({n} trades, necesitas >= 100)")
    if not edge_ok:
        verdict_parts.append("sin edge positivo aún")

    if edge_ok and statistically_ok:
        verdict = "EDGE POSITIVO ✅ — puede probarse en demo"
    elif verdict_parts:
        verdict = "NO LISTO ❌  →  " + " | ".join(verdict_parts)
    else:
        verdict = "NEUTRAL — continua ajustando parámetros"

    print(f"\n  VEREDICTO: {verdict}\n")

    if not edge_ok or not statistically_ok:
        print("  Diagnóstico:")
        if win_rate < be_wr:
            print(f"    • Win rate {win_rate:.1f}% por debajo del break-even {be_wr:.0f}%")
            print( "      → Revisar filtros de confluencia o reducir R:R a 1:2")
        if n < 100:
            print(f"    • Solo {n} trades: umbrales muy estrictos o pocos datos")
            print( "      → Bajar MIN_SCORE en config.py o probar timeframe M15/M30")
        if max_dd > 20:
            print(f"    • Drawdown máx {max_dd:.1f}% es peligroso para $1000")
            print( "      → Reducir RISK_PCT o MAX_DAILY_LOSS_PCT")
    print()
    return {
        "n": n, "win_rate": win_rate, "profit_factor": profit_factor,
        "expectancy_r": expectancy_r, "max_dd": max_dd, "final": equity,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", type=int,   default=5000, help="Velas por dataset")
    ap.add_argument("--seeds",   type=int,   default=8,    help="Nº de datasets")
    ap.add_argument("--risk",    type=float, default=0.5,  help="Riesgo %% por trade")
    ap.add_argument("--rr",      type=float, default=3.0,  help="R:R objetivo")
    ap.add_argument("--balance", type=float, default=1000, help="Balance inicial")
    args = ap.parse_args()

    print(f"\n{'─'*60}")
    print(f"  Corriendo {args.seeds} datasets × {args.candles:,} velas")
    print(f"  Parámetros: riesgo={args.risk}%  R:R=1:{args.rr:g}  balance=${args.balance:g}")
    print(f"{'─'*60}\n")

    all_trades, _ = run_batch(
        n_candles=args.candles,
        rr=args.rr,
        risk=args.risk,
        balance=args.balance,
        n_seeds=args.seeds,
        verbose=True,
    )
    aggregate_report(all_trades, args.balance, args.risk, args.rr)


if __name__ == "__main__":
    main()
