from dataclasses import dataclass

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