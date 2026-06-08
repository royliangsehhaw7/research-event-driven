# tools/fetch_tool.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pydantic_ai import RunContext

from core.deps import Deps
from mcps.fetch_client import fetch_client

logger = logging.getLogger("fetch_tool")


@dataclass
class FetchResult:
    url:     str
    content: str         # page content as markdown-formatted text
    status:  str         # "ok" | "error"
    error:   str | None  # error message if status == "error", else None


async def fetch_page(ctx: RunContext[Deps], url: str) -> str:
    """Fetch a specific URL via the Fetch MCP server.

    Use for university catalog pages, rankings pages, or any URL found
    in search results when you need the full page content.

    Does not count against tool_budget — targeted retrieval, not a search.

    Args:
        url: the full URL to fetch (must start with https://)

    Returns:
        JSON string containing url, content, status, and optional error.
        Never raises — returns status "error" on failure so the agent
        can note the failure and continue.
    """
    try:
        raw = await fetch_client.call_tool("fetch", {
            "url": url,
            "max_length": 50000,   # characters — enough for a full catalog page
        })
        result = FetchResult(url=url, content=str(raw), status="ok", error=None)
        logger.debug("fetch_tool | fetched %r — %d chars", url, len(result.content))
    except Exception as exc:
        logger.error("fetch_tool | fetch failed for %r: %s", url, exc)
        result = FetchResult(url=url, content="", status="error", error=str(exc))

    return json.dumps({
        "url": result.url,
        "content": result.content,
        "status": result.status,
        "error": result.error,
    })