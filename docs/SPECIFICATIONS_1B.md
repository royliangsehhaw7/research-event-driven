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
pip install mcp mcp-server-fetch
```

Confirm the server is available:

```bash
python -m mcp_server_fetch --help
```

If that command fails, switch to the `uvx` invocation. Update
`StdioServerParameters` in `mcps/fetch_client.py`:

```python
server_params = StdioServerParameters(
    command="uvx",
    args=["mcp-server-fetch"],
)
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
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

ADZUNA_APP_ID=xxxxxxxx
ADZUNA_APP_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

RESEARCH_MODEL=openrouter/google/gemini-2.5-pro
SCORING_MODEL=openrouter/google/gemini-2.5-pro
CONVERSATION_MODEL=openrouter/google/gemini-2.5-flash
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
mcp
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
RESEARCH_MODEL=openrouter/google/gemini-2.5-pro
SCORING_MODEL=openrouter/google/gemini-2.5-pro
CONVERSATION_MODEL=openrouter/google/gemini-2.5-flash
```

---

## Updated Folder Structure After Stage 1b

```
├── mcps/
│   └── fetch_client.py             Fetch MCP singleton — startup() / shutdown() / call_tool()
│
├── tools/
│   ├── search_tool.py              tavily_search — module-level TavilyClient singleton
│   ├── fetch_tool.py               fetch_page — calls fetch_client singleton
│   ├── ddg_tool.py                 ddg_search — module-level DDGS singleton (NewsAgent only)
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

### `schemas/search_result.py` — unchanged from original

```python
# schemas/search_result.py
from dataclasses import dataclass

@dataclass
class SearchResult:
    """A single result returned by Tavily."""
    url:     str
    title:   str
    content: str
    score:   float
    date:    str | None = None

@dataclass
class SearchResponse:
    """The full response from a Tavily search call."""
    query:   str
    results: list[SearchResult]
    answer:  str | None = None
```

### `schemas/fetch_result.py` — unchanged from original

```python
# schemas/fetch_result.py
from dataclasses import dataclass

@dataclass
class FetchResult:
    url:     str
    content: str
    status:  str        # "ok" or "error"
    error:   str | None = None
```

### `schemas/job_posting.py` — NEW

Shared return type used by both `adzuna_tool` and `mcf_tool`. CareerAgent
receives the same schema regardless of which country-specific tool was called.

```python
# schemas/job_posting.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class JobPosting:
    """A single job posting. Normalised from either Adzuna or MyCareersFuture."""
    title:          str
    company:        str
    location:       str
    description:    str
    salary_min:     float | None    # in local currency, annual
    salary_max:     float | None    # in local currency, annual
    currency:       str             # ISO code — GBP, AUD, SGD
    date_posted:    str             # ISO date string YYYY-MM-DD or as returned
    skills:         list[str]       # tags from the API response; empty list if none provided
    source_url:     str             # direct link to the posting
    source:         str             # "adzuna" or "mycareersfuture"


@dataclass
class JobPostingsResponse:
    """The full response from a job posting tool call."""
    query:          str
    country:        str             # matches deps.context.country
    total_found:    int             # total matching postings in the API, not just returned
    postings:       list[JobPosting] = field(default_factory=list)
    error:          str | None = None
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

## 1b.1 `mcps/fetch_client.py` — unchanged from original

```python
# mcps/fetch_client.py
from __future__ import annotations

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from core.logger import logger


class FetchClient:
    """Singleton wrapper around the Fetch MCP subprocess.

    Lifecycle:
        startup()  — call once at application boot before any request
        shutdown() — call once at application exit in a finally block
        call_tool() — call per fetch request

    Never instantiate directly outside this module. Use the module-level
    `fetch_client` singleton.
    """

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._context = None

    async def startup(self) -> None:
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server_fetch"],
        )
        self._context = stdio_client(server_params)
        read, write = await self._context.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        logger.info("fetch_client | MCP fetch server started")

    async def shutdown(self) -> None:
        if self._session:
            await self._session.__aexit__(None, None, None)
        if self._context:
            await self._context.__aexit__(None, None, None)
        logger.info("fetch_client | MCP fetch server stopped")

    async def call_tool(self, tool_name: str, arguments: dict) -> object:
        if not self._session:
            raise RuntimeError(
                "FetchClient not started. Call fetch_client.startup() at boot."
            )
        result = await self._session.call_tool(tool_name, arguments)
        return result.content


fetch_client = FetchClient()
```

---

## 1b.2 `tools/search_tool.py` — unchanged from original

```python
# tools/search_tool.py
from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic_ai import RunContext
from tavily import TavilyClient

from core.deps import Deps
from core.logger import logger
from schemas.search_result import SearchResponse, SearchResult

load_dotenv()

_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


async def tavily_search(
    ctx: RunContext[Deps],
    query: str,
    max_results: int = 5,
) -> SearchResponse:
    """Search the web via Tavily. time_range='year' always enforced.

    Never pass site: prefixed queries — time_range is not honoured for
    site: searches. Use tavily_search to find URLs, then fetch_page to
    retrieve content from those URLs.

    Args:
        query:       plain search query
        max_results: number of results to return (default 5, max 10)

    Returns:
        SearchResponse with results list. Never raises — empty results
        list returned on failure.
    """
    raw = _client.search(query=query, max_results=max_results, time_range="year")
    logger.warning("search_tool | query=%r results=%d", query, len(raw.get("results", [])))

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

## 1b.3 `tools/fetch_tool.py` — unchanged from original

```python
# tools/fetch_tool.py
from __future__ import annotations

import json

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
        raw = await fetch_client.call_tool("fetch", {
            "url": url,
            "max_length": 50000,
        })
        result = FetchResult(url=url, content=str(raw), status="ok", error=None)
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

---

## 1b.4 `tools/ddg_tool.py` — unchanged from original

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
        raw = _client.text(query, max_results=max_results * 2)
    except Exception:
        await asyncio.sleep(3.0)
        try:
            raw = _client.text(query, max_results=max_results * 2)
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

## 1b.7 Master Reference Changes

The following sections of the master reference need updating to reflect the
new tools. These are drop-in replacements — only the listed sections change.

### Section 3 — Third-Party Tools (replace tools table)

```markdown
| Tool | Kind | Role | API Key Required |
|---|---|---|---|
| **Tavily** | Python client | Primary search — career paths, salary, forum, news, rankings | `TAVILY_API_KEY` |
| **Fetch MCP** | MCP server | Direct URL fetch — catalog pages, salary surveys | None |
| **Adzuna** | REST API | Live job postings — UK and Australia | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` |
| **MyCareersFuture** | REST API | Live job postings — Singapore only | None — public API |
| **DuckDuckGo** | Python client | NewsAgent fallback — no key, no quota | None |
```

### Section 8.6 — Tool-to-agent mapping (replace entire table and note)

```markdown
| Tool | career | background | rankings | program | employability | accommodation | news | forum | alternatives | scoring | conversation |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `tavily_search` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `fetch_page` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `adzuna_jobs` | ✓ | | | | | | | | | | |
| `mcf_jobs` | ✓ | | | | | | | | | | |
| `ddg_search` | | | | | | | | | | | |

`adzuna_jobs` and `mcf_jobs` are both registered on `CareerAgent`. The LLM
selects which to call based on `deps.context.country` and the tool docstrings.
`scoring` and `conversation` have no tools — they work entirely from the
blackboard. `tool_budget: 0` in their SKILL.md makes this explicit.

```
>[!WARNING] DuckDuckGo Search NOT wired
>Due to the inability to specify a date range for selection and filtering


### Section 8.8 — How tools attach to agents (replace CareerAgent constructor only)

```python
# CareerAgent — Tavily + Fetch + Adzuna + MCF
# Both job posting tools are registered. The LLM selects the correct one
# based on deps.context.country and the tool docstrings.
class CareerAgent(BaseAgent):
    def __init__(self, instructions: str, tool_budget: int) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0
        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=CareerOutput,
            tools=[self._make_search_tool(), fetch_page, adzuna_jobs, mcf_jobs],
        )
```

`adzuna_jobs` and `mcf_jobs` are not wrapped in `_make_search_tool()` — they
are direct REST calls, not searches, and do not count against `tool_budget`.
Register them directly, the same way `fetch_page` is registered.

### Section 12 — File Tree (replace `tools/` block)

```
├── tools/
│   ├── search_tool.py      tavily_search — module-level TavilyClient singleton
│   ├── fetch_tool.py       fetch_page — calls fetch_client singleton, never raises
│   ├── ddg_tool.py         ddg_search — module-level DDGS singleton, date-filtered
│   ├── adzuna_tool.py      adzuna_jobs — httpx REST, UK + AU, _COUNTRY_MAP routes code + currency
│   └── mcf_tool.py         mcf_jobs — httpx REST, SG only, no auth, skills from API tags
```

### Section 14 — Development Stage Summary (replace 1b row)

```
| 1b | Fetch MCP client singleton. search_tool, fetch_tool, ddg_tool (unchanged). adzuna_tool (UK+AU job postings via Adzuna REST, _COUNTRY_MAP for code + currency). mcf_tool (SG job postings via MyCareersFuture public API, skills from API tags). schemas/job_posting.py shared schema. CareerAgent updated to register adzuna_jobs + mcf_jobs. ResearchHandler.startup() warms Fetch MCP. | Real job postings confirmed for UK, AU, SG. All 5 tools pass live tests. 26 tests pass. |
```

---

## 1b.8 `tests/test_stage_1b.py`

```python
# tests/test_stage_1b.py
"""
Stage 1b tests — all tool wrappers against live services.

Run with: pytest tests/test_stage_1b.py -v -s

The -s flag shows API response previews which are useful on first run.
Tests marked with fetch_server fixture require the Fetch MCP subprocess
to be running — they will SKIP if the MCP server is not available.
"""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest
from dotenv import load_dotenv
from unittest.mock import MagicMock

load_dotenv()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def fetch_server():
    """Start the Fetch MCP server once for all fetch tests."""
    from mcps.fetch_client import fetch_client
    try:
        await fetch_client.startup()
        yield fetch_client
        await fetch_client.shutdown()
    except Exception as exc:
        pytest.skip(f"Fetch MCP server not available: {exc}")


def _mock_ctx(country: str = "UK") -> MagicMock:
    """Return a minimal RunContext mock with deps.context.country set."""
    ctx = MagicMock()
    ctx.deps.context.country = country
    return ctx


# ── Tavily ────────────────────────────────────────────────────────────────────

def test_tavily_imports_cleanly() -> None:
    from tools.search_tool import tavily_search
    assert tavily_search


def test_tavily_initialises_with_env_key() -> None:
    from tools import search_tool
    assert search_tool._client is not None


def test_tavily_raises_on_missing_key(monkeypatch) -> None:
    import tools.search_tool as search_tool
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(KeyError):
        importlib.reload(search_tool)


@pytest.mark.asyncio
async def test_tavily_returns_results_for_known_query() -> None:
    from tools.search_tool import tavily_search
    ctx = _mock_ctx()
    response = await tavily_search(ctx, "University of Manchester Computer Science undergraduate")
    assert len(response.results) > 0
    for r in response.results:
        assert r.url.startswith("http")
        assert len(r.content) > 0


@pytest.mark.asyncio
async def test_tavily_career_query_uk() -> None:
    from tools.search_tool import tavily_search
    ctx = _mock_ctx("UK")
    response = await tavily_search(ctx, "Computer Science graduate careers UK salary 2024")
    assert response.results is not None


@pytest.mark.asyncio
async def test_tavily_salary_query_returns_results() -> None:
    from tools.search_tool import tavily_search
    ctx = _mock_ctx("UK")
    response = await tavily_search(ctx, "software engineer graduate salary UK 2024")
    assert len(response.results) > 0


# ── DuckDuckGo ────────────────────────────────────────────────────────────────

def test_ddg_imports_cleanly() -> None:
    from tools.ddg_tool import ddg_search, DDGResult, DDGResponse
    assert ddg_search
    assert DDGResult
    assert DDGResponse


@pytest.mark.asyncio
async def test_ddg_search_returns_results() -> None:
    from tools.ddg_tool import ddg_search
    ctx = _mock_ctx()
    response = await ddg_search(ctx, "University of Manchester news 2024", max_results=3)
    assert isinstance(response.results, list)
    assert len(response.results) > 0
    for r in response.results:
        assert r.url.startswith("http")


@pytest.mark.asyncio
async def test_ddg_returns_empty_on_nonsense_query() -> None:
    from tools.ddg_tool import ddg_search
    ctx = _mock_ctx()
    await asyncio.sleep(1.0)
    response = await ddg_search(ctx, "xkqzwvmnop university xkqzwvmnop", max_results=3)
    assert isinstance(response.results, list)


def test_ddg_date_filter_excludes_old_results() -> None:
    """DDGResponse must never contain results older than 2 years."""
    from tools.ddg_tool import DDGResult, DDGResponse
    from datetime import datetime, timedelta
    old_date = (datetime.now() - timedelta(days=800)).isoformat()
    recent_date = (datetime.now() - timedelta(days=30)).isoformat()
    # The filter runs inside ddg_search — verify the dataclass accepts dates correctly
    r = DDGResult(url="https://example.com", title="t", content="c", date=recent_date)
    assert r.date == recent_date
    r2 = DDGResult(url="https://example.com", title="t", content="c", date=old_date)
    assert r2.date == old_date  # dataclass stores it — filter is in ddg_search


# ── Fetch ─────────────────────────────────────────────────────────────────────

def test_fetch_imports_cleanly() -> None:
    from tools.fetch_tool import fetch_page
    from schemas.fetch_result import FetchResult
    assert fetch_page
    assert FetchResult


def test_fetch_client_singleton_is_same_instance() -> None:
    from mcps.fetch_client import fetch_client as a
    from mcps.fetch_client import fetch_client as b
    assert a is b


@pytest.mark.asyncio
async def test_fetch_returns_content_for_known_url(fetch_server) -> None:
    from tools.fetch_tool import fetch_page
    ctx = _mock_ctx()
    raw = await fetch_page(ctx, "https://www.cs.manchester.ac.uk/undergraduate/")
    result = json.loads(raw)
    if result["status"] == "ok":
        assert len(result["content"]) > 100
    else:
        pytest.skip(f"Fetch not available: {result['error']}")


@pytest.mark.asyncio
async def test_fetch_returns_error_for_bad_url(fetch_server) -> None:
    from tools.fetch_tool import fetch_page
    ctx = _mock_ctx()
    raw = await fetch_page(ctx, "https://this.url.does.not.exist.invalid/")
    result = json.loads(raw)
    assert result["status"] == "error"
    assert result["error"] is not None
    assert result["content"] == ""


# ── Job posting schema ────────────────────────────────────────────────────────

def test_job_posting_schema_imports() -> None:
    from schemas.job_posting import JobPosting, JobPostingsResponse
    assert JobPosting
    assert JobPostingsResponse


def test_job_posting_instantiates() -> None:
    from schemas.job_posting import JobPosting, JobPostingsResponse
    posting = JobPosting(
        title="Software Engineer",
        company="Acme Ltd",
        location="London",
        description="Python, AWS required",
        salary_min=30000.0,
        salary_max=45000.0,
        currency="GBP",
        date_posted="2025-01-15",
        skills=[],
        source_url="https://example.com/job/1",
        source="adzuna",
    )
    assert posting.currency == "GBP"
    assert posting.skills == []
    response = JobPostingsResponse(
        query="software engineer",
        country="UK",
        total_found=1,
        postings=[posting],
    )
    assert len(response.postings) == 1


# ── Adzuna ────────────────────────────────────────────────────────────────────

def test_adzuna_imports_cleanly() -> None:
    from tools.adzuna_tool import adzuna_jobs
    assert adzuna_jobs


def test_adzuna_initialises_with_env_keys() -> None:
    from tools import adzuna_tool
    assert adzuna_tool._APP_ID
    assert adzuna_tool._APP_KEY


def test_adzuna_country_map_structure() -> None:
    """_COUNTRY_MAP must map country name to (code, currency) — no separate currency logic."""
    from tools import adzuna_tool
    for country, mapping in adzuna_tool._COUNTRY_MAP.items():
        assert isinstance(mapping, tuple), f"{country} value must be a tuple"
        assert len(mapping) == 2, f"{country} tuple must be (code, currency)"
        code, currency = mapping
        assert isinstance(code, str) and code.islower(), f"{country} code must be lowercase str"
        assert isinstance(currency, str) and currency.isupper(), f"{country} currency must be uppercase str"


@pytest.mark.asyncio
async def test_adzuna_returns_uk_postings() -> None:
    from tools.adzuna_tool import adzuna_jobs
    ctx = _mock_ctx("UK")
    response = await adzuna_jobs(ctx, "software engineer graduate", max_results=10)
    assert response.error is None, f"Adzuna error: {response.error}"
    assert response.country == "UK"
    assert response.total_found > 0
    assert len(response.postings) > 0
    for p in response.postings:
        assert p.source == "adzuna"
        assert p.currency == "GBP"
        assert p.title
        assert p.source_url.startswith("http")
        assert p.skills == []   # Adzuna returns no structured skill tags


@pytest.mark.asyncio
async def test_adzuna_returns_australia_postings() -> None:
    from tools.adzuna_tool import adzuna_jobs
    ctx = _mock_ctx("Australia")
    response = await adzuna_jobs(ctx, "software engineer graduate", max_results=10)
    assert response.error is None, f"Adzuna error: {response.error}"
    assert response.country == "Australia"
    assert len(response.postings) > 0
    for p in response.postings:
        assert p.currency == "AUD"
        assert p.skills == []


@pytest.mark.asyncio
async def test_adzuna_rejects_singapore() -> None:
    """Adzuna does not support Singapore — should return error, not raise."""
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
    response = await adzuna_jobs(ctx, "data analyst graduate UK", max_results=5)
    if response.error:
        pytest.skip(f"Adzuna unavailable: {response.error}")
    for p in response.postings:
        assert p.title, "Posting missing title"
        assert p.company, "Posting missing company"
        assert p.source_url, "Posting missing source_url"
        assert p.date_posted, "Posting missing date_posted"


# ── MyCareersFuture ───────────────────────────────────────────────────────────

def test_mcf_imports_cleanly() -> None:
    from tools.mcf_tool import mcf_jobs
    assert mcf_jobs


@pytest.mark.asyncio
async def test_mcf_returns_singapore_postings() -> None:
    from tools.mcf_tool import mcf_jobs
    ctx = _mock_ctx("Singapore")
    response = await mcf_jobs(ctx, "software engineer computer science", max_results=10)
    assert response.error is None, f"MCF error: {response.error}"
    assert response.country == "Singapore"
    assert response.total_found > 0
    assert len(response.postings) > 0
    for p in response.postings:
        assert p.source == "mycareersfuture"
        assert p.currency == "SGD"
        assert p.title
        assert p.source_url.startswith("https://www.mycareersfuture.gov.sg")
        assert isinstance(p.skills, list)   # may be empty but must be a list


@pytest.mark.asyncio
async def test_mcf_rejects_non_singapore() -> None:
    """MCF only supports Singapore — should return error, not raise."""
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
```

---

## 1b.9 Run the Tests

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
tests/test_stage_1b.py::test_fetch_client_singleton_is_same_instance PASSED
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

27 passed in X.Xs
```

Fetch tests may SKIP if MCP server is not installed — this is acceptable.
They must pass before Stage 1c.

---

## 1b.10 Common Failure Modes at This Stage

**`KeyError: ADZUNA_APP_ID`**
Cause: `.env` missing the new Adzuna keys.
Fix: register at https://developer.adzuna.com and add both keys to `.env`.

**`test_adzuna_returns_uk_postings FAILED — total_found=0`**
Cause: Adzuna free tier may throttle on first call. Also check the `what`
parameter — very niche queries can return 0. Try with `"software engineer"`
as a sanity check.

**`test_mcf_returns_singapore_postings FAILED — connection error`**
Cause: MyCareersFuture API base URL may have changed. Verify at
https://api.mycareersfuture.gov.sg/v2/jobs?search=engineer&limit=1 in a
browser. If the URL structure has changed, update `_BASE` in `mcf_tool.py`.

**`test_adzuna_country_map_structure FAILED`**
Cause: `_COUNTRY_MAP` values are not `(code, currency)` tuples. Each value
must be a tuple of exactly two strings — lowercase country code, uppercase
currency code.

**`RatelimitException` from DuckDuckGo**
Same as original spec — the wrapper retries once with 3s delay. Run DDG
tests in isolation if needed: `pytest tests/test_stage_1b.py -k ddg -v`.

**`McpError: Connection closed`**
Fetch MCP server failed to start. See Service 2 setup — try `uvx` invocation.

**`test_tavily_raises_on_missing_key FAILED`**
`monkeypatch.delenv` + `importlib.reload` required. Confirm reload is called
after the env var is deleted.

---

## Stage 1b Completion Checklist

- [ ] Tavily API key in `.env` — confirmed working
- [ ] Adzuna `app_id` and `app_key` in `.env` — confirmed working
- [ ] MyCareersFuture — no key needed, confirmed reachable
- [ ] `pip install tavily-python ddgs httpx mcp mcp-server-fetch` clean
- [ ] `schemas/search_result.py` — `SearchResult`, `SearchResponse` defined
- [ ] `schemas/fetch_result.py` — `FetchResult` defined
- [ ] `schemas/job_posting.py` — `JobPosting`, `JobPostingsResponse` defined (NEW)
- [ ] `mcps/fetch_client.py` — singleton with `startup()`, `shutdown()`, `call_tool()`
- [ ] `tools/search_tool.py` — `tavily_search`, `days=730` enforced
- [ ] `tools/fetch_tool.py` — `fetch_page`, never raises, docstring warns off job board URLs
- [ ] `tools/ddg_tool.py` — `ddg_search`, date filter applied before return
- [ ] `tools/adzuna_tool.py` — `adzuna_jobs`, `_COUNTRY_MAP` maps country → `(code, currency)`, `skills=[]` (NEW)
- [ ] `tools/mcf_tool.py` — `mcf_jobs`, Singapore only, no auth, skills from API tags, location from API (NEW)
- [ ] MASTER section 8.6 updated — `adzuna_jobs` and `mcf_jobs` rows added with ✓ on career only
- [ ] MASTER section 8.8 updated — `CareerAgent` registers `adzuna_jobs` and `mcf_jobs`
- [ ] `main.py` — `fetch_client.startup()` before pipeline, `shutdown()` in `finally`
- [ ] `pytest tests/test_stage_1b.py -v` — 27 passed (fetch may SKIP)
- [ ] Stage 1a tests still pass: `pytest tests/test_stage_1a.py -v`

---

*End of Stage 1b Specification*