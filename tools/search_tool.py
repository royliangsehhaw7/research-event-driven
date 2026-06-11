# tools/search_tool.py
from __future__ import annotations

import json as _json
import logging
import os as _os

from dotenv import load_dotenv
from pydantic_ai import RunContext
from tavily import TavilyClient

from core.deps import Deps

load_dotenv()

logger = logging.getLogger("search_tool")

_client = TavilyClient(api_key=_os.environ["TAVILY_API_KEY"])


async def tavily_search(ctx: RunContext[Deps], query: str, max_results: int = 5) -> str:
    """Search the web via Tavily. days=730 always enforced.
    Never register this directly on an agent — agents wrap it via
    _make_search_tool() to add budget enforcement."""
    raw = _client.search(query=query, max_results=max_results, days=730)
    logger.debug("search_tool | query=%r results=%d", query, len(raw.get("results", [])))
    return _json.dumps({
        "query": query,
        "results": [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "score": float(r.get("score", 0.0)),
                "date": r.get("published_date"),
            }
            for r in raw.get("results", [])
        ],
    })