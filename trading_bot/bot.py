"""
Trading Bot – main loop.

Run:
    python bot.py

Set DRY_RUN=false in .env (or config.py) to enable live trading.

Profitability / survival rules enforced here:
  - Acts only on CLOSED candles (no repainting on the live bar).
  - At most one trade per candle / setup (ONE_TRADE_PER_BAR).
  - Daily loss limit, consecutive-loss cool-down, total drawdown kill-switch.
  - R:R >= MIN_RR_RATIO (default 1:3) by construction.
"""
import time
import logging
import signal
import sys
from datetime import datetime, date

import pandas as pd

from config import (
    SYMBOLS, SYMBOL, TIMEFRAME, LOOP_INTERVAL_SEC, MAX_OPEN_TRADES,
    MIN_RR_RATIO, DRY_RUN,
    MAX_DAILY_LOSS_PCT, MAX_CONSECUTIVE_LOSSES, MAX_TOTAL_DRAWDOWN_PCT, ONE_TRADE_PER_BAR,
)
import mt5_connector as mt5c
import strategy
import risk_manager as rm
import portfolio
import journal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trading_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot")

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("Shutdown signal received, stopping bot…")
    _running = False


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Session / risk state ──────────────────────────────────────────────────────

class RiskState:
    """Tracks per-session capital-protection counters."""
    def __init__(self, start_equity: float):
        self.start_equity = start_equity
        self.day = date.today()
        self.day_start_equity = start_equity
        self.consecutive_losses = 0
        self.last_traded_bar = None       # datetime of the candle we last traded
        self.halted = False               # hard kill-switch tripped

    def roll_day(self, equity: float):
        today = date.today()
        if today != self.day:
            self.day = today
            self.day_start_equity = equity
            self.consecutive_losses = 0
            logger.info("New trading day — daily counters reset.")

    def can_trade(self, equity: float) -> tuple[bool, str]:
        if self.halted:
            return False, "kill-switch active"

        # Total drawdown kill-switch
        dd = (self.start_equity - equity) / self.start_equity * 100
        if dd >= MAX_TOTAL_DRAWDOWN_PCT:
            self.halted = True
            return False, f"max total drawdown {dd:.1f}% >= {MAX_TOTAL_DRAWDOWN_PCT}%"

        # Daily loss limit
        day_dd = (self.day_start_equity - equity) / self.day_start_equity * 100
        if day_dd >= MAX_DAILY_LOSS_PCT:
            return False, f"daily loss {day_dd:.1f}% >= {MAX_DAILY_LOSS_PCT}% (resumes tomorrow)"

        # Losing-streak cool-down
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            return False, f"{self.consecutive_losses} consecutive losses — cooling down"

        return True, ""


# ── Data helpers ──────────────────────────────────────────────────────────────

def fetch_df(symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
    rates = mt5c.get_candles(symbol, timeframe, count)
    if rates is None or len(rates) == 0:
        raise ValueError(f"No data returned for {symbol} {timeframe}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df


# ── Main cycle ────────────────────────────────────────────────────────────────

def run_cycle(symbol: str, timeframe: str, state: RiskState):
    equity = mt5c.get_balance()
    state.roll_day(equity)

    ok, reason = state.can_trade(equity)
    if not ok:
        logger.warning("Trading paused: %s", reason)
        return

    try:
        df = fetch_df(symbol, timeframe)
    except Exception as e:
        logger.error("Data fetch error: %s", e)
        return

    # Drop the live (still-forming) candle — analyse only CLOSED bars.
    closed = df.iloc[:-1]
    if len(closed) < 60:
        logger.warning("Not enough closed candles (%d).", len(closed))
        return

    last_bar_time = closed.index[-1]

    # One trade per candle / setup.
    if ONE_TRADE_PER_BAR and state.last_traded_bar == last_bar_time:
        logger.debug("Already evaluated bar %s — waiting for next candle.", last_bar_time)
        return

    open_trades = mt5c.get_open_trades(symbol)
    if len(open_trades) >= MAX_OPEN_TRADES:
        logger.info("Max open trades (%d) reached.", MAX_OPEN_TRADES)
        return

    sig = strategy.analyse(closed, symbol)
    if sig.direction is None:
        # mark the bar as evaluated so we don't re-run strategy 60x per candle
        state.last_traded_bar = last_bar_time
        logger.info("No signal for %s %s @ %s", symbol, timeframe, last_bar_time)
        return

    logger.info("Signal: %s | Score=%.2f | %s", sig.direction, sig.score, sig.reason)

    # Correlation filter — don't double a macro risk-on/off bet across instruments.
    all_open = mt5c.get_open_trades()
    ok_corr, corr_reason = portfolio.allows_new_trade(symbol, sig.direction, all_open)
    if not ok_corr:
        logger.info("Blocked by %s", corr_reason)
        state.last_traded_bar = last_bar_time
        return

    # Respect broker minimum stop distance, then size from the real price distance.
    sl = rm.enforce_min_stop(symbol, sig.entry, sig.sl, sig.direction)
    sl_distance = abs(sig.entry - sl)
    if sl_distance <= 0:
        logger.warning("Non-positive SL distance — skipping.")
        state.last_traded_bar = last_bar_time
        return

    lot = rm.calculate_lot(symbol, sl_distance)
    if lot <= 0:
        logger.warning("Lot size resolved to 0 — skipping.")
        state.last_traded_bar = last_bar_time
        return

    tp = rm.calculate_tp(sig.entry, sl, sig.direction, rr_ratio=MIN_RR_RATIO)
    actual_rr = abs(tp - sig.entry) / (sl_distance + 1e-10)
    if actual_rr < MIN_RR_RATIO - 1e-6:
        logger.info("R:R %.2f below minimum %.2f — skipping.", actual_rr, MIN_RR_RATIO)
        state.last_traded_bar = last_bar_time
        return

    logger.info("Trade: %s %s | Lot=%.2f | Entry=%.5f | SL=%.5f | TP=%.5f | R:R=%.2f",
                sig.direction, symbol, lot, sig.entry, sl, tp, actual_rr)

    ticket = mt5c.place_order(symbol, sig.direction, lot, sl, tp, comment=f"SMC|{sig.score:.2f}")
    if ticket:
        state.last_traded_bar = last_bar_time
        journal.log_trade(symbol, sig.direction, lot, sig.entry, sl, tp,
                          actual_rr, sig.score, ticket, comment=f"SMC|{sig.score:.2f}")
        logger.info("Order placed – ticket=%s", ticket)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    logger.info("=" * 60)
    logger.info("SMC + Wyckoff Bot | %s | %s | Symbols: %s | R:R>=%.1f",
                mode, TIMEFRAME, ", ".join(SYMBOLS), MIN_RR_RATIO)
    logger.info("=" * 60)

    if not mt5c.connect():
        logger.error("Cannot connect to MT5. Exiting.")
        sys.exit(1)

    state = RiskState(start_equity=mt5c.get_balance())
    logger.info("Start equity: %.2f", state.start_equity)

    try:
        while _running:
            for sym in SYMBOLS:
                if not _running:
                    break
                run_cycle(sym, TIMEFRAME, state)
                time.sleep(2)   # brief pause between symbols to avoid rate limits

            for _ in range(LOOP_INTERVAL_SEC):
                if not _running:
                    break
                time.sleep(1)
    finally:
        mt5c.disconnect()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
