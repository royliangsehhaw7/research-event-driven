# schemas/fetch_result.py
from __future__ import annotations

from pydantic import BaseModel, Field


class FetchResult(BaseModel):
    url: str = Field(
        description=(
            "The URL that was fetched. Matches the url argument passed to fetch_page. "
            "Use to confirm the correct page was retrieved."
        )
    )
    content: str = Field(
        description=(
            "Full text content of the fetched page, extracted and cleaned by the "
            "Fetch MCP server. Typically 5,000–50,000 characters for a standard page. "
            "Empty string when status is 'error'. "
            "Content is returned as plain text — HTML tags are stripped. "
            "Some pages may still contain navigation boilerplate or footer text "
            "mixed with the main content."
        )
    )
    status: str = Field(
        description=(
            "Fetch outcome. One of: "
            "'ok' — page was retrieved and content is populated; "
            "'error' — fetch failed, content is empty, error field explains why. "
            "Always check status before reading content."
        )
    )
    error: str | None = Field(
        default=None,
        description=(
            "Error message when status is 'error'. None when status is 'ok'. "
            "Common error causes: connection timeout (the page took too long), "
            "403 Forbidden (page blocks automated access — job boards, paywalled sites), "
            "404 Not Found (URL has changed or the page no longer exists), "
            "SSL error (certificate issue on the target server). "
            "If error is set, do not retry the same URL — move to the next "
            "search result or use an alternative source."
        )
    )