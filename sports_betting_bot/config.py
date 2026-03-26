"""
Configuration for Sports Betting Stats Bot.
Copy .env.example to .env and fill in your API keys.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
# TheSportsDB (free tier – no key required for most endpoints)
SPORTSDB_API_KEY = os.getenv("SPORTSDB_API_KEY", "3")          # "3" = free key
SPORTSDB_BASE    = "https://www.thesportsdb.com/api/v1/json"

# The-Odds-API  https://the-odds-api.com  (500 free req/month)
ODDS_API_KEY  = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# NewsAPI  https://newsapi.org  (100 free req/day)
NEWS_API_KEY  = os.getenv("NEWS_API_KEY", "")
NEWS_API_BASE = "https://newsapi.org/v2"

# ── Supported sports ──────────────────────────────────────────────────────────
SPORTS = {
    "soccer":      {"db_id": "Soccer",     "odds_key": "soccer_spain_la_liga"},
    "basketball":  {"db_id": "Basketball", "odds_key": "basketball_nba"},
    "american_football": {"db_id": "American Football", "odds_key": "americanfootball_nfl"},
    "tennis":      {"db_id": "Tennis",     "odds_key": "tennis_atp_french_open"},
    "baseball":    {"db_id": "Baseball",   "odds_key": "baseball_mlb"},
}

# ── Analysis settings ─────────────────────────────────────────────────────────
MIN_MATCHES_FOR_ANALYSIS = 5   # minimum past matches to make a prediction
CONFIDENCE_THRESHOLD     = 55  # % – only show bets above this confidence
KELLY_FRACTION           = 0.25  # fractional Kelly (conservative)
MAX_BET_PCT              = 10    # max % of bankroll per bet

# ── Output ────────────────────────────────────────────────────────────────────
DATE_FMT = "%Y-%m-%d"
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)
