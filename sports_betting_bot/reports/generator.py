"""
Rich CLI report generator.
Renders MatchPrediction into colourful tables and panels using the
`rich` library.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.rule import Rule
from rich import box

from analysis.predictor import MatchPrediction

console = Console()


# ── Colour helpers ────────────────────────────────────────────────────────────

def _prob_colour(pct: float) -> str:
    if pct >= 60: return "bold green"
    if pct >= 45: return "yellow"
    return "red"


def _conf_bar(value: float, width: int = 20) -> str:
    filled = int(value / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _form_coloured(form_str: str) -> Text:
    t = Text()
    for ch in form_str:
        colour = {"W": "green", "D": "yellow", "L": "red"}.get(ch, "white")
        t.append(ch + " ", style=f"bold {colour}")
    return t


# ── Main report ───────────────────────────────────────────────────────────────

def print_match_report(pred: MatchPrediction):
    console.print()
    console.print(Rule(f"[bold cyan]MATCH ANALYSIS REPORT", style="cyan"))

    # ── Header ────────────────────────────────────────────────────────────────
    header = Text(justify="center")
    header.append(f"  {pred.home.name}  ", style="bold white on blue")
    header.append("  vs  ", style="bold white")
    header.append(f"  {pred.away.name}  ", style="bold white on red")
    console.print(Panel(header, border_style="cyan"))

    # ── Probability summary ───────────────────────────────────────────────────
    prob_table = Table(title="Win Probabilities (Blended Model)", box=box.ROUNDED,
                       show_header=True, header_style="bold magenta")
    prob_table.add_column("Outcome",   style="bold", width=18)
    prob_table.add_column("Probability", justify="right", width=14)
    prob_table.add_column("Visual",    width=24)
    prob_table.add_column("Best Odd",  justify="right", width=10)
    prob_table.add_column("Impl. Prob", justify="right", width=12)
    prob_table.add_column("Edge",      justify="right", width=10)

    rows = [
        (
            f"🏠 {pred.home.name}",
            pred.home_win_prob,
            pred.home_best_odd,
            pred.market_home_implied,
            pred.home_win_prob - pred.market_home_implied,
        ),
        (
            "🤝 Draw",
            pred.draw_prob,
            pred.draw_best_odd,
            pred.market_draw_implied,
            pred.draw_prob - pred.market_draw_implied,
        ),
        (
            f"✈️  {pred.away.name}",
            pred.away_win_prob,
            pred.away_best_odd,
            pred.market_away_implied,
            pred.away_win_prob - pred.market_away_implied,
        ),
    ]

    for label, prob, odd, impl, edge in rows:
        edge_str = (
            f"[green]+{edge:.1f}%[/green]" if edge > 2 else
            f"[red]{edge:.1f}%[/red]"      if edge < -2 else
            f"[yellow]{edge:.1f}%[/yellow]"
        )
        prob_table.add_row(
            label,
            f"[{_prob_colour(prob)}]{prob:.1f}%[/{_prob_colour(prob)}]",
            f"[{_prob_colour(prob)}]{_conf_bar(prob)}[/{_prob_colour(prob)}]",
            f"{odd:.2f}" if odd else "-",
            f"{impl:.1f}%" if impl else "-",
            edge_str if impl else "-",
        )

    console.print(prob_table)

    # ── Model breakdown ───────────────────────────────────────────────────────
    model_table = Table(title="Model Breakdown", box=box.SIMPLE_HEAVY,
                        header_style="bold cyan")
    model_table.add_column("Model",    style="dim", width=18)
    model_table.add_column("Home",     justify="right", width=12)
    model_table.add_column("Draw",     justify="right", width=12)
    model_table.add_column("Away",     justify="right", width=12)

    model_table.add_row(
        "⚽ Poisson",
        f"{pred.poisson_home_win:.1f}%",
        f"{pred.poisson_draw:.1f}%",
        f"{pred.poisson_away_win:.1f}%",
    )
    model_table.add_row(
        "📊 ELO Rating",
        f"{pred.elo_home_prob:.1f}%",
        "-",
        f"{pred.elo_away_prob:.1f}%",
    )
    model_table.add_row(
        "📈 Expected Goals",
        f"{pred.exp_goals_home:.2f} xG",
        "vs",
        f"{pred.exp_goals_away:.2f} xG",
    )
    console.print(model_table)

    # ── Top predicted scores ─────────────────────────────────────────────────
    score_tbl = Table(title="Most Likely Scorelines", box=box.MINIMAL_DOUBLE_HEAD,
                      header_style="bold yellow")
    score_tbl.add_column("Score", justify="center", width=10)
    score_tbl.add_column("Probability", justify="right", width=14)
    for score, prob in pred.top_scores:
        score_tbl.add_row(score, f"{prob:.2f}%")
    console.print(score_tbl)

    # ── Team stats side by side ───────────────────────────────────────────────
    def team_panel(ts, side: str) -> Panel:
        f = ts.form
        t = Table.grid(padding=(0, 1))
        t.add_column(style="dim", width=16)
        t.add_column(justify="right", width=12)
        t.add_row("Recent form:", _form_coloured(f.get("form_str", "-")))
        t.add_row("W/D/L:", f"[green]{f.get('wins',0)}[/green]/"
                             f"[yellow]{f.get('draws',0)}[/yellow]/"
                             f"[red]{f.get('losses',0)}[/red]")
        t.add_row("Goals scored:", f"[green]{f.get('gf',0)}[/green] ({f.get('avg_gf',0)} avg)")
        t.add_row("Goals conceded:", f"[red]{f.get('ga',0)}[/red] ({f.get('avg_ga',0)} avg)")
        t.add_row("Goal diff:", str(f.get("gd", 0)))
        t.add_row("Pts %:", f"[bold]{f.get('points_pct',0)}%[/bold]")
        t.add_row("Momentum:", f"[bold cyan]{ts.momentum}[/bold cyan] / 100")
        t.add_row("ELO:", f"[bold]{ts.elo:.0f}[/bold]")
        t.add_row("Att. strength:", f"{ts.attack_str:.2f}")
        t.add_row("Def. strength:", f"{ts.defence_str:.2f}")
        colour = "blue" if side == "home" else "red"
        return Panel(t, title=f"[bold {colour}]{ts.name}[/bold {colour}]",
                     border_style=colour)

    console.print(Columns([
        team_panel(pred.home, "home"),
        team_panel(pred.away, "away"),
    ]))

    # ── H2H ──────────────────────────────────────────────────────────────────
    total_h2h = pred.h2h_home_wins + pred.h2h_draws + pred.h2h_away_wins
    if total_h2h:
        h2h_txt = Text(justify="center")
        h2h_txt.append(f"{pred.home.name}  ", style="bold blue")
        h2h_txt.append(f"{pred.h2h_home_wins}W - {pred.h2h_draws}D - {pred.h2h_away_wins}L",
                       style="bold white")
        h2h_txt.append(f"  {pred.away.name}", style="bold red")
        console.print(Panel(h2h_txt, title="Head-to-Head History", border_style="dim"))

    # ── Recommendation ────────────────────────────────────────────────────────
    _print_recommendation(pred)

    # ── Notes ─────────────────────────────────────────────────────────────────
    if pred.notes:
        console.print(Panel(
            "\n".join(f"• {n}" for n in pred.notes),
            title="[bold yellow]Key Signals & Alerts",
            border_style="yellow",
        ))

    console.print(Rule(style="dim"))
    console.print()


def _print_recommendation(pred: MatchPrediction):
    bet   = pred.recommended_bet
    conf  = pred.confidence
    edge  = pred.value_edge
    kelly = pred.kelly_stake_pct

    colour = "green" if conf >= 65 else "yellow" if conf >= 50 else "red"

    lines = [
        f"[bold]Recommended Bet:[/bold]  [bold {colour}]{bet}[/bold {colour}]",
        f"[bold]Confidence:[/bold]       [{colour}]{conf:.1f}%[/{colour}]  "
        f"[dim]{_conf_bar(conf, 30)}[/dim]",
    ]
    if edge:
        lines.append(f"[bold]Value Edge:[/bold]       "
                     f"{'[green]' if edge>0 else '[red]'}{edge:+.2f}%"
                     f"{'[/green]' if edge>0 else '[/red]'} over market")
    if kelly > 0:
        lines.append(f"[bold]Kelly Stake:[/bold]      [cyan]{kelly:.2f}% of bankroll[/cyan]  "
                     f"[dim](Fractional Kelly ×0.25)[/dim]")
    else:
        lines.append("[dim]No market odds available for Kelly calculation.[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title=f"[bold {'green' if conf >= 65 else 'yellow'}]BETTING RECOMMENDATION",
        border_style=colour,
        padding=(1, 2),
    ))


# ── News report ───────────────────────────────────────────────────────────────

def print_news(articles: list[dict], title: str = "Recent News"):
    if not articles:
        console.print(f"[dim]No recent news found for {title}.[/dim]")
        return
    tbl = Table(title=title, box=box.SIMPLE, header_style="bold cyan")
    tbl.add_column("Date",   width=12)
    tbl.add_column("Source", width=18)
    tbl.add_column("Headline", width=60)
    tbl.add_column("Sentiment", width=12, justify="center")
    for a in articles:
        s = a.get("sentiment", "neutral")
        s_style = {"positive": "[green]▲[/green]",
                   "negative": "[red]▼[/red]",
                   "neutral":  "[yellow]●[/yellow]"}.get(s, "●")
        tbl.add_row(
            a.get("published_at", ""),
            a.get("source", ""),
            a.get("title", "")[:60],
            s_style,
        )
    console.print(tbl)
