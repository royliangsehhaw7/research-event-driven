# Stage 1b — Tool Wrappers: Tavily, Fetch MCP, Reddit API (PRAW), DuckDuckGo
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
| `FetchTool` | `tools/fetch_tool.py` | ProgramAgent, BackgroundAgent | Direct URL fetch — catalog pages |
| `RedditTool` | `tools/reddit_tool.py` | ForumAgent only | Full post bodies + comment threads via PRAW |
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
pip install mcp
```

**How it works in this project:** `FetchTool` spawns the MCP fetch server
as a subprocess and sends it a single URL. The server returns the page content
as markdown-formatted text. The wrapper handles the subprocess lifecycle.

**No `.env` entry required** for this tool.

---

### Service 3 — Reddit API (PRAW)

**What it is:** the official Reddit API Python wrapper. Used exclusively by
`ForumAgent`. Returns full post bodies, comment threads, upvote scores, and
subreddit metadata — data quality that `site:reddit.com` Tavily queries cannot
match because Tavily only returns snippets from Reddit's public search index.

**How to get Reddit API credentials:**

1. Log in to Reddit at **https://www.reddit.com**
   (Create an account if you don't have one — a throwaway is fine)
2. Go to **https://www.reddit.com/prefs/apps**
3. Scroll to the bottom and click **"are you a developer? create an app..."**
4. Fill in the form:
   - **Name:** anything, e.g. `university-research-tool`
   - **App type:** select **"script"** — this is important. Script apps use
     password-based auth and work for read-only bots without OAuth redirects.
   - **Description:** optional
   - **About URL:** leave blank
   - **Redirect URI:** enter `http://localhost:8080` — required even for script
     apps. The value does not matter as long as it is a valid URL.
5. Click **"Create app"**
6. Your credentials are now shown:
   - **client_id:** the string shown directly under the app name and the word
     "personal use script" — a short alphanumeric string
   - **client_secret:** labelled "secret"
7. Copy both values.

**Free tier:** Reddit's API is free for read-only script access.
The rate limit is 100 requests per minute per OAuth client — well above
what this project needs (ForumAgent uses 10 calls maximum).

**PRAW also requires your Reddit username and password** for script-type
authentication. Add all four values to `.env`:

```bash
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
```

> **Note on `REDDIT_USERNAME` and `REDDIT_PASSWORD`:** these are only used
> for the initial OAuth token exchange. PRAW does not store or transmit your
> password beyond that. If you are uncomfortable using your main account,
> create a throwaway. The account needs no special permissions — read-only
> access to public subreddits is sufficient.

**Install the client:**

```bash
pip install praw
```

---

### Service 4 — DuckDuckGo Search

**What it is:** a zero-cost, no-key web search library that wraps DuckDuckGo's
search. Used by `NewsAgent` as a fallback when Tavily returns fewer than 3
news items for a query.

**No API key required. No account required. No quota.**

**Install:**

```bash
pip install duckduckgo-search
```

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
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password

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
praw
duckduckgo-search
mcp
jinja2
pytest
pytest-asyncio
```

---

## 1b.1 `tools/search_tool.py` — Tavily Wrapper

`TavilySearchTool` wraps the Tavily client. Its single enforced behaviour:
`days=730` is always set — it cannot be overridden by the caller. This is
the mechanism that enforces the 2-year data filter system-wide. Any agent
that calls this wrapper gets filtered results automatically.

```python
# tools/search_tool.py
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
```

**Why `days=730` cannot be overridden:** a caller that passes `days=365`
would silently break the 2-year filter contract. By not exposing `days`
as a parameter, the contract is enforced at the type level.

**Why `min(max_results, 10)`:** Tavily's maximum per call is 10. Clamping
prevents a silent API error if an agent requests more.

**Why `search_depth` is a parameter:** most queries use `"basic"` (fast,
returns snippets). `ProgramAgent` and `EmployabilityAgent` may use `"advanced"`
to get full page content when a snippet is not enough. The choice is left to
the agent, not hardcoded.

---

## 1b.2 `tools/fetch_tool.py` — Fetch MCP Wrapper

`FetchTool` fetches a specific URL and returns its content as plain text.
Used when an agent has a URL already (from a prior search result) and needs
the full page — for example, to read a course catalog page that a search
result pointed to.

```python
# tools/fetch_tool.py
from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger("fetch_tool")


@dataclass
class FetchResult:
    url:     str
    content: str    # page content, markdown-formatted text
    status:  str    # "ok" | "error"
    error:   str | None  # error message if status == "error"


from dataclasses import dataclass


class FetchTool:
    """Wraps the MCP fetch server for direct URL content retrieval.

    Spawns the MCP fetch server as a subprocess, sends a single fetch
    request, returns the page content as text, then closes the subprocess.

    Usage:
        tool = FetchTool()
        result = await tool.fetch("https://www.cs.manchester.ac.uk/undergraduate/")
        print(result.content)
    """

    async def fetch(self, url: str) -> FetchResult:
        """Fetch a URL via the MCP fetch server.

        Returns FetchResult with status "ok" and content on success,
        or status "error" and error message on failure.
        Never raises — always returns a FetchResult.
        """
        try:
            result = await self._run_fetch(url)
            return result
        except Exception as exc:
            logger.error("fetch_tool | fetch failed for %r: %s", url, exc)
            return FetchResult(url=url, content="", status="error", error=str(exc))

    async def _run_fetch(self, url: str) -> FetchResult:
        """Spawn mcp fetch server, send request, return result."""
        # MCP fetch server command
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "mcp_server_fetch",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # JSON-RPC request to the MCP fetch tool
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "fetch",
                "arguments": {
                    "url": url,
                    "max_length": 50000,   # characters — enough for a catalog page
                }
            }
        }) + "\n"

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(request.encode()),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"FetchTool: timeout after 30s fetching {url}")

        if proc.returncode != 0:
            raise RuntimeError(
                f"FetchTool: MCP server error (exit {proc.returncode}): "
                f"{stderr.decode()[:200]}"
            )

        try:
            response = json.loads(stdout.decode())
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"FetchTool: invalid JSON response: {exc}") from exc

        if "error" in response:
            return FetchResult(
                url=url,
                content="",
                status="error",
                error=response["error"].get("message", "unknown error"),
            )

        content = ""
        result_data = response.get("result", {})
        for block in result_data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        logger.debug("fetch_tool | fetched %r — %d chars", url, len(content))
        return FetchResult(url=url, content=content, status="ok", error=None)
```

**Why never raises:** fetch failures should not crash an agent. A `FetchResult`
with `status="error"` lets the agent decide what to do — typically log the
failure, note it in `notes`, and proceed with what search results already
returned.

**Why `max_length=50000`:** course catalog pages can be large. 50,000
characters is enough for a full module listing. Larger values risk
consuming the agent's context window.

---

## 1b.3 `tools/reddit_tool.py` — PRAW Wrapper

`RedditTool` wraps PRAW for structured Reddit search. `ForumAgent` uses it
as its primary source because it returns full post bodies, comment threads,
and upvote scores — signal quality that `site:reddit.com` Tavily queries
cannot provide.

```python
# tools/reddit_tool.py
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import praw
from dotenv import load_dotenv

logger = logging.getLogger("reddit_tool")


@dataclass
class RedditComment:
    body:   str
    score:  int    # upvotes minus downvotes
    author: str    # username, or "[deleted]"


@dataclass
class RedditPost:
    url:          str
    title:        str
    body:         str          # selftext — empty string for link posts
    score:        int          # post upvotes
    subreddit:    str          # e.g. "UniUK"
    created_utc:  float        # Unix timestamp
    top_comments: list[RedditComment] = field(default_factory=list)
    num_comments: int = 0


@dataclass
class RedditSearchResponse:
    query:    str
    subreddit: str           # subreddit searched — "all" if cross-subreddit
    posts:    list[RedditPost]


class RedditTool:
    """PRAW wrapper for Reddit search. Used exclusively by ForumAgent.

    Returns full post bodies and top comments — not just snippets.
    This is the primary differentiator vs site:reddit.com Tavily queries.

    Usage:
        tool = RedditTool()
        response = await tool.search(
            query="University of Manchester Computer Science student experience",
            subreddits=["UniUK", "AskUK"],
            limit=10,
        )
        for post in response.posts:
            print(post.title, post.body[:200])
    """

    # Subreddits ForumAgent searches by default for UK universities.
    # ProgramAgent passes explicit subreddit lists when targeting university-specific subs.
    DEFAULT_SUBREDDITS = ["UniUK", "AskUK", "6thForm", "GCSE"]

    def __init__(self) -> None:
        load_dotenv()
        client_id     = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        username      = os.getenv("REDDIT_USERNAME")
        password      = os.getenv("REDDIT_PASSWORD")

        missing = [
            k for k, v in {
                "REDDIT_CLIENT_ID": client_id,
                "REDDIT_CLIENT_SECRET": client_secret,
                "REDDIT_USERNAME": username,
                "REDDIT_PASSWORD": password,
            }.items() if not v
        ]
        if missing:
            raise EnvironmentError(
                f"Reddit credentials not set: {missing}. "
                "See Stage 1b setup instructions for how to create a Reddit app."
            )

        self._reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent="university-research-tool/0.1 (by /u/{username})",
        )
        logger.info("reddit_tool | RedditTool initialised — read-only mode")

    async def search(
        self,
        query: str,
        subreddits: list[str] | None = None,
        limit: int = 10,
        top_comments_per_post: int = 5,
        time_filter: str = "year",
    ) -> RedditSearchResponse:
        """Search Reddit posts matching query across given subreddits.

        Args:
            query:                  Search string — include university + course.
            subreddits:             List of subreddit names (without r/ prefix).
                                    Defaults to DEFAULT_SUBREDDITS.
                                    Pass ["all"] to search all of Reddit.
            limit:                  Max posts to return per subreddit. Default 10.
            top_comments_per_post:  Number of top comments to include per post.
                                    Default 5. Set 0 to skip comment fetching.
            time_filter:            "year" (default), "month", "week", "all".
                                    "year" enforces approximate 2-year recency
                                    (2 passes may be needed for strict 2yr filter —
                                    ForumAgent handles this in its tool calls).

        Returns:
            RedditSearchResponse with all posts collected across all subreddits.
        """
        subs = subreddits or self.DEFAULT_SUBREDDITS
        all_posts: list[RedditPost] = []

        for sub_name in subs:
            try:
                posts = await self._search_subreddit(
                    query=query,
                    subreddit_name=sub_name,
                    limit=limit,
                    top_comments_per_post=top_comments_per_post,
                    time_filter=time_filter,
                )
                all_posts.extend(posts)
                logger.debug(
                    "reddit_tool | r/%s: %d posts for query %r",
                    sub_name, len(posts), query
                )
            except Exception as exc:
                # Log and skip — a single failed subreddit should not stop ForumAgent
                logger.warning(
                    "reddit_tool | r/%s: search failed: %s", sub_name, exc
                )

        return RedditSearchResponse(
            query=query,
            subreddit="+".join(subs),
            posts=all_posts,
        )

    async def _search_subreddit(
        self,
        query: str,
        subreddit_name: str,
        limit: int,
        top_comments_per_post: int,
        time_filter: str,
    ) -> list[RedditPost]:
        """Search a single subreddit. Runs in executor to avoid blocking asyncio."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._search_subreddit_sync,
            query, subreddit_name, limit, top_comments_per_post, time_filter,
        )

    def _search_subreddit_sync(
        self,
        query: str,
        subreddit_name: str,
        limit: int,
        top_comments_per_post: int,
        time_filter: str,
    ) -> list[RedditPost]:
        """Synchronous PRAW search — called via run_in_executor."""
        subreddit = self._reddit.subreddit(subreddit_name)
        posts = []

        for submission in subreddit.search(
            query,
            limit=limit,
            time_filter=time_filter,
            sort="relevance",
        ):
            comments = []
            if top_comments_per_post > 0:
                try:
                    submission.comments.replace_more(limit=0)
                    for comment in list(submission.comments)[:top_comments_per_post]:
                        if hasattr(comment, "body"):
                            comments.append(RedditComment(
                                body=comment.body,
                                score=comment.score,
                                author=str(comment.author) if comment.author else "[deleted]",
                            ))
                except Exception:
                    pass  # comment fetch failure does not discard the post

            posts.append(RedditPost(
                url=f"https://reddit.com{submission.permalink}",
                title=submission.title,
                body=submission.selftext,
                score=submission.score,
                subreddit=subreddit_name,
                created_utc=submission.created_utc,
                top_comments=comments,
                num_comments=submission.num_comments,
            ))

        return posts
```

**Why `run_in_executor`:** PRAW is a synchronous library. Calling it directly
in an async function would block the asyncio event loop for the duration of
the network round trip — blocking all other concurrent agents. Running it in
an executor makes PRAW calls non-blocking from asyncio's perspective.

**Why single-subreddit errors are swallowed:** if `r/UniUK` is unavailable
(private, banned, or network error), `r/AskUK` and other subreddits should
still be searched. One failed subreddit is a partial degradation, not a
`ForumAgent` failure.

**Why `time_filter="year"` rather than `"all"`:** Reddit's time filter options
are `hour`, `day`, `week`, `month`, `year`, `all` — there is no `2year` option.
Using `year` keeps most results within the recency window. `ForumAgent` is
responsible for discarding posts whose `created_utc` is outside the 2-year
window when building `ForumFinding` entries.

---

## 1b.4 `tools/ddg_tool.py` — DuckDuckGo Wrapper

`DuckDuckGoTool` wraps `duckduckgo-search` as a fallback for `NewsAgent`.
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
        from duckduckgo_search import DDGS
        from duckduckgo_search.exceptions import RatelimitException

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

---

## 1b.5 Registering Tools on `Deps`

Tool instances are created once at startup in `ResearchHandler.__init__()` and
added to `Deps` so agents can access them via `param.deps`.

**Update `core/deps.py`** to add tool fields:

```python
# core/deps.py — updated for Stage 1b
from __future__ import annotations

from dataclasses import dataclass, field
from core.message_hub import MessageHub
from core.blackboard import Blackboard


@dataclass
class ResearchContext:
    university_name: str
    intended_course: str
    country:         str
    study_level:     str = "undergraduate"


@dataclass
class Deps:
    hub:     MessageHub
    board:   Blackboard
    context: ResearchContext
    # Tool instances — set by ResearchHandler after tool initialisation
    # All typed as Any here to avoid circular imports; agents use them as-is
    tavily:  object | None = None   # TavilySearchTool instance
    fetch:   object | None = None   # FetchTool instance
    reddit:  object | None = None   # RedditTool instance
    ddg:     object | None = None   # DuckDuckGoTool instance
```

**Update `services/research_handler.py`** to initialise tools and add them
to `Deps`. Tool initialisation happens once in `__init__()` — not per request:

```python
# services/research_handler.py — __init__ update
from tools.search_tool import TavilySearchTool
from tools.fetch_tool import FetchTool
from tools.reddit_tool import RedditTool
from tools.ddg_tool import DuckDuckGoTool

class ResearchHandler:
    def __init__(self) -> None:
        # Skills loaded first — before agents and tools
        skills = scan_skills_dir(Path("skills"))

        # Tool instances — created once, shared across requests (all stateless)
        self._tavily = TavilySearchTool()
        self._fetch  = FetchTool()
        self._reddit = RedditTool()
        self._ddg    = DuckDuckGoTool()

        # ... agent construction follows (unchanged from Stage 1a) ...
```

In `handle_request()`, add tools to `Deps`:

```python
deps = Deps(
    hub=hub,
    board=board,
    context=context,
    tavily=self._tavily,
    fetch=self._fetch,
    reddit=self._reddit,
    ddg=self._ddg,
)
```

**Why tools are shared across requests:** the tool instances are stateless
wrappers around API clients. Sharing them avoids the overhead of re-initialising
PRAW's OAuth token exchange on every request. The `MessageHub` and `Blackboard`
must still be created fresh per request — tools must not.

---

## 1b.6 Tests — `tests/test_stage_1b.py`

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
  - REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD in .env

DuckDuckGo and Fetch MCP require no credentials.
Each test confirms: import works, client initialises, real call returns data.
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest

from dotenv import load_dotenv
load_dotenv()


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


# ── Reddit ────────────────────────────────────────────────────────────────────

def test_reddit_imports_cleanly() -> None:
    from tools.reddit_tool import RedditTool, RedditPost, RedditSearchResponse
    assert RedditTool
    assert RedditPost
    assert RedditSearchResponse


def test_reddit_initialises_with_env_credentials() -> None:
    from tools.reddit_tool import RedditTool
    tool = RedditTool()
    assert tool is not None


@pytest.mark.asyncio
async def test_reddit_search_returns_posts() -> None:
    from tools.reddit_tool import RedditTool
    tool = RedditTool()
    response = await tool.search(
        query="University of Manchester Computer Science",
        subreddits=["UniUK"],
        limit=5,
        top_comments_per_post=2,
    )
    assert response.query == "University of Manchester Computer Science"
    assert isinstance(response.posts, list), "Expected a list of posts"
    # Posts may be 0 if no recent matching threads — assert type, not count
    for post in response.posts:
        assert post.url.startswith("https://reddit.com"), f"Bad URL: {post.url}"
        assert isinstance(post.score, int)
        assert isinstance(post.created_utc, float)


@pytest.mark.asyncio
async def test_reddit_bad_subreddit_does_not_raise() -> None:
    """A nonexistent subreddit should be skipped, not crash the tool."""
    from tools.reddit_tool import RedditTool
    tool = RedditTool()
    response = await tool.search(
        query="test query",
        subreddits=["ThisSubredditAbsolutelyDoesNotExist99999"],
        limit=3,
    )
    assert response.posts == []


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
    from tools.fetch_tool import FetchTool, FetchResult
    assert FetchTool
    assert FetchResult


@pytest.mark.asyncio
async def test_fetch_returns_content_for_known_url() -> None:
    from tools.fetch_tool import FetchTool
    tool = FetchTool()
    result = await tool.fetch("https://www.cs.manchester.ac.uk/undergraduate/")
    # FetchTool never raises — check status instead
    if result.status == "ok":
        assert len(result.content) > 100, "Expected non-trivial page content"
    else:
        # MCP server not installed or page unavailable — log and pass
        pytest.skip(f"FetchTool not available in test environment: {result.error}")


@pytest.mark.asyncio
async def test_fetch_returns_error_status_for_bad_url() -> None:
    from tools.fetch_tool import FetchTool
    tool = FetchTool()
    result = await tool.fetch("https://this.url.does.not.exist.invalid/")
    assert result.status == "error"
    assert result.error is not None
    assert result.content == ""


# ── Deps integration ─────────────────────────────────────────────────────────

def test_deps_accepts_tool_fields() -> None:
    """Deps can be constructed with tool instances attached."""
    from core.message_hub import MessageHub
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from tools.search_tool import TavilySearchTool
    from tools.ddg_tool import DuckDuckGoTool

    hub     = MessageHub()
    board   = Blackboard()
    context = ResearchContext(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    )
    tavily = TavilySearchTool()
    ddg    = DuckDuckGoTool()

    deps = Deps(hub=hub, board=board, context=context, tavily=tavily, ddg=ddg)
    assert deps.tavily is tavily
    assert deps.ddg    is ddg
    assert deps.reddit is None   # not set in this test — should default to None
    assert deps.fetch  is None
```

---

## 1b.7 Run the Tests

```bash
pytest tests/test_stage_1b.py -v -s
```

The `-s` flag shows `print()` output and log messages — useful for seeing
what each API call returns during the first run.

Expected output on clean pass:

```
tests/test_stage_1b.py::test_tavily_imports_cleanly PASSED
tests/test_stage_1b.py::test_tavily_initialises_with_env_key PASSED
tests/test_stage_1b.py::test_tavily_raises_on_missing_key PASSED
tests/test_stage_1b.py::test_tavily_returns_results_for_known_query PASSED
tests/test_stage_1b.py::test_tavily_site_query_returns_results PASSED
tests/test_stage_1b.py::test_reddit_imports_cleanly PASSED
tests/test_stage_1b.py::test_reddit_initialises_with_env_credentials PASSED
tests/test_stage_1b.py::test_reddit_search_returns_posts PASSED
tests/test_stage_1b.py::test_reddit_bad_subreddit_does_not_raise PASSED
tests/test_stage_1b.py::test_ddg_imports_cleanly PASSED
tests/test_stage_1b.py::test_ddg_search_returns_results PASSED
tests/test_stage_1b.py::test_ddg_returns_empty_on_nonsense_query PASSED
tests/test_stage_1b.py::test_fetch_imports_cleanly PASSED
tests/test_stage_1b.py::test_fetch_returns_content_for_known_url PASSED
tests/test_stage_1b.py::test_fetch_returns_error_status_for_bad_url PASSED
tests/test_stage_1b.py::test_deps_accepts_tool_fields PASSED

16 passed in X.Xs
```

The fetch test may `SKIP` if the MCP server is not installed — this is acceptable
at Stage 1b. It must pass before Stage 2a.

---

## 1b.8 Common Failure Modes at This Stage

**`EnvironmentError: TAVILY_API_KEY not set`**
Cause: `.env` file not in project root, or key has extra whitespace.
Fix: confirm the file exists at the root, not inside a subfolder.
Check for leading/trailing spaces around the `=` sign.

**`praw.exceptions.ResponseException: 401 Unauthorized`**
Cause: wrong `client_id` or `client_secret`. The most common mistake is
copying the app name instead of the `client_id` (shown below the app name
on the Reddit apps page).
Fix: return to https://www.reddit.com/prefs/apps. The `client_id` is the
short string directly under the "personal use script" label, not the app name.

**`praw.exceptions.MissingRequiredAttributeException`**
Cause: `REDDIT_USERNAME` or `REDDIT_PASSWORD` not set.
Fix: add both to `.env`. These are your Reddit account credentials, not the
app credentials.

**`RatelimitException` from DuckDuckGo**
Cause: too many DDG queries in quick succession during test runs.
Fix: the wrapper retries once with a 3-second delay. If tests still fail,
add `time.sleep(2)` between DDG test calls, or run DDG tests in isolation:
`pytest tests/test_stage_1b.py -k ddg -v`.

**`ModuleNotFoundError: mcp_server_fetch`**
Cause: `mcp` package installed but the fetch server module not available.
Fix: `pip install mcp` and confirm with `python -m mcp_server_fetch --help`.
If that command fails, the fetch server may need a separate install:
`pip install mcp-server-fetch`.

**`test_tavily_raises_on_missing_key FAILED`**
Cause: `monkeypatch.delenv` does not work if `load_dotenv()` was already called
at module import time and the key is now in `os.environ`.
Fix: the test reloads the module after deleting the env var. Confirm
`importlib.reload(search_tool)` is called after the `monkeypatch.delenv` call.

---

## Stage 1b Completion Checklist

- [ ] Tavily API key obtained from https://app.tavily.com — added to `.env`
- [ ] Reddit app created at https://www.reddit.com/prefs/apps — `client_id`,
      `client_secret`, `username`, `password` added to `.env`
- [ ] `pip install tavily-python praw duckduckgo-search mcp` confirmed clean
- [ ] `tools/search_tool.py` — `TavilySearchTool` implemented with `days=730` enforced
- [ ] `tools/fetch_tool.py` — `FetchTool` implemented, never raises
- [ ] `tools/reddit_tool.py` — `RedditTool` implemented with `run_in_executor`
- [ ] `tools/ddg_tool.py` — `DuckDuckGoTool` implemented with rate-limit retry
- [ ] `core/deps.py` updated — `tavily`, `fetch`, `reddit`, `ddg` fields added
- [ ] `services/research_handler.py` updated — tools initialised in `__init__()`,
      added to `Deps` in `handle_request()`
- [ ] `pytest tests/test_stage_1b.py -v` — 16 passed (fetch test may SKIP)
- [ ] Stage 1a tests still pass: `pytest tests/test_stage_1a.py -v`

---

*End of Stage 1b Specification*