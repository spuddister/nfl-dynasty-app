"""Free stats fetcher using the Pro Football Reference / nfl-data-py approach.
Falls back to ESPN's public stats endpoint when nfl-data-py isn't available.

This gives us historical stats + ADP + dynasty rankings from free sources.
"""
from __future__ import annotations
import json
import httpx
from ..db.database import save_reddit_cache, load_reddit_cache  # reuse cache infra

# FantasyPros dynasty rankings (public CSV endpoint)
_DYNASTY_RANKINGS_URL = "https://www.fantasypros.com/nfl/rankings/dynasty-overall.php"
# Pro Football Reference player search (JSON)
_PFR_SEARCH_URL = "https://www.pro-football-reference.com/search/search.fcgi"

# KTC dynasty rankings page (values are embedded as a JS variable)
_KTC_PAGE_URL = "https://keeptradecut.com/dynasty-rankings"


def get_ktc_values() -> dict[str, int]:
    """Fetch KeepTradeCut dynasty trade values. Returns {player_name: value}.
    KTC is the gold standard for dynasty trade value. Values are scraped from
    the playersArray JS variable embedded in the dynasty-rankings page.
    Uses superflexValues since this is a SuperFlex league.
    """
    import re

    cache_key = "ktc_values"
    cached = load_reddit_cache(cache_key, max_age_hours=24)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    try:
        resp = httpx.get(
            _KTC_PAGE_URL,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        if resp.status_code == 200:
            match = re.search(r"var\s+playersArray\s*=\s*(\[{.*?}\]);", resp.text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                values: dict[str, int] = {}
                for p in data:
                    name = p.get("playerName", "")
                    # Prefer superflexValues for this SuperFlex league
                    val = (
                        p.get("superflexValues", {}).get("value")
                        or p.get("oneQBValues", {}).get("value")
                        or 0
                    )
                    if name:
                        values[name] = int(val)
                if values:
                    save_reddit_cache(cache_key, json.dumps(values))
                    return values
    except Exception:
        pass

    return {}


def get_player_adp(player_name: str, format: str = "dynasty") -> str:
    """Get Average Draft Position for a player from FantasyPros."""
    cache_key = f"adp:{player_name.lower().replace(' ', '_')}:{format}"
    cached = load_reddit_cache(cache_key, max_age_hours=48)
    if cached:
        return cached

    url = f"https://api.fantasypros.com/v2/json/nfl/2025/consensus-rankings?type={format}&scoring=PPR&limit=300"
    try:
        resp = httpx.get(url, timeout=10, headers={"User-Agent": "fantasy-ai/0.1"})
        if resp.status_code == 200:
            data = resp.json()
            players = data.get("players", [])
            for p in players:
                if player_name.lower() in p.get("player_name", "").lower():
                    result = (
                        f"{p['player_name']} ({p.get('player_position_id', '')} - {p.get('player_team_id', '')}): "
                        f"Rank #{p.get('rank_ecr', '?')}, ADP {p.get('r2p_pts', '?')}"
                    )
                    save_reddit_cache(cache_key, result)
                    return result
    except Exception:
        pass

    return f"ADP data not available for {player_name}"


def get_injury_report() -> str:
    """Fetch current NFL injury report from ESPN's public API."""
    cache_key = "injury_report"
    cached = load_reddit_cache(cache_key, max_age_hours=2)
    if cached:
        return cached

    try:
        resp = httpx.get(
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
            timeout=10,
            headers={"User-Agent": "fantasy-ai/0.1"},
        )
        if resp.status_code == 200:
            data = resp.json()
            lines: list[str] = []
            for team in data.get("injuries", []):
                team_name = team.get("team", {}).get("abbreviation", "")
                for p in team.get("injuries", []):
                    name = p.get("athlete", {}).get("displayName", "Unknown")
                    status = p.get("status", "")
                    detail = p.get("shortComment", "") or p.get("longComment", "")
                    lines.append(f"{name} ({team_name}) — {status}: {detail}")
            result = "\n".join(lines[:100]) if lines else "No injury data available."
            save_reddit_cache(cache_key, result)
            return result
    except Exception:
        pass

    return "Injury report unavailable."


def get_player_news(player_name: str) -> str:
    """Fetch recent news for a player from ESPN's public API."""
    cache_key = f"news:{player_name.lower().replace(' ', '_')}"
    cached = load_reddit_cache(cache_key, max_age_hours=3)
    if cached:
        return cached

    try:
        resp = httpx.get(
            f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=10",
            timeout=10,
            headers={"User-Agent": "fantasy-ai/0.1"},
        )
        if resp.status_code == 200:
            data = resp.json()
            articles = data.get("articles", [])
            relevant = [
                a for a in articles
                if player_name.lower() in a.get("headline", "").lower()
                or player_name.lower() in a.get("description", "").lower()
            ]
            if relevant:
                lines = [f"• {a['headline']}: {a.get('description', '')}" for a in relevant[:5]]
                result = f"Recent news for {player_name}:\n" + "\n".join(lines)
            else:
                result = f"No recent news found for {player_name}."
            save_reddit_cache(cache_key, result)
            return result
    except Exception:
        pass

    return f"News unavailable for {player_name}."
