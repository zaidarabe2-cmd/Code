"""
Trading Bot – main loop.

Run:
    python bot.py

Set DRY_RUN=false in .env (or config.py) to enable live trading.
"""
import time
import logging
import signal
import sys
import numpy as np
import pandas as pd

from config import (
    SYMBOL, TIMEFRAME, LOOP_INTERVAL_SEC, MAX_OPEN_TRADES, MIN_RR_RATIO, DRY_RUN
)
import mt5_connector as mt5c
import strategy
import risk_manager as rm

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

def run_cycle(symbol: str, timeframe: str):
    # 1. Fetch data
    try:
        df = fetch_df(symbol, timeframe)
    except Exception as e:
        logger.error("Data fetch error: %s", e)
        return

    # 2. Check open positions
    open_trades = mt5c.get_open_trades(symbol)
    if len(open_trades) >= MAX_OPEN_TRADES:
        logger.info("Max open trades (%d) reached, skipping analysis.", MAX_OPEN_TRADES)
        return

    # 3. Run strategy
    sig = strategy.analyse(df, symbol)

    if sig.direction is None:
        logger.info("No signal for %s %s", symbol, timeframe)
        return

    logger.info("Signal: %s | Score=%.2f | Reason: %s", sig.direction, sig.score, sig.reason)

    # 4. Calculate lot size and TP
    sl_distance = abs(sig.entry - sig.sl)
    symbol_info = mt5c.get_symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.0001
    sl_pips = sl_distance / (point * 10) if point else 10

    lot = rm.calculate_lot(symbol, sl_pips)
    sl, tp = rm.calculate_sl_tp(sig.entry, sig.direction, sig.sl, rr_ratio=MIN_RR_RATIO)
    actual_rr = abs(tp - sig.entry) / (abs(sig.entry - sl) + 1e-10)

    if actual_rr < MIN_RR_RATIO:
        logger.info("R:R %.2f below minimum %.2f – skipping trade.", actual_rr, MIN_RR_RATIO)
        return

    logger.info("Trade: %s %s | Lot=%.4f | Entry=%.5f | SL=%.5f | TP=%.5f | R:R=%.2f",
                sig.direction, symbol, lot, sig.entry, sl, tp, actual_rr)

    # 5. Place order
    ticket = mt5c.place_order(
        symbol=symbol,
        order_type=sig.direction,
        lot=lot,
        sl=sl,
        tp=tp,
        comment=f"SMC|{sig.score:.2f}",
    )

    if ticket:
        logger.info("Order placed – ticket=%s", ticket)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    logger.info("=" * 60)
    logger.info("SMC + Wyckoff Trading Bot | %s | %s %s", mode, SYMBOL, TIMEFRAME)
    logger.info("=" * 60)

    if not mt5c.connect():
        logger.error("Cannot connect to MT5. Exiting.")
        sys.exit(1)

    try:
        while _running:
            logger.info("─── Cycle start: %s %s ───", SYMBOL, TIMEFRAME)
            run_cycle(SYMBOL, TIMEFRAME)
            logger.info("Next cycle in %ds…", LOOP_INTERVAL_SEC)
            # Sleep in small increments to remain responsive to SIGINT
            for _ in range(LOOP_INTERVAL_SEC):
                if not _running:
                    break
                time.sleep(1)
    finally:
        mt5c.disconnect()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
