"""Fantasy AI — CLI entry point.

Commands:
  fantasy setup            Configure .env (API keys)
  fantasy analyze-roster   Full dynasty roster analysis
  fantasy weekly           Weekly start/sit + waiver wire advice
  fantasy trade            Evaluate a trade offer interactively
  fantasy rookies          Scout the incoming rookie class
  fantasy ask "question"   Ask anything about your team
"""
from __future__ import annotations
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.live import Live
from rich.text import Text

app = typer.Typer(
    name="fantasy",
    help="Agentic dynasty fantasy football assistant powered by Gemini.",
    add_completion=False,
)
console = Console()


def _load_league():
    from .tools.sleeper_tool import get_league
    with console.status("[cyan]Loading league from Sleeper...[/cyan]"):
        return get_league()


def _run_agent(label: str, agent_fn, *args, **kwargs) -> str:
    """Run an agent function with a live spinner that shows each tool call."""
    tool_calls: list[str] = []

    def on_tool_call(name: str, inputs: dict):
        player = inputs.get("player_name", "")
        desc = name.replace("_", " ")
        msg = f"[dim]→ {desc}" + (f": {player}" if player else "") + "[/dim]"
        tool_calls.append(msg)

    with Live(console=console, refresh_per_second=4) as live:
        def _cb(name, inputs):
            on_tool_call(name, inputs)
            recent = "\n".join(tool_calls[-6:])
            live.update(Panel(
                f"[cyan]{label}[/cyan]\n\n{recent}",
                title=f"[bold]Working[/bold] ({len(tool_calls)} tool calls)",
                expand=False,
            ))

        kwargs["on_tool_call"] = _cb
        result = agent_fn(*args, **kwargs)
        live.update(Panel(f"[green]Done![/green]", expand=False))

    return result


@app.command()
def setup():
    """Configure your .env file with API keys."""
    console.print(Panel.fit(
        "[bold cyan]Fantasy AI Setup[/bold cyan]\n"
        "Sleeper is pre-configured — you just need your Google Gemini API key.",
        title="Setup"
    ))

    env_path = Path(".env")
    example_path = Path(".env.example")

    if not env_path.exists():
        if example_path.exists():
            import shutil
            shutil.copy(example_path, env_path)
            console.print("[green]Created .env from .env.example[/green]")
        else:
            env_path.write_text("")

    existing: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            existing[k.strip()] = v.strip()

    updates: dict[str, str] = {}

    console.print("\n[bold]1. Google Gemini API Key (free)[/bold]")
    console.print("  Get yours at: https://aistudio.google.com → Get API key")
    key = Prompt.ask("  GOOGLE_API_KEY", default=existing.get("GOOGLE_API_KEY", ""), password=True)
    if key:
        updates["GOOGLE_API_KEY"] = key

    # Write back
    lines = env_path.read_text().splitlines()
    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        if "=" in line and not line.startswith("#"):
            k = line.split("=")[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                written.add(k)
                continue
        new_lines.append(line)
    for k, v in updates.items():
        if k not in written:
            new_lines.append(f"{k}={v}")

    env_path.write_text("\n".join(new_lines) + "\n")
    console.print("\n[green].env saved.[/green]")
    console.print("Run [bold cyan]fantasy analyze-roster[/bold cyan] to start.")


@app.command(name="analyze-roster")
def analyze_roster():
    """Full dynasty tier analysis of your entire roster."""
    from .agents.fantasy_agent import FantasyAgent

    league = _load_league()
    if not league.my_team:
        console.print("[red]Your team was not found. Check SLEEPER_USER_ID in .env.[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Team:[/cyan] {league.my_team.name}  "
                  f"[cyan]League:[/cyan] {league.name}  "
                  f"[cyan]Season:[/cyan] {league.season}")

    agent = FantasyAgent()
    result = _run_agent("Dynasty Roster Analysis", agent.analyze_roster, league)
    console.print(Panel(Markdown(result), title="[bold cyan]Dynasty Roster Analysis[/bold cyan]", expand=True))


@app.command()
def weekly(week: int = typer.Option(None, "--week", "-w", help="Override week number")):
    """Weekly start/sit decisions and waiver wire targets."""
    from .agents.fantasy_agent import FantasyAgent

    league = _load_league()
    agent = FantasyAgent()
    result = _run_agent("Weekly Advice", agent.weekly_lineup_advice, league, week=week)
    console.print(Panel(Markdown(result), title="[bold cyan]Weekly Advice[/bold cyan]", expand=True))


@app.command()
def trade():
    """Interactively evaluate a trade offer."""
    from .agents.fantasy_agent import FantasyAgent
    from .models.player import Player, Position
    from .models.league import TradeOffer

    console.print(Panel.fit(
        "[bold]Trade Evaluator[/bold]\n"
        "Enter the players involved. Type [cyan]done[/cyan] when finished each side.",
        title="Trade Analysis"
    ))

    def _collect_players(label: str) -> list[Player]:
        players: list[Player] = []
        console.print(f"\n[cyan]{label}[/cyan]")
        while True:
            name = Prompt.ask("  Player name (or 'done')")
            if name.lower() == "done":
                break
            pos_str = Prompt.ask("  Position", choices=["QB", "RB", "WR", "TE", "K"])
            team = Prompt.ask("  NFL team (e.g. KC, SF)", default="UNK")
            age_s = Prompt.ask("  Age (or leave blank)", default="")
            age = int(age_s) if age_s.isdigit() else None
            players.append(Player(
                player_id=f"manual_{name.replace(' ', '_')}",
                name=name,
                position=Position(pos_str),
                nfl_team=team,
                age=age,
            ))
        return players

    i_give = _collect_players("Players I would GIVE")
    i_receive = _collect_players("Players I would RECEIVE")
    context = Prompt.ask("\nAdditional context? (team needs, pick included, etc.)", default="")

    offer = TradeOffer(i_give=i_give, i_receive=i_receive, context_notes=context)

    try:
        league = _load_league()
    except Exception:
        league = None

    agent = FantasyAgent()
    result = _run_agent("Trade Analysis", agent.evaluate_trade, offer, league)
    console.print(Panel(Markdown(result), title="[bold cyan]Trade Evaluation[/bold cyan]", expand=True))


@app.command(name="draft-board")
def draft_board():
    """Ranked rookie draft board — re-run anytime to see who's still available.

    Shows all incoming rookies scored for this league (Full PPR + SUPER_FLEX),
    cross-referenced against Sleeper draft picks already made. Run this mid-draft
    to get a live view of who's gone and who to target next.
    """
    from .agents.fantasy_agent import FantasyAgent
    from .tools.draft_tool import build_rookie_board, format_draft_board, get_my_draft_picks_context

    # First, print the raw board instantly (no API wait) so user has something to read
    console.print(Panel.fit(
        "[bold cyan]Loading rookie board from Sleeper...[/bold cyan]\n"
        "Draft: May 15, 2026 | Your pick: Slot 7 (linear) | 4 rounds",
        title="Rookie Draft Board"
    ))

    with console.status("[cyan]Fetching draft state and player data...[/cyan]"):
        prospects = build_rookie_board(include_drafted=True)
        board_text = format_draft_board(prospects)
        picks_ctx = get_my_draft_picks_context()

    # Print the raw scored board
    console.print(f"\n[bold]{picks_ctx}[/bold]\n")
    console.print(board_text)

    # Then run the agent for deep analysis
    console.print("\n[dim]Running Gemini analysis for draft strategy...[/dim]\n")
    try:
        league = _load_league()
    except Exception:
        league = None

    agent = FantasyAgent()
    result = _run_agent("Draft Strategy Analysis", agent.draft_board_analysis, league)
    console.print(Panel(Markdown(result), title="[bold cyan]Draft Strategy[/bold cyan]", expand=True))


@app.command(name="roster-review")
def roster_review(week: int = typer.Option(None, "--week", "-w", help="Override week number")):
    """Deep weekly roster review — injury alerts, lineup, waivers, dynasty pulse, trades.

    More comprehensive than `weekly`. Run this once a week to get a full
    strategic picture: lineup optimization, waiver wire bids, dynasty hold/sell
    signals, trade opportunities, and a to-do checklist for Sleeper.
    """
    from .agents.fantasy_agent import FantasyAgent

    league = _load_league()
    if not league.my_team:
        console.print("[red]Your team was not found. Check SLEEPER_USER_ID in .env.[/red]")
        raise typer.Exit(1)

    w = week or league.current_week
    console.print(
        f"[cyan]Team:[/cyan] {league.my_team.name}  "
        f"[cyan]Week:[/cyan] {w}  "
        f"[cyan]Record:[/cyan] {league.my_team.record_wins}W-{league.my_team.record_losses}L"
    )

    agent = FantasyAgent()
    result = _run_agent("Weekly Roster Review", agent.weekly_roster_review, league, week=week)
    console.print(Panel(Markdown(result), title=f"[bold cyan]Week {w} Roster Review[/bold cyan]", expand=True))


@app.command()
def rookies():
    """Qualitative rookie class scouting (KTC values + landing spot analysis).

    Use `draft-board` for the full ranked board with live draft availability.
    Use this command for a qualitative deep-dive on the rookie class.
    """
    from .agents.fantasy_agent import FantasyAgent

    agent = FantasyAgent()
    result = _run_agent("Rookie Scouting", agent.scout_rookies)
    console.print(Panel(Markdown(result), title="[bold cyan]2026 Rookie Class Scouting[/bold cyan]", expand=True))


@app.command(name="propose-trade")
def propose_trade(
    team: str = typer.Option(
        None, "--team", "-t",
        help="Target a specific team owner name (e.g. 'Rickdaddy47'). Omit to find the top 3 deals across all teams."
    )
):
    """Generate trade proposals you should send to maximize your dynasty team.

    Scans all league rosters, identifies the best trading partners for your needs,
    and outputs concrete deals that are favorable to you but enticing for the
    other team. Optionally target a specific team with --team.
    """
    from .agents.fantasy_agent import FantasyAgent

    league = _load_league()
    if not league.my_team:
        console.print("[red]Your team was not found. Check SLEEPER_USER_ID in .env.[/red]")
        raise typer.Exit(1)

    console.print(
        f"[cyan]Team:[/cyan] {league.my_team.name}  "
        f"[cyan]Record:[/cyan] {league.my_team.record_wins}W-{league.my_team.record_losses}L"
        + (f"  [cyan]Targeting:[/cyan] {team}" if team else "  [cyan]Scanning all opponents...[/cyan]")
    )

    label = f"Trade Proposals → {team}" if team else "Trade Proposal Scanner"
    agent = FantasyAgent()
    result = _run_agent(label, agent.generate_trade_proposal, league, target_team=team)
    title = f"[bold cyan]Proposed Trades{f' → {team}' if team else ''}[/bold cyan]"
    console.print(Panel(Markdown(result), title=title, expand=True))


@app.command()
def ask(question: str = typer.Argument(..., help="Your fantasy football question")):
    """Ask the agent anything about your team or the NFL."""
    from .agents.fantasy_agent import FantasyAgent

    try:
        league = _load_league()
    except Exception:
        league = None

    agent = FantasyAgent()
    result = _run_agent("Analyzing", agent.ask, question, league=league)
    console.print(Panel(Markdown(result), title="[bold cyan]Fantasy AI[/bold cyan]", expand=True))


def main():
    app()


if __name__ == "__main__":
    main()
