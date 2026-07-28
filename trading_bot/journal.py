"""
Trade journal — logs every trade and daily P&L to CSV.

These files are what the daily briefing (and your own review) read. Without a
journal you have no record of what the bot did or how it performed — this was a
real gap versus the Alpaca playbook.
"""
import os
import csv
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TRADES_CSV    = os.getenv("TRADES_CSV", "trades.csv")
DAILY_PNL_CSV = os.getenv("DAILY_PNL_CSV", "daily_pnl.csv")

_TRADE_HEADER = ["timestamp", "symbol", "direction", "lot", "entry",
                 "sl", "tp", "rr", "score", "ticket", "comment"]
_PNL_HEADER   = ["date", "equity", "realized_pnl", "trades", "wins", "losses"]


def _ensure_header(path: str, header: list[str]):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def log_trade(symbol, direction, lot, entry, sl, tp, rr, score, ticket, comment=""):
    """Append one trade entry to trades.csv."""
    try:
        _ensure_header(TRADES_CSV, _TRADE_HEADER)
        with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.utcnow().isoformat(timespec="seconds"),
                symbol, direction, f"{lot:.2f}", f"{entry:.5f}",
                f"{sl:.5f}", f"{tp:.5f}", f"{rr:.2f}", f"{score:.3f}",
                ticket, comment,
            ])
    except Exception as e:
        logger.warning("Could not write trade to journal: %s", e)


def log_daily_pnl(equity, realized_pnl, trades, wins, losses):
    """Append (or you can dedupe by date) a daily P&L summary row."""
    try:
        _ensure_header(DAILY_PNL_CSV, _PNL_HEADER)
        with open(DAILY_PNL_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.utcnow().date().isoformat(),
                f"{equity:.2f}", f"{realized_pnl:.2f}", trades, wins, losses,
            ])
    except Exception as e:
        logger.warning("Could not write daily P&L: %s", e)
