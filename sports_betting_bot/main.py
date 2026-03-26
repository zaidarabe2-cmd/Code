#!/usr/bin/env python3
"""
Sports Betting Stats Bot
========================
CLI tool that fetches live stats, news and odds then runs a multi-model
analysis (Poisson + ELO + form + H2H + market odds) to suggest bets
with confidence scores and Kelly-criterion stake sizing.

Usage examples
--------------
# Analyse a match between two teams (search by name):
  python main.py match "Real Madrid" "Barcelona"

# Analyse with live odds (requires ODDS_API_KEY in .env):
  python main.py match "Real Madrid" "Barcelona" --sport soccer_spain_la_liga

# Show recent news for a team:
  python main.py news "Manchester City"

# Quick team stats:
  python main.py stats "Liverpool"

# Show today's upcoming matches for a sport:
  python main.py upcoming --sport soccer_spain_la_liga
"""
import sys
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_team(name: str):
    from fetchers.sports_data import search_team
    team = search_team(name)
    if not team:
        console.print(f"[red]Team not found:[/red] '{name}'")
        sys.exit(1)
    return team


def _banner():
    t = Text(justify="center")
    t.append("⚽  SPORTS BETTING STATS BOT  ⚽", style="bold cyan")
    console.print(Panel(t, border_style="cyan"))


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_match(home_name: str, away_name: str, sport_key: str = ""):
    from analysis.predictor import predict_match
    from reports.generator import print_match_report

    _banner()
    console.print(f"\n[bold]Looking up teams…[/bold]")

    home = _find_team(home_name)
    away = _find_team(away_name)

    home_id = home["idTeam"]
    away_id = away["idTeam"]
    home_resolved = home["strTeam"]
    away_resolved = away["strTeam"]

    console.print(f"  Home: [cyan]{home_resolved}[/cyan]  (id={home_id})")
    console.print(f"  Away: [cyan]{away_resolved}[/cyan]  (id={away_id})")
    console.print(f"\n[bold]Running analysis…[/bold]")

    with console.status("[bold green]Fetching data and computing predictions…"):
        pred = predict_match(home_resolved, home_id,
                             away_resolved, away_id,
                             sport_key=sport_key)

    print_match_report(pred)


def cmd_news(team_name: str):
    from fetchers.news import get_team_news
    from reports.generator import print_news

    _banner()
    team = _find_team(team_name)
    resolved = team["strTeam"]
    console.print(f"\n[bold]Fetching news for[/bold] [cyan]{resolved}[/cyan]…\n")

    with console.status("Fetching news…"):
        articles = get_team_news(resolved, days_back=7)

    print_news(articles, title=f"Latest News – {resolved}")


def cmd_stats(team_name: str):
    from fetchers.sports_data import (
        get_team_last_matches, get_team_next_matches, get_team_players
    )
    from analysis.stats import compute_form, momentum_score, EloRating
    from rich.table import Table
    from rich import box

    _banner()
    team = _find_team(team_name)
    team_id   = team["idTeam"]
    resolved  = team["strTeam"]
    console.print(f"\n[bold]Stats for[/bold] [cyan]{resolved}[/cyan]\n")

    with console.status("Fetching match history…"):
        events = get_team_last_matches(team_id, 15)
        next_m = get_team_next_matches(team_id, 3)

    form = compute_form(events, team_id, last_n=10)
    mom  = momentum_score(form)

    elo = EloRating()
    elo.build_from_events(events)
    elo_rating = elo.ratings.get(team_id, 1500)

    # Summary panel
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="dim", width=18)
    summary.add_column(width=20)
    summary.add_row("Team:",       f"[bold cyan]{resolved}[/bold cyan]")
    summary.add_row("Country:",    team.get("strCountry", "-"))
    summary.add_row("League:",     team.get("strLeague", "-"))
    summary.add_row("Stadium:",    team.get("strStadium", "-"))
    summary.add_row("Founded:",    team.get("intFormedYear", "-"))
    summary.add_row("ELO Rating:", f"[bold]{elo_rating:.0f}[/bold]")
    summary.add_row("Momentum:",   f"[bold cyan]{mom}[/bold cyan] / 100")
    console.print(Panel(summary, title="Team Info", border_style="cyan"))

    # Form table
    form_tbl = Table(title="Last 10 Matches – Form", box=box.MINIMAL, header_style="bold")
    form_tbl.add_column("Stat")
    form_tbl.add_column("Value", justify="right")
    from reports.generator import _form_coloured
    form_tbl.add_row("Form (latest→oldest)", _form_coloured(form.get("form_str", "-")))
    form_tbl.add_row("Wins / Draws / Losses",
                     f"[green]{form['wins']}[/green] / "
                     f"[yellow]{form['draws']}[/yellow] / "
                     f"[red]{form['losses']}[/red]")
    form_tbl.add_row("Goals scored",    f"[green]{form['gf']}[/green] ({form['avg_gf']} avg)")
    form_tbl.add_row("Goals conceded",  f"[red]{form['ga']}[/red] ({form['avg_ga']} avg)")
    form_tbl.add_row("Goal difference", str(form["gd"]))
    form_tbl.add_row("Points %",        f"{form['points_pct']}%")
    console.print(form_tbl)

    # Upcoming matches
    if next_m:
        up_tbl = Table(title="Upcoming Matches", box=box.SIMPLE, header_style="bold magenta")
        up_tbl.add_column("Date", width=12)
        up_tbl.add_column("Home", width=22)
        up_tbl.add_column("Away", width=22)
        up_tbl.add_column("Competition", width=24)
        for ev in next_m:
            up_tbl.add_row(
                ev.get("dateEvent", "-"),
                ev.get("strHomeTeam", "-"),
                ev.get("strAwayTeam", "-"),
                ev.get("strLeague", "-"),
            )
        console.print(up_tbl)


def cmd_upcoming(sport_key: str):
    from fetchers.odds import get_odds
    from rich.table import Table
    from rich import box

    _banner()
    console.print(f"\n[bold]Upcoming events for sport:[/bold] [cyan]{sport_key}[/cyan]\n")

    with console.status("Fetching odds…"):
        events = get_odds(sport_key)

    if not events:
        console.print("[yellow]No events found. Check your ODDS_API_KEY and sport key.[/yellow]")
        return

    tbl = Table(title=f"Upcoming – {sport_key}", box=box.ROUNDED, header_style="bold cyan")
    tbl.add_column("Date",      width=14)
    tbl.add_column("Home",      width=24)
    tbl.add_column("Away",      width=24)
    tbl.add_column("Home Odd",  justify="right", width=10)
    tbl.add_column("Draw",      justify="right", width=10)
    tbl.add_column("Away Odd",  justify="right", width=10)

    for ev in events[:20]:
        home_odd = draw_odd = away_odd = "-"
        for bm in (ev.get("bookmakers") or [])[:1]:
            for mkt in bm.get("markets", []):
                if mkt["key"] != "h2h": continue
                outs = {o["name"].lower(): o["price"] for o in mkt["outcomes"]}
                home_odd = f"{outs.get(ev['home_team'].lower(), '-'):.2f}" \
                           if isinstance(outs.get(ev["home_team"].lower()), float) else "-"
                away_odd = f"{outs.get(ev['away_team'].lower(), '-'):.2f}" \
                           if isinstance(outs.get(ev["away_team"].lower()), float) else "-"
                draw_odd = f"{outs.get('draw', '-'):.2f}" \
                           if isinstance(outs.get("draw"), float) else "-"
        date = (ev.get("commence_time") or "")[:10]
        tbl.add_row(date, ev.get("home_team", "-"), ev.get("away_team", "-"),
                    home_odd, draw_odd, away_odd)
    console.print(tbl)


# ── CLI parser ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="betting-bot",
        description="Sports Betting Stats Bot – multi-model match analysis",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # match
    p_match = sub.add_parser("match", help="Analyse a specific match")
    p_match.add_argument("home", help="Home team name")
    p_match.add_argument("away", help="Away team name")
    p_match.add_argument("--sport", default="",
                         help="Odds-API sport key (e.g. soccer_spain_la_liga)")

    # news
    p_news = sub.add_parser("news", help="Latest news & injury alerts for a team")
    p_news.add_argument("team", help="Team name")

    # stats
    p_stats = sub.add_parser("stats", help="Team form, ELO and upcoming fixtures")
    p_stats.add_argument("team", help="Team name")

    # upcoming
    p_up = sub.add_parser("upcoming", help="Upcoming matches with live odds")
    p_up.add_argument("--sport", required=True,
                      help="Sport key e.g. soccer_spain_la_liga, basketball_nba")

    args = parser.parse_args()

    if args.command == "match":
        cmd_match(args.home, args.away, args.sport)
    elif args.command == "news":
        cmd_news(args.team)
    elif args.command == "stats":
        cmd_stats(args.team)
    elif args.command == "upcoming":
        cmd_upcoming(args.sport)


if __name__ == "__main__":
    main()
