"""Draft board tool — tracks the Sleeper rookie draft in real time.

Key capabilities:
  - Fetches all picks already made in the draft
  - Builds ranked rookie list from Sleeper player DB
  - Cross-references to show who is still available
  - Computes a league-specific score for each rookie
    (Full PPR + SUPER_FLEX boosts QBs, PPR boosts pass-catchers)

Draft details (Washington Football League, 2026):
  Draft ID:    1337099185064779776
  Start:       May 15, 2026
  Rounds:      4 (rookie picks only)
  Your slot:   7 of 10 (linear — same slot every round)
  Type:        Linear (not snake — you always pick 7th)
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field

import httpx

from ..db.database import save_reddit_cache, load_reddit_cache

_BASE = "https://api.sleeper.app/v1"
_DRAFT_ID = "1337099185064779776"
_MY_PICK_SLOT = 7     # spuddister picks 7th every round
_NUM_TEAMS = 10
_NUM_ROUNDS = 4

# League scoring weights for rookie value score
# Full PPR + SUPER_FLEX (2QB)
_POSITION_MULTIPLIER = {
    "QB": 1.5,   # SUPER_FLEX makes QBs 50% more valuable than a 1QB league
    "WR": 1.2,   # PPR heavily rewards WRs
    "TE": 1.1,   # PPR boosts TEs; late developers
    "RB": 1.0,   # Good PPR RBs are great; but age cliff is steep
}


@dataclass
class RookieProspect:
    player_id: str
    name: str
    position: str
    nfl_team: str
    age: int | None
    college: str
    depth_chart_order: int | None   # 1 = starter, 2 = backup, etc.
    search_rank: int                # Sleeper community rank (lower = better)
    years_exp: int

    # Computed
    league_score: float = 0.0       # 0–100, higher = better fit for this league
    available: bool = True
    drafted_by: str = ""            # team name if already drafted
    pick_number: int | None = None  # overall pick number in draft

    @property
    def age_score(self) -> float:
        """Dynasty age bonus — younger is better."""
        if self.age is None:
            return 50.0
        age_scores = {
            19: 100, 20: 95, 21: 90, 22: 83, 23: 74, 24: 63,
            25: 50, 26: 35, 27: 20, 28: 10,
        }
        return age_scores.get(self.age, max(0, 5 - (self.age - 28) * 5))

    @property
    def opportunity_score(self) -> float:
        """Depth chart signal — lower depth_chart_order = more opportunity."""
        if self.depth_chart_order is None:
            return 40.0
        scores = {1: 100, 2: 60, 3: 30, 4: 15}
        return scores.get(self.depth_chart_order, 5)

    @property
    def tier(self) -> str:
        if self.league_score >= 80:
            return "1 — Elite"
        elif self.league_score >= 65:
            return "2 — Great"
        elif self.league_score >= 50:
            return "3 — Good"
        elif self.league_score >= 35:
            return "4 — Fringe"
        else:
            return "5 — Depth"


def _get(path: str) -> dict | list:
    url = f"{_BASE}{path}"
    resp = httpx.get(url, timeout=15, headers={"User-Agent": "fantasy-ai/0.1"})
    resp.raise_for_status()
    return resp.json()


def _load_player_db() -> dict[str, dict]:
    from .sleeper_tool import _load_player_db as _load
    return _load()


def get_draft_picks() -> list[dict]:
    """Fetch all picks made so far in the draft. Returns [] if draft hasn't started."""
    cache_key = f"draft_picks:{_DRAFT_ID}"
    cached = load_reddit_cache(cache_key, max_age_hours=0)  # always fresh during draft

    try:
        picks = _get(f"/draft/{_DRAFT_ID}/picks")
        return picks if isinstance(picks, list) else []
    except Exception:
        return []


def build_rookie_board(include_drafted: bool = True) -> list[RookieProspect]:
    """Build complete ranked rookie board with availability status."""
    player_db = _load_player_db()

    # Get picks already made
    picks = get_draft_picks()
    # Map player_id → {pick_number, picked_by}
    drafted: dict[str, dict] = {}
    for pick in picks:
        pid = str(pick.get("player_id", ""))
        if pid:
            drafted[pid] = {
                "pick_no": pick.get("pick_no", 0),
                "picked_by": pick.get("picked_by", ""),
                "roster_id": pick.get("roster_id"),
            }

    # Get users for display names
    try:
        users_raw = _get(f"/league/1337099185056395264/users")
        user_map = {u["user_id"]: u.get("display_name", "") for u in users_raw}
        # Also map roster_id → display name via rosters
        rosters_raw = _get(f"/league/1337099185056395264/rosters")
        roster_to_user = {str(r["roster_id"]): r.get("owner_id", "") for r in rosters_raw}
    except Exception:
        user_map = {}
        roster_to_user = {}

    prospects: list[RookieProspect] = []

    for pid, p in player_db.items():
        # 2026 rookies: years_exp == 0 and active skill position players
        if p.get("years_exp") != 0:
            continue
        pos = p.get("position", "")
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        if not p.get("active") or not p.get("full_name"):
            continue
        # Filter out placeholder/test players
        if not p.get("team") and not p.get("college"):
            continue

        search_rank = p.get("search_rank") or 9999

        prospect = RookieProspect(
            player_id=pid,
            name=p.get("full_name", "Unknown"),
            position=pos,
            nfl_team=p.get("team") or "FA",
            age=p.get("age"),
            college=p.get("college") or "Unknown",
            depth_chart_order=p.get("depth_chart_order"),
            search_rank=search_rank,
            years_exp=p.get("years_exp", 0),
        )

        # Set drafted status
        if pid in drafted:
            prospect.available = False
            prospect.pick_number = drafted[pid]["pick_no"]
            roster_id = str(drafted[pid].get("roster_id", ""))
            owner_id = roster_to_user.get(roster_id, "")
            prospect.drafted_by = user_map.get(owner_id, f"Roster {roster_id}")

        # Compute league score
        rank_score = max(0, 100 - (search_rank / 10))
        pos_mult = _POSITION_MULTIPLIER.get(pos, 1.0)
        raw = (rank_score * 0.5) + (prospect.age_score * 0.3) + (prospect.opportunity_score * 0.2)
        prospect.league_score = min(100, raw * pos_mult)

        prospects.append(prospect)

    # Sort: available first, then by league_score descending
    prospects.sort(key=lambda x: (-x.league_score, x.search_rank))

    if not include_drafted:
        prospects = [p for p in prospects if p.available]

    return prospects


def format_draft_board(prospects: list[RookieProspect], show_all: bool = False) -> str:
    """Format the draft board as a text table for display / Gemini context."""
    available = [p for p in prospects if p.available]
    drafted = [p for p in prospects if not p.available]

    lines: list[str] = [
        "=" * 80,
        f"  ROOKIE DRAFT BOARD — Washington Football League 2026",
        f"  Full PPR + SUPER_FLEX | Your pick: Slot 7 (linear) | Rounds: {_NUM_ROUNDS}",
        f"  Picks made: {len(drafted)} / {_NUM_TEAMS * _NUM_ROUNDS} total",
        "=" * 80,
        "",
        f"  {'#':<4} {'Name':<24} {'Pos':<4} {'NFL Team':<8} {'Age':<4} {'College':<20} {'Score':<6} {'Tier'}",
        f"  {'-'*4} {'-'*24} {'-'*4} {'-'*8} {'-'*4} {'-'*20} {'-'*6} {'-'*14}",
    ]

    lines.append("\n  ── AVAILABLE ──\n")
    for i, p in enumerate(available[:50], 1):
        lines.append(
            f"  {i:<4} {p.name:<24} {p.position:<4} {p.nfl_team:<8} "
            f"{str(p.age or '?'):<4} {p.college[:20]:<20} {p.league_score:<6.1f} {p.tier}"
        )

    if drafted:
        lines.append(f"\n  ── ALREADY DRAFTED ({len(drafted)}) ──\n")
        for p in sorted(drafted, key=lambda x: x.pick_number or 999)[:30]:
            lines.append(
                f"  Pick #{p.pick_number or '?':<3}  {p.name:<24} {p.position:<4} "
                f"{p.nfl_team:<8} {str(p.age or '?'):<4} → drafted by {p.drafted_by}"
            )

    return "\n".join(lines)


def get_my_draft_picks_context() -> str:
    """Return a summary of upcoming pick slots for the user."""
    picks_made = get_draft_picks()
    total_picks = _NUM_ROUNDS * _NUM_TEAMS
    picks_done = len(picks_made)
    picks_remaining = total_picks - picks_done

    my_picks = []
    for round_num in range(1, _NUM_ROUNDS + 1):
        overall = (round_num - 1) * _NUM_TEAMS + _MY_PICK_SLOT
        # Check if this pick was already made
        matching = [p for p in picks_made if p.get("pick_no") == overall]
        if matching:
            pid = str(matching[0].get("player_id", ""))
            from .sleeper_tool import _load_player_db
            db = _load_player_db()
            player_name = db.get(pid, {}).get("full_name", f"ID:{pid}")
            my_picks.append(f"  Round {round_num} (Pick #{overall}): MADE — {player_name}")
        else:
            my_picks.append(f"  Round {round_num} (Pick #{overall}): AVAILABLE")

    lines = [
        f"Draft status: {picks_done}/{total_picks} picks made",
        f"Your picks (slot 7, linear draft):",
    ] + my_picks

    return "\n".join(lines)
