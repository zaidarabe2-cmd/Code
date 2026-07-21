"""
Trading Bot Configuration
=========================
Instruments: XAUUSD (Gold) + NAS100 (Nasdaq 100) — selected for SMC+Wyckoff.
Timeframe  : M30 — optimal frequency/noise balance for institutional flow.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── MT5 Connection ────────────────────────────────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")
MT5_PATH     = os.getenv("MT5_PATH", "")

# ── Instruments ───────────────────────────────────────────────────────────────
# XAUUSD: highest-consensus SMC instrument. Liquidity sweeps and OBs are the
#   cleanest of any market; ICT built much of the SMC framework around it.
# NAS100: strong trending structure, clear CHoCH, uncorrelated to gold
#   (risk-on vs risk-off) → natural portfolio diversification.
SYMBOLS   = os.getenv("SYMBOLS", "XAUUSD,NAS100").split(",")
SYMBOL    = SYMBOLS[0]        # primary symbol (used by single-symbol commands)
TIMEFRAME = os.getenv("TIMEFRAME", "M30")
MAGIC     = 20240001

# ── Risk Management ───────────────────────────────────────────────────────────
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PCT", "0.5"))   # % of balance per trade
MAX_OPEN_TRADES    = int(os.getenv("MAX_TRADES", "2"))      # total across all symbols
MIN_RR_RATIO       = float(os.getenv("MIN_RR", "3.0"))      # minimum risk:reward
SLIPPAGE           = 30                                      # M30 wider spread buffer

# ── Capital-protection rules ──────────────────────────────────────────────────
MAX_DAILY_LOSS_PCT     = float(os.getenv("MAX_DAILY_LOSS_PCT", "3.0"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSEC_LOSSES", "4"))
MAX_TOTAL_DRAWDOWN_PCT = float(os.getenv("MAX_DD_PCT", "15.0"))
ONE_TRADE_PER_BAR      = True

# ── Session filter ────────────────────────────────────────────────────────────
# XAUUSD and NAS100 have peak institutional volume in London+NY overlap (13-17 UTC).
# Outside these hours liquidity sweeps are less reliable → skip.
# Set to empty list [] to disable the filter.
ALLOWED_SESSIONS_UTC = [(7, 17)]   # (open_hour, close_hour) tuples, UTC
                                   # covers London open → NY close

# ── Stop-loss sizing ──────────────────────────────────────────────────────────
# M30 is noisier than H1 → floor the SL at 1.5× ATR so stops have room.
# Gold ATR on M30 ≈ $3–6; NAS100 ATR on M30 ≈ 40–80 pts.
ATR_PERIOD    = 14
SL_ATR_MULT   = float(os.getenv("SL_ATR_MULT",  "1.5"))
SL_ATR_BUFFER = float(os.getenv("SL_ATR_BUFFER", "0.3"))

# ── Signal threshold ──────────────────────────────────────────────────────────
MIN_CONFLUENCE_SCORE = float(os.getenv("MIN_SCORE", "0.60"))

# ── Kronos AI forecast (optional confluence layer) ────────────────────────────
# Kronos (Tsinghua, AAAI 2026) is a foundation model that forecasts future
# K-lines (OHLCV). Used here as ONE additional confluence factor, NOT as a
# standalone signal. Requires `torch` + downloaded weights on the LIVE machine.
# Disabled by default until you validate it on real data — the bot runs fine
# without it (graceful fallback returns a neutral signal).
KRONOS_ENABLED   = os.getenv("KRONOS_ENABLED", "false").lower() == "true"
KRONOS_MODEL     = os.getenv("KRONOS_MODEL", "NeoQuasar/Kronos-small")
KRONOS_TOKENIZER = os.getenv("KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-base")
KRONOS_DEVICE    = os.getenv("KRONOS_DEVICE", "cpu")   # "cuda:0" if you have a GPU
KRONOS_LOOKBACK  = int(os.getenv("KRONOS_LOOKBACK", "400"))   # candles fed to the model (<= max_context 512)
KRONOS_PRED_LEN  = int(os.getenv("KRONOS_PRED_LEN", "12"))    # candles to forecast ahead (12 × M30 = 6h)
KRONOS_SAMPLES   = int(os.getenv("KRONOS_SAMPLES", "20"))     # Monte-Carlo forecast paths (dispersion = confidence)
KRONOS_WEIGHT    = float(os.getenv("KRONOS_WEIGHT", "0.20"))  # max contribution to the confluence score
KRONOS_MIN_MOVE  = float(os.getenv("KRONOS_MIN_MOVE", "0.001"))  # min forecast move (0.1%) to count as directional

# ── SMC Settings (tuned for M30) ─────────────────────────────────────────────
# M30 gives ~48 candles/day → use wider lookbacks to get the same
# structural coverage as H1 did with smaller lookbacks.
SWING_WINDOW       = 3      # smaller window = faster swing confirmation on M30
OB_LOOKBACK        = 100    # covers ~2 days of M30 candles
FVG_MIN_GAP_PCT    = 0.0003 # 0.03% → ~$0.70 on gold, ~5.7 pts on NAS100
LIQUIDITY_LOOKBACK = 60     # ~1.25 days of M30
BOS_LOOKBACK       = 40

# ── Wyckoff Settings ──────────────────────────────────────────────────────────
WYCKOFF_LOOKBACK = 200    # ~4 days of M30 — enough to see full W phases
VOLUME_MA_PERIOD = 30

# ── Loop ─────────────────────────────────────────────────────────────────────
# Check every 30 min, synced to bar close. The bot waits for closed candles so
# polling faster than the bar interval wastes CPU without producing new signals.
LOOP_INTERVAL_SEC = 1800   # 30 minutes
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# ── Timeframe map (MT5 constants) ─────────────────────────────────────────────
TIMEFRAME_MAP = {
    "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5,
    "M6": 6, "M10": 10, "M12": 12, "M15": 15, "M20": 20,
    "M30": 30, "H1": 16385, "H2": 16386, "H3": 16387,
    "H4": 16388, "H6": 16390, "H8": 16392, "H12": 16396,
    "D1": 16408, "W1": 32769, "MN1": 49153,
}

# ── Instrument-specific characteristics (used by backtester & data generator) ─
INSTRUMENT_PROFILES = {
    "XAUUSD": {
        "start_price": 2300.0,
        "base_vol_m30": 0.0025,   # ~$5.75 per M30 candle, realistic for gold
        # Realistic round-trip trading cost (typical retail/ECN broker):
        "spread_price":     0.25,   # ~25 cents spread on gold
        "commission_price": 0.07,   # ~$7/lot round turn ≈ $0.07/oz in price terms
        "slippage_price":   0.10,   # avg slippage on market orders
        "description": "Gold — cleanest SMC instrument, highest institutional flow",
    },
    "NAS100": {
        "start_price": 19000.0,
        "base_vol_m30": 0.0035,   # ~$66 per M30 candle, realistic for Nasdaq
        "spread_price":     1.5,    # ~1.5 index points spread
        "commission_price": 0.0,    # usually spread-only on indices CFD
        "slippage_price":   1.0,
        "description": "Nasdaq 100 — strong trends, clear CHoCH, risk-on asset",
    },
    "EURUSD": {
        "start_price": 1.10,
        "base_vol_m30": 0.0004,
        "spread_price":     0.00008,  # ~0.8 pip
        "commission_price": 0.00004,
        "slippage_price":   0.00003,
        "description": "Euro/Dollar — highest liquidity forex pair",
    },
}
