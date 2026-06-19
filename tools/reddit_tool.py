# tools/reddit_tool.py
from __future__ import annotations

import json
import re

import httpx
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger

# Reddit's public JSON API requires a non-generic User-Agent.
# Format per Reddit API terms: "<AppName>/version (by /u/<username> or contact)"
# This UA identifies the bot clearly and is accepted for read-only public access.
_UA = "UniversityResearchBot/1.0 (university research pipeline; read-only public data)"

# Matches a standard Reddit post URL and extracts subreddit + post_id.
# Handles both www.reddit.com and old.reddit.com.
_POST_URL_RE = re.compile(
    r"https?://(?:www\.|old\.)?reddit\.com"
    r"/r/(?P<sub>[^/]+)/comments/(?P<post_id>[^/?#]+)"
)


def _to_json_url(post_url: str) -> str | None:
    """Convert a Reddit post URL to its public JSON API URL.

    Returns None if the URL does not match the expected Reddit post pattern.

    Examples:
        https://www.reddit.com/r/edinburghuniversity/comments/abc123/title/
        → https://www.reddit.com/r/edinburghuniversity/comments/abc123/.json

        https://old.reddit.com/r/edinburghuniversity/comments/abc123/
        → https://www.reddit.com/r/edinburghuniversity/comments/abc123/.json
    """
    m = _POST_URL_RE.match(post_url)
    if not m:
        return None
    sub     = m.group("sub")
    post_id = m.group("post_id")
    return f"https://www.reddit.com/r/{sub}/comments/{post_id}/.json"


async def reddit_fetch_thread(
    ctx: RunContext[Deps],
    post_url: str,
    max_comments: int = 20,
) -> str:
    """Fetch the full comment thread for a Reddit post.

    Use this tool for Reddit URLs found by tavily_search. Do NOT use
    fetch_page for Reddit URLs — Reddit blocks the MCP server User-Agent.

    Calls Reddit's public JSON API via httpx with a descriptive User-Agent.
    No authentication required. Works for any public subreddit.

    Args:
        post_url:     full Reddit post URL (www or old.reddit.com)
        max_comments: maximum top-level comments to return (default 20)

    Returns:
        JSON string containing post title, selftext, and top-level comments.
        Comments with score < 1 are excluded. Never raises — returns error
        field on failure.
    """
    json_url = _to_json_url(post_url)
    if not json_url:
        logger.warning("reddit_tool | unrecognised URL pattern: %r", post_url)
        return json.dumps({
            "error": f"URL does not match Reddit post pattern: {post_url!r}",
            "post_url": post_url,
            "comments": [],
        })

    try:
        async with httpx.AsyncClient(
        timeout=15.0,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,        
        ) as client:
        
            resp = await client.get(json_url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("reddit_tool | request failed for %r: %s", json_url, exc)
        return json.dumps({
            "error": str(exc),
            "post_url": post_url,
            "comments": [],
        })

    # Reddit JSON structure: [post_listing, comment_listing]
    # data[0].data.children[0].data  → post metadata
    # data[1].data.children          → top-level comment nodes
    try:
        post_data = data[0]["data"]["children"][0]["data"]
        title    = post_data.get("title", "")
        selftext = post_data.get("selftext", "")

        comment_nodes = data[1]["data"]["children"]
        comments = []
        for node in comment_nodes:
            if node.get("kind") != "t1":
                continue   # skip "more" nodes and non-comment kinds
            cd = node["data"]
            score = cd.get("score", 0)
            if score < 1:
                continue   # exclude downvoted / collapsed comments
            comments.append({
                "author": cd.get("author", "[deleted]"),
                "score":  score,
                "body":   cd.get("body", ""),
                "created_utc": cd.get("created_utc"),
            })
            if len(comments) >= max_comments:
                break

    except (KeyError, IndexError, TypeError) as exc:
        logger.error("reddit_tool | parse error for %r: %s", json_url, exc)
        return json.dumps({
            "error": f"Failed to parse Reddit JSON response: {exc}",
            "post_url": post_url,
            "comments": [],
        })

    logger.info(
        "reddit_tool | %r — title=%r comments=%d",
        json_url, title[:60], len(comments),
    )

    return json.dumps({
        "post_url":  post_url,
        "json_url":  json_url,
        "title":     title,
        "selftext":  selftext,
        "comments":  comments,
        "error":     None,
    })
