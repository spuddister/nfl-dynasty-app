"""Core Gemini-powered fantasy football agent.

Uses Google Gemini's function calling API (google-genai SDK) to autonomously:
  - Search Reddit for player sentiment
  - Pull Sleeper trending data and draft info
  - Fetch KTC dynasty values, ADP, injury reports, news
  - Analyze rosters, trades, lineups, and waiver wire picks

Free tier: gemini-2.0-flash — 1,500 requests/day, no credit card required.
Get a key at: https://aistudio.google.com
"""
from __future__ import annotations
import json
import time
from typing import Any

from google import genai
from google.genai import types

from ..config.settings import get_settings
from ..models.player import Player, Position
from ..models.league import LeagueInfo, TradeOffer
from ..tools.reddit_tool import search_reddit_for_player, get_weekly_news_digest
from ..tools.stats_tool import get_ktc_values, get_player_adp, get_injury_report, get_player_news
from ..tools.sleeper_tool import get_trending_adds, get_trending_drops, get_draft_info, format_roster_summary
from ..tools.draft_tool import build_rookie_board, format_draft_board, get_my_draft_picks_context
from ..db.database import init_db


# ── Tool definitions ──────────────────────────────────────────────────────────

_TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="search_reddit",
        description=(
            "Search Reddit (r/dynastyff, r/fantasyfootball, r/nfl) for recent posts "
            "about a specific NFL player. Returns post titles and top comments. "
            "Use for sentiment, injury news, depth chart updates, dynasty outlook."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "player_name": types.Schema(type=types.Type.STRING, description="Full name, e.g. 'George Pickens'"),
                "max_posts": types.Schema(type=types.Type.INTEGER, description="Number of posts to fetch (default 10)"),
            },
            required=["player_name"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_ktc_dynasty_value",
        description=(
            "Look up a player's KeepTradeCut (KTC) dynasty trade value (0-10000). "
            "KTC is the community gold standard for dynasty trade value."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"player_name": types.Schema(type=types.Type.STRING)},
            required=["player_name"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_player_adp",
        description="Get a player's Average Draft Position from FantasyPros (dynasty or redraft).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "player_name": types.Schema(type=types.Type.STRING),
                "format": types.Schema(type=types.Type.STRING, description="dynasty or redraft"),
            },
            required=["player_name"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_injury_report",
        description="Get the current full NFL injury report for all teams.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="get_player_news",
        description="Get the latest ESPN news articles about a specific player.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"player_name": types.Schema(type=types.Type.STRING)},
            required=["player_name"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_weekly_reddit_digest",
        description="Fetch weekly discussion and waiver wire threads from r/fantasyfootball.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="get_sleeper_trending",
        description=(
            "Get players trending as adds or drops on Sleeper waivers across all leagues. "
            "Useful for waiver wire buzz and spotting players losing value."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "type": types.Schema(type=types.Type.STRING, description="add or drop"),
                "count": types.Schema(type=types.Type.INTEGER, description="Number of players to return"),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="get_draft_info",
        description="Get information about the upcoming rookie draft for this league.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="get_rookie_draft_board",
        description=(
            "Get the full rookie draft board with league-specific scores, showing who is "
            "still available vs already drafted. Re-run during the draft for live availability."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "available_only": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="If true, only show available (un-drafted) players",
                ),
            },
        ),
    ),
]

GEMINI_TOOLS = types.Tool(function_declarations=_TOOL_DECLARATIONS)


# ── Tool execution ────────────────────────────────────────────────────────────

def _execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "search_reddit":
            return search_reddit_for_player(
                inputs["player_name"], max_posts=inputs.get("max_posts", 10)
            )
        elif name == "get_ktc_dynasty_value":
            values = get_ktc_values()
            player = inputs["player_name"]
            for k, v in values.items():
                if player.lower() in k.lower() or k.lower() in player.lower():
                    return f"{k}: KTC dynasty value = {v}/10000"
            return f"No KTC value found for {player} — may be unranked or a new rookie."
        elif name == "get_player_adp":
            return get_player_adp(inputs["player_name"], inputs.get("format", "dynasty"))
        elif name == "get_injury_report":
            return get_injury_report()
        elif name == "get_player_news":
            return get_player_news(inputs["player_name"])
        elif name == "get_weekly_reddit_digest":
            return get_weekly_news_digest()
        elif name == "get_sleeper_trending":
            trend_type = inputs.get("type", "add")
            count = int(inputs.get("count", 20))
            if trend_type == "drop":
                results = get_trending_drops(count)
                label = "Most dropped"
            else:
                results = get_trending_adds(count)
                label = "Most added"
            if not results:
                return "Trending data unavailable."
            lines = [f"{label} on Sleeper (last 24h):"]
            for r in results:
                metric = r.get("adds") or r.get("drops", 0)
                lines.append(f"  {r['name']} ({r['position']}, {r['team']}) — {metric:,} moves")
            return "\n".join(lines)
        elif name == "get_draft_info":
            drafts = get_draft_info()
            if not drafts:
                return "No draft information available yet."
            return json.dumps(drafts, indent=2)
        elif name == "get_rookie_draft_board":
            available_only = inputs.get("available_only", False)
            prospects = build_rookie_board(include_drafted=True)
            if available_only:
                prospects = [p for p in prospects if p.available]
            board = format_draft_board(prospects)
            picks_ctx = get_my_draft_picks_context()
            return f"{picks_ctx}\n\n{board}"
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error ({name}): {e}"


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert dynasty fantasy football analyst and personal advisor. Your user (spuddister) is brand new to fantasy football. They have taken over a dynasty team that finished 2nd place last season and is already built to compete.

LEAGUE DETAILS:
- Platform: Sleeper (Washington Football League)
- Format: Dynasty — rosters carry over year to year. Long-term player value matters enormously.
- Scoring: Full PPR (1pt/reception) + SUPER_FLEX (can start 2 QBs)
- 10 teams, 6 playoff spots
- Lineup: QB, RB, RB, WR, WR, TE, FLEX, FLEX, FLEX, SUPER_FLEX + 14 bench + 4 taxi + 4 IR
- FAAB waivers: $100 budget
- 4-round rookie draft on May 15, 2026 — user picks slot 7 (linear, same every round)
- Trade deadline: Week 12

CRITICAL SCORING CONTEXT — SUPER_FLEX LEAGUE:
Because of SUPER_FLEX, QBs are worth HUGE dynasty value. Top ~18 QBs have starting value.
Young QBs with upside (under 26) are premium dynasty assets in this format.

DYNASTY PRINCIPLES:
- Age curves: RBs peak 22-25, steep cliff after 27. WRs peak 24-27. QBs peak 25-33. TEs develop late.
- "Buy young" — a 22-year-old with upside beats a 29-year-old producing now in dynasty.
- KTC (KeepTradeCut) values are the community standard for trade value (0-10000 scale).
- Taxi squad: young players (up to 2 years pro) can be stashed without taking a roster spot.
- Draft picks are tradeable assets — future first-round picks have real value.

YOUR APPROACH:
- Always use your tools before answering — search Reddit, check KTC, get injury/news first.
- Explain every recommendation in plain language the user can understand.
- Be decisive: give clear STARTER/BENCH/TRADE/DROP calls, not vague hedging.
- For trades: evaluate both dynasty (long-term) AND redraft (this season) value separately.
- End every analysis with a clear action list: exactly what to do in Sleeper."""


# ── Agent class ───────────────────────────────────────────────────────────────

class FantasyAgent:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY not set in .env\n"
                "Get a free key at: https://aistudio.google.com"
            )
        self.client = genai.Client(api_key=settings.google_api_key)
        self.model = settings.gemini_model
        init_db()

    def _run_agent_loop(self, prompt: str, on_tool_call: Any = None) -> str:
        """Agentic loop: Gemini calls tools until it has enough info to answer."""
        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            tools=[GEMINI_TOOLS],
        )

        # Build conversation history
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part(text=prompt)])
        ]

        while True:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0]
            model_content = candidate.content

            # Collect text and function calls
            text_parts: list[str] = []
            function_calls: list[Any] = []
            for part in (model_content.parts or []):
                if part.text:
                    text_parts.append(part.text)
                if part.function_call:
                    function_calls.append(part.function_call)

            # No tool calls — done
            if not function_calls:
                return "\n".join(text_parts) or "No response generated."

            # Add model turn to history
            contents.append(model_content)

            # Execute tools and build response parts
            tool_parts: list[types.Part] = []
            for fc in function_calls:
                inputs = dict(fc.args) if fc.args else {}
                if on_tool_call:
                    on_tool_call(fc.name, inputs)
                result = _execute_tool(fc.name, inputs)
                tool_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                        )
                    )
                )

            # Add tool results as user turn and loop
            contents.append(types.Content(role="user", parts=tool_parts))

    # ── Public commands ───────────────────────────────────────────────────────

    def analyze_roster(self, league: LeagueInfo, on_tool_call: Any = None) -> str:
        if not league.my_team:
            return "Could not find your team. Check SLEEPER_USER_ID in .env."
        roster_text = format_roster_summary(league)
        prompt = f"""Analyze my dynasty roster completely. Here's my current team:

{roster_text}

For each player: search Reddit, check KTC dynasty value, get news/injury updates.

Then provide:
- Dynasty tier for each player: Elite / Great / Good / Fringe / Depth / Drop
- Age outlook using dynasty age curves
- Which players to HOLD long-term vs TRADE away
- Sell-high candidates (aging or overvalued right now)
- Buy-low targets I should pursue via trade
- Positions of weakness to target in the rookie draft
- Overall team grade (A-F) and honest assessment

I'm new to fantasy football — explain your reasoning clearly."""
        return self._run_agent_loop(prompt, on_tool_call)

    def weekly_lineup_advice(self, league: LeagueInfo, week: int | None = None,
                              on_tool_call: Any = None) -> str:
        if not league.my_team:
            return "Could not find your team. Check SLEEPER_USER_ID in .env."
        current_week = week or league.current_week
        roster_text = format_roster_summary(league)
        prompt = f"""It's Week {current_week}. I need my lineup set and waiver wire targets.

{roster_text}

Steps:
1. Get the full injury report
2. Check Sleeper trending adds
3. Search Reddit weekly discussion thread
4. Check news for any questionable players on my roster

Deliver:
- Optimal starting lineup (QB, RB, RB, WR, WR, TE, FLEX, FLEX, FLEX, SUPER_FLEX)
- Start/sit decisions with reasoning for close calls
- Top 5 waiver wire pickups with FAAB bid amounts (I have ${league.faab_budget or 100} budget)
- Anyone I should drop to make room
- Any urgent trade targets"""
        return self._run_agent_loop(prompt, on_tool_call)

    def evaluate_trade(self, offer: TradeOffer, league: LeagueInfo | None = None,
                       on_tool_call: Any = None) -> str:
        i_give = "\n".join(
            f"- {p.name} ({p.position.value}, {p.nfl_team}, age {p.age or '?'})"
            for p in offer.i_give
        )
        i_receive = "\n".join(
            f"- {p.name} ({p.position.value}, {p.nfl_team}, age {p.age or '?'})"
            for p in offer.i_receive
        )
        context = offer.context_notes or "No additional context."
        roster_ctx = ""
        if league and league.my_team:
            roster_ctx = f"\nMy full roster:\n{format_roster_summary(league)}"
        prompt = f"""Evaluate this trade offer in my dynasty league.

I would GIVE:
{i_give}

I would RECEIVE:
{i_receive}

Context: {context}
{roster_ctx}

Steps:
1. Check KTC dynasty value for every player in the trade
2. Search Reddit for sentiment on each player
3. Get recent news for each player

Analysis:
- Dynasty value comparison (KTC scores)
- Age trajectory comparison
- How this affects my roster construction
- Verdict: ACCEPT / REJECT / COUNTER (be decisive)
- If COUNTER: exactly what I should ask for instead"""
        return self._run_agent_loop(prompt, on_tool_call)

    def draft_board_analysis(self, league: LeagueInfo | None = None,
                              on_tool_call: Any = None) -> str:
        prospects = build_rookie_board(include_drafted=True)
        board_text = format_draft_board(prospects)
        picks_ctx = get_my_draft_picks_context()
        num_available = sum(1 for p in prospects if p.available)
        num_drafted = sum(1 for p in prospects if not p.available)
        roster_ctx = ""
        if league and league.my_team:
            roster_ctx = f"\nMy current roster:\n{format_roster_summary(league)}"
        prompt = f"""I need a complete rookie draft strategy for my 4-round dynasty draft.

DRAFT STATUS:
{picks_ctx}

CURRENT BOARD ({num_available} available, {num_drafted} already drafted):
{board_text}
{roster_ctx}

Steps:
1. Search Reddit r/dynastyff for "2026 rookie rankings" and top prospects
2. Check KTC dynasty values for the top 10 available rookies
3. Get news on the top 5 prospects (landing spot, depth chart, injury history)

Deliver:

## My Picks Strategy (Slot 7, linear draft — picks 7, 17, 27, 37)
Who to target at each pick based on who will likely still be available at pick 7 in each round.

## Top Available Prospects
For each of the top 15 available players:
- Name (Pos, Team, Age) — Tier
- Why they fit Full PPR + SUPER_FLEX scoring
- Dynasty outlook and risk factors

## Round-by-Round Plan
- Round 1 (Pick #7): Primary target + backup if taken
- Round 2 (Pick #17): Best available strategy
- Round 3 (Pick #27): Value/upside picks
- Round 4 (Pick #37): Stash candidates

## Players to Avoid
Overhyped rookies who don't fit dynasty or this scoring format."""
        return self._run_agent_loop(prompt, on_tool_call)

    def weekly_roster_review(self, league: LeagueInfo, week: int | None = None,
                              on_tool_call: Any = None) -> str:
        if not league.my_team:
            return "Could not find your team. Check SLEEPER_USER_ID in .env."
        current_week = week or league.current_week
        roster_text = format_roster_summary(league)
        prompt = f"""It's Week {current_week}. Give me a complete weekly roster review.

{roster_text}

Step 1 — Gather data:
1. Get the full injury report
2. Check Sleeper trending adds and drops
3. Get the weekly Reddit discussion digest
4. Check news for each player with an injury status on my roster

Step 2 — Deliver this structured report:

### Injury & Status Alerts
Flag every player with injury risk. Give specific start/sit guidance.

### Optimal Lineup (Week {current_week})
Fill all 10 starting spots: QB, RB, RB, WR, WR, TE, FLEX, FLEX, FLEX, SUPER_FLEX
Explain close decisions.

### Bench Priority Order
Rank bench players in case someone scratches.

### Waiver Wire Actions
- Must-add (bid up to X FAAB): player + reason
- Strong adds (bid Y FAAB): player + reason
- Low-cost stashes: $1-5 FAAB fliers
- Drop candidates: who I can safely cut

### Dynasty Pulse Check
For each starter: HOLD / SELL-HIGH / BUY-LOW / MONITOR with one-line reason.

### Trade Opportunities
- 1-2 sell-high targets
- 1-2 buy-low targets

### Weekly Action Checklist
Numbered to-do list of everything to do in Sleeper before the week locks."""
        return self._run_agent_loop(prompt, on_tool_call)

    def scout_rookies(self, on_tool_call: Any = None) -> str:
        prompt = """I'm preparing for a 4-round dynasty rookie draft (Full PPR + SUPER_FLEX, 10 teams).

Steps:
1. Search Reddit r/dynastyff for "2026 rookie rankings" and "best dynasty rookies 2026"
2. Search for the top 5 most-discussed individual rookies
3. Check KTC dynasty values for top rookies
4. Get news on top prospects (landing spot, depth chart, injury history)

Deliver:
- Top 20 dynasty rookie rankings with tier breaks
- Position-by-position breakdown
- SUPER_FLEX note: any QBs worth drafting early?
- Best value picks in rounds 2-4 (sleepers)
- Rookies to avoid (hype > reality)
- Draft strategy given my team needs"""
        return self._run_agent_loop(prompt, on_tool_call)

    def ask(self, question: str, league: LeagueInfo | None = None,
            on_tool_call: Any = None) -> str:
        context = ""
        if league and league.my_team:
            context = f"\n\nFor context, here's my current roster:\n{format_roster_summary(league)}"
        return self._run_agent_loop(question + context, on_tool_call)
