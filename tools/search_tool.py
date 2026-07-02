# tools/search_tool.py
from __future__ import annotations

import json as _json
import os as _os

from dotenv import load_dotenv
from pydantic_ai import RunContext
from tavily import TavilyClient

from core.deps import Deps
from core.logger import logger   # <-- was: logging.getLogger("search_tool")

load_dotenv()

_client = TavilyClient(api_key=_os.environ["TAVILY_API_KEY"])


async def tavily_search(ctx: RunContext[Deps], query: str, max_results: int = 5) -> str:
    """Search the web via Tavily.
    Never register this directly on an agent — agents wrap it via
    _make_search_tool() to add budget enforcement."""

    # raw = _client.search(query=query, max_results=max_results, time_range="year")
    raw = _client.search(query=query, max_results=max_results)

    logger.info("search_tool | query=%r results=%d", query, len(raw.get("results", [])))
    for r in raw.get("results", []):
        logger.info(
            "search_tool |   url=%s score=%.3f date=%s title=%r",
            r.get("url", ""), float(r.get("score", 0.0)),
            r.get("published_date"), r.get("title", ""),
        )

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