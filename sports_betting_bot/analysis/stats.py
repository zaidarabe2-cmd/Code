"""
Core statistical engine.

Implements:
  - Basic form / W-D-L aggregation
  - Attack / Defence strength (Dixon-Coles style)
  - Poisson goal model for soccer
  - Simple ELO-style rating
  - Trend analysis (last-N performance)
"""
import math
from typing import Optional
from fetchers.sports_data import parse_score


# ── Form aggregation ──────────────────────────────────────────────────────────

def compute_form(events: list[dict], team_id: str, last_n: int = 5) -> dict:
    """
    Compute W/D/L, goals scored/conceded for the last_n matches.
    Returns dict with keys: wins, draws, losses, gf, ga, form_str, points_pct
    """
    results = []
    for ev in events[:last_n]:
        home_id = ev.get("idHomeTeam")
        away_id = ev.get("idAwayTeam")
        hs, as_ = parse_score(ev)
        if hs is None:
            continue
        is_home = (home_id == team_id)
        gf = hs if is_home else as_
        ga = as_ if is_home else hs
        if gf > ga:
            results.append(("W", gf, ga))
        elif gf == ga:
            results.append(("D", gf, ga))
        else:
            results.append(("L", gf, ga))

    wins   = sum(1 for r in results if r[0] == "W")
    draws  = sum(1 for r in results if r[0] == "D")
    losses = sum(1 for r in results if r[0] == "L")
    gf     = sum(r[1] for r in results)
    ga     = sum(r[2] for r in results)
    n      = len(results)
    pts    = wins * 3 + draws
    max_pts = n * 3 if n else 1

    return {
        "wins":        wins,
        "draws":       draws,
        "losses":      losses,
        "gf":          gf,
        "ga":          ga,
        "gd":          gf - ga,
        "form_str":    "".join(r[0] for r in results),
        "points_pct":  round(pts / max_pts * 100, 1) if max_pts else 0,
        "avg_gf":      round(gf / n, 2) if n else 0,
        "avg_ga":      round(ga / n, 2) if n else 0,
        "matches":     n,
    }


# ── Attack / Defence strength ─────────────────────────────────────────────────

def _league_averages(events: list[dict]) -> tuple[float, float]:
    """Compute league average home goals and away goals from events list."""
    home_goals = away_goals = count = 0
    for ev in events:
        hs, as_ = parse_score(ev)
        if hs is None:
            continue
        home_goals += hs
        away_goals += as_
        count += 1
    if count == 0:
        return 1.5, 1.2  # sensible soccer defaults
    return home_goals / count, away_goals / count


def attack_defence_strength(
    team_events: list[dict],
    team_id: str,
    all_league_events: list[dict],
) -> dict:
    """
    Compute attack and defence strength relative to league average.
    att_strength > 1  => better than average attacker
    def_strength < 1  => better than average defender (concedes less)
    """
    lg_home_avg, lg_away_avg = _league_averages(all_league_events)

    home_gf = home_ga = home_n = 0
    away_gf = away_ga = away_n = 0

    for ev in team_events:
        hs, as_ = parse_score(ev)
        if hs is None:
            continue
        if ev.get("idHomeTeam") == team_id:
            home_gf += hs; home_ga += as_; home_n += 1
        else:
            away_gf += as_; away_ga += hs; away_n += 1

    att_h = (home_gf / home_n / lg_home_avg) if home_n else 1.0
    def_h = (home_ga / home_n / lg_away_avg) if home_n else 1.0
    att_a = (away_gf / away_n / lg_away_avg) if away_n else 1.0
    def_a = (away_ga / away_n / lg_home_avg) if away_n else 1.0

    return {
        "att_home": round(att_h, 3),
        "def_home": round(def_h, 3),
        "att_away": round(att_a, 3),
        "def_away": round(def_a, 3),
    }


# ── Poisson model ─────────────────────────────────────────────────────────────

def _poisson_pmf(k: int, lam: float) -> float:
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def poisson_match_probs(
    home_expected: float,
    away_expected: float,
    max_goals: int = 8,
) -> dict:
    """
    Given expected goals for home/away, compute:
      - home_win / draw / away_win probabilities
      - score matrix (most likely scores)
    """
    matrix: dict[tuple, float] = {}
    home_win = draw = away_win = 0.0

    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            p = _poisson_pmf(hg, home_expected) * _poisson_pmf(ag, away_expected)
            matrix[(hg, ag)] = p
            if hg > ag:
                home_win += p
            elif hg == ag:
                draw += p
            else:
                away_win += p

    # normalise (tail cut-off correction)
    total = home_win + draw + away_win
    home_win /= total
    draw     /= total
    away_win /= total

    top_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "home_win": round(home_win * 100, 2),
        "draw":     round(draw * 100, 2),
        "away_win": round(away_win * 100, 2),
        "top_scores": [(f"{h}-{a}", round(p * 100, 2)) for (h, a), p in top_scores],
        "exp_home":   round(home_expected, 2),
        "exp_away":   round(away_expected, 2),
    }


# ── ELO rating ────────────────────────────────────────────────────────────────

class EloRating:
    """
    Simple ELO tracker.  Feed it matches in chronological order.
    K=32 by default (FIFA uses 40 for important matches).
    """
    K = 32
    DEFAULT = 1500

    def __init__(self):
        self.ratings: dict[str, float] = {}

    def _get(self, team_id: str) -> float:
        return self.ratings.get(team_id, self.DEFAULT)

    def _expected(self, ra: float, rb: float) -> float:
        return 1 / (1 + 10 ** ((rb - ra) / 400))

    def update(self, home_id: str, away_id: str, home_score: int, away_score: int):
        ra = self._get(home_id)
        rb = self._get(away_id)
        ea = self._expected(ra, rb)
        if home_score > away_score:
            sa, sb = 1, 0
        elif home_score == away_score:
            sa = sb = 0.5
        else:
            sa, sb = 0, 1
        self.ratings[home_id] = ra + self.K * (sa - ea)
        self.ratings[away_id] = rb + self.K * (sb - (1 - ea))

    def win_probability(self, home_id: str, away_id: str) -> dict:
        ra = self._get(home_id)
        rb = self._get(away_id)
        home_prob = self._expected(ra, rb)
        return {
            "home_elo":  round(ra, 1),
            "away_elo":  round(rb, 1),
            "home_prob": round(home_prob * 100, 2),
            "away_prob": round((1 - home_prob) * 100, 2),
        }

    def build_from_events(self, events: list[dict]):
        """Train ELO on a list of events sorted oldest-first."""
        for ev in sorted(events, key=lambda e: e.get("dateEvent", "")):
            hs, as_ = parse_score(ev)
            if hs is None:
                continue
            self.update(
                ev.get("idHomeTeam"),
                ev.get("idAwayTeam"),
                hs, as_,
            )


# ── Trend helper ──────────────────────────────────────────────────────────────

def momentum_score(form: dict) -> float:
    """
    Simple momentum index 0-100.
    Weights recent form heavier.
    """
    pts_pct  = form.get("points_pct", 50)
    gd       = form.get("gd", 0)
    gd_norm  = max(min(gd * 5, 25), -25)   # cap at ±25
    return round(min(max(pts_pct + gd_norm / 2, 0), 100), 1)
