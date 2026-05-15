"""Reddit tool — searches r/dynastyff, r/fantasyfootball, etc. for player
news, sentiment, and injury updates. Results are cached for 6 hours."""
from __future__ import annotations
import re
from typing import TYPE_CHECKING

from ..config.settings import get_settings
from ..db.database import save_reddit_cache, load_reddit_cache

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False


def _make_reddit() -> "praw.Reddit":
    s = get_settings()
    if not PRAW_AVAILABLE:
        raise RuntimeError("praw not installed — run: uv add praw")
    if not s.reddit_client_id:
        raise RuntimeError("REDDIT_CLIENT_ID not set in .env")
    return praw.Reddit(
        client_id=s.reddit_client_id,
        client_secret=s.reddit_client_secret,
        user_agent=s.reddit_user_agent,
        read_only=True,
    )


def search_reddit_for_player(player_name: str, max_posts: int | None = None) -> str:
    """Search Reddit for recent discussion about a player.

    Returns a text summary of the top posts/comments, suitable for passing
    to Gemini for sentiment analysis.
    """
    settings = get_settings()
    limit = max_posts or settings.reddit_post_limit
    cache_key = f"player:{player_name.lower().replace(' ', '_')}:{limit}"

    cached = load_reddit_cache(cache_key)
    if cached:
        return cached

    if not PRAW_AVAILABLE or not settings.reddit_client_id:
        return f"[Reddit unavailable — configure REDDIT_CLIENT_ID in .env to enable live search for {player_name}]"

    reddit = _make_reddit()
    subs = "+".join(settings.reddit_sub_list)
    results: list[str] = []

    try:
        for submission in reddit.subreddit(subs).search(
            player_name, sort="new", time_filter="month", limit=limit
        ):
            title = submission.title.strip()
            score = submission.score
            url = submission.url
            # Grab top 3 comments
            submission.comments.replace_more(limit=0)
            top_comments = []
            for c in list(submission.comments)[:3]:
                if hasattr(c, "body") and len(c.body) < 500:
                    top_comments.append(f"    → {c.body.strip()}")
            comment_block = "\n".join(top_comments)
            results.append(
                f"[{score}↑] {title}\n{url}\n{comment_block}"
            )
    except Exception as e:
        return f"[Reddit search error for {player_name}: {e}]"

    if not results:
        summary = f"No recent Reddit discussion found for {player_name}."
    else:
        summary = f"Reddit discussion for {player_name} (last 30 days):\n\n" + "\n\n---\n\n".join(results)

    save_reddit_cache(cache_key, summary)
    return summary


def get_weekly_news_digest(position_filter: str | None = None) -> str:
    """Fetch the weekly discussion/news thread from r/fantasyfootball."""
    cache_key = f"weekly_digest:{position_filter or 'all'}"
    cached = load_reddit_cache(cache_key, max_age_hours=3)
    if cached:
        return cached

    settings = get_settings()
    if not PRAW_AVAILABLE or not settings.reddit_client_id:
        return "[Reddit unavailable — configure credentials to fetch weekly digest]"

    reddit = _make_reddit()
    results: list[str] = []

    try:
        sub = reddit.subreddit("fantasyfootball")
        for post in sub.search("weekly discussion OR injury OR waiver wire", sort="new", time_filter="week", limit=5):
            results.append(f"• {post.title} ({post.score}↑)\n  {post.url}")
    except Exception as e:
        return f"[Reddit weekly digest error: {e}]"

    summary = "Weekly Reddit digest:\n\n" + "\n\n".join(results) if results else "No weekly threads found."
    save_reddit_cache(cache_key, summary)
    return summary
