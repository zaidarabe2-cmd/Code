"""
Prediction engine.

Combines:
  - Poisson expected-goals model
  - ELO rating
  - Recent form / momentum
  - Head-to-head history
  - News sentiment signals
  - Market odds (when available)

Outputs a MatchPrediction dataclass with confidence scores and
betting recommendations including Kelly Criterion stake sizing.
"""
from dataclasses import dataclass, field
from typing import Optional

from analysis.stats import (
    compute_form,
    attack_defence_strength,
    poisson_match_probs,
    EloRating,
    momentum_score,
)
from fetchers.sports_data import (
    get_team_last_matches,
    get_h2h,
    parse_score,
)
from fetchers.news import get_match_news, summarise_news_signals
from fetchers.odds import best_odds_for_teams, implied_probability
from config import MIN_MATCHES_FOR_ANALYSIS, KELLY_FRACTION, MAX_BET_PCT


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class TeamStats:
    name: str
    team_id: str
    form: dict = field(default_factory=dict)
    momentum: float = 0.0
    elo: float = 1500.0
    attack_str: float = 1.0
    defence_str: float = 1.0
    news_signals: dict = field(default_factory=dict)


@dataclass
class MatchPrediction:
    home: TeamStats
    away: TeamStats

    # Poisson model
    poisson_home_win: float = 0.0
    poisson_draw: float = 0.0
    poisson_away_win: float = 0.0
    top_scores: list = field(default_factory=list)
    exp_goals_home: float = 0.0
    exp_goals_away: float = 0.0

    # ELO
    elo_home_prob: float = 0.0
    elo_away_prob: float = 0.0

    # Blended final probabilities
    home_win_prob: float = 0.0
    draw_prob: float = 0.0
    away_win_prob: float = 0.0

    # H2H
    h2h_home_wins: int = 0
    h2h_draws: int = 0
    h2h_away_wins: int = 0

    # Market odds
    home_best_odd: Optional[float] = None
    draw_best_odd: Optional[float] = None
    away_best_odd: Optional[float] = None
    market_home_implied: float = 0.0
    market_draw_implied: float = 0.0
    market_away_implied: float = 0.0

    # Recommendations
    recommended_bet: str = "NO BET"
    confidence: float = 0.0        # 0–100
    value_edge: float = 0.0        # model_prob - implied_prob
    kelly_stake_pct: float = 0.0   # % of bankroll

    notes: list[str] = field(default_factory=list)


# ── Core prediction function ──────────────────────────────────────────────────

def predict_match(
    home_name: str,
    home_id: str,
    away_name: str,
    away_id: str,
    sport_key: str = "",
    league_events: list[dict] = None,
) -> MatchPrediction:
    """
    Full prediction pipeline for a single match.
    """
    league_events = league_events or []

    # -- 1. Fetch past results ------------------------------------------------
    home_events = get_team_last_matches(home_id, 15)
    away_events = get_team_last_matches(away_id, 15)
    h2h_events  = get_h2h(home_id, away_id)

    # -- 2. Form & momentum --------------------------------------------------
    home_form = compute_form(home_events, home_id, last_n=6)
    away_form = compute_form(away_events, away_id, last_n=6)
    home_mom  = momentum_score(home_form)
    away_mom  = momentum_score(away_form)

    # -- 3. Attack / defence strength ----------------------------------------
    all_evs = list({e["idEvent"]: e for e in home_events + away_events + league_events}.values())
    home_str = attack_defence_strength(home_events, home_id, all_evs)
    away_str = attack_defence_strength(away_events, away_id, all_evs)

    # -- 4. Expected goals (Dixon-Coles simplified) ---------------------------
    # league averages
    lg_home_avg = 1.45   # typical soccer defaults; refined if data available
    lg_away_avg = 1.15
    if len(all_evs) >= MIN_MATCHES_FOR_ANALYSIS:
        total_h = total_a = cnt = 0
        for ev in all_evs:
            hs, as_ = parse_score(ev)
            if hs is None: continue
            total_h += hs; total_a += as_; cnt += 1
        if cnt:
            lg_home_avg = total_h / cnt
            lg_away_avg = total_a / cnt

    # Home team attacking at home vs away team defending away
    exp_home = (home_str["att_home"] * away_str["def_away"] * lg_home_avg)
    # Away team attacking away vs home team defending at home
    exp_away = (away_str["att_away"] * home_str["def_home"] * lg_away_avg)

    # Home advantage tweak (+8%)
    exp_home *= 1.08

    poisson = poisson_match_probs(max(exp_home, 0.1), max(exp_away, 0.1))

    # -- 5. ELO ---------------------------------------------------------------
    elo = EloRating()
    elo.build_from_events(all_evs)
    elo_probs = elo.win_probability(home_id, away_id)

    # -- 6. H2H summary -------------------------------------------------------
    h2h_hw = h2h_d = h2h_aw = 0
    for ev in h2h_events:
        hs, as_ = parse_score(ev)
        if hs is None: continue
        is_home = ev.get("idHomeTeam") == home_id
        gf = hs if is_home else as_
        ga = as_ if is_home else hs
        if gf > ga:   h2h_hw += 1
        elif gf == ga: h2h_d += 1
        else:          h2h_aw += 1

    # -- 7. News signals -------------------------------------------------------
    news = get_match_news(home_name, away_name, days_back=4)
    news_sig = summarise_news_signals(news)

    # -- 8. Blend probabilities -----------------------------------------------
    # Weights: Poisson 45%, ELO 30%, form momentum 20%, H2H 5%
    total_h2h = h2h_hw + h2h_d + h2h_aw or 1
    h2h_home_pct  = h2h_hw / total_h2h * 100
    h2h_draw_pct  = h2h_d  / total_h2h * 100
    h2h_away_pct  = h2h_aw / total_h2h * 100

    # Momentum shift (+-5% range)
    mom_diff = (home_mom - away_mom) / 100  # -1..+1
    mom_home_adj = mom_diff * 5
    mom_away_adj = -mom_diff * 5
    elo_draw_pct = max(100 - elo_probs["home_prob"] - elo_probs["away_prob"], 5)

    home_blended = (
        poisson["home_win"] * 0.45
        + elo_probs["home_prob"] * 0.30
        + (50 + mom_home_adj) * 0.20
        + h2h_home_pct * 0.05
    )
    draw_blended = (
        poisson["draw"] * 0.45
        + elo_draw_pct * 0.30
        + 25 * 0.20
        + h2h_draw_pct * 0.05
    )
    away_blended = (
        poisson["away_win"] * 0.45
        + elo_probs["away_prob"] * 0.30
        + (50 + mom_away_adj) * 0.20
        + h2h_away_pct * 0.05
    )

    # News sentiment adjustment (±3%)
    home_sentiment = news_sig.get("positive", 0) - news_sig.get("negative", 0)
    home_blended += home_sentiment * 1.5
    away_blended -= home_sentiment * 0.5

    # Normalise
    total = home_blended + draw_blended + away_blended
    if total > 0:
        home_blended  = round(home_blended / total * 100, 2)
        draw_blended  = round(draw_blended / total * 100, 2)
        away_blended  = round(away_blended / total * 100, 2)

    # -- 9. Market odds -------------------------------------------------------
    mkt = best_odds_for_teams(home_name, away_name, sport_key) if sport_key else None
    home_odd = (mkt or {}).get("home_best")
    draw_odd = (mkt or {}).get("draw_best")
    away_odd = (mkt or {}).get("away_best")

    mkt_home_impl = implied_probability(home_odd) if home_odd else 0
    mkt_draw_impl = implied_probability(draw_odd) if draw_odd else 0
    mkt_away_impl = implied_probability(away_odd) if away_odd else 0

    # -- 10. Value edge & Kelly -----------------------------------------------
    edges = {
        "HOME WIN":  (home_blended - mkt_home_impl, home_odd),
        "DRAW":      (draw_blended  - mkt_draw_impl,  draw_odd),
        "AWAY WIN":  (away_blended  - mkt_away_impl,  away_odd),
    }
    best_bet = max(edges, key=lambda k: edges[k][0])
    best_edge, best_odd_val = edges[best_bet]

    # Kelly: f = (bp - q) / b   where b = decimal-1
    kelly = 0.0
    if best_odd_val and best_odd_val > 1 and best_edge > 0:
        b = best_odd_val - 1
        p = {
            "HOME WIN": home_blended / 100,
            "DRAW":     draw_blended / 100,
            "AWAY WIN": away_blended / 100,
        }[best_bet]
        q = 1 - p
        kelly = max((b * p - q) / b, 0) * KELLY_FRACTION * 100
        kelly = round(min(kelly, MAX_BET_PCT), 2)

    # Confidence: how far model agrees with itself + edge magnitude
    max_prob   = max(home_blended, draw_blended, away_blended)
    confidence = round(min(max_prob * 0.7 + abs(best_edge) * 0.3, 100), 1)

    # -- 11. Notes ------------------------------------------------------------
    notes = []
    if news_sig.get("injury_alerts"):
        notes.append(f"Injury alerts: {'; '.join(news_sig['injury_alerts'][:2])}")
    if h2h_hw + h2h_d + h2h_aw >= 3:
        notes.append(f"H2H last {h2h_hw+h2h_d+h2h_aw}: {home_name} {h2h_hw}W-{h2h_d}D-{h2h_aw}L")
    if abs(home_mom - away_mom) > 20:
        leader = home_name if home_mom > away_mom else away_name
        notes.append(f"{leader} has significantly better recent momentum")
    if best_edge > 5 and best_odd_val:
        notes.append(f"Value bet detected: model edge +{best_edge:.1f}% over market")

    # -- Assemble result -------------------------------------------------------
    home_stats = TeamStats(
        name=home_name, team_id=home_id,
        form=home_form, momentum=home_mom,
        elo=elo_probs["home_elo"],
        attack_str=home_str["att_home"],
        defence_str=home_str["def_home"],
        news_signals=news_sig,
    )
    away_stats = TeamStats(
        name=away_name, team_id=away_id,
        form=away_form, momentum=away_mom,
        elo=elo_probs["away_elo"],
        attack_str=away_str["att_away"],
        defence_str=away_str["def_away"],
        news_signals=news_sig,
    )

    return MatchPrediction(
        home=home_stats,
        away=away_stats,
        poisson_home_win=poisson["home_win"],
        poisson_draw=poisson["draw"],
        poisson_away_win=poisson["away_win"],
        top_scores=poisson["top_scores"],
        exp_goals_home=poisson["exp_home"],
        exp_goals_away=poisson["exp_away"],
        elo_home_prob=elo_probs["home_prob"],
        elo_away_prob=elo_probs["away_prob"],
        home_win_prob=home_blended,
        draw_prob=draw_blended,
        away_win_prob=away_blended,
        h2h_home_wins=h2h_hw,
        h2h_draws=h2h_d,
        h2h_away_wins=h2h_aw,
        home_best_odd=home_odd,
        draw_best_odd=draw_odd,
        away_best_odd=away_odd,
        market_home_implied=mkt_home_impl,
        market_draw_implied=mkt_draw_impl,
        market_away_implied=mkt_away_impl,
        recommended_bet=best_bet if (best_edge > 0 or not sport_key) else "NO VALUE",
        confidence=confidence,
        value_edge=round(best_edge, 2),
        kelly_stake_pct=kelly,
        notes=notes,
    )
