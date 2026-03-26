"""
Fetches live odds from The-Odds-API.
Free tier: 500 requests/month.  Quota displayed after each call.
If no API key is set the module returns empty lists gracefully.
"""
import requests
from typing import Optional
from config import ODDS_API_KEY, ODDS_API_BASE

SESSION = requests.Session()


def _get(endpoint: str, params: dict = None) -> Optional[dict | list]:
    if not ODDS_API_KEY:
        return None
    try:
        r = SESSION.get(
            f"{ODDS_API_BASE}{endpoint}",
            params={"apiKey": ODDS_API_KEY, **(params or {})},
            timeout=10,
        )
        remaining = r.headers.get("x-requests-remaining", "?")
        used      = r.headers.get("x-requests-used", "?")
        print(f"  [odds-api] used={used} remaining={remaining}")
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"  [!] Odds API error: {e}")
        return None


def get_sports() -> list[dict]:
    """List all available sport keys."""
    data = _get("/sports")
    return data if isinstance(data, list) else []


def get_odds(sport_key: str, regions: str = "eu", markets: str = "h2h") -> list[dict]:
    """
    Return odds for upcoming events in a sport.
    regions: us | uk | eu | au
    markets: h2h | spreads | totals
    """
    data = _get(
        f"/sports/{sport_key}/odds",
        {"regions": regions, "markets": markets, "oddsFormat": "decimal"},
    )
    return data if isinstance(data, list) else []


def best_odds_for_teams(
    home_team: str, away_team: str, sport_key: str
) -> Optional[dict]:
    """
    Find the event matching home/away team and return best decimal odds
    across all bookmakers.
    Returns dict with keys: home_best, draw_best, away_best, bookmakers
    """
    events = get_odds(sport_key)
    for event in events:
        ht = event.get("home_team", "").lower()
        at = event.get("away_team", "").lower()
        if home_team.lower() in ht or away_team.lower() in at:
            home_best = draw_best = away_best = 0.0
            books_used = []
            for bm in event.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    if mkt.get("key") != "h2h":
                        continue
                    for outcome in mkt.get("outcomes", []):
                        name  = outcome["name"].lower()
                        price = float(outcome["price"])
                        if home_team.lower() in name:
                            home_best = max(home_best, price)
                        elif away_team.lower() in name:
                            away_best = max(away_best, price)
                        elif "draw" in name:
                            draw_best = max(draw_best, price)
                books_used.append(bm["title"])
            return {
                "home_best": home_best or None,
                "draw_best": draw_best or None,
                "away_best": away_best or None,
                "bookmakers": list(set(books_used)),
                "commence_time": event.get("commence_time"),
            }
    return None


def implied_probability(decimal_odd: float) -> float:
    """Convert decimal odds to implied probability (0-100)."""
    if not decimal_odd or decimal_odd <= 1:
        return 0.0
    return round(100 / decimal_odd, 2)
