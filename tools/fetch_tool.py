# tools/fetch_tool.py
from __future__ import annotations

import json

from mcp.types import TextContent
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger
from mcps.fetch_client import fetch_client
from schemas.fetch_result import FetchResult


async def fetch_page(ctx: RunContext[Deps], url: str) -> str:
    """Fetch a specific URL via the Fetch MCP server.

    Use for university catalog pages, salary survey pages, or any URL
    found in search results when you need the full page content.

    Do NOT use for job board URLs (Indeed, Reed, LinkedIn) — these return
    403/500. Use adzuna_jobs or mcf_jobs for job posting data instead.

    Does not count against tool_budget — targeted retrieval, not a search.

    Args:
        url: the full URL to fetch (must start with https://)

    Returns:
        JSON string containing url, content, status, and optional error.
        Never raises — returns status "error" on failure.
    """
    try:
        async with fetch_client:
            raw = await fetch_client.call_tool("fetch", {
                "url": url,
                "max_length": 50000,
            })

        content = "".join(
            block.text for block in raw.content if isinstance(block, TextContent)
        )
        
        result = FetchResult(url=url, content=content, status="ok", error=None)
        logger.info("fetch_tool | fetched %r — %d chars", url, len(result.content))

    except Exception as exc:
        logger.error("fetch_tool | failed for %r: %s", url, exc)
        result = FetchResult(url=url, content="", status="error", error=str(exc))

    return json.dumps({
        "url": result.url,
        "content": result.content,
        "status": result.status,
        "error": result.error,
    })