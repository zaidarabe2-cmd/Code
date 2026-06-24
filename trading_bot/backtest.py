"""
Backtester
==========
Replays historical CLOSED candles through the exact same strategy the live bot
uses, simulates SL/TP fills, and reports the statistics that tell you whether
the edge is real BEFORE you risk the demo account:

  - Trades, win rate
  - Profit factor  (gross win / gross loss)  — want > 1.3
  - Expectancy in R (avg R per trade)        — must be > 0
  - Max drawdown
  - Final equity from a starting bankroll

Position sizing is fixed-fractional (risk RISK_PCT of equity per trade), which
is broker-independent and the correct way to measure raw edge.

Usage:
    python backtest.py                 # runs on synthetic data (smoke test)
    python backtest.py data/EURUSD_H1.csv
    python backtest.py data/EURUSD_H1.csv --risk 0.5 --rr 3 --balance 1000

CSV format: columns time,open,high,low,close,tick_volume (header required).
"""
import sys
import argparse
import numpy as np
import pandas as pd
from dataclasses import dataclass

import strategy
from config import MIN_RR_RATIO, RISK_PER_TRADE_PCT, INSTRUMENT_PROFILES


def _round_trip_cost(instrument: str) -> float:
    """Total cost in PRICE units paid per trade (spread + commission + slippage)."""
    p = INSTRUMENT_PROFILES.get((instrument or "").upper(), {})
    return (p.get("spread_price", 0.0)
            + p.get("commission_price", 0.0)
            + p.get("slippage_price", 0.0))


@dataclass
class Trade:
    direction: str
    entry: float
    sl: float
    tp: float
    exit_price: float
    r_multiple: float
    bars_held: int
    won: bool


def simulate(df: pd.DataFrame, rr: float, warmup: int = 150,
             instrument: str = "BACKTEST") -> list[Trade]:
    """Walk forward one bar at a time, open at most one position, resolve SL/TP.

    Realism:
      - Entry is the NEXT bar's OPEN (you cannot fill at the signal candle's
        close — that price is already gone when the candle closes).
      - Each trade pays the round-trip cost (spread + commission + slippage),
        expressed as a fraction of the risk distance and subtracted from R.
    """
    trades: list[Trade] = []
    n = len(df)
    cost_price = _round_trip_cost(instrument)
    i = warmup
    while i < n - 1:
        window = df.iloc[:i + 1]            # candles closed up to and including i
        sig = strategy.analyse(window, instrument)
        if sig.direction is None:
            i += 1
            continue

        # Fill at next bar's open — the realistic execution price.
        entry = float(df.iloc[i + 1]["open"])
        sl = sig.sl
        # Re-anchor the stop distance to the actual fill price.
        risk = abs(entry - sl)
        if risk <= 0:
            i += 1
            continue
        tp = entry + risk * rr if sig.direction == "BUY" else entry - risk * rr

        cost_r = cost_price / risk          # trading cost as a fraction of 1R

        # Resolve the trade on subsequent bars (start AFTER the entry bar).
        exit_price = None
        won = False
        bars_held = 0
        for k in range(i + 2, n):
            bar = df.iloc[k]
            bars_held += 1
            if sig.direction == "BUY":
                hit_sl = bar["low"] <= sl
                hit_tp = bar["high"] >= tp
            else:
                hit_sl = bar["high"] >= sl
                hit_tp = bar["low"] <= tp
            # Conservative: if a bar straddles both, assume SL first.
            if hit_sl:
                exit_price, won = sl, False
                break
            if hit_tp:
                exit_price, won = tp, True
                break

        if exit_price is None:           # ran out of data with position open
            break

        # R outcome net of trading costs.
        r = (rr if won else -1.0) - cost_r
        trades.append(Trade(sig.direction, entry, sl, tp, exit_price, r, bars_held, won))
        i += bars_held + 1               # skip past the closed trade (no overlap)

    return trades


def report(trades: list[Trade], start_balance: float, risk_pct: float) -> dict:
    if not trades:
        print("No trades generated. Loosen filters or provide more data.")
        return {}

    equity = start_balance
    peak = start_balance
    max_dd = 0.0
    curve = [start_balance]
    wins = losses = 0
    gross_win = gross_loss = 0.0
    r_sum = 0.0

    for t in trades:
        risk_amount = equity * (risk_pct / 100.0)
        pnl = t.r_multiple * risk_amount
        equity += pnl
        curve.append(equity)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
        r_sum += t.r_multiple
        if t.won:
            wins += 1
            gross_win += pnl
        else:
            losses += 1
            gross_loss += abs(pnl)

    n = len(trades)
    win_rate = wins / n * 100
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    expectancy_r = r_sum / n
    ret_pct = (equity - start_balance) / start_balance * 100

    print("\n" + "=" * 52)
    print("                BACKTEST RESULTS")
    print("=" * 52)
    print(f"  Trades            : {n}")
    print(f"  Win rate          : {win_rate:5.1f}%  ({wins}W / {losses}L)")
    print(f"  Profit factor     : {profit_factor:5.2f}      (want > 1.3)")
    print(f"  Expectancy / trade : {expectancy_r:+5.2f} R    (must be > 0)")
    print(f"  Max drawdown      : {max_dd:5.1f}%")
    print(f"  Start balance     : {start_balance:,.2f}")
    print(f"  Final balance     : {equity:,.2f}   ({ret_pct:+.1f}%)")
    print("=" * 52)

    # Break-even win rate needed for this R:R, as a sanity anchor.
    rr = trades[0].tp and abs(trades[0].tp - trades[0].entry) / abs(trades[0].entry - trades[0].sl)
    be = 1 / (1 + rr) * 100 if rr else 0
    verdict = "POSITIVE EDGE ✅" if expectancy_r > 0 and profit_factor > 1.0 else "NO EDGE ❌"
    print(f"  Break-even WR @ 1:{rr:.0f} ≈ {be:.0f}%  →  Verdict: {verdict}\n")

    return {
        "trades": n, "win_rate": win_rate, "profit_factor": profit_factor,
        "expectancy_r": expectancy_r, "max_dd": max_dd, "final": equity,
    }


def synthetic_data(n: int = 3000, seed: int = 7) -> pd.DataFrame:
    """Generate trending/ranging OHLCV so the pipeline can be smoke-tested."""
    rng = np.random.default_rng(seed)
    price = 1.10
    rows = []
    trend = 0.0
    for t in range(n):
        if t % 250 == 0:                       # periodically flip regime
            trend = rng.normal(0, 0.00010)
        ret = trend + rng.normal(0, 0.0006)
        o = price
        c = price * (1 + ret)
        hi = max(o, c) * (1 + abs(rng.normal(0, 0.0004)))
        lo = min(o, c) * (1 - abs(rng.normal(0, 0.0004)))
        vol = abs(rng.normal(1000, 350)) + (2000 if abs(ret) > 0.0010 else 0)
        rows.append((t, o, hi, lo, c, vol))
        price = c
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "tick_volume"])
    df["time"] = pd.to_datetime(df["time"], unit="h", origin="2023-01-01")
    return df.set_index("time")


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
    needed = {"open", "high", "low", "close", "tick_volume"}
    if not needed.issubset(df.columns):
        if "volume" in df.columns and "tick_volume" not in df.columns:
            df["tick_volume"] = df["volume"]
        missing = needed - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing columns: {missing}")
    return df


def main():
    ap = argparse.ArgumentParser(description="Backtest the SMC+Wyckoff strategy")
    ap.add_argument("csv", nargs="?", help="OHLCV CSV file (omit to use synthetic data)")
    ap.add_argument("--risk", type=float, default=RISK_PER_TRADE_PCT, help="%% risk per trade")
    ap.add_argument("--rr", type=float, default=MIN_RR_RATIO, help="Risk:Reward ratio")
    ap.add_argument("--balance", type=float, default=1000.0, help="Starting balance")
    args = ap.parse_args()

    if args.csv:
        print(f"Loading {args.csv} …")
        df = load_csv(args.csv)
    else:
        print("No CSV given — generating synthetic data (smoke test).")
        df = synthetic_data()

    print(f"Data: {len(df)} candles  ({df.index[0]} → {df.index[-1]})")
    print(f"Params: risk={args.risk}%  R:R=1:{args.rr:g}  balance={args.balance:g}")

    trades = simulate(df, rr=args.rr)
    report(trades, start_balance=args.balance, risk_pct=args.risk)


if __name__ == "__main__":
    main()
