"""
Fetches recent sports news via NewsAPI and plain web scraping fallback.
Free NewsAPI tier: 100 requests/day.
"""
import re
import requests
from datetime import datetime, timedelta
from typing import Optional
from config import NEWS_API_KEY, NEWS_API_BASE, DATE_FMT

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "SportsBettingBot/1.0"})


def _newsapi_search(query: str, days_back: int = 3) -> list[dict]:
    if not NEWS_API_KEY:
        return []
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime(DATE_FMT)
    try:
        r = SESSION.get(
            f"{NEWS_API_BASE}/everything",
            params={
                "q": query,
                "from": from_date,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": 10,
                "apiKey": NEWS_API_KEY,
            },
            timeout=10,
        )
        r.raise_for_status()
        articles = r.json().get("articles", [])
        return [
            {
                "title":       a["title"],
                "source":      a["source"]["name"],
                "url":         a["url"],
                "published_at": a["publishedAt"][:10],
                "description": (a.get("description") or "")[:200],
            }
            for a in articles
            if a.get("title") and "[Removed]" not in a.get("title", "")
        ]
    except requests.RequestException as e:
        print(f"  [!] NewsAPI error: {e}")
        return []


def _extract_sentiment(text: str) -> str:
    """Very lightweight keyword sentiment for injury/form signals."""
    text = text.lower()
    negative = ["injur", "suspend", "absent", "doubt", "miss", "crisis",
                 "ban", "red card", "fracture", "ruled out"]
    positive = ["return", "fit", "form", "win streak", "unbeaten", "boost",
                 "confident", "record", "dominant"]
    neg = sum(1 for kw in negative if kw in text)
    pos = sum(1 for kw in positive if kw in text)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def get_team_news(team_name: str, days_back: int = 5) -> list[dict]:
    """Return recent news articles for a team with sentiment tag."""
    articles = _newsapi_search(f"{team_name} football OR soccer OR NBA OR NFL", days_back)
    for a in articles:
        combined = f"{a['title']} {a['description']}"
        a["sentiment"] = _extract_sentiment(combined)
    return articles


def get_match_news(home: str, away: str, days_back: int = 3) -> list[dict]:
    """Return news specifically about an upcoming match."""
    query = f'"{home}" AND "{away}"'
    articles = _newsapi_search(query, days_back)
    for a in articles:
        combined = f"{a['title']} {a['description']}"
        a["sentiment"] = _extract_sentiment(combined)
    return articles


def summarise_news_signals(articles: list[dict]) -> dict:
    """
    Aggregate news into simple signal counts for the analysis engine.
    Returns: {positive: int, negative: int, neutral: int, injury_alerts: list}
    """
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    injuries = []
    for a in articles:
        s = a.get("sentiment", "neutral")
        counts[s] = counts.get(s, 0) + 1
        text = f"{a['title']} {a.get('description', '')}".lower()
        if any(kw in text for kw in ["injur", "ruled out", "absent", "suspend"]):
            injuries.append(a["title"])
    return {**counts, "injury_alerts": injuries[:5]}
