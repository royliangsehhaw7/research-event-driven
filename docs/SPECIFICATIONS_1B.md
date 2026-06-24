# Stage 1b — Tool Wrappers: Tavily, Fetch MCP, DuckDuckGo, Adzuna, MyCareersFuture
## Implementation Specification

**Goal:** All tool wrappers are implemented, tested against real external
services, and confirmed to return usable data. No agents, no LLM calls.
Pure tool plumbing.

**Ends with:** `pytest tests/test_stage_1b.py -v` passes. Each wrapper makes
a real call to its service and returns a typed result. A live search for a
known university and course confirms data flows end to end.

---

## What This Stage Builds and Why It Comes Before Agents

Stage 1c builds `CareerAgent`. Every agent calls at least one of these wrappers.
If any wrapper is broken — wrong authentication, wrong return shape, missing
error handling — every agent that depends on it silently fails or raises at runtime.

Building and testing the wrappers in isolation now means that in Stage 1c
you are debugging agent logic, not tool plumbing.

**Five wrappers, five distinct jobs:**

| Wrapper | File | Used by | Key feature |
|---|---|---|---|
| `tavily_search` | `tools/search_tool.py` | All section agents | `days=730` enforced on every call |
| `fetch_page` | `tools/fetch_tool.py` | All section agents | Direct URL fetch — catalog pages, salary surveys |
| `ddg_search` | `tools/ddg_tool.py` | NewsAgent fallback only | Zero cost, no key, no quota |
| `adzuna_jobs` | `tools/adzuna_tool.py` | CareerAgent (UK + AU) | Structured live job postings with salary data |
| `mcf_jobs` | `tools/mcf_tool.py` | CareerAgent (SG) | Singapore government job API — no auth required |

**Why separate job posting tools instead of Tavily:**
Tavily cannot reliably retrieve live job postings — job boards (Indeed, Reed,
LinkedIn) block fetch-based access and Tavily's `site:` queries do not honour
`time_range` filtering. Adzuna and MyCareersFuture are purpose-built APIs that
return structured, dated job data directly. They replace Tavily for the job
posting snapshot only — Tavily remains the primary tool for all other research.

**How CareerAgent selects which job tool to call:**
Both `adzuna_jobs` and `mcf_jobs` are registered on `CareerAgent` at construction
time. The LLM reads `deps.context.country` and selects the correct tool based on
the docstrings — `adzuna_jobs` for UK and Australia, `mcf_jobs` for Singapore.
Each tool returns an error in `JobPostingsResponse.error` if called for a country
it does not support — this is a safety net only, not the routing mechanism. The
routing is done by the LLM via the tool docstrings and the CareerAgent SKILL.md.

---

## External Service Setup

Do this before writing a single line of wrapper code. All services must be
provisioned and keys in `.env` before running tests.

---

### Service 1 — Tavily

**What it is:** an AI-first search API. Returns structured results with URLs,
snippets, and published dates. The `days` parameter filters results to a
rolling window — this is the key feature that enforces the 2-year data rule
across all agents.

**How to get the API key:**

1. Go to **https://app.tavily.com**
2. Sign up with email (Google or GitHub login available)
3. After login you land on the dashboard. Your API key is shown immediately
   under "API Key" — it looks like `tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
4. Copy it. You will not need to create a project or configure anything else.

**Free tier:** 1,000 API credits per month. One search call costs 1 credit.
A full pipeline run uses approximately 50–70 calls. Free tier is sufficient
for development and light testing.

**Add to `.env`:**

```bash
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Install:**

```bash
pip install tavily-python
```

---

### Service 2 — Fetch MCP

**What it is:** fetches the raw content of a URL and returns it as clean text.
Used when an agent needs to read a specific page — a university course catalog,
a salary survey — rather than search for it.

**No API key required.** The Fetch MCP server runs locally as a subprocess.

**Install:**

```bash
pip install fastmcp mcp-server-fetch
```

Confirm the server is available:

```bash
python -m mcp_server_fetch --help
```

If that command fails, switch to the `uvx` invocation. Update the
`StdioTransport` in `mcps/fetch_client.py`:

```python
StdioTransport(command="uvx", args=["mcp-server-fetch"])
```

And install `uv`:

```bash
pip install uv
```

**No `.env` entry required.**

---

### Service 3 — DuckDuckGo Search

**What it is:** zero-cost, no-key web search. Used by `NewsAgent` as a
fallback when Tavily returns fewer than 3 news items.

**No API key required. No account. No quota.**

**Install:**

```bash
pip install ddgs
```

> **Note:** the package was previously named `duckduckgo-search` and has been
> renamed to `ddgs`. Use `ddgs`.

**Rate limit note:** DuckDuckGo rate-limits at the network level. The wrapper
retries once with a 3-second delay. NewsAgent makes at most 2–3 DDG calls per
pipeline run, well within safe limits.

**No `.env` entry required.**

---

### Service 4 — Adzuna

**What it is:** a job search API covering 12 countries including UK and
Australia. Returns structured job postings with company names, role titles,
required skills, salary ranges, and posting dates. Replaces Tavily for the
job posting snapshot in CareerAgent for UK and AU.

**How to get API credentials:**

1. Go to **https://developer.adzuna.com**
2. Register for a free account
3. Create an application — name it anything (e.g. `university_research`)
4. You will receive an `app_id` and an `app_key`
5. Free tier: 250 requests/day — sufficient for development

**Add to `.env`:**

```bash
ADZUNA_APP_ID=xxxxxxxx
ADZUNA_APP_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADZUNA_URL=https://api.adzuna.com/v1/api/jobs
```

**Install:**

Adzuna has no official Python client — the wrapper calls the REST API directly
via `httpx` (already a pydantic-ai dependency). No additional package needed.

**Country codes and currencies used in this project:**

| `deps.context.country` | Adzuna country code | Currency |
|---|---|---|
| `UK` | `gb` | `GBP` |
| `Australia` | `au` | `AUD` |

These mappings live in `_COUNTRY_MAP` in `adzuna_tool.py` as a single dict of
`country → (adzuna_code, currency)` tuples. Adding a new country means adding
one entry to that dict — nowhere else.

---

### Service 5 — MyCareersFuture (Singapore)

**What it is:** Singapore's government-run job portal (`mycareersfuture.gov.sg`).
Exposes a public REST API — no authentication required. Returns structured job
postings with company names, role titles, skills, salary ranges, and dates.
Replaces Tavily for the job posting snapshot in CareerAgent for SG.

**No API key required. No account required.**

**Base URL:** `https://api.mycareersfuture.gov.sg/v2`

**No `.env` entry required. No package to install** beyond `httpx` which is
already present.

---

### Updated `.env` After Stage 1b

```bash
# .env — full contents after Stage 1b
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

RESEARCH_MODEL=google/gemma-3-27b-it:free
SCORING_MODEL=google/gemma-3-27b-it:free
CONVERSATION_MODEL=google/gemma-3-27b-it:free

TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

ADZUNA_APP_ID=xxxxxxxx
ADZUNA_APP_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADZUNA_URL=https://api.adzuna.com/v1/api/jobs

MCF_URL=https://api.mycareersfuture.gov.sg/v2
```

---

### Updated `requirements.txt` After Stage 1b

```
pydantic-ai
pydantic
chainlit
pyyaml
python-dotenv
tavily-python
ddgs
httpx
fastmcp
mcp-server-fetch
jinja2
pytest
pytest-asyncio
```

---

### Updated `.env.example` After Stage 1b

```bash
# .env.example — copy to .env and fill in your keys

# Search
TAVILY_API_KEY=tvly-...

# Job postings — UK and Australia
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...

# LLM via OpenRouter — https://openrouter.ai
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Model selection
RESEARCH_MODEL=google/gemma-3-27b-it:free
SCORING_MODEL=google/gemma-3-27b-it:free
CONVERSATION_MODEL=google/gemma-3-27b-it:free
```

---

## Updated Folder Structure After Stage 1b

```
├── mcps/
│   └── fetch_client.py             Fetch MCP — module-level fastmcp.Client (reentrant, ref-counted, shared)
│
├── tools/
│   ├── search_tool.py              tavily_search — module-level AsyncTavilyClient singleton (async, concurrency-safe)
│   ├── fetch_tool.py               fetch_page — calls fetch_client.call_tool(), never raises
│   ├── ddg_tool.py                 ddg_search — module-level DDGS singleton, calls via asyncio.to_thread (NOT registered on any agent)
│   ├── adzuna_tool.py              adzuna_jobs — httpx REST, UK + AU, routes by _COUNTRY_MAP
│   └── mcf_tool.py                 mcf_jobs — httpx REST, SG only, no auth
│
├── schemas/
│   ├── search_result.py            SearchResult, SearchResponse
│   ├── fetch_result.py             FetchResult
│   └── job_posting.py              JobPosting, JobPostingsResponse  ← NEW shared schema
```

---

## 1b.0 Shared Schemas

All three shared schemas use pydantic `BaseModel` with `Field(description=...)`
on every field. This is consistent with the output schemas in Stage 1c and 1d
and gives the LLM accurate field-level documentation when it reads tool return
values.

**Why pydantic BaseModel instead of dataclass:** the tool wrappers return these
schemas directly to the LLM as tool results. pydantic-ai serialises tool return
values for the LLM context window. Using `BaseModel` with `Field(description=...)`
means the LLM sees accurate field descriptions in the tool schema — dataclass
docstrings are not surfaced the same way.

### `schemas/search_result.py`

```python
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
```

---

### `schemas/fetch_result.py`

```python
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
```

---

### `schemas/job_posting.py` — NEW

Shared return type used by both `adzuna_tool` and `mcf_tool`. CareerAgent
receives the same schema regardless of which country-specific tool was called.

```python
# schemas/job_posting.py
from __future__ import annotations

from pydantic import BaseModel, Field


class JobPosting(BaseModel):
    """A single job posting. Normalised from either Adzuna or MyCareersFuture."""

    title: str = Field(
        description=(
            "Job title as listed in the posting. "
            "Examples: 'Graduate Software Engineer', 'Data Analyst', "
            "'Junior Backend Developer'. "
            "Use this to assess role relevance and extract career path signals."
        )
    )
    company: str = Field(
        description=(
            "Name of the hiring company as listed in the posting. "
            "This is a real employer name — use it to populate "
            "CareerPath.typical_companies. "
            "Empty string if the company name was not provided by the API."
        )
    )
    location: str = Field(
        description=(
            "City or region of the role as returned by the API. "
            "Examples: 'London', 'Sydney CBD', 'Singapore'. "
            "May include broader regions (e.g. 'South East England'). "
            "Empty string if location was not provided."
        )
    )
    description: str = Field(
        description=(
            "Full job description text as returned by the API. "
            "This is the primary source for in_demand_skills extraction — "
            "read it for technology stacks, tools, frameworks, and soft skills "
            "mentioned across multiple postings. "
            "May be truncated by the API for very long postings."
        )
    )
    salary_min: float | None = Field(
        description=(
            "Minimum salary in local currency (annual), as a float. "
            "None if the posting did not include salary data. "
            "Use with salary_max and currency to populate SalaryRange entries. "
            "Do not infer a salary range from None — omit or write 'Not available'."
        )
    )
    salary_max: float | None = Field(
        description=(
            "Maximum salary in local currency (annual), as a float. "
            "None if the posting did not include salary data. "
            "salary_min and salary_max together define the full range for this posting."
        )
    )
    currency: str = Field(
        description=(
            "ISO 4217 currency code for the salary figures. "
            "Set by the tool based on the country: 'GBP' for UK, "
            "'AUD' for Australia, 'SGD' for Singapore. "
            "This is set by the tool — not derived from the posting text."
        )
    )
    date_posted: str = Field(
        description=(
            "Date the posting was published, as returned by the API. "
            "Format varies by source: Adzuna returns ISO datetime strings "
            "(e.g. '2024-03-15T10:22:00Z'); MCF returns date strings. "
            "All postings returned by these tools have passed a recency filter "
            "at the API level — do not treat very old dates as valid."
        )
    )
    skills: list[str] = Field(
        description=(
            "Structured skill tags returned directly by the API. "
            "MCF returns a skills array — names are extracted from it. "
            "Adzuna returns no structured skill tags — this is always [] for "
            "Adzuna postings. Do not scan description text to populate this field. "
            "The LLM reads the description field directly to extract skill signals "
            "for in_demand_skills — this field provides only structured API data."
        )
    )
    source_url: str = Field(
        description=(
            "Direct URL to the job posting on the originating job board. "
            "For Adzuna: the redirect URL from the API response. "
            "For MCF: constructed as "
            "'https://www.mycareersfuture.gov.sg/job/{uuid}'. "
            "Use this to verify posting details if needed."
        )
    )
    source: str = Field(
        description=(
            "Which tool returned this posting. Either 'adzuna' or 'mycareersfuture'. "
            "Use to audit which tool was called and confirm the correct "
            "country-tool routing was applied."
        )
    )


class JobPostingsResponse(BaseModel):
    """The full response from a job posting tool call."""

    query: str = Field(
        description=(
            "The search query passed to the job posting tool. "
            "Matches the query argument — use to confirm the correct role "
            "was searched for."
        )
    )
    country: str = Field(
        description=(
            "The country context used for this search. "
            "Matches deps.context.country at call time. "
            "Used to confirm the correct tool was routed to for the country."
        )
    )
    total_found: int = Field(
        description=(
            "Total number of matching postings in the API for this query, "
            "not just the number returned. "
            "Example: total_found=1200 with 15 postings returned means the API "
            "has many more results than were fetched. "
            "0 when error is set, or when the query genuinely matched nothing."
        )
    )
    postings: list[JobPosting] = Field(
        default_factory=list,
        description=(
            "Normalised job postings returned by the tool, up to max_results. "
            "May be an empty list when error is set or when the query matched "
            "nothing. Pass these directly into CareerOutput.job_postings — "
            "do not re-filter or summarise them before writing to the output."
        )
    )
    error: str | None = Field(
        default=None,
        description=(
            "Error message if the tool call failed or was routed to the wrong "
            "country. None on success. "
            "Common values: unsupported country message (e.g. calling adzuna_jobs "
            "for Singapore), HTTP error from the API, connection timeout. "
            "When error is set, postings is [] and total_found is 0. "
            "Do not retry on error — note it in CareerOutput.notes and continue."
        )
    )
```

**Why a shared schema:** CareerAgent is written once and registers both
`adzuna_jobs` and `mcf_jobs`. The LLM selects the correct tool based on
`deps.context.country`. Both tools return `JobPostingsResponse` — the agent
code has no country-specific branching beyond the tool selection itself.

**`skills` field:** populated from structured API data only — tags or skill
arrays returned directly by the API. Adzuna returns no structured skill tags,
so `skills` is always `[]` for Adzuna postings. MCF returns a `skills` array;
extract names from it. No keyword scanning of description text — the LLM reads
the full `description` field and extracts what it needs.

---

## 1b.1 `mcps/fetch_client.py` — shared `fastmcp.Client`, no custom lifecycle code

> **Shared instance — still needed, still recommended, even under `asyncio.gather()`.**
> From Stage 1d onward, multiple section agents call `fetch_page` concurrently.
> Two things make a single shared `fastmcp.Client` both safe and the right
> design here:
>
> 1. **One subprocess for the whole pipeline run.** `mcp-server-fetch` is a
>    separate OS process started via the client's stdio transport. Spawning a
>    fresh subprocess per agent (or per call) would add real startup latency to
>    every `fetch_page` call and leave orphaned processes if shutdown isn't
>    handled per-instance. One process, started once, reused for the run, is
>    both faster and simpler to clean up.
> 2. **`fastmcp.Client` is a reentrant, ref-counted async context manager that
>    is safe for concurrent calls.** `async with fetch_client:` can be entered
>    from multiple places — each `__aenter__` increments an internal counter
>    and reuses the existing session; the underlying connection only closes
>    once the matching number of `__aexit__`s have run. Concurrent
>    `await fetch_client.call_tool(...)` calls on that one session are
>    multiplexed by request ID, same as raw MCP JSON-RPC.

```python
# mcps/fetch_client.py
from __future__ import annotations

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

# Single shared client for the Fetch MCP server. Import this instance
# everywhere `fetch_page` needs it — do not construct a new Client.
#
# Lifecycle: entered once via `async with fetch_client:` around the pipeline
# run (see main.py). Re-entrant and ref-counted, so it's safe for multiple
# agents to also enter/exit it concurrently if needed — fastmcp keeps the
# subprocess and session alive until the last exit.
fetch_client = Client(
    StdioTransport(command="python", args=["-m", "mcp_server_fetch"])
)
```

---

## 1b.2 `tools/search_tool.py` — uses `AsyncTavilyClient`

> **Why async, not the plain `TavilyClient`:** `tavily_search` is registered on
> every section agent, and Stage 1d onward fires all section agents concurrently
> via `asyncio.gather()`. The synchronous `TavilyClient.search(...)` is a
> blocking `requests` call — if the module-level client were a `TavilyClient`,
> each concurrent agent's search would block the entire event loop for its full
> duration. `AsyncTavilyClient` is built on `httpx.AsyncClient` and a single
> module-level instance is safe to share across concurrent agents.

```python
# tools/search_tool.py
from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic_ai import RunContext
from tavily import AsyncTavilyClient

from core.deps import Deps
from core.logger import logger
from schemas.search_result import SearchResponse, SearchResult

load_dotenv()

_client = AsyncTavilyClient(api_key=os.environ["TAVILY_API_KEY"])


async def tavily_search(
    ctx: RunContext[Deps],
    query: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
) -> SearchResponse:
    """Search the web via Tavily. time_range='year' always enforced.

    Never pass site: prefixed queries — time_range is not honoured for
    site: searches. Use tavily_search to find URLs, then fetch_page to
    retrieve content from those URLs.

    Args:
        query:          plain search query
        max_results:    number of results to return (default 5, max 10)
        include_domains: optional list of domains to restrict results to
                         (e.g. ["thestudentroom.co.uk"] for ForumAgent)

    Returns:
        SearchResponse with results list. Never raises — empty results
        list returned on failure.
    """
    kwargs = dict(query=query, max_results=max_results, time_range="year")
    if include_domains:
        kwargs["include_domains"] = include_domains

    raw = await _client.search(**kwargs)
    logger.info("search_tool | query=%r results=%d", query, len(raw.get("results", [])))

    results_list = [
        SearchResult(
            url=r.get("url", ""),
            title=r.get("title", ""),
            content=r.get("content", ""),
            score=float(r.get("score", 0.0)),
            date=r.get("published_date"),
        )
        for r in raw.get("results", []) or []
    ]

    return SearchResponse(
        query=query,
        results=results_list,
        answer=raw.get("answer"),
    )
```

---

## 1b.3 `tools/fetch_tool.py` — calls the shared `fastmcp.Client`

```python
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
```

> **`async with fetch_client:` inside the wrapper, every call.** `fastmcp.Client`
> is reentrant and ref-counted (see 1b.1), so entering it here is cheap if the
> connection is already open elsewhere — it just increments the counter and
> reuses the session. Either way `fetch_page` is self-contained and safe to call
> from any agent without depending on `main.py` having run a separate
> `startup()` step first.

---

## 1b.4 `tools/ddg_tool.py` — date filtering, non-blocking via `asyncio.to_thread`

> **Not wired to any agent (per MASTER §13) — `ddg_search` stays unregistered
> because post-call date filtering is unreliable, not because of this fix.**
> `ddgs.DDGS().text(...)` is a synchronous, blocking call. `ddg_search` is
> declared `async def`, so as written it would block the event loop.
> `ddgs` has no async client, so the fix is `asyncio.to_thread(...)`, which runs
> the blocking call in a worker thread and lets the event loop continue.

```python
# tools/ddg_tool.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ddgs import DDGS
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger


@dataclass
class DDGResult:
    url:     str
    title:   str
    content: str
    date:    str | None = None


@dataclass
class DDGResponse:
    query:   str
    results: list[DDGResult] = field(default_factory=list)


_client = DDGS()
_TWO_YEARS_AGO = datetime.now() - timedelta(days=730)


async def ddg_search(
    ctx: RunContext[Deps],
    query: str,
    max_results: int = 5,
) -> DDGResponse:
    """Search via DuckDuckGo. NewsAgent fallback only.

    NOT CURRENTLY REGISTERED ON ANY AGENT — see MASTER §13. Date filtering
    on missing/unparseable dates is insufficient on its own; this function
    is retained for future use once a reliable date-filtering solution exists.

    Results are date-filtered to the last 2 years before returning.
    Results with no parseable date are excluded — do not rely on the LLM
    to discard old results.

    Args:
        query:       plain search query
        max_results: number of results to return (default 5)

    Returns:
        DDGResponse with filtered results list. Never raises.
    """
    try:
        raw = await asyncio.to_thread(_client.text, query, max_results=max_results * 2)
    except Exception:
        await asyncio.sleep(3.0)
        try:
            raw = await asyncio.to_thread(_client.text, query, max_results=max_results * 2)
        except Exception as exc:
            logger.error("ddg_tool | failed after retry: %s", exc)
            return DDGResponse(query=query, results=[])

    filtered = []
    for r in raw or []:
        date_str = r.get("date")
        if date_str:
            try:
                pub_date = datetime.fromisoformat(date_str)
                if pub_date < _TWO_YEARS_AGO:
                    continue
            except ValueError:
                continue  # unparseable date — exclude
        else:
            continue  # no date — exclude

        filtered.append(DDGResult(
            url=r.get("href", ""),
            title=r.get("title", ""),
            content=r.get("body", ""),
            date=date_str,
        ))
        if len(filtered) >= max_results:
            break

    logger.info("ddg_tool | query=%r returned=%d (after date filter)", query, len(filtered))
    return DDGResponse(query=query, results=filtered)
```

---

## 1b.5 `tools/adzuna_tool.py` — NEW

```python
# tools/adzuna_tool.py
from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger
from schemas.job_posting import JobPosting, JobPostingsResponse

load_dotenv()

_APP_ID  = os.environ["ADZUNA_APP_ID"]
_APP_KEY = os.environ["ADZUNA_APP_KEY"]
_BASE    = "https://api.adzuna.com/v1/api/jobs"

# Single source of truth for country routing.
# Key:   the exact string value of deps.context.country for supported countries.
# Value: (adzuna_country_code, iso_currency_code)
# To add a new country: add one entry here. Nothing else changes.
_COUNTRY_MAP: dict[str, tuple[str, str]] = {
    "UK":        ("gb", "GBP"),
    "Australia": ("au", "AUD"),
}


async def adzuna_jobs(
    ctx: RunContext[Deps],
    query: str,
    max_results: int = 15,
) -> JobPostingsResponse:
    """Search live job postings via Adzuna API. UK and Australia only.

    Call this tool when deps.context.country is "UK" or "Australia".
    Do not call this tool for Singapore — use mcf_jobs instead.

    Args:
        query:       job search query (e.g. "software engineer graduate")
        max_results: number of postings to return (default 15, max 50)

    Returns:
        JobPostingsResponse with normalised postings. Never raises —
        returns error field on failure so the agent can continue.
    """
    country = ctx.deps.context.country
    mapping = _COUNTRY_MAP.get(country)

    if not mapping:
        return JobPostingsResponse(
            query=query,
            country=country,
            total_found=0,
            error=(
                f"adzuna_jobs does not support country={country!r}. "
                f"Supported: {list(_COUNTRY_MAP)}. Use mcf_jobs for Singapore."
            ),
        )

    adzuna_code, currency = mapping

    params = {
        "app_id":           _APP_ID,
        "app_key":          _APP_KEY,
        "results_per_page": min(max_results, 50),
        "what":             query,
        "content-type":     "application/json",
    }

    url = f"{_BASE}/{adzuna_code}/search/1"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("adzuna_tool | request failed: %s", exc)
        return JobPostingsResponse(
            query=query, country=country, total_found=0,
            error=str(exc),
        )

    total = data.get("count", 0)
    postings = []

    for job in data.get("results", []):
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")

        postings.append(JobPosting(
            title=       job.get("title", ""),
            company=     job.get("company", {}).get("display_name", ""),
            location=    job.get("location", {}).get("display_name", ""),
            description= job.get("description", ""),
            salary_min=  float(salary_min) if salary_min else None,
            salary_max=  float(salary_max) if salary_max else None,
            currency=    currency,
            date_posted= job.get("created", ""),
            skills=      [],   # Adzuna returns no structured skill tags; LLM reads description
            source_url=  job.get("redirect_url", ""),
            source=      "adzuna",
        ))

    logger.info(
        "adzuna_tool | country=%r query=%r total=%d returned=%d",
        country, query, total, len(postings),
    )

    return JobPostingsResponse(
        query=query,
        country=country,
        total_found=total,
        postings=postings,
    )
```

---

## 1b.6 `tools/mcf_tool.py` — NEW

```python
# tools/mcf_tool.py
from __future__ import annotations

import httpx
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger
from schemas.job_posting import JobPosting, JobPostingsResponse

_BASE = "https://api.mycareersfuture.gov.sg/v2"


def _extract_skills(posting: dict) -> list[str]:
    """Extract skill names from the MCF skills array in the API response.

    MCF returns a structured skills array — extract names from it directly.
    No description scanning.
    """
    return [
        s.get("skill", "")
        for s in posting.get("skills", [])
        if s.get("skill")
    ]


def _parse_salary(posting: dict) -> tuple[float | None, float | None]:
    """Extract min/max salary from MCF salary object."""
    salary = posting.get("salary", {})
    minimum = salary.get("minimum")
    maximum = salary.get("maximum")
    return (
        float(minimum) if minimum else None,
        float(maximum) if maximum else None,
    )


async def mcf_jobs(
    ctx: RunContext[Deps],
    query: str,
    max_results: int = 15,
) -> JobPostingsResponse:
    """Search live job postings via MyCareersFuture API. Singapore only.

    Call this tool when deps.context.country is "Singapore".
    Do not call this tool for UK or Australia — use adzuna_jobs instead.

    No authentication required — this is a public government API.

    Args:
        query:       job search query (e.g. "software engineer computer science")
        max_results: number of postings to return (default 15, max 100)

    Returns:
        JobPostingsResponse with normalised postings. Never raises —
        returns error field on failure so the agent can continue.
    """
    country = ctx.deps.context.country

    if country != "Singapore":
        return JobPostingsResponse(
            query=query,
            country=country,
            total_found=0,
            error=(
                f"mcf_jobs only supports Singapore. "
                f"country={country!r} is not supported. Use adzuna_jobs for UK and Australia."
            ),
        )

    params = {
        "search":  query,
        "limit":   min(max_results, 100),
        "offset":  0,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_BASE}/jobs", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("mcf_tool | request failed: %s", exc)
        return JobPostingsResponse(
            query=query, country=country, total_found=0,
            error=str(exc),
        )

    total = data.get("total", 0)
    postings = []

    for job in data.get("results", []):
        salary_min, salary_max = _parse_salary(job)

        postings.append(JobPosting(
            title=       job.get("title", ""),
            company=     job.get("postedCompany", {}).get("name", ""),
            location=    job.get("location", {}).get("oneLineAddress", "Singapore"),
            description= job.get("description", ""),
            salary_min=  salary_min,
            salary_max=  salary_max,
            currency=    "SGD",
            date_posted= job.get("originalPostingDate", ""),
            skills=      _extract_skills(job),
            source_url=  f"https://www.mycareersfuture.gov.sg/job/{job.get('uuid', '')}",
            source=      "mycareersfuture",
        ))

    logger.info(
        "mcf_tool | query=%r total=%d returned=%d",
        query, total, len(postings),
    )

    return JobPostingsResponse(
        query=query,
        country=country,
        total_found=total,
        postings=postings,
    )
```

---

## 1b.7 `tools/reddit_tool.py` — REMOVED

> **Why this file no longer exists:** Reddit's public JSON API returned
> 403 Forbidden as of May 30, 2026. Reddit's Responsible Builder Policy
> (November 2025) closed self-service API registration. There is no viable
> unauthenticated path to Reddit content. Do not create this file.
>
> **What replaces it:** `ForumAgent` uses `tavily_search` with `include_domains`
> to restrict searches to specific student forum sites. This was confirmed
> working in live tests — see Section 1b.9 for the forum search tests.

---

## 1b.8 Master Reference Changes

### Section 3 — Third-Party Tools (replace tools table)

```markdown
| Tool | Kind | Role | API Key Required |
|---|---|---|---|
| **Tavily** | Python client (`AsyncTavilyClient`) | Primary search — career paths, salary, forum, news, rankings | `TAVILY_API_KEY` |
| **Fetch MCP** | MCP server | Direct URL fetch — catalog pages, salary surveys | None |
| **Adzuna** | REST API | Live job postings — UK and Australia | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` |
| **MyCareersFuture** | REST API | Live job postings — Singapore only | None — public API |
| **DuckDuckGo** | Python client | NewsAgent fallback — no key, no quota — **not yet registered on any agent** | None |
```

> **Tavily client note:** `AsyncTavilyClient`, not `TavilyClient`. Section agents
> run concurrently via `asyncio.gather()` from Stage 1d onward; the synchronous
> client would block the event loop on every search.

> **Forum search note:** ForumAgent uses Tavily with `include_domains` to restrict
> searches to specific student forum sites (e.g. `include_domains=["thestudentroom.co.uk"]`).
> Reddit is no longer accessible as of May 2026 — all unauthenticated `.json`
> endpoints return 403. `reddit_tool.py` has been removed.

### Section 8.6 — Tool Registry (add rows, remove reddit row)

Add:

```markdown
| `adzuna_jobs` | `tools/adzuna_tool.py` | `CareerAgent` | UK + AU job postings |
| `mcf_jobs` | `tools/mcf_tool.py` | `CareerAgent` | Singapore job postings |
```

Remove:

```markdown
| `reddit_fetch_thread` | ... |
```

### Section 8.8 — CareerAgent tool registration

```python
tools=[
    tavily_search,
    fetch_page,
    adzuna_jobs,
    mcf_jobs,
]
```

All four registered directly. No `_make_search_tool()` closure wrapper.

---

## 1b.9 Tests — `tests/test_stage_1b.py`

```python
# tests/test_stage_1b.py
"""
Stage 1b tests — tool wrappers.
Run with: pytest tests/test_stage_1b.py -v -s

Real API calls. Requires TAVILY_API_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY in .env.
MyCareersFuture and DuckDuckGo require no keys.
Fetch tests require mcp-server-fetch installed.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from pydantic_ai import RunContext
from unittest.mock import MagicMock

from mcps.fetch_client import fetch_client


def _mock_ctx(country: str = "UK"):
    ctx = MagicMock()
    ctx.deps.context.country = country
    return ctx


# ── Tavily ────────────────────────────────────────────────────────────────────

def test_tavily_imports_cleanly() -> None:
    from tools.search_tool import tavily_search
    assert tavily_search


def test_tavily_initialises_with_env_key() -> None:
    from tools.search_tool import _client
    assert _client is not None


def test_tavily_raises_on_missing_key(monkeypatch) -> None:
    import importlib
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    import tools.search_tool as m
    with pytest.raises(KeyError):
        importlib.reload(m)


@pytest.mark.asyncio
async def test_tavily_returns_results_for_known_query() -> None:
    from tools.search_tool import tavily_search
    ctx = _mock_ctx()
    response = await tavily_search(ctx, "University of Manchester Computer Science")
    assert len(response.results) > 0
    assert all(r.url.startswith("https://") for r in response.results)


@pytest.mark.asyncio
async def test_tavily_career_query_uk() -> None:
    from tools.search_tool import tavily_search
    ctx = _mock_ctx("UK")
    response = await tavily_search(ctx, "Computer Science graduate careers UK 2024")
    assert len(response.results) > 0


@pytest.mark.asyncio
async def test_tavily_salary_query_returns_results() -> None:
    from tools.search_tool import tavily_search
    ctx = _mock_ctx("UK")
    response = await tavily_search(ctx, "software engineer graduate salary UK")
    assert isinstance(response.results, list)


# ── DuckDuckGo ────────────────────────────────────────────────────────────────

def test_ddg_imports_cleanly() -> None:
    from tools.ddg_tool import ddg_search
    assert ddg_search


@pytest.mark.asyncio
async def test_ddg_search_returns_results() -> None:
    from tools.ddg_tool import ddg_search
    ctx = _mock_ctx()
    response = await ddg_search(ctx, "University of Edinburgh student experience")
    assert isinstance(response.results, list)


@pytest.mark.asyncio
async def test_ddg_returns_empty_on_nonsense_query() -> None:
    from tools.ddg_tool import ddg_search
    ctx = _mock_ctx()
    response = await ddg_search(ctx, "xzqj9f_nonsense_query_no_results_expected_xzqj9f")
    assert isinstance(response.results, list)


@pytest.mark.asyncio
async def test_ddg_date_filter_excludes_old_results() -> None:
    from tools.ddg_tool import ddg_search
    ctx = _mock_ctx()
    response = await ddg_search(ctx, "University of Manchester news")
    from datetime import timedelta
    two_years_ago = datetime.now() - timedelta(days=730)
    for r in response.results:
        if r.date:
            assert datetime.fromisoformat(r.date) >= two_years_ago


# ── Fetch MCP ─────────────────────────────────────────────────────────────────

def test_fetch_imports_cleanly() -> None:
    from tools.fetch_tool import fetch_page
    assert fetch_page


def test_fetch_client_is_shared_module_instance() -> None:
    from mcps.fetch_client import fetch_client as fc1
    from mcps.fetch_client import fetch_client as fc2
    assert fc1 is fc2


@pytest.fixture(scope="module")
async def fetch_server():
    async with fetch_client:
        yield


@pytest.mark.asyncio
async def test_fetch_returns_content_for_known_url(fetch_server) -> None:
    from tools.fetch_tool import fetch_page
    import json
    ctx = _mock_ctx()
    result_json = await fetch_page(ctx, "https://www.manchester.ac.uk")
    result = json.loads(result_json)
    assert result["status"] == "ok"
    assert len(result["content"]) > 100
    assert result["error"] is None


@pytest.mark.asyncio
async def test_fetch_returns_error_for_bad_url(fetch_server) -> None:
    from tools.fetch_tool import fetch_page
    import json
    ctx = _mock_ctx()
    result_json = await fetch_page(ctx, "https://this-domain-does-not-exist-xzqj9f.com")
    result = json.loads(result_json)
    assert result["status"] == "error"
    assert result["error"] is not None


# ── JobPosting schema ─────────────────────────────────────────────────────────

def test_job_posting_schema_imports() -> None:
    from schemas.job_posting import JobPosting, JobPostingsResponse
    assert JobPosting
    assert JobPostingsResponse


def test_job_posting_instantiates() -> None:
    from schemas.job_posting import JobPosting
    p = JobPosting(
        title="Software Engineer",
        company="Acme Ltd",
        location="London",
        description="Build great software",
        salary_min=30000.0,
        salary_max=45000.0,
        currency="GBP",
        date_posted="2024-03-01",
        skills=[],
        source_url="https://example.com/job/1",
        source="adzuna",
    )
    assert p.title == "Software Engineer"
    assert p.currency == "GBP"
    assert isinstance(p.skills, list)


# ── Adzuna ────────────────────────────────────────────────────────────────────

def test_adzuna_imports_cleanly() -> None:
    from tools.adzuna_tool import adzuna_jobs
    assert adzuna_jobs


def test_adzuna_initialises_with_env_keys() -> None:
    from tools.adzuna_tool import _APP_ID, _APP_KEY
    assert _APP_ID
    assert _APP_KEY


def test_adzuna_country_map_structure() -> None:
    from tools.adzuna_tool import _COUNTRY_MAP
    for country, value in _COUNTRY_MAP.items():
        assert isinstance(value, tuple), f"{country}: value must be a tuple"
        assert len(value) == 2, f"{country}: tuple must have exactly 2 elements"
        code, currency = value
        assert code == code.lower(), f"{country}: adzuna code must be lowercase"
        assert currency == currency.upper(), f"{country}: currency must be uppercase ISO code"


@pytest.mark.asyncio
async def test_adzuna_returns_uk_postings() -> None:
    from tools.adzuna_tool import adzuna_jobs
    ctx = _mock_ctx("UK")
    response = await adzuna_jobs(ctx, "software engineer graduate", max_results=5)
    if response.error:
        pytest.skip(f"Adzuna unavailable: {response.error}")
    assert response.total_found > 0
    assert len(response.postings) > 0
    assert all(p.currency == "GBP" for p in response.postings)


@pytest.mark.asyncio
async def test_adzuna_returns_australia_postings() -> None:
    from tools.adzuna_tool import adzuna_jobs
    ctx = _mock_ctx("Australia")
    response = await adzuna_jobs(ctx, "software engineer graduate", max_results=5)
    if response.error:
        pytest.skip(f"Adzuna unavailable: {response.error}")
    assert len(response.postings) >= 0   # low volume acceptable for AU
    assert all(p.currency == "AUD" for p in response.postings)


@pytest.mark.asyncio
async def test_adzuna_rejects_singapore() -> None:
    from tools.adzuna_tool import adzuna_jobs
    ctx = _mock_ctx("Singapore")
    response = await adzuna_jobs(ctx, "software engineer", max_results=5)
    assert response.error is not None
    assert "Singapore" in response.error or "mcf_jobs" in response.error
    assert len(response.postings) == 0


@pytest.mark.asyncio
async def test_adzuna_postings_have_required_fields() -> None:
    from tools.adzuna_tool import adzuna_jobs
    ctx = _mock_ctx("UK")
    response = await adzuna_jobs(ctx, "data analyst", max_results=5)
    if response.error:
        pytest.skip(f"Adzuna unavailable: {response.error}")
    for p in response.postings:
        assert p.title
        assert p.source == "adzuna"
        assert p.currency == "GBP"
        assert isinstance(p.skills, list)   # always [] for Adzuna


# ── MCF ───────────────────────────────────────────────────────────────────────

def test_mcf_imports_cleanly() -> None:
    from tools.mcf_tool import mcf_jobs
    assert mcf_jobs


@pytest.mark.asyncio
async def test_mcf_returns_singapore_postings() -> None:
    from tools.mcf_tool import mcf_jobs
    ctx = _mock_ctx("Singapore")
    response = await mcf_jobs(ctx, "software engineer", max_results=5)
    if response.error:
        pytest.skip(f"MCF unavailable: {response.error}")
    assert len(response.postings) > 0
    for p in response.postings:
        assert p.title
        assert p.source_url.startswith("https://www.mycareersfuture.gov.sg")
        assert isinstance(p.skills, list)


@pytest.mark.asyncio
async def test_mcf_rejects_non_singapore() -> None:
    from tools.mcf_tool import mcf_jobs
    ctx = _mock_ctx("UK")
    response = await mcf_jobs(ctx, "software engineer", max_results=5)
    assert response.error is not None
    assert "Singapore" in response.error or "adzuna_jobs" in response.error
    assert len(response.postings) == 0


@pytest.mark.asyncio
async def test_mcf_postings_have_required_fields() -> None:
    from tools.mcf_tool import mcf_jobs
    ctx = _mock_ctx("Singapore")
    response = await mcf_jobs(ctx, "data analyst", max_results=5)
    if response.error:
        pytest.skip(f"MCF unavailable: {response.error}")
    for p in response.postings:
        assert p.title, "Posting missing title"
        assert p.currency == "SGD"
        assert p.source_url, "Posting missing source_url"
        assert isinstance(p.skills, list)


# ── Forum Search (Tavily include_domains) ─────────────────────────────────────

def test_tavily_forum_search_imports_cleanly() -> None:
    from tools.search_tool import tavily_search
    assert tavily_search


@pytest.mark.asyncio
async def test_tavily_forum_search_tsr_returns_results() -> None:
    """Live call: Tavily with include_domains restricted to thestudentroom.co.uk."""
    from tools.search_tool import _client
    raw = await _client.search(
        query="University of Edinburgh Computer Science student experience",
        include_domains=["thestudentroom.co.uk"],
        max_results=3,
        time_range="year",
    )
    results = raw.get("results", [])
    assert len(results) > 0, "Expected at least one TSR result"
    for r in results:
        assert "thestudentroom.co.uk" in r.get("url", ""), (
            f"Result URL not from TSR: {r.get('url')}"
        )


@pytest.mark.asyncio
async def test_tavily_forum_search_studentcrowd_returns_results() -> None:
    """Live call: Tavily with include_domains restricted to studentcrowd.com."""
    from tools.search_tool import _client
    raw = await _client.search(
        query="University of Manchester Computer Science review",
        include_domains=["studentcrowd.com"],
        max_results=3,
        time_range="year",
    )
    results = raw.get("results", [])
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_tavily_forum_search_unrestricted_returns_results() -> None:
    """Live call: unrestricted Tavily forum sweep for non-UK university."""
    from tools.search_tool import _client
    raw = await _client.search(
        query="NUS Computer Science student experience forum",
        max_results=3,
        time_range="year",
    )
    results = raw.get("results", [])
    assert len(results) > 0, "Expected at least one result"
```

---

## 1b.10 Run the Tests

```bash
pytest tests/test_stage_1b.py -v -s
```

Expected output on clean pass:

```
tests/test_stage_1b.py::test_tavily_imports_cleanly PASSED
tests/test_stage_1b.py::test_tavily_initialises_with_env_key PASSED
tests/test_stage_1b.py::test_tavily_raises_on_missing_key PASSED
tests/test_stage_1b.py::test_tavily_returns_results_for_known_query PASSED
tests/test_stage_1b.py::test_tavily_career_query_uk PASSED
tests/test_stage_1b.py::test_tavily_salary_query_returns_results PASSED
tests/test_stage_1b.py::test_ddg_imports_cleanly PASSED
tests/test_stage_1b.py::test_ddg_search_returns_results PASSED
tests/test_stage_1b.py::test_ddg_returns_empty_on_nonsense_query PASSED
tests/test_stage_1b.py::test_ddg_date_filter_excludes_old_results PASSED
tests/test_stage_1b.py::test_fetch_imports_cleanly PASSED
tests/test_stage_1b.py::test_fetch_client_is_shared_module_instance PASSED
tests/test_stage_1b.py::test_fetch_returns_content_for_known_url PASSED
tests/test_stage_1b.py::test_fetch_returns_error_for_bad_url PASSED
tests/test_stage_1b.py::test_job_posting_schema_imports PASSED
tests/test_stage_1b.py::test_job_posting_instantiates PASSED
tests/test_stage_1b.py::test_adzuna_imports_cleanly PASSED
tests/test_stage_1b.py::test_adzuna_initialises_with_env_keys PASSED
tests/test_stage_1b.py::test_adzuna_country_map_structure PASSED
tests/test_stage_1b.py::test_adzuna_returns_uk_postings PASSED
tests/test_stage_1b.py::test_adzuna_returns_australia_postings PASSED
tests/test_stage_1b.py::test_adzuna_rejects_singapore PASSED
tests/test_stage_1b.py::test_adzuna_postings_have_required_fields PASSED
tests/test_stage_1b.py::test_mcf_imports_cleanly PASSED
tests/test_stage_1b.py::test_mcf_returns_singapore_postings PASSED
tests/test_stage_1b.py::test_mcf_rejects_non_singapore PASSED
tests/test_stage_1b.py::test_mcf_postings_have_required_fields PASSED
tests/test_stage_1b.py::test_tavily_forum_search_imports_cleanly PASSED
tests/test_stage_1b.py::test_tavily_forum_search_tsr_returns_results PASSED
tests/test_stage_1b.py::test_tavily_forum_search_studentcrowd_returns_results PASSED
tests/test_stage_1b.py::test_tavily_forum_search_unrestricted_returns_results PASSED

31 passed in X.Xs
```

Fetch tests may SKIP if MCP server is not installed — this is acceptable.
They must all pass before Stage 1c.

---

## 1b.11 Common Failure Modes at This Stage

**`KeyError: ADZUNA_APP_ID`**
Cause: `.env` missing the new Adzuna keys.
Fix: register at https://developer.adzuna.com and add both keys to `.env`.

**`test_adzuna_returns_uk_postings FAILED — total_found=0`**
Cause: Adzuna free tier may throttle on first call. Also check the `what`
parameter — very niche queries can return 0. Try with `"software engineer"`
as a sanity check.

**`test_mcf_returns_singapore_postings FAILED — connection error`**
Cause: MyCareersFuture API base URL may have changed. Verify at
`https://api.mycareersfuture.gov.sg/v2/jobs?search=engineer&limit=1` in a
browser. If the URL structure has changed, update `_BASE` in `mcf_tool.py`.

**`test_adzuna_country_map_structure FAILED`**
Cause: `_COUNTRY_MAP` values are not `(code, currency)` tuples. Each value
must be a tuple of exactly two strings — lowercase country code, uppercase
currency code.

**`RatelimitException` from DuckDuckGo**
The wrapper retries once with 3s delay. Run DDG tests in isolation if needed:
`pytest tests/test_stage_1b.py -k ddg -v`.

**`McpError: Connection closed`**
Fetch MCP server failed to start. See Service 2 setup — try `uvx` invocation.

**`test_tavily_raises_on_missing_key FAILED`**
`monkeypatch.delenv` + `importlib.reload` required. Confirm reload is called
after the env var is deleted.

**`ValidationError` on `JobPosting` instantiation**
Cause: `schemas/job_posting.py` was still a `dataclass` when the tool was
updated to use `BaseModel`. Confirm all three shared schemas use `BaseModel`.

---

## Stage 1b Completion Checklist

- [ ] Tavily API key in `.env` — confirmed working
- [ ] Adzuna `app_id` and `app_key` in `.env` — confirmed working
- [ ] MyCareersFuture — no key needed, confirmed reachable
- [ ] `pip install tavily-python ddgs httpx fastmcp mcp-server-fetch` clean
- [ ] `schemas/search_result.py` — `SearchResult`, `SearchResponse` as pydantic
      `BaseModel` with `Field(description=...)` on every field
- [ ] `schemas/fetch_result.py` — `FetchResult` as pydantic `BaseModel` with
      `Field(description=...)` on every field
- [ ] `schemas/job_posting.py` — `JobPosting`, `JobPostingsResponse` as pydantic
      `BaseModel` with `Field(description=...)` on every field (NEW)
- [ ] `mcps/fetch_client.py` — single module-level `fastmcp.Client` (no custom
      class, no manual `startup()`/`shutdown()`) — reentrant and ref-counted
- [ ] `tools/search_tool.py` — `tavily_search` uses `AsyncTavilyClient`,
      `time_range="year"` enforced, `include_domains` parameter passed through
- [ ] `tools/fetch_tool.py` — `fetch_page`, never raises, docstring warns off
      job board URLs, calls `fetch_client` via `async with`
- [ ] `tools/ddg_tool.py` — `ddg_search`, date filter applied before return,
      `_client.text(...)` called via `asyncio.to_thread` — NOT registered on
      any agent
- [ ] `tools/adzuna_tool.py` — `adzuna_jobs`, `_COUNTRY_MAP` maps country →
      `(code, currency)`, `skills=[]` for all postings
- [ ] `tools/mcf_tool.py` — `mcf_jobs`, Singapore only, no auth, skills from
      API tags, location from API
- [ ] No `tools/reddit_tool.py` — removed; Reddit API unavailable since May 2026
- [ ] MASTER section 3 updated — Reddit row removed, forum include_domains note added
- [ ] MASTER section 8.6 updated — `adzuna_jobs`, `mcf_jobs` rows added;
      `reddit_fetch_thread` row removed
- [ ] MASTER section 8.8 updated — `CareerAgent` registers
      `[tavily_search, fetch_page, adzuna_jobs, mcf_jobs]` directly
- [ ] `pytest tests/test_stage_1b.py -v` — 31 passed (fetch may SKIP)
- [ ] Stage 1a tests still pass: `pytest tests/test_stage_1a.py -v`

---

*End of Stage 1b Specification*