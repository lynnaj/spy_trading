"""
Reddit sentiment tool for SPY.

Fetches recent posts from r/wallstreetbets, r/investing, r/SPY, r/stocks,
and r/options, extracts sentiment signals, and formats them for the LLM.

Requires in .env:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT   (e.g. "spy-trading-agent/1.0")
"""

import os
from datetime import datetime, timezone
from typing import Annotated

from langchain_core.tools import tool

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "spy-trading-agent/1.0")

SUBREDDITS = ["wallstreetbets", "investing", "SPY", "stocks", "options"]
SEARCH_TERMS = ["SPY", "S&P 500", "SPDR"]
MAX_POSTS_PER_TERM = 10
MAX_COMMENT_CHARS = 300
MAX_BODY_CHARS = 500


def _reddit_client():
    """Return an authenticated PRAW Reddit client, or None if credentials missing."""
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None
    try:
        import praw
        return praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
    except Exception:
        return None


def _age_label(created_utc: float) -> str:
    age_hours = (datetime.now(timezone.utc).timestamp() - created_utc) / 3600
    if age_hours < 24:
        return f"{age_hours:.0f}h ago"
    return f"{age_hours/24:.0f}d ago"


def _fetch_reddit_sentiment(trade_date: str) -> str:
    """
    Fetch SPY-related posts from Reddit and return a formatted sentiment report.
    Falls back to a clear error message if credentials are missing or the API fails.
    """
    reddit = _reddit_client()
    if reddit is None:
        return (
            "Reddit sentiment unavailable: REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET "
            "not set in .env. Skipping Reddit data."
        )

    subreddit_str = "+".join(SUBREDDITS)
    sub = reddit.subreddit(subreddit_str)

    seen_ids = set()
    posts = []

    try:
        for term in SEARCH_TERMS:
            results = sub.search(
                term,
                time_filter="week",
                sort="hot",
                limit=MAX_POSTS_PER_TERM,
            )
            for post in results:
                if post.id in seen_ids:
                    continue
                seen_ids.add(post.id)

                # Fetch top 3 comments
                post.comments.replace_more(limit=0)
                top_comments = []
                for comment in list(post.comments)[:3]:
                    if hasattr(comment, "body") and comment.body not in ("[deleted]", "[removed]"):
                        top_comments.append(
                            f"    ↳ [{comment.score:+d}] {comment.body[:MAX_COMMENT_CHARS].strip()}"
                        )

                posts.append({
                    "title":        post.title,
                    "subreddit":    post.subreddit.display_name,
                    "score":        post.score,
                    "upvote_ratio": post.upvote_ratio,
                    "num_comments": post.num_comments,
                    "flair":        post.link_flair_text or "",
                    "age":          _age_label(post.created_utc),
                    "body":         (post.selftext or "")[:MAX_BODY_CHARS].strip(),
                    "top_comments": top_comments,
                })

    except Exception as exc:
        return f"Reddit API error: {exc}"

    if not posts:
        return f"No Reddit posts found mentioning SPY in the past week (as of {trade_date})."

    # ── Aggregate sentiment signals ───────────────────────────────────────────
    avg_upvote_ratio = sum(p["upvote_ratio"] for p in posts) / len(posts)
    total_score      = sum(p["score"] for p in posts)
    high_score_posts = [p for p in posts if p["score"] > 500]
    bullish_posts    = [p for p in posts if p["upvote_ratio"] >= 0.75]
    bearish_posts    = [p for p in posts if p["upvote_ratio"] < 0.50]

    lines = [
        f"## Reddit SPY Sentiment — {trade_date}",
        f"Subreddits searched: {', '.join('r/' + s for s in SUBREDDITS)}",
        f"Posts analyzed: {len(posts)}  |  "
        f"Avg upvote ratio: {avg_upvote_ratio:.0%}  |  "
        f"Total net score: {total_score:,}",
        f"High-engagement posts (score > 500): {len(high_score_posts)}  |  "
        f"Bullish lean (ratio ≥ 75%): {len(bullish_posts)}  |  "
        f"Bearish lean (ratio < 50%): {len(bearish_posts)}",
        "",
        "### Top Posts",
    ]

    # Sort by score descending, show top 15
    for p in sorted(posts, key=lambda x: x["score"], reverse=True)[:15]:
        lines.append(
            f"\n**[r/{p['subreddit']}]** {p['title']}"
            + (f" [{p['flair']}]" if p["flair"] else "")
        )
        lines.append(
            f"Score: {p['score']:,}  |  Upvote ratio: {p['upvote_ratio']:.0%}  |  "
            f"Comments: {p['num_comments']:,}  |  {p['age']}"
        )
        if p["body"]:
            lines.append(p["body"])
        for c in p["top_comments"]:
            lines.append(c)

    return "\n".join(lines)


# ── LangChain tool ────────────────────────────────────────────────────────────

@tool
def get_reddit_sentiment(
    ticker: Annotated[str, "Ticker symbol (used for context; always fetches SPY subreddits)"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Fetch Reddit posts about SPY from r/wallstreetbets, r/investing, r/SPY,
    r/stocks, and r/options. Returns post titles, scores, upvote ratios,
    comment counts, and top comments as a sentiment report.
    """
    return _fetch_reddit_sentiment(curr_date)
