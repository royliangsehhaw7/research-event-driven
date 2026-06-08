# tools/ddg_tool.py
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("ddg_tool")


@dataclass
class DDGResult:
    url:     str
    title:   str
    snippet: str
    date:    str | None   # date string from DDG, or None


@dataclass
class DDGResponse:
    query:   str
    results: list[DDGResult]


class DuckDuckGoTool:
    """DuckDuckGo search fallback. No API key. No quota.

    Used only by NewsAgent when Tavily returns fewer than 3 news results.
    Do not use as a primary search tool — Tavily has better structured
    results and the days= filter. DDG has neither.

    Usage:
        tool = DuckDuckGoTool()
        response = await tool.search("University of Manchester CS department news 2024")
        for r in response.results:
            print(r.url, r.snippet)
    """

    _RETRY_DELAY_SECONDS = 3.0   # wait before retrying on rate limit

    async def search(
        self,
        query: str,
        max_results: int = 5,
        region: str = "wt-wt",
    ) -> DDGResponse:
        """Run a DuckDuckGo text search.

        Args:
            query:       Search query.
            max_results: Max results to return. Default 5.
            region:      DDG region code. Default "wt-wt" (no region filter).
                         Use "uk-en" for UK-specific results.

        Returns:
            DDGResponse with results list.
        """
        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(
                None,
                self._search_sync,
                query, max_results, region,
            )
            logger.debug("ddg_tool | query=%r results=%d", query, len(results))
            return DDGResponse(query=query, results=results)
        except Exception as exc:
            logger.error("ddg_tool | search failed for %r: %s", query, exc)
            return DDGResponse(query=query, results=[])

    def _search_sync(
        self,
        query: str,
        max_results: int,
        region: str,
    ) -> list[DDGResult]:
        """Synchronous DDG search with one retry on rate limit."""
        # new
        from ddgs import DDGS
        from ddgs.exceptions import RatelimitException

        for attempt in range(2):
            try:
                with DDGS() as ddgs:
                    raw = list(ddgs.text(
                        query,
                        max_results=max_results,
                        region=region,
                    ))
                return [
                    DDGResult(
                        url=r.get("href", ""),
                        title=r.get("title", ""),
                        snippet=r.get("body", ""),
                        date=r.get("published"),
                    )
                    for r in raw
                ]
            except RatelimitException:
                if attempt == 0:
                    logger.warning(
                        "ddg_tool | rate limited — retrying after %.1fs",
                        self._RETRY_DELAY_SECONDS,
                    )
                    time.sleep(self._RETRY_DELAY_SECONDS)
                else:
                    logger.error("ddg_tool | rate limited twice — giving up")
                    return []