# schemas/search_result.py
from __future__ import annotations

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    url: str = Field(
        description=(
            "Full URL of the search result page. Always starts with https://. "
            "Use this URL with fetch_page when you need the full page content — "
            "the content snippet from Tavily is often truncated."
        )
    )
    title: str = Field(
        description=(
            "Page title as returned by Tavily. Use to quickly assess relevance "
            "before calling fetch_page. An empty string means Tavily did not "
            "return a title for this result."
        )
    )
    content: str = Field(
        description=(
            "Snippet of the page content returned by Tavily. This is a short "
            "extract — typically 200–500 characters. It is NOT the full page. "
            "If you need the complete text of this page, call fetch_page(url). "
            "Do not treat this snippet as the authoritative source for any fact."
        )
    )
    score: float = Field(
        description=(
            "Tavily's relevance score for this result relative to the query, "
            "between 0.0 and 1.0. Higher scores indicate stronger relevance. "
            "Results are returned in descending score order. "
            "Do not use this score as a quality or credibility signal — a highly "
            "relevant page may still contain outdated information."
        )
    )
    date: str | None = Field(
        default=None,
        description=(
            "Published or last-modified date of the page as returned by Tavily, "
            "in ISO format (YYYY-MM-DD) where available. "
            "None means Tavily did not return a date for this result — this is "
            "common for dynamically generated pages. "
            "Do not assume a None date means the content is recent — verify "
            "the publication date on the page itself if recency matters."
        )
    )


class SearchResponse(BaseModel):
    query: str = Field(
        description=(
            "The exact query string passed to tavily_search. "
            "Use this to confirm the search was executed as intended."
        )
    )
    results: list[SearchResult] = Field(
        description=(
            "Search results returned by Tavily, in descending relevance order. "
            "May be an empty list if Tavily returned no results for the query. "
            "All results have passed Tavily's time_range='year' filter — "
            "results older than 12 months are excluded before this list is returned. "
            "An empty list means either the query matched nothing, or all matches "
            "were filtered out by the date constraint."
        )
    )
    answer: str | None = Field(
        default=None,
        description=(
            "Tavily's optional AI-generated answer synthesised from the search results. "
            "Present only when Tavily's answer feature is enabled. "
            "Treat as a starting point only — verify any specific facts against "
            "the source URLs in results before including them in output."
        )
    )