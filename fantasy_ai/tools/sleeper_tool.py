"""Sleeper Fantasy API connector — no authentication required for reads.

Sleeper API docs: https://docs.sleeper.com/

Key endpoints used:
  GET /league/{id}                  — league metadata
  GET /league/{id}/rosters          — all team rosters
  GET /league/{id}/users            — all team owners
  GET /players/nfl                  — full NFL player DB (cached 24h, ~14MB)
  GET /league/{id}/drafts           — upcoming/past drafts
  GET /league/{id}/transactions/{week} — trades/waiver moves
  GET /players/nfl/trending/add     — trending adds on waivers
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import httpx

from ..config.settings import get_settings
from ..models.player import Player, Position, InjuryStatus
from ..models.league import LeagueInfo, Team

_BASE = "https://api.sleeper.app/v1"
_PLAYER_CACHE_PATH = Path("./data/sleeper_players.json")

# Sleeper position string → our enum
_POS_MAP: dict[str, Position] = {
    "QB": Position.QB,
    "RB": Position.RB,
    "WR": Position.WR,
    "TE": Position.TE,
    "K": Position.K,
    "DEF": Position.DEF,
    "FB": Position.RB,   # fullback → treat as RB
}

_INJ_MAP: dict[str, InjuryStatus] = {
    "Active": InjuryStatus.HEALTHY,
    "Questionable": InjuryStatus.QUESTIONABLE,
    "Doubtful": InjuryStatus.DOUBTFUL,
    "Out": InjuryStatus.OUT,
    "IR": InjuryStatus.IR,
    "PUP": InjuryStatus.PUP,
    "Sus": InjuryStatus.UNKNOWN,
    "COV": InjuryStatus.UNKNOWN,
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(path: str, timeout: int = 15) -> dict | list:
    url = f"{_BASE}{path}"
    resp = httpx.get(url, timeout=timeout, headers={"User-Agent": "fantasy-ai/0.1"})
    resp.raise_for_status()
    return resp.json()


# ── Player database ───────────────────────────────────────────────────────────

def _load_player_db() -> dict[str, dict]:
    """Load Sleeper's full NFL player DB. Downloads once then caches to disk."""
    _PLAYER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Use cached file if it exists and is less than 24 hours old
    if _PLAYER_CACHE_PATH.exists():
        age_hours = (
            (__import__("time").time() - _PLAYER_CACHE_PATH.stat().st_mtime) / 3600
        )
        if age_hours < 24:
            with open(_PLAYER_CACHE_PATH) as f:
                return json.load(f)

    data = _get("/players/nfl", timeout=30)
    with open(_PLAYER_CACHE_PATH, "w") as f:
        json.dump(data, f)
    return data


def _parse_player(player_id: str, raw: dict, slot: str = "BN") -> Player:
    pos_str = raw.get("position", "WR")
    pos = _POS_MAP.get(pos_str, Position.WR)

    inj_str = raw.get("injury_status") or "Active"
    inj = _INJ_MAP.get(inj_str, InjuryStatus.UNKNOWN)

    return Player(
        player_id=f"sleeper_{player_id}",
        name=raw.get("full_name") or f"{raw.get('first_name','')} {raw.get('last_name','')}".strip(),
        position=pos,
        nfl_team=raw.get("team") or "FA",
        age=raw.get("age"),
        years_pro=raw.get("years_exp"),
        injury_status=inj,
        injury_note=raw.get("injury_notes") or "",
    )


# ── League data ───────────────────────────────────────────────────────────────

def get_league() -> LeagueInfo:
    """Fetch full league snapshot from Sleeper."""
    s = get_settings()
    league_id = s.sleeper_league_id
    user_id = s.sleeper_user_id

    league_raw = _get(f"/league/{league_id}")
    rosters_raw = _get(f"/league/{league_id}/rosters")
    users_raw = _get(f"/league/{league_id}/users")
    player_db = _load_player_db()

    # Build user_id → display info map
    user_map: dict[str, dict] = {u["user_id"]: u for u in users_raw}

    # Scoring detection
    scoring = league_raw.get("scoring_settings", {})
    rec_pts = scoring.get("rec", 0)
    if rec_pts >= 1.0:
        scoring_type = "PPR"
    elif rec_pts >= 0.5:
        scoring_type = "Half-PPR"
    else:
        scoring_type = "Standard"

    # Has SUPER_FLEX?
    roster_positions = league_raw.get("roster_positions", [])
    has_superflex = "SUPER_FLEX" in roster_positions

    teams: list[Team] = []
    my_team: Team | None = None

    for roster in rosters_raw:
        owner_id = roster.get("owner_id", "")
        user_info = user_map.get(owner_id, {})
        team_name = (
            user_info.get("metadata", {}).get("team_name")
            or user_info.get("display_name")
            or f"Team {roster['roster_id']}"
        )
        is_mine = owner_id == user_id

        starters_set = set(roster.get("starters") or [])
        ir_set = set(roster.get("reserve") or [])
        taxi_set = set(roster.get("taxi") or [])

        roster_players: list[Player] = []
        for pid in roster.get("players") or []:
            raw_player = player_db.get(pid, {})
            if not raw_player:
                continue
            slot = (
                "STARTER" if pid in starters_set
                else "IR" if pid in ir_set
                else "TAXI" if pid in taxi_set
                else "BENCH"
            )
            p = _parse_player(pid, raw_player, slot)
            p.is_on_my_roster = is_mine
            # Store slot info in acquisition_cost field (reusing for slot)
            p.acquisition_cost = slot
            roster_players.append(p)

        settings = roster.get("settings", {})
        team = Team(
            team_id=str(roster["roster_id"]),
            name=team_name,
            owner=user_info.get("display_name", ""),
            is_mine=is_mine,
            record_wins=settings.get("wins", 0),
            record_losses=settings.get("losses", 0),
            waiver_priority=settings.get("waiver_position"),
            roster=roster_players,
        )
        teams.append(team)
        if is_mine:
            my_team = team

    season = int(league_raw.get("season", 2025))

    return LeagueInfo(
        league_id=league_id,
        name=league_raw.get("name", "Sleeper League"),
        platform="sleeper",
        season=season,
        format="dynasty",
        scoring_type=scoring_type + (" SuperFlex" if has_superflex else ""),
        num_teams=league_raw.get("total_rosters", len(teams)),
        roster_spots={pos: roster_positions.count(pos) for pos in set(roster_positions)},
        teams=teams,
        my_team=my_team,
        current_week=league_raw.get("settings", {}).get("leg", 1),
        faab_budget=league_raw.get("settings", {}).get("waiver_budget", 100),
    )


def get_trending_adds(count: int = 20) -> list[dict]:
    """Players being added most on waivers across all Sleeper leagues."""
    try:
        data = _get(f"/players/nfl/trending/add?lookback_hours=24&limit={count}")
        player_db = _load_player_db()
        results = []
        for item in data:
            pid = item.get("player_id", "")
            raw = player_db.get(pid, {})
            name = raw.get("full_name", f"ID:{pid}")
            pos = raw.get("position", "?")
            team = raw.get("team", "FA")
            count_adds = item.get("count", 0)
            results.append({
                "name": name, "position": pos, "team": team,
                "adds": count_adds, "player_id": pid,
            })
        return results
    except Exception:
        return []


def get_trending_drops(count: int = 20) -> list[dict]:
    """Players being dropped most across all Sleeper leagues."""
    try:
        data = _get(f"/players/nfl/trending/drop?lookback_hours=24&limit={count}")
        player_db = _load_player_db()
        results = []
        for item in data:
            pid = item.get("player_id", "")
            raw = player_db.get(pid, {})
            results.append({
                "name": raw.get("full_name", f"ID:{pid}"),
                "position": raw.get("position", "?"),
                "team": raw.get("team", "FA"),
                "drops": item.get("count", 0),
            })
        return results
    except Exception:
        return []


def get_draft_info() -> list[dict]:
    """Fetch upcoming draft info for the league."""
    s = get_settings()
    try:
        drafts = _get(f"/league/{s.sleeper_league_id}/drafts")
        return drafts if isinstance(drafts, list) else []
    except Exception:
        return []


def get_transactions(week: int = 1) -> list[dict]:
    """Fetch recent trades and waiver moves."""
    s = get_settings()
    try:
        txns = _get(f"/league/{s.sleeper_league_id}/transactions/{week}")
        return txns if isinstance(txns, list) else []
    except Exception:
        return []


def format_roster_summary(league: LeagueInfo) -> str:
    """Return a text summary of the user's roster for passing to Gemini."""
    if not league.my_team:
        return "No team found."

    lines: list[str] = [
        f"Team: {league.my_team.name}  |  League: {league.name}  |  "
        f"Season: {league.season}  |  Scoring: {league.scoring_type}",
        f"Record: {league.my_team.record_wins}W-{league.my_team.record_losses}L  |  "
        f"Waiver priority: #{league.my_team.waiver_priority}  |  FAAB: ${league.faab_budget}",
        "",
        f"{'Name':<25} {'Pos':<5} {'Team':<5} {'Age':<4} {'Slot':<8} {'Injury'}",
        "-" * 65,
    ]
    for p in sorted(league.my_team.roster, key=lambda x: (x.position.value, x.name)):
        lines.append(
            f"{p.name:<25} {p.position.value:<5} {p.nfl_team:<5} "
            f"{str(p.age or '?'):<4} {p.acquisition_cost:<8} "
            f"{p.injury_status.value if p.injury_status.value != 'Healthy' else ''}"
        )
    return "\n".join(lines)


def format_all_teams_summary(league: LeagueInfo) -> str:
    """Return a compact summary of all other teams' rosters for trade analysis."""
    lines: list[str] = [
        f"OPPONENT ROSTERS — {league.name} {league.season}",
        "=" * 60,
    ]
    for team in sorted(league.teams, key=lambda t: (-t.record_wins, t.name)):
        if team.is_mine:
            continue
        record = f"{team.record_wins}W-{team.record_losses}L"
        waiver = f"  [Waiver: #{team.waiver_priority}]" if team.waiver_priority else ""
        lines.append(f"\nTeam: {team.name} ({record}){waiver}")
        by_pos: dict[str, list[str]] = {}
        for p in team.roster:
            pos = p.position.value
            if pos not in ("QB", "RB", "WR", "TE"):
                continue
            inj = (
                f" [{p.injury_status.value}]"
                if p.injury_status.value not in ("Healthy", "Unknown") else ""
            )
            by_pos.setdefault(pos, []).append(
                f"{p.name} ({p.age or '?'}, {p.nfl_team}){inj}"
            )
        for pos in ("QB", "RB", "WR", "TE"):
            players = by_pos.get(pos)
            if players:
                lines.append(f"  {pos:<4}: {' | '.join(players)}")
    return "\n".join(lines)
