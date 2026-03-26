"""
Fetches team info, past results and league standings from TheSportsDB.
Free API key "3" is enough for all public endpoints used here.
"""
import json
import time
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import SPORTSDB_BASE, SPORTSDB_API_KEY, CACHE_DIR, DATE_FMT

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "SportsBettingBot/1.0"})
CACHE_TTL = 3600  # seconds


# ── cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(key: str) -> str:
    h = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.json")


def _cached_get(url: str, params: dict = None) -> Optional[dict]:
    cache_key = url + str(sorted((params or {}).items()))
    path = _cache_path(cache_key)
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < CACHE_TTL:
            with open(path) as f:
                return json.load(f)
    try:
        r = SESSION.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        with open(path, "w") as f:
            json.dump(data, f)
        return data
    except requests.RequestException as e:
        print(f"  [!] HTTP error: {e}")
        return None


# ── public functions ──────────────────────────────────────────────────────────

def search_team(team_name: str) -> Optional[dict]:
    """Return first matching team dict from TheSportsDB."""
    data = _cached_get(
        f"{SPORTSDB_BASE}/{SPORTSDB_API_KEY}/searchteams.php",
        {"t": team_name},
    )
    teams = (data or {}).get("teams")
    return teams[0] if teams else None


def get_team_last_matches(team_id: str, n: int = 10) -> list[dict]:
    """Return last n finished events for a team."""
    data = _cached_get(
        f"{SPORTSDB_BASE}/{SPORTSDB_API_KEY}/eventslast.php",
        {"id": team_id},
    )
    events = (data or {}).get("results") or []
    return events[:n]


def get_team_next_matches(team_id: str, n: int = 5) -> list[dict]:
    """Return next n scheduled events for a team."""
    data = _cached_get(
        f"{SPORTSDB_BASE}/{SPORTSDB_API_KEY}/eventsnext.php",
        {"id": team_id},
    )
    events = (data or {}).get("events") or []
    return events[:n]


def get_league_table(league_id: str, season: str = "") -> list[dict]:
    """Return standings for a league/season."""
    params = {"l": league_id}
    if season:
        params["s"] = season
    data = _cached_get(
        f"{SPORTSDB_BASE}/{SPORTSDB_API_KEY}/lookuptable.php",
        params,
    )
    return (data or {}).get("table") or []


def search_league(league_name: str) -> Optional[dict]:
    """Return first matching league."""
    data = _cached_get(
        f"{SPORTSDB_BASE}/{SPORTSDB_API_KEY}/search_all_leagues.php",
        {"l": league_name},
    )
    leagues = (data or {}).get("countrys")
    return leagues[0] if leagues else None


def get_team_players(team_id: str) -> list[dict]:
    """Return player roster for a team."""
    data = _cached_get(
        f"{SPORTSDB_BASE}/{SPORTSDB_API_KEY}/lookup_all_players.php",
        {"id": team_id},
    )
    return (data or {}).get("player") or []


def get_h2h(team1_id: str, team2_id: str) -> list[dict]:
    """Return head-to-head history between two teams (v2 endpoint)."""
    # v2 requires premium; fall back to filtering last results
    last1 = get_team_last_matches(team1_id, 15)
    last2 = get_team_last_matches(team2_id, 15)
    ids2 = {e.get("idHomeTeam") for e in last2} | {e.get("idAwayTeam") for e in last2}
    h2h = [
        e for e in last1
        if e.get("idHomeTeam") in ids2 or e.get("idAwayTeam") in ids2
    ]
    return h2h


def parse_score(event: dict) -> tuple[Optional[int], Optional[int]]:
    """Parse home/away score from an event dict, returns (home, away)."""
    try:
        home = int(event.get("intHomeScore") or "x")
        away = int(event.get("intAwayScore") or "x")
        return home, away
    except (ValueError, TypeError):
        return None, None
