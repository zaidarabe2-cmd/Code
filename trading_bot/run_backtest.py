"""
Backtest completo para XAUUSD + NAS100 en M30.

Corre 12 simulaciones por instrumento (diversidad de regímenes) y reporta:
  - Estadísticas individuales por instrumento
  - Portfolio combinado (ambos en paralelo)
  - Proyección mensual/anual resultante
"""
import sys
import os
import numpy as np
import argparse

sys.path.insert(0, os.path.dirname(__file__))

import generate_data
from backtest import simulate
from config import MIN_RR_RATIO, RISK_PER_TRADE_PCT, SYMBOLS


# ── Per-instrument backtest ───────────────────────────────────────────────────

def run_instrument(instrument: str, n_candles: int, rr: float, n_seeds: int) -> list:
    all_trades = []
    print(f"\n  [{instrument}]")
    for seed in range(n_seeds):
        df = generate_data.generate_market(n_candles, instrument, seed, timeframe_minutes=30)
        trades = simulate(df, rr=rr, instrument=instrument)
        all_trades.extend(trades)
        n = len(trades)
        if n == 0:
            print(f"    Semilla {seed:2d}:  sin señales")
            continue
        wins = sum(1 for t in trades if t.won)
        wr   = wins / n * 100
        gross_win  = sum(t.r_multiple for t in trades if t.won)
        gross_loss = abs(sum(t.r_multiple for t in trades if not t.won))
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
        print(f"    Semilla {seed:2d}: {n:3d} trades | WR {wr:5.1f}% | PF {pf:.2f}")
    return all_trades


# ── Aggregate stats ───────────────────────────────────────────────────────────

def stats(trades: list, rr: float) -> dict:
    if not trades:
        return {}
    n = len(trades)
    wins   = [t for t in trades if t.won]
    losses = [t for t in trades if not t.won]
    wr     = len(wins) / n * 100
    r_vals = [t.r_multiple for t in trades]
    exp    = float(np.mean(r_vals))
    # Profit factor from ACTUAL net R outcomes (cost-aware), not idealised rr.
    gross_win  = sum(r for r in r_vals if r > 0)
    gross_loss = abs(sum(r for r in r_vals if r < 0))
    pf     = gross_win / gross_loss if gross_loss > 0 else float("inf")
    bars   = float(np.mean([t.bars_held for t in trades]))
    return {"n": n, "wr": wr, "pf": pf, "exp": exp, "bars": bars}


def print_stats(label: str, s: dict, rr: float):
    if not s:
        print(f"  {label}: sin trades")
        return
    be = 1 / (1 + rr) * 100
    ok = "✅" if s["exp"] > 0 and s["pf"] > 1.3 else ("⚠️ " if s["exp"] > 0 else "❌")
    print(f"  {label:<10} | Trades: {s['n']:>4} | WR: {s['wr']:5.1f}%"
          f" (BE:{be:.0f}%) | PF: {s['pf']:.2f} | E: {s['exp']:+.3f}R | {ok}")


# ── Projection ────────────────────────────────────────────────────────────────

def project(trades: list, n_seeds: int, n_candles: int,
            balance: float, risk: float, rr: float) -> None:
    if not trades:
        return
    # M30: 30min/candle, 24h/day × 5 days/week = 48 × 5 = 240 candles/week
    # 240 × 4.33 weeks/month = ~1039 candles/month (forex/indices, 24h/5d market)
    M30_CANDLES_PER_MONTH = 240 * 4.33
    months_per_seed = n_candles / M30_CANDLES_PER_MONTH
    trades_per_month = (len(trades) / n_seeds) / months_per_seed

    exp = float(np.mean([t.r_multiple for t in trades]))
    gain_per_trade = exp * (risk / 100.0)
    monthly_factor = (1 + gain_per_trade) ** trades_per_month
    monthly_pct    = (monthly_factor - 1) * 100
    annual_pct     = (monthly_factor ** 12 - 1) * 100

    print(f"\n  {'─'*56}")
    print(f"  PROYECCIÓN M30 ({','.join(SYMBOLS)}) — riesgo {risk}% | R:R 1:{rr:g}")
    print(f"  {'─'*56}")
    print(f"  Trades/mes por instrumento : {trades_per_month/len(SYMBOLS):.1f}")
    print(f"  Trades/mes total (2 pares) : {trades_per_month:.1f}")
    print(f"  Expectancy media           : {exp:+.3f} R/trade")
    print(f"  Rentabilidad mensual       : {monthly_pct:+.2f}%")
    print(f"  Rentabilidad anual         : {annual_pct:+.1f}%")
    print(f"  $1,000 → ${balance*monthly_factor**12:,.0f} en 12 meses")
    print(f"  $1,000 → ${balance*monthly_factor**36:,.0f} en 36 meses (compuesto)")

    # Worst case
    r_vals = [t.r_multiple for t in trades]
    exp_lo = exp - float(np.std(r_vals))
    gpt_lo = exp_lo * (risk / 100.0)
    mf_lo  = (1 + gpt_lo) ** trades_per_month
    mp_lo  = (mf_lo - 1) * 100
    print(f"\n  Peor caso estadístico (-1σ): {mp_lo:+.2f}%/mes"
          f" | ${balance*mf_lo**12:,.0f} en 12m")
    print(f"  {'─'*56}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", type=int,   default=8000, help="Velas M30 por dataset")
    ap.add_argument("--seeds",   type=int,   default=12,   help="Nº de simulaciones")
    ap.add_argument("--risk",    type=float, default=RISK_PER_TRADE_PCT)
    ap.add_argument("--rr",      type=float, default=MIN_RR_RATIO)
    ap.add_argument("--balance", type=float, default=1000.0)
    args = ap.parse_args()

    instruments = SYMBOLS   # XAUUSD, NAS100

    print(f"\n{'═'*60}")
    print(f"  BACKTEST M30 — {' + '.join(instruments)}")
    print(f"  {args.seeds} simulaciones × {args.candles:,} velas | riesgo {args.risk}% | R:R 1:{args.rr:g}")
    print(f"{'═'*60}")

    all_trades = []
    per_instrument = {}

    for inst in instruments:
        trades = run_instrument(inst, args.candles, args.rr, args.seeds)
        per_instrument[inst] = trades
        all_trades.extend(trades)

    # ── Individual stats ──────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  RESUMEN POR INSTRUMENTO")
    print(f"{'─'*60}")
    for inst, trades in per_instrument.items():
        s = stats(trades, args.rr)
        print_stats(inst, s, args.rr)

    # ── Combined stats ────────────────────────────────────────────────────────
    print(f"{'─'*60}")
    s_all = stats(all_trades, args.rr)
    print_stats("PORTFOLIO", s_all, args.rr)

    # Drawdown simulation on combined portfolio
    equity = args.balance
    peak   = args.balance
    max_dd = 0.0
    max_cl = cl = 0
    for t in all_trades:
        pnl  = t.r_multiple * equity * (args.risk / 100.0)
        equity += pnl
        peak   = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
        cl = cl + 1 if not t.won else 0
        max_cl = max(max_cl, cl)

    print(f"\n  Max drawdown (portfolio)   : {max_dd:.1f}%")
    print(f"  Max pérdidas consecutivas  : {max_cl}")
    print(f"  Balance final              : ${equity:,.2f}"
          f"  ({(equity/args.balance-1)*100:+.1f}%)")

    project(all_trades, args.seeds, args.candles,
            args.balance, args.risk, args.rr)


if __name__ == "__main__":
    main()
