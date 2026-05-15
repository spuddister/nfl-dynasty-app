"""SQLite persistence layer — caches player analysis so we don't re-run
Gemini on every command. Analysis results expire after 24 hours."""
from __future__ import annotations
import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from ..models.player import Player
from ..config.settings import get_settings


def _get_conn() -> sqlite3.Connection:
    settings = get_settings()
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS player_cache (
                player_id    TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                position     TEXT NOT NULL,
                data_json    TEXT NOT NULL,
                analyzed_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reddit_cache (
                cache_key    TEXT PRIMARY KEY,
                content      TEXT NOT NULL,
                fetched_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_json   TEXT NOT NULL,
                verdict      TEXT NOT NULL,
                reasoning    TEXT NOT NULL,
                created_at   TEXT NOT NULL
            );
        """)


def save_player(player: Player) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO player_cache
               (player_id, name, position, data_json, analyzed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                player.player_id,
                player.name,
                player.position.value,
                player.model_dump_json(),
                datetime.utcnow().isoformat(),
            ),
        )


def load_player(player_id: str, max_age_hours: int = 24) -> Player | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM player_cache WHERE player_id = ?", (player_id,)
        ).fetchone()
    if row is None:
        return None
    analyzed_at = datetime.fromisoformat(row["analyzed_at"])
    if datetime.utcnow() - analyzed_at > timedelta(hours=max_age_hours):
        return None
    return Player.model_validate_json(row["data_json"])


def save_reddit_cache(key: str, content: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO reddit_cache (cache_key, content, fetched_at)
               VALUES (?, ?, ?)""",
            (key, content, datetime.utcnow().isoformat()),
        )


def load_reddit_cache(key: str, max_age_hours: int = 6) -> str | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reddit_cache WHERE cache_key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.utcnow() - fetched_at > timedelta(hours=max_age_hours):
        return None
    return row["content"]


def save_trade_verdict(offer_json: str, verdict: str, reasoning: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO trade_history (offer_json, verdict, reasoning, created_at)
               VALUES (?, ?, ?, ?)""",
            (offer_json, verdict, reasoning, datetime.utcnow().isoformat()),
        )
