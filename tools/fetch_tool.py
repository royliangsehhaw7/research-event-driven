from __future__ import annotations

import json
from mcp.types import TextContent
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger
from mcps.fetch_client import fetch_client
from schemas.fetch_result import FetchResult

# Only trigger fallback if a page returns effectively nothing (e.g. empty JS shell)
MINIMUM_CONTENT_THRESHOLD = 500
MAX_CONTENT_LIMIT = 60000

_fetch_cache: dict[str, str] = {}


async def fetch_page(ctx: RunContext[Deps], url: str) -> str:
    """Fetch a specific URL. Falls back to a headless-rendered fetch when a
    static fetch returns virtually no content (common on modern JS-heavy SPA sites).
    
    Safe for all agents (background, rankings, careers) to retrieve full, untruncated 
    webpage text. Repeated calls to the same URL within a run are served from cache.

    Args:
        url: the full URL to fetch (must start with https://)

    Returns:
        JSON string containing url, content, status, error, and rendered flag.
    """
    if url in _fetch_cache:
        logger.info("fetch_tool | cache hit for %r — skipping re-fetch", url)
        return _fetch_cache[url]

    result, rendered = await _static_fetch(url), False
    is_pdf = url.lower().endswith(".pdf")

    # Only fall back to heavy headless rendering if static fetch returned near-empty content
    if (
        result.status == "ok"
        and not is_pdf
        and len(result.content) < MINIMUM_CONTENT_THRESHOLD
    ):
        logger.warning(
            "fetch_tool | %r returned thin content (%d chars) — falling back to headless render",
            url, len(result.content),
        )
        rendered_result = await _rendered_fetch(url)
        if rendered_result.status == "ok" and len(rendered_result.content) > len(result.content):
            result = rendered_result
            rendered = True

    # Keep a reasonable cap just so massive documents don't instantly crash token contexts
    content_out = result.content
    if len(content_out) > MAX_CONTENT_LIMIT:
        logger.info("fetch_tool | capping massive page stream to first %d chars", MAX_CONTENT_LIMIT)
        content_out = content_out[:MAX_CONTENT_LIMIT]

    payload = json.dumps({
        "url": result.url,
        "content": content_out,
        "status": result.status,
        "error": result.error,
        "rendered": rendered,
    })

    if result.status == "ok":
        _fetch_cache[url] = payload

    return payload


async def _static_fetch(url: str) -> FetchResult:
    try:
        async with fetch_client:
            raw = await fetch_client.call_tool("fetch", {"url": url, "max_length": MAX_CONTENT_LIMIT})
        content = "".join(b.text for b in raw.content if isinstance(b, TextContent))
        logger.info("fetch_tool | static fetched %r — %d chars", url, len(content))
        return FetchResult(url=url, content=content, status="ok", error=None)
    except Exception as exc:
        logger.error("fetch_tool | static fetch failed for %r: %s", url, exc)
        return FetchResult(url=url, content="", status="error", error=str(exc))


async def _rendered_fetch(url: str) -> FetchResult:
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                page = await browser.new_page()
                await page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                })
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(1000)
                text = await page.inner_text("body")
            finally:
                await browser.close()

        content = text[:MAX_CONTENT_LIMIT]
        logger.info("fetch_tool | rendered fetched %r — %d chars", url, len(content))
        return FetchResult(url=url, content=content, status="ok", error=None)
    except Exception as exc:
        logger.error("fetch_tool | rendered fetch failed for %r: %s", url, exc)
        return FetchResult(url=url, content="", status="error", error=str(exc))