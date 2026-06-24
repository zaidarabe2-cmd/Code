"""
Trading Bot Configuration
=========================
Edit this file to set your MT5 credentials, symbol, timeframe, and risk params.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── MT5 Connection ────────────────────────────────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")
MT5_PATH     = os.getenv("MT5_PATH", "")  # Path to terminal64.exe (optional)

# ── Trading Parameters ────────────────────────────────────────────────────────
SYMBOL     = os.getenv("SYMBOL", "EURUSD")
TIMEFRAME  = os.getenv("TIMEFRAME", "H1")   # M5, M15, M30, H1, H4, D1
MAGIC      = 20240001                        # Unique magic number for this bot

# ── Risk Management ───────────────────────────────────────────────────────────
RISK_PER_TRADE_PCT  = float(os.getenv("RISK_PCT", "0.5"))  # % of balance per trade
MAX_OPEN_TRADES     = int(os.getenv("MAX_TRADES", "2"))
MIN_RR_RATIO        = float(os.getenv("MIN_RR", "3.0"))     # minimum risk:reward (user wants >= 1:3)
SLIPPAGE            = 20                                     # max slippage in points

# ── Capital-protection rules (the "stay alive" layer) ─────────────────────────
# These are checked by the bot before every trade; they are what turns a
# positive-expectancy strategy into a *survivable* one on the $1000 demo.
MAX_DAILY_LOSS_PCT      = float(os.getenv("MAX_DAILY_LOSS_PCT", "3.0"))   # stop trading for the day
MAX_CONSECUTIVE_LOSSES  = int(os.getenv("MAX_CONSEC_LOSSES", "4"))        # cool-down after a losing streak
MAX_TOTAL_DRAWDOWN_PCT  = float(os.getenv("MAX_DD_PCT", "15.0"))         # hard kill-switch vs start equity
ONE_TRADE_PER_BAR       = True   # never open >1 trade on the same candle / setup

# ── Stop-loss floor ──────────────────────────────────────────────────────────
# A structure-based SL can be microscopically tight (a tiny OB), which then
# blows up lot size and gets stopped by spread/noise. We floor the SL distance
# at ATR * SL_ATR_MULT so every stop has room to breathe.
ATR_PERIOD     = 14
SL_ATR_MULT    = float(os.getenv("SL_ATR_MULT", "1.0"))   # min SL distance = 1.0 * ATR
SL_ATR_BUFFER  = float(os.getenv("SL_ATR_BUFFER", "0.2")) # extra ATR padding beyond the structure level

# ── Signal threshold ──────────────────────────────────────────────────────────
MIN_CONFLUENCE_SCORE = float(os.getenv("MIN_SCORE", "0.60"))  # min confluence to take a trade

# ── SMC Settings ──────────────────────────────────────────────────────────────
OB_LOOKBACK       = 50      # candles to look back for Order Blocks
FVG_MIN_GAP_PCT   = 0.0005  # minimum FVG gap as fraction of price (5 pips on EURUSD)
LIQUIDITY_LOOKBACK = 30     # candles to detect liquidity pools
BOS_LOOKBACK       = 20     # candles to detect Break of Structure swing points

# ── Wyckoff Settings ──────────────────────────────────────────────────────────
WYCKOFF_LOOKBACK  = 100   # candles for Wyckoff phase analysis
VOLUME_MA_PERIOD  = 20    # period for volume moving average

# ── Loop Settings ────────────────────────────────────────────────────────────
LOOP_INTERVAL_SEC = 60    # seconds between each analysis cycle
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"  # True = no real orders

# ── Timeframe map ─────────────────────────────────────────────────────────────
TIMEFRAME_MAP = {
    "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5,
    "M6": 6, "M10": 10, "M12": 12, "M15": 15, "M20": 20,
    "M30": 30, "H1": 16385, "H2": 16386, "H3": 16387,
    "H4": 16388, "H6": 16390, "H8": 16392, "H12": 16396,
    "D1": 16408, "W1": 32769, "MN1": 49153,
}
