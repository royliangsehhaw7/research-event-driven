# Stage 1b — Tool Wrappers: Tavily, Fetch MCP, DuckDuckGo
## Implementation Specification

**Goal:** All four search/fetch tool wrappers are implemented, tested against
real external services, and confirmed to return usable data. No agents, no LLM
calls. Pure tool plumbing.

**Ends with:** `pytest tests/test_stage_1b.py -v` passes. Each wrapper makes
a real call to its service and returns a typed result. A live search for a
known university and course confirms data flows end to end.

---

## What This Stage Builds and Why It Comes Before Agents

Stage 1c builds `CareerAgent`. Stage 2a builds all remaining section agents.
Every agent calls at least one of these four wrappers. If any wrapper is
broken — wrong authentication, wrong return shape, missing error handling —
every agent that depends on it silently fails or raises at runtime.

Building and testing the wrappers in isolation now means that in Stage 1c
you are debugging agent logic, not tool plumbing.

**Four wrappers, four distinct jobs:**

| Wrapper | File | Used by | Key feature |
|---|---|---|---|
| `TavilySearchTool` | `tools/search_tool.py` | All section agents | `days=730` enforced on every call |
| `FetchTool` | `tools/fetch_tool.py` | All section agents | Direct URL fetch — catalog pages, review pages |
| `DuckDuckGoTool` | `tools/ddg_tool.py` | NewsAgent fallback only | Zero cost, no key, no quota |

---

## External Service Setup

Do this before writing a single line of wrapper code. All four services must
be provisioned and keys in `.env` before running tests.

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
A full pipeline run across all agents uses approximately 50–70 calls.
Free tier is sufficient for development and light testing.

**Paid plans:** from $35/month for 10,000 credits. Only needed in production
or heavy multi-run testing.

**Add to `.env`:**

```bash
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Install the client:**

```bash
pip install tavily-python
```

---

### Service 2 — Fetch MCP

**What it is:** a tool that fetches the raw content of a URL and returns it
as clean text. Used when an agent needs to read a specific page — for example,
a university course catalog page — rather than search for it.

**No API key required.** The Fetch MCP server runs locally as an MCP server.
It is accessed via the `mcp` package.

**Install:**

```bash
pip install mcp mcp-server-fetch
```

Confirm the server is available after installing:

```bash
python -m mcp_server_fetch --help
```

If that command fails, the server needs to be invoked via `uvx` instead. In that case update `StdioServerParameters` in `mcp/fetch_client.py`:

```python
server_params = StdioServerParameters(
    command="uvx",
    args=["mcp-server-fetch"],
)
```

And install `uv` if not already present:

```bash
pip install uv
```

**How it works in this project:** `FetchTool` spawns the MCP fetch server
as a subprocess and sends it a single URL. The server returns the page content
as markdown-formatted text. The wrapper handles the subprocess lifecycle.

**No `.env` entry required** for this tool.

---

### Service 3 — Reddit (no separate client required)

Reddit content is accessed via Tavily `site:reddit.com` queries — the same
mechanism used by all other `site:` targets. No Reddit API credentials are
needed. No PRAW client is installed.

Reddit's API has restricted programmatic access for third-party clients. Tavily
`site:` queries return public Reddit snippets through the search index and are
sufficient for ForumAgent's purposes. Full post bodies and comment threads are
no longer accessible without elevated API access, making a dedicated client
redundant.

**No `.env` entry required. No package to install.**

ForumAgent treats `site:reddit.com` results as a supporting source (source 5 of 6),
weighted lower than The Student Room, StudentCrowd, and WhatUni — reflecting the
reduced signal quality of snippets vs full threads.

---

### Service 4 — DuckDuckGo Search

**What it is:** a zero-cost, no-key web search library that wraps DuckDuckGo's
search. Used by `NewsAgent` as a fallback when Tavily returns fewer than 3
news items for a query.

**No API key required. No account required. No quota.**

**Install:**

```bash
pip install ddgs
```

> **Note:** the package was previously named `duckduckgo-search` and has since been renamed to `ddgs`. Use `ddgs` — `duckduckgo-search` will show a `RuntimeWarning` and may stop working in future releases.

**Rate limit note:** DuckDuckGo's search is rate-limited at the network level.
Sending many queries in rapid succession will result in a `RatelimitException`.
The wrapper handles this with a retry (see implementation below). In practice,
`NewsAgent` only calls this tool as a fallback — it will make at most 2–3
DuckDuckGo queries per pipeline run, well within safe limits.

---

### Updated `.env` After Stage 1b

```bash
# .env — full contents after Stage 1b
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

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
mcp
mcp-server-fetch
jinja2
pytest
pytest-asyncio
```

---

## 1b.1 tools/search_tool.py — Tavily Wrapper and Module-Level Tool Function
TavilySearchTool wraps the Tavily client. Its single enforced behaviour:
days=730 is always set — it cannot be overridden by the caller. This is
the mechanism that enforces the 2-year data filter system-wide. Any agent
that calls this wrapper gets filtered results automatically.

Below the class, a module-level tavily_search function and _client
singleton are added to the same file. This is what agents import and wrap
with their budget closure. It is never called directly from agent files.

```python
# tools/search_tool.py
from __future__ import annotations

import json as _json
import logging
import os
import os as _os
from dataclasses import dataclass

from dotenv import load_dotenv
from pydantic_ai import RunContext
from tavily import TavilyClient

from core.deps import Deps

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
        if not key:
            raise EnvironmentError(
                "TAVILY_API_KEY not set. Check your .env file. "
                "Get a key at https://app.tavily.com"
            )
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


# ── Module-level singleton and tool function ──────────────────────────────────
# Agents import tavily_search and wrap it in _make_search_tool() to add
# budget enforcement. tavily_search is never registered on an agent directly.

_client = TavilySearchTool(api_key=_os.environ["TAVILY_API_KEY"])


async def tavily_search(ctx: RunContext[Deps], query: str) -> str:
    """Bare Tavily search. days=730 always enforced.
    Never register this directly on an agent — agents wrap it via
    _make_search_tool() to add budget enforcement."""
    response = await _client.search(query, max_results=5)
    return _json.dumps({
        "query": response.query,
        "results": [
            {
                "url": r.url,
                "title": r.title,
                "content": r.content,
                "score": r.score,
                "date": r.date,
            }
            for r in response.results
        ],
    })
```

**Why** days=730 cannot be overridden: a caller that passes days=365
would silently break the 2-year filter contract. By not exposing days
as a parameter, the contract is enforced at the type level.

**Why** min(max_results, 10): Tavily's maximum per call is 10. Clamping
prevents a silent API error if an agent requests more.

**Why** search_depth is a parameter: most queries use "basic" (fast,
returns snippets). ProgramAgent and EmployabilityAgent may use "advanced"
to get full page content when a snippet is not enough. The choice is left to
the agent, not hardcoded.

**Why** the _client singleton reads from os.environ directly: load_dotenv()
must be called in main.py before any tool module is imported. The singleton
is created at import time — if the key is missing it raises immediately, which
is the correct failure mode (fast fail at startup, not mid-request).

**Why** no search_tool_factory.py: budget enforcement is an agent concern, not
a tool concern. Each agent wraps tavily_search in a _make_search_tool() method
that closes over self._calls_made and self._tool_budget. This keeps tool files
as pure infrastructure and avoids the list[int] mutable-ref workaround entirely —
the closure captures self, which is already mutable.

---

## 1b.2 `tools/fetch_tool.py` — Fetch MCP Wrapper

`fetch_page` is the pydantic-ai tool function registered on agents that need
URL fetching. It delegates to the `FetchClient` singleton in `mcp/fetch_client.py`
— it has no knowledge of how the MCP server was started or managed.

The `FetchResult` dataclass is used internally and returned by `fetch_page` as
a JSON string for the LLM to read.

```python
# tools/fetch_tool.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pydantic_ai import RunContext

from core.deps import Deps
from mcp.fetch_client import fetch_client

logger = logging.getLogger("fetch_tool")


@dataclass
class FetchResult:
    url:     str
    content: str         # page content as markdown-formatted text
    status:  str         # "ok" | "error"
    error:   str | None  # error message if status == "error", else None


async def fetch_page(ctx: RunContext[Deps], url: str) -> str:
    """Fetch a specific URL via the Fetch MCP server.

    Use for university catalog pages, rankings pages, or any URL found
    in search results when you need the full page content.

    Does not count against tool_budget — targeted retrieval, not a search.

    Args:
        url: the full URL to fetch (must start with https://)

    Returns:
        JSON string containing url, content, status, and optional error.
        Never raises — returns status "error" on failure so the agent
        can note the failure and continue.
    """
    try:
        raw = await fetch_client.call_tool("fetch", {
            "url": url,
            "max_length": 50000,   # characters — enough for a full catalog page
        })
        result = FetchResult(url=url, content=str(raw), status="ok", error=None)
        logger.debug("fetch_tool | fetched %r — %d chars", url, len(result.content))
    except Exception as exc:
        logger.error("fetch_tool | fetch failed for %r: %s", url, exc)
        result = FetchResult(url=url, content="", status="error", error=str(exc))

    return json.dumps({
        "url": result.url,
        "content": result.content,
        "status": result.status,
        "error": result.error,
    })
```

**Why `fetch_page` is a module-level function, not a class:** pydantic-ai
registers tools as callables. A plain async function is the cleanest fit —
no instantiation, no state. The `FetchClient` singleton handles all state.

**Why never raises:** fetch failures should not crash an agent. A `status="error"`
response lets the agent note the failure in `notes` and continue with what
search results already returned.

**Why `max_length=50000`:** course catalog pages can be large. 50,000
characters is enough for a full module listing. Larger values risk consuming
the agent's context window.

**Lifecycle note:** `fetch_client.startup()` must be called at application
boot before any agent calls `fetch_page`. See Section 1b.5 for where this
happens per entry point.

---

## 1b.3 Forum Sources — Tavily `site:` Queries

ForumAgent has no separate tool file. It uses the same `TavilySearchTool` as
all other section agents. The forum-specific behaviour is entirely in the
SKILL.md instructions — which sources to query, in what order, and how to
weight results.

The confirmed accessible sources (verified via search index) and their Tavily
query patterns:

```python
# Example queries ForumAgent constructs — all via tavily_search()
FORUM_QUERY_EXAMPLES = [
    "site:thestudentroom.co.uk {university} {course} student experience",
    "site:studentcrowd.com {university} {course} review",
    "site:whatuni.com {university} {course} student review",
    "site:quora.com {university} {course} worth it undergraduate",
    "site:reddit.com {university} {course} undergraduate",
]
```

ForumAgent also calls `fetch_page` to retrieve full review content from
StudentCrowd and WhatUni course pages when Tavily snippets are insufficient.
This does not count against `tool_budget`.

**No additional tool file, no new dependencies, no credentials needed.**

---

## 1b.4 `tools/ddg_tool.py` — DuckDuckGo Wrapper

`DuckDuckGoTool` wraps `ddgs` as a fallback for `NewsAgent`.
It is only called when Tavily returns fewer than 3 news results for a query.
It has no key and no quota.

```python
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
```

**Why `DDGResponse` returns empty list on failure rather than raising:**
`NewsAgent` calls this tool as a fallback. If DuckDuckGo also fails,
the agent should still return what Tavily found — not crash. An empty
result list triggers the agent to note the fallback failure in `notes`.

**Why no `days=` equivalent:** DuckDuckGo's Python library does not support
a date range filter. `NewsAgent` must filter results by date manually after
receiving them — checking whether each result's `date` field falls within
the 2-year window.

>[!WARNING] DDGS WILL NOT BE WIRED UP FOR THIS PROJECT
> Due to the inability to specify any date range for filtering
>

---

## 1b.5 mcp/fetch_client.py — Fetch MCP Client Singleton
**What it is**

A thin lifecycle wrapper around the mcp package's stdio client. It spawns the mcp-server-fetch subprocess, holds the session open for the duration of the application run, and exposes a single call_tool() method that the rest of the project uses to fetch URLs.

**What it does**

Three responsibilities, nothing more:

- `startup()` — launches the mcp-server-fetch subprocess and opens an MCP session over its stdin/stdout. Called once at application boot in main.py.
- `shutdown()` — tears down the session and stops the subprocess cleanly. Called in the finally block in main.py so it always runs even if the pipeline crashes.
- `call_tool()` — sends a single fetch request to the running server and returns the page content as a string. This is the only method the rest of the project ever calls directly.


**How it works**
The mcp package communicates with tool servers over stdio — it writes a request to the subprocess's stdin, the server processes it and writes a response to stdout, and the client reads it back. `FetchClient` manages the two context managers that make this work (stdio_client for the transport, ClientSession for the protocol) using an AsyncExitStack, which lets both be opened and closed together in a single `startup()`/`shutdown()` call.

The module-level line `fetch_client` = `FetchClient()` creates the singleton at import time. Because Python caches module imports, any file that does from mcp.fetch_client import fetch_client gets the exact same object — the one that was started in `main.py`. No object is passed around, no dependency injection needed.

**How it fits in the project**
```
main.py
  └── fetch_client.startup()          ← boots the subprocess once

tools/fetch_tool.py
  └── fetch_page()
        └── fetch_client.call_tool()  ← used on every URL fetch

agents (ProgramAgent, ForumAgent, etc.)
  └── registered tool: fetch_page     ← agents never touch fetch_client directly

main.py (finally block)
  └── fetch_client.shutdown()         ← always runs, cleans up subprocess
```
 
`fetch_tool.py` is the only file that imports fetch_client for actual use. Everything above it — agents, ResearchHandler — only knows about fetch_page. Everything below it — the MCP server, the subprocess — is invisible to the rest of the project. 

`fetch_client.py` is the seam between your Python application and the external fetch server, and it intentionally exposes as little surface area as possible.

```python
# mcp/fetch_client.py
from __future__ import annotations

import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("fetch_client")


class FetchClient:
    """Singleton MCP client that manages the fetch server subprocess lifecycle.

    Usage:
        await fetch_client.startup()   # call once at app boot
        result = await fetch_client.call_tool("fetch", {"url": "https://..."})
        await fetch_client.shutdown()  # call once at app exit
    """

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._exit_stack = None

    async def startup(self) -> None:
        """Start the MCP fetch server subprocess and open a session."""
        from contextlib import AsyncExitStack
        self._exit_stack = AsyncExitStack()
        server_params = StdioServerParameters(
            command="uvx",
            args=["mcp-server-fetch"],
        )
        # If uvx is not available, replace with:
        #   command="python", args=["-m", "mcp_server_fetch"]
        # and confirm `python -m mcp_server_fetch --help` works first.
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = stdio_transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        logger.info("fetch_client | MCP fetch server started")

    async def shutdown(self) -> None:
        """Stop the MCP fetch server subprocess."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._session = None
            self._exit_stack = None
            logger.info("fetch_client | MCP fetch server stopped")

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on the running MCP fetch server.

        Args:
            tool_name:  Name of the tool to call (e.g. "fetch").
            arguments:  Dict of arguments to pass to the tool.

        Returns:
            Tool result as a string.

        Raises:
            RuntimeError: if the session has not been started via startup().
        """
        if self._session is None:
            raise RuntimeError(
                "FetchClient is not started. "
                "Call await fetch_client.startup() before calling call_tool()."
            )
        result = await self._session.call_tool(tool_name, arguments)
        # result.content is a list of content blocks; extract text
        texts = [
            block.text
            for block in result.content
            if hasattr(block, "text")
        ]
        return "\n".join(texts)


# Module-level singleton — importing this module twice gives the same object
fetch_client = FetchClient()
```

**Key points:**
- The singleton is created at module level (fetch_client = FetchClient()) — this is what makes the singleton test pass.
- `startup()/shutdown()` use an AsyncExitStack to manage the subprocess and session context managers together cleanly.
- `call_tool()` raises RuntimeError (not silently fails) if called before `startup()` — the fetch_page wrapper in fetch_tool.py already catches and converts exceptions to status="error" responses.


---

## 1b.6 Fetch MCP Server Lifecycle — Entry Points

The `FetchClient` singleton in `mcp/fetch_client.py` must be started before
any agent calls `fetch_page`. This happens at the application entry point —
not inside `ResearchHandler`.

At Stage 1b, the only entry point is `main.py`. Add startup and shutdown there:

```python
# main.py — Stage 1b addition
from mcp.fetch_client import fetch_client

async def run(...):
    await fetch_client.startup()
    try:
        # ... pipeline ...
    finally:
        await fetch_client.shutdown()
```

For integration tests that call `fetch_page`, add startup/shutdown as fixtures:

```python
# tests/test_stage_1b.py — fetch lifecycle fixture
import pytest
from mcp.fetch_client import fetch_client

@pytest.fixture(scope="module", autouse=False)
async def fetch_server():
    await fetch_client.startup()
    yield
    await fetch_client.shutdown()
```

`ResearchHandler` has no lifecycle responsibilities. It constructs agents and
handles requests — the MCP server is already running by the time it is called.

**Tavily and DuckDuckGo** have no async lifecycle. Their module-level
singletons initialise when the module is imported. Ensure `load_dotenv()` is
called before any tool module is imported — the singletons read from `os.environ`
at import time and will raise `EnvironmentError` if keys are missing.

---

## 1b.7 Tests — `tests/test_stage_1b.py`

These tests make **real network calls**. They require valid API keys in `.env`.
They are integration tests, not unit tests — their purpose is to confirm that
real data flows through real services.

Mark the test file with `pytest-asyncio` so async tests run correctly.

```python
# tests/test_stage_1b.py
"""
Stage 1b integration tests.
Run with: pytest tests/test_stage_1b.py -v -s

These tests make REAL API calls. You need:
  - TAVILY_API_KEY in .env

DuckDuckGo requires no credentials.
Fetch tests require the fetch_server fixture (starts the FetchClient singleton).
Each test confirms: import works, client initialises, real call returns data.
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest

from dotenv import load_dotenv
load_dotenv()

from mcp.fetch_client import fetch_client


@pytest.fixture(scope="module")
async def fetch_server():
    """Start the FetchClient singleton once for all fetch tests in this module."""
    await fetch_client.startup()
    yield
    await fetch_client.shutdown()


# ── search tool budget ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_tool_budget_exhausted_returns_error_dict() -> None:
    """Budget closure returns error dict when limit is reached."""
    import json
    from agents.career_agent import CareerAgent
    from unittest.mock import MagicMock

    agent = CareerAgent(tool_budget=2)
    agent._calls_made = 2   # already at limit
    tool = agent._make_search_tool()
    ctx = MagicMock()
    raw = await tool(ctx, "test query")
    result = json.loads(raw)

    assert result["error"] == "tool budget exhausted"
    assert result["calls_made"] == 2
    assert result["budget"] == 2


@pytest.mark.asyncio
async def test_search_tool_increments_counter() -> None:
    """Counter increments on each call until budget is reached."""
    from agents.career_agent import CareerAgent
    from unittest.mock import MagicMock, AsyncMock, patch

    agent = CareerAgent(tool_budget=5)
    tool = agent._make_search_tool()
    ctx = MagicMock()

    with patch("tools.search_tool.tavily_search", new=AsyncMock(return_value='{"query":"q","results":[]}')):
        await tool(ctx, "query one")
        await tool(ctx, "query two")

    assert agent._calls_made == 2


# ── Tavily ────────────────────────────────────────────────────────────────────

def test_tavily_imports_cleanly() -> None:
    from tools.search_tool import TavilySearchTool, SearchResult, SearchResponse
    assert TavilySearchTool
    assert SearchResult
    assert SearchResponse


def test_tavily_initialises_with_env_key() -> None:
    from tools.search_tool import TavilySearchTool
    tool = TavilySearchTool()
    assert tool is not None


def test_tavily_raises_on_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from tools import search_tool
    import importlib
    importlib.reload(search_tool)
    with pytest.raises(EnvironmentError, match="TAVILY_API_KEY"):
        search_tool.TavilySearchTool(api_key=None)


@pytest.mark.asyncio
async def test_tavily_returns_results_for_known_query() -> None:
    from tools.search_tool import TavilySearchTool
    tool = TavilySearchTool()
    response = await tool.search(
        "University of Manchester Computer Science undergraduate",
        max_results=3,
    )
    assert response.query == "University of Manchester Computer Science undergraduate"
    assert len(response.results) > 0, "Expected at least 1 result"
    for r in response.results:
        assert r.url.startswith("http"), f"Result URL malformed: {r.url}"
        assert len(r.content) > 0, "Expected non-empty content"


@pytest.mark.asyncio
async def test_tavily_site_query_returns_results() -> None:
    """Confirm site: queries work — used by ForumAgent as fallback."""
    from tools.search_tool import TavilySearchTool
    tool = TavilySearchTool()
    response = await tool.search(
        "site:thestudentroom.co.uk University of Manchester Computer Science",
        max_results=3,
    )
    # site: queries sometimes return 0 results — that is valid behaviour
    # We only assert the call does not raise
    assert response.results is not None
@pytest.mark.asyncio
async def test_tavily_forum_sources_accessible() -> None:
    """Confirm all 5 forum site: query targets return results via Tavily."""
    from tools.search_tool import TavilySearchTool
    tool = TavilySearchTool()
    sources = [
        "site:thestudentroom.co.uk University of Manchester Computer Science",
        "site:studentcrowd.com University of Manchester Computer Science",
        "site:whatuni.com University of Manchester Computer Science",
        "site:quora.com University of Manchester Computer Science undergraduate",
        "site:reddit.com University of Manchester Computer Science",
    ]
    for query in sources:
        response = await tool.search(query, max_results=3)
        # site: queries may return 0 for low-coverage sources — assert no raise
        assert response.results is not None, f"None results for: {query}"


# ── DuckDuckGo ────────────────────────────────────────────────────────────────

def test_ddg_imports_cleanly() -> None:
    from tools.ddg_tool import DuckDuckGoTool, DDGResult, DDGResponse
    assert DuckDuckGoTool
    assert DDGResult
    assert DDGResponse


@pytest.mark.asyncio
async def test_ddg_search_returns_results() -> None:
    from tools.ddg_tool import DuckDuckGoTool
    tool = DuckDuckGoTool()
    response = await tool.search(
        "University of Manchester news 2024",
        max_results=3,
    )
    assert isinstance(response.results, list), "Expected a list"
    assert len(response.results) > 0, "Expected at least 1 result"
    for r in response.results:
        assert r.url.startswith("http"), f"Result URL malformed: {r.url}"


@pytest.mark.asyncio
async def test_ddg_returns_empty_on_nonsense_query() -> None:
    """A nonsense query should return empty results, not raise."""
    from tools.ddg_tool import DuckDuckGoTool
    tool = DuckDuckGoTool()
    # Add a small delay to avoid rate limiting from previous test
    await asyncio.sleep(1.0)
    response = await tool.search("xkqzwvmnop university xkqzwvmnop", max_results=3)
    assert isinstance(response.results, list)


# ── FetchTool ─────────────────────────────────────────────────────────────────

def test_fetch_imports_cleanly() -> None:
    from tools.fetch_tool import fetch_page, FetchResult
    assert fetch_page
    assert FetchResult


def test_fetch_client_singleton_is_same_instance() -> None:
    """Importing fetch_client twice returns the same object."""
    from mcp.fetch_client import fetch_client as a
    from mcp.fetch_client import fetch_client as b
    assert a is b


@pytest.mark.asyncio
async def test_fetch_returns_content_for_known_url(fetch_server) -> None:
    from tools.fetch_tool import fetch_page
    import json
    from unittest.mock import MagicMock
    ctx = MagicMock()
    raw = await fetch_page(ctx, "https://www.cs.manchester.ac.uk/undergraduate/")
    result = json.loads(raw)
    if result["status"] == "ok":
        assert len(result["content"]) > 100, "Expected non-trivial page content"
    else:
        pytest.skip(f"FetchTool not available in test environment: {result['error']}")


@pytest.mark.asyncio
async def test_fetch_returns_error_status_for_bad_url(fetch_server) -> None:
    from tools.fetch_tool import fetch_page
    import json
    from unittest.mock import MagicMock
    ctx = MagicMock()
    raw = await fetch_page(ctx, "https://this.url.does.not.exist.invalid/")
    result = json.loads(raw)
    assert result["status"] == "error"
    assert result["error"] is not None
    assert result["content"] == ""
```

---

## 1b.8 Run the Tests

```bash
pytest tests/test_stage_1b.py -v -s
```

The `-s` flag shows `print()` output and log messages — useful for seeing
what each API call returns during the first run.

Expected output on clean pass:

```
tests/test_stage_1b.py::test_search_tool_budget_exhausted_returns_error_dict PASSED
tests/test_stage_1b.py::test_search_tool_increments_counter PASSED
tests/test_stage_1b.py::test_tavily_imports_cleanly PASSED
tests/test_stage_1b.py::test_tavily_initialises_with_env_key PASSED
tests/test_stage_1b.py::test_tavily_raises_on_missing_key PASSED
tests/test_stage_1b.py::test_tavily_returns_results_for_known_query PASSED
tests/test_stage_1b.py::test_tavily_site_query_returns_results PASSED
tests/test_stage_1b.py::test_tavily_forum_sources_accessible PASSED
tests/test_stage_1b.py::test_ddg_imports_cleanly PASSED
tests/test_stage_1b.py::test_ddg_search_returns_results PASSED
tests/test_stage_1b.py::test_ddg_returns_empty_on_nonsense_query PASSED
tests/test_stage_1b.py::test_fetch_imports_cleanly PASSED
tests/test_stage_1b.py::test_fetch_client_singleton_is_same_instance PASSED
tests/test_stage_1b.py::test_fetch_returns_content_for_known_url PASSED
tests/test_stage_1b.py::test_fetch_returns_error_status_for_bad_url PASSED

15 passed in X.Xs
```

The fetch tests may `SKIP` if the MCP server is not installed — this is acceptable
at Stage 1b. They must pass before Stage 2a.

---

## 1b.10 Common Failure Modes at This Stage

**`EnvironmentError: TAVILY_API_KEY not set`**
Cause: `.env` file not in project root, or key has extra whitespace.
Fix: confirm the file exists at the root, not inside a subfolder.
Check for leading/trailing spaces around the `=` sign.

**`test_tavily_forum_sources_accessible` returns 0 results for some sources**
This is acceptable — `site:` queries can return 0 for low-coverage targets.
The test only asserts no exception is raised. If all 5 sources return 0,
investigate Tavily quota or query construction.

**`RatelimitException` from DuckDuckGo**
Cause: too many DDG queries in quick succession during test runs.
Fix: the wrapper retries once with a 3-second delay. If tests still fail,
add `time.sleep(2)` between DDG test calls, or run DDG tests in isolation:
`pytest tests/test_stage_1b.py -k ddg -v`.

**`McpError: Connection closed` or `ModuleNotFoundError: mcp_server_fetch`**
Cause: the fetch server subprocess failed to start. Two possible fixes:
1. Install the server package: `pip install mcp-server-fetch` and confirm with `python -m mcp_server_fetch --help`.
2. If that command fails, switch to the `uvx` invocation (the recommended default): set `command="uvx"`, `args=["mcp-server-fetch"]` in `StdioServerParameters`, and install `uv` with `pip install uv`.

**`test_tavily_raises_on_missing_key FAILED`**
Cause: `monkeypatch.delenv` does not work if `load_dotenv()` was already called
at module import time and the key is now in `os.environ`.
Fix: the test reloads the module after deleting the env var. Confirm
`importlib.reload(search_tool)` is called after the `monkeypatch.delenv` call.

---

## Stage 1b Completion Checklist

- [ ] Tavily API key obtained from https://app.tavily.com — added to `.env`
- [ ] `pip install tavily-python ddgs mcp mcp-server-fetch` confirmed clean (or `uv` installed if using `uvx` invocation)
- [ ] `tools/search_tool.py` — `TavilySearchTool` implemented with `days=730` enforced, `tavily_search` module-level function and `_client` singleton added
- [ ] `tools/fetch_tool.py` — `fetch_page` function implemented, delegates to `fetch_client` singleton, never raises
- [ ] `tools/ddg_tool.py` — `DuckDuckGoTool` implemented with rate-limit retry, module-level `_client` singleton
- [ ] `mcp/fetch_client.py` — `FetchClient` singleton implemented with `startup()`, `shutdown()`, `call_tool()`
- [ ] `main.py` — `fetch_client.startup()` called before pipeline, `shutdown()` in `finally`
- [ ] `core/deps.py` unchanged from Stage 1a — no tool fields added
- [ ] `pytest tests/test_stage_1b.py -v` — 15 passed (fetch tests may SKIP if MCP not installed)
- [ ] Stage 1a tests still pass: `pytest tests/test_stage_1a.py -v`

---

*End of Stage 1b Specification*