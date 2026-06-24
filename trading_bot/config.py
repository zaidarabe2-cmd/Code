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
RISK_PER_TRADE_PCT  = float(os.getenv("RISK_PCT", "1.0"))  # % of balance per trade
MAX_OPEN_TRADES     = int(os.getenv("MAX_TRADES", "3"))
MIN_RR_RATIO        = float(os.getenv("MIN_RR", "2.0"))     # minimum risk:reward
SLIPPAGE            = 20                                     # max slippage in points

# ── SMC Settings ──────────────────────────────────────────────────────────────
OB_LOOKBACK       = 50    # candles to look back for Order Blocks
FVG_MIN_GAP_PCT   = 0.01  # minimum FVG gap as % of price
LIQUIDITY_LOOKBACK = 30   # candles to detect liquidity pools
BOS_LOOKBACK       = 20   # candles to detect Break of Structure swing points

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
