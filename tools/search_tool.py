from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from tavily import TavilyClient

logger = logging.getLogger("search_tool")


@dataclass
class SearchResult:
    """A single result returned by Tavily."""
    url:     str
    title:   str
    content: str          # snippet or full content depending on search_depth
    score:   float        # Tavily relevance score — higher is better
    date:    str | None   # published date string, or None if unavailable


@dataclass
class SearchResponse:
    """Wrapper around the full Tavily response."""
    query:   str
    results: list[SearchResult]
    answer:  str | None   # Tavily's synthesised answer, if requested



class TavilySearchTool:
    """Tavily search wrapper. Enforces days=730 on every call.

    One instance is shared across all agents that use it.
    Created by ResearchHandler at startup and passed via Deps.

    Usage:
        response = await tool.search("Computer Science jobs UK 2024")
        for result in response.results:
            print(result.url, result.content)
    """

    def __init__(self, api_key: str | None = None) -> None:
        load_dotenv()
        key = api_key or os.getenv("TAVILY_API_KEY")
        self._client = TavilyClient(api_key=key)

        logger.info("search_tool | TavilySearchTool initialised")

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = False,
    ) -> SearchResponse:
        """Run a Tavily search. days=730 is always set — cannot be overridden.

        Args:
            query:          The search query string.
            max_results:    Number of results to return. Default 5, max 10.
            search_depth:   "basic" (fast, snippets) or "advanced" (slower, full content).
                            Use "advanced" only when the agent needs full page text,
                            not just snippets.
            include_answer: If True, Tavily synthesises an answer from results.
                            Costs additional credits. Default False.

        Returns:
            SearchResponse with results list and optional answer.

        Raises:
            RuntimeError: if the Tavily API returns an error.
        """
        try:
            raw = self._client.search(
                query=query,
                max_results=min(max_results, 10),
                search_depth=search_depth,
                include_answer=include_answer,
                days=730,          # ENFORCED — 2-year filter — never remove this
            )
        except Exception as exc:
            logger.error("search_tool | Tavily error for query %r: %s", query, exc)
            raise RuntimeError(f"Tavily search failed: {exc}") from exc

        results = [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 0.0)),
                date=r.get("published_date"),
            )
            for r in raw.get("results", [])
        ]

        logger.debug(
            "search_tool | query=%r results=%d", query, len(results)
        )

        return SearchResponse(
            query=query,
            results=results,
            answer=raw.get("answer"),
        )