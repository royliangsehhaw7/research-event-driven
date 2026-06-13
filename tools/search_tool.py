# tools/search_tool.py
from __future__ import annotations

import os as _os

from dotenv import load_dotenv
from pydantic_ai import RunContext
from tavily import TavilyClient

from core.deps import Deps
from core.logger import logger
from schemas.search_result import SearchResponse, SearchResult  

load_dotenv()

_client = TavilyClient(api_key=_os.environ["TAVILY_API_KEY"])


async def tavily_search(ctx: RunContext[Deps], query: str, max_results: int = 5) -> SearchResponse:
    """
    Search the web via Tavily. time_range='year' always enforced.
    """

    raw = _client.search(query=query, max_results=max_results, time_range="year")

    logger.warning("search_tool | query=%r results=%d", query, len(raw.get("results", [])))
    
    # Map the raw API results into your strict dataclass models
    results_list = [
        SearchResult(
            url=r.get("url", ""),
            title=r.get("title", ""),
            content=r.get("content", ""),
            score=float(r.get("score", 0.0)),
            date=r.get("published_date"),
        )
        # Safely handle an empty results list if Tavily returns nothing
        for r in raw.get("results", []) or [] 
    ]
    
    # Return the structural object directly
    return SearchResponse(
        query=query,
        results=results_list,
        answer=raw.get("answer"),
    )