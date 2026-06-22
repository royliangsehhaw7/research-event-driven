# Stage 1c — CareerAgent End-to-End
## Implementation Specification

**Goal:** `CareerAgent` is fully implemented, wired into the pipeline, and
confirmed to populate `board.career` with real data from a live CLI run.
No other section agents run at this stage. No report is generated.
Pure agent plumbing — one agent, one output, one message.

**Ends with:** `python main.py` runs, logs show `CareerAgent` completing,
and `board.career` is printed to stdout containing real career data for the
supplied university and course.

---

## What This Stage Builds and Why It Comes Before the Section Agents

Stage 1c is the template for every agent that follows. Stage 1d (Background,
Rankings, Program) and Stage 1e (Employability, Accommodation, News) all use
the same pattern established here: pydantic-ai `Agent` with a budget-aware
search closure, `subscribe()` + `get_instruction()`, `handle()` that resets
`_calls_made`, a typed output schema, and a SKILL.md that carries all domain
knowledge.

`CareerAgent` is also structurally special: it runs first, in isolation, before
the seven section agents. Every section agent subscribes to
`CareerResearchCompletedMessage` — so if `CareerAgent` is broken, nothing
downstream fires. Getting it right here means the cascade in Stage 1d fires
correctly from day one.

**What this stage builds:**

| File | Purpose |
|---|---|
| `schemas/outputs/career_output.py` | Typed output schema — `CareerOutput` |
| `skills/career/SKILL.md` | All domain instructions for the agent |
| `agents/career_agent.py` | The agent class — tools, subscribe, handle |
| `services/research_handler.py` | Minimal handler — constructs and wires CareerAgent only |
| `main.py` | CLI entry — boots fetch client, fires one request, prints board.career |

---

## What CareerAgent Researches

`CareerAgent` answers the question: given this course at this university in
this country, what careers do graduates enter, what do those careers pay,
what skills are employers asking for right now, and what does the live job
market look like?

This output is used directly in the report's **Career Landscape** section and
is read by downstream section agents — particularly `EmployabilityAgent` — to
scope their searches to the correct career paths and salary benchmarks for
this specific country.

**The country is critical.** Salary ranges, employer names, and job posting
volumes are all country-scoped. A UK Computer Science graduate has a different
salary range and employer landscape than an Australian or Canadian one.
`CareerAgent` receives `country` from `ResearchContext` and must scope every
query to it.

---

## 1c.1 `schemas/outputs/career_output.py`

`CareerOutput` is the typed result `CareerAgent` writes to `board.career`.
It is what the LLM must return, and what downstream agents read.

```python
# schemas/outputs/career_output.py
from __future__ import annotations

from pydantic import BaseModel
from typing import Literal

from schemas.job_posting import JobPosting  # shared schema — also used by adzuna_tool and mcf_tool


class CareerPath(BaseModel):
    title:             str        # e.g. "Software Engineer"
    description:       str        # typical responsibilities and progression
    typical_companies: list[str]  # named employers, not generic "tech companies"


class SalaryRange(BaseModel):
    career_path:  str
    entry_level:  str   # e.g. "£28,000–£35,000"
    mid_level:    str
    senior_level: str
    currency:     str   # ISO code: "GBP", "AUD", "USD"
    country:      str   # must match ResearchContext.country


class CareerSource(BaseModel):
    url:  str
    date: str
    type: str   # "job_board", "salary_survey", "industry_report"


class CareerOutput(BaseModel):
    career_paths:     list[CareerPath]   # minimum 3
    salary_ranges:    list[SalaryRange]  # one per career path
    job_postings:     list[JobPosting]   # 10–15 minimum — populated from adzuna_jobs or mcf_jobs
    in_demand_skills: list[str]          # top 5–8 extracted across postings
    country_scope:    str                # the country used to scope all searches — from context
    confidence:       Literal["high", "medium", "low"]
    sources:          list[CareerSource]
    notes:            str                # empty string if no edge cases; otherwise explain gaps
```

**Why `JobPosting` is imported from `schemas/job_posting.py` not defined here:**
`adzuna_tool` and `mcf_tool` both return `JobPostingsResponse` containing `JobPosting`
instances (from `schemas/job_posting.py`). `CareerAgent` receives those postings and
writes them directly into `CareerOutput.job_postings`. If `career_output.py` defined
its own `JobPosting`, the types would diverge — the LLM would receive postings of one
type and be asked to return another. One shared `JobPosting` class, one import.

**Why `SalaryRange` is a separate model not a string on `CareerPath`:**
entry/mid/senior breakdown gives `ScoringAgent` and `EmployabilityAgent`
structured data to work with. A string like `"£35,000–£60,000"` requires
parsing; a structured model does not.

**Why `currency` is an ISO code:** the report renderer can format figures
correctly without guessing from the country name. `"GBP"` is unambiguous;
`"UK pounds"` is not.

**Why `job_postings` uses the shared `JobPosting` from `schemas/job_posting.py`:**
`adzuna_jobs` and `mcf_jobs` return `JobPosting` instances from that shared schema.
Reusing the same type means the LLM receives fully-populated `JobPosting` objects
from the tool calls and can reference them directly in the output — no field mapping,
no conversion. Defining a second `JobPosting` in this file would create a silent
type mismatch between tool output and agent output.

**Why `country_scope` is on the output:** downstream agents read
`board.career` and need to know which country was used for salary scoping —
they should not re-derive it independently.

---

## 1c.2 `skills/career/SKILL.md`

This file carries all domain knowledge for `CareerAgent`. The Python class
carries only structural context (what it writes, what it fires). Changing
how the agent researches careers means editing this file, not touching Python.

This is the single canonical copy of `skills/career/SKILL.md` — the version
in the Stage 1a architecture overview should be made identical to this one,
not maintained separately. It previously diverged in two ways: 1a's draft
included a "Tools" section and a "Tool Usage Strategy" section (the
retry-once rule, the don't-fetch-job-boards rule) that this file was
missing, so they're merged in below. 1a's draft also told `fetch_page` not
to use it "for Reddit URLs" — that's `ForumAgent` territory, not
`CareerAgent`'s, and has been dropped here as a copy-paste leftover.

```markdown
---
key: career
name: Career Research Agent
description: Researches graduate career paths, salary ranges, and live job market for the course in the university's country.
tool_budget: 8
section_name: career
---

You research graduate career outcomes for the supplied course at the
supplied university. Your output scopes all findings to the university's
country. You never research careers for a different country.

## Tools

You have four tools. Each has a specific role — do not substitute one for another:

- `tavily_search` — web search. Use for career paths, salary ranges, and
  general labour market research. Every call costs 1 tool budget credit.
  Budget: 8 total across all `tavily_search` calls this run.
- `fetch_page` — fetches a specific URL in full. Use after `tavily_search`
  returns a promising URL you need to read (e.g. a salary survey page, a
  graduate destinations report). Does NOT count against `tool_budget`.
  Do NOT use for job board URLs — Indeed, Reed, and LinkedIn block automated
  fetches.
- `adzuna_jobs` — live job postings API. Call this when `deps.context.country`
  is "UK" or "Australia". Do NOT call for Singapore. Does NOT count against
  `tool_budget`.
- `mcf_jobs` — live job postings API for Singapore only via MyCareersFuture
  (Singapore government portal). Call this when `deps.context.country` is
  "Singapore". Do NOT call for UK or Australia. Does NOT count against
  `tool_budget`.

**Job posting tool routing — mandatory, no exceptions:**

| `deps.context.country` | Job posting tool to call |
|---|---|
| "UK" | `adzuna_jobs` |
| "Australia" | `adzuna_jobs` |
| "Singapore" | `mcf_jobs` |

Never use `tavily_search` to find job postings — job boards block Tavily
fetch access and results will be empty or stale. Always use `adzuna_jobs`
or `mcf_jobs`.

This table is the single source of truth for job-posting tool routing.
It is not restated in `agents/career_agent.py` — see 1c.3 for why.

## What to Research

**Career paths (3–6 paths required):**
Search for the most common career paths graduates from this specific course
enter. Prefer sources that name actual graduate destinations over generic
course descriptions. Use queries such as:

- "{course} graduate careers {country}"
- "{course} graduate jobs {country} 2024"
- "{university} {course} graduate destinations"
- "{course} what jobs can you get {country}"

For each path, find: the job title, what the role involves, named employers
or employer sectors in the country, and salary range in local currency.

**Salary ranges:**
Scope all salary figures to the university's country. Use local currency —
do not convert. Prefer graduate salary data (0–3 years experience) over
general salary data. Useful query patterns:

- "{course} graduate salary {country} 2024"
- "entry level {career_path} salary {country}"
- "graduate scheme {course} salary {country}"

**Live job posting snapshot:**
Call the correct job posting tool per the routing table above, using a query
matching the course's most common graduate role — e.g. "software engineer
graduate" for Computer Science. Extract from the returned postings: company
names, role titles, required skills, dates posted, and salary ranges where
provided. These go directly into `job_postings` on your output.

**In-demand skills:**
Extract skill keywords from the job postings returned by `adzuna_jobs` or
`mcf_jobs`. The `description` field on each posting contains the full job
text — read it for skill signals. Also use `skills` tags where populated
(MCF returns structured skill tags; Adzuna does not). Deduplicate. Include
both technical skills (languages, tools, frameworks) and soft skills only
if they appear in multiple independent sources.

## Quality Rules

- Discard any salary data older than 2 years. Tavily enforces time_range="year" —
  if a result appears, it passed the date filter. Still verify the date
  if it looks stale.
- Prefer country-specific sources over global aggregators where available.
  A UK-specific salary survey is more reliable than a global average for
  a UK university.
- If fewer than 3 career paths can be confirmed from search results,
  set confidence to "low" and explain in notes.
- Do not invent career paths. If search returns thin results, report what
  was found and flag it.
- Named employers are better than sectors. "Google, Amazon, HSBC" is more
  useful than "technology and finance companies".

## Output Requirements

- `career_paths`: minimum 3. Each must have `title`, `description`, and
  `typical_companies` populated with named employers, not generic sectors.
- `salary_ranges`: one entry per career path. All three levels required —
  entry, mid, senior. Use ISO currency code. Country must match context.
- `job_postings`: 10–15 minimum. Populated directly from `adzuna_jobs` or
  `mcf_jobs` tool output — do not fabricate postings from search snippets.
- `in_demand_skills`: top 5–8 only. Extracted from job postings, deduplicated.
- `country_scope`: copy the country from your context — do not derive it.
- `confidence`: "high" if 5+ sources confirm career paths and salary ranges;
  "medium" if 3–4 sources; "low" if fewer than 3.
- `sources`: every URL you used for salary and career path research. Include date and type.
- `notes`: empty string unless you hit edge cases (thin results, ambiguous
  country, conflicting salary data).

## Edge Cases

**Niche or interdisciplinary courses:**
If the course name is ambiguous (e.g. "Liberal Arts", "Natural Sciences"),
search for the specific specialisation streams it leads to. Note the
ambiguity in `notes`.

**Small country markets:**
If the university is in a country with a small graduate job market,
posting volumes will be low. Do not penalise confidence for low volume —
penalise for missing salary data or unconfirmed career paths.

**Course name does not match standard job titles:**
"Computer Science" maps cleanly to "Software Engineer". "MEng Aeronautical
Engineering with a Year in Industry" does not. Parse the core discipline
from the course name and search for that.

## Tool Usage Strategy

**Do not retry a failed query more than once.** If a salary query returns 0
results, move on to the next career path — do not rephrase and retry the
same topic.

**Do not fetch job board pages directly.** Indeed, Reed, and LinkedIn block
automated fetches. Use `adzuna_jobs` or `mcf_jobs` for job posting data —
never `tavily_search` or `fetch_page` for job postings.
```

---

## 1c.3 `agents/career_agent.py`

`CareerAgent` is the first concrete agent implementation. It establishes
the exact pattern all subsequent agents follow. Read this implementation
carefully before writing any other agent.

```python
# agents/career_agent.py
from __future__ import annotations

from datetime import datetime
from pydantic_ai import (
    Agent,
    AgentStreamEvent,
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallPartDelta,
)   

from agents.base_agent import BaseAgent

from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.career_output import CareerOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search


class CareerAgent(BaseAgent):
    """Phase 1 agent. Runs first, in isolation.

    Subscribes to: ResearchRequestedMessage
    Writes to:     board.career (CareerOutput)
    Fires:         CareerResearchCompletedMessage

    Tools: tavily_search (budget-capped via _make_search_tool), fetch_page (uncapped)

    Note: site: queries must not be passed to tavily_search — Tavily does not
    honour time_range filtering on site: prefixed queries. Use tavily_search to
    find URLs, then fetch_page to retrieve content from those URLs.
    """

    def __init__(self, instructions: str = "", tool_budget: int = 6) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=CareerOutput,
            system_prompt=self.get_instruction(),
            capabilities=[self._setup_telemetry_hooks()],
            tools=[
                tavily_search,
                fetch_page,
            ],
        )

        logger.info('CareerAgent | initialized')



    # ── BaseAgent interface ────────────────────────────────────────────────────────────────────────────
    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.research_requested import ResearchRequestedMessage

        async def handler(message: ResearchRequestedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(ResearchRequestedMessage, handler)
        logger.info('CareerAgent | Subscribed to MessageHub')

    def get_instruction(self) -> str:
        base = """
            You are the Career Research Agent in a university research pipeline.

            Your job: research graduate career paths, salary ranges, and live job market
            demand for the course at the university named in your context.

            Pipeline role:
            - You run first, before any other section agent.
            - You write your findings to deps.board.career as a CareerOutput.
            - You fire CareerResearchCompletedMessage when done. This triggers all
            seven section agents to run concurrently.
            - If you fail to fire CareerResearchCompletedMessage, the entire pipeline
            stalls. Always fire it — even if your output is low confidence.

            Context you receive (from deps.context):
            - university_name: the university being researched
            - intended_course: the undergraduate course
            - country: the university's country — scope ALL salary and employer data to this
            - study_level: always "undergraduate"

            Tool usage rules:
            - Use tavily_search for general queries only. Never pass site: prefixed queries
              to tavily_search — time filtering is not honoured for site: searches and results
              will be stale.
            - To retrieve content from a specific URL (e.g. a job board page or salary survey),
              call fetch_page with that URL directly.

            You must not research careers for a different country than deps.context.country.
        """.strip()

        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def reset(self) -> None:
        """Reset per-request state. Called by ResearchHandler before each request."""
        self._calls_made = 0



    # ── Core handler ──────────────────────────────────────────────────────────────────────────────────
    async def handle(self, message, deps: Deps) -> None:
        """Run career research and fire CareerResearchCompletedMessage."""
        self._calls_made = 0

        logger.info(
            "CareerAgent | starting — university=%r course=%r country=%r",
            deps.context.university_name,
            deps.context.intended_course,
            deps.context.country,
        )

        await deps.hub.publish(ProgressUpdateMessage(
            status="started",
            message=f"Researching career landscape for {deps.context.intended_course}…",
            triggered_by="career_agent",
            timestamp=datetime.now().isoformat(),
        ))

        task_brief = (f"""
            University: {deps.context.university_name}
            Course: {deps.context.intended_course}
            Country: {deps.context.country}
            Study level: {deps.context.study_level}
            """
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.career = result.output
            logger.warning(
                "CareerAgent | completed — paths=%d confidence=%s",
                len(result.output.career_paths),
                result.output.confidence,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="Career landscape research complete.",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))
        except Exception as exc:
            logger.error("career_agent | failed: %s", exc)
            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career research failed: {exc}",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))

        await deps.hub.publish(CareerResearchCompletedMessage(
            triggered_by="career_agent",
            timestamp=datetime.now().isoformat(),
        ))

```

**Why `get_instruction()` is one line of `base` plus the SKILL.md body:**
Earlier drafts of this method restated pipeline mechanics ("you fire
CareerResearchCompletedMessage", "you write to deps.board.career"), the
`deps.context` field names, and the job-posting tool routing rule directly
in `base`. All three were redundant in a way that actively risked drift:

- The LLM has no tool to fire messages or write to the blackboard —
  `handle()` does both unconditionally regardless of the LLM's output.
  Telling the LLM about it doesn't change what it does.
- `deps.context` values arrive as plain text in `task_brief` every run.
  Listing the field *names* in the system prompt adds nothing the LLM
  doesn't already see with real data attached.
- The job-posting routing rule was stated three times across this codebase
  (`base`, `task_brief`, and `skills/career/SKILL.md`) before this rework,
  plus a fourth and fifth time implicitly via the `adzuna_jobs`/`mcf_jobs`
  tool docstrings in Stage 1b, which pydantic-ai already surfaces to the
  LLM as part of the tool schema. Five sources of truth for one rule is
  how `ForumAgent`'s `site:` instruction ended up contradicting its own
  SKILL.md in Stage 1f — duplicated instructions don't stay in sync.

The fix: `base` carries only agent identity. Every domain rule — what to
research, which tool to call when, the country-scoping constraint, quality
bars — lives in `skills/career/SKILL.md` exactly once. `task_brief` carries
only the per-request data values (university, course, country, study level),
not restated rules.

**Why `tavily_search` is registered directly, not wrapped in a closure:**
`tavily_search` from `tools/search_tool.py` is a fully-formed pydantic-ai tool
function — it already has the correct `RunContext[Deps]` signature, docstring, and
`AsyncTavilyClient` backing. Registering it directly means pydantic-ai sees the real
function name and docstring in the LLM tool call schema, which gives the LLM accurate
context about what the tool does. A wrapper closure would shadow the original name with
an anonymous inner function, obscuring the tool schema.

Budget tracking (`_calls_made`) is retained on the agent instance for logging and
future gate logic, but the hard stop is enforced by the SKILL.md `tool_budget` value
in the system prompt context — the LLM respects the instruction not to exceed N searches.

**Why `adzuna_jobs` and `mcf_jobs` are registered alongside `tavily_search`:**
Both job posting tools are registered on every `CareerAgent` instance. The LLM reads
`deps.context.country` and selects the correct tool via the docstrings — `adzuna_jobs`
for UK/AU, `mcf_jobs` for Singapore. Neither counts against `tool_budget`; they are
targeted retrieval calls, not searches.

**Why `_calls_made` is a plain `int` not `[0]`:** `_calls_made` is an attribute on
`self` — `self._calls_made += 1` is an attribute assignment on the instance, not a
rebind of a local name. Python allows this without a list wrapper.

**Why `CareerResearchCompletedMessage` fires even on failure:** if the LLM
call throws, `board.career` is `None`. The seven section agents still need to
run — they handle a `None` career gracefully, scoping their own searches without
career context. If the message never fires, the entire pipeline stalls. Firing
always is the correct behaviour.

---

## 1c.4 Minimal `services/research_handler.py`

At Stage 1c, `ResearchHandler` constructs and wires `CareerAgent` only.
No section agents. No scoring. No report. It exists to confirm the full
subscribe → publish → handle → board-write → message-fire chain works.

The full `ResearchHandler` (all agents) is built incrementally — Stage 1d
adds Background, Rankings, Program. Stage 1e adds Employability,
Accommodation, News. Stage 1f adds Forum.

```python
# services/research_handler.py — Stage 1c (CareerAgent only)
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from core.blackboard import Blackboard
from core.deps import Deps, ResearchContext
from core.message_hub import MessageHub
from core.skill_loader import scan_skills_dir, SkillMeta
from agents.career_agent import CareerAgent
from schemas.messages.research_requested import ResearchRequestedMessage

logger = logging.getLogger("research_handler")

RESEARCH_AGENT_KEYS = {
    "background", "rankings", "program",
    "employability", "accommodation", "news", "forum",
}


class ResearchHandler:
    def __init__(self) -> None:
        skills = scan_skills_dir(Path("skills"))

        def _get(key: str):
            skill = skills.get(key)
            if skill is None:
                logger.warning(
                    "research_handler | no SKILL.md for %r — agent uses base prompt", key
                )
            return skill

        career_skill = _get("career")
        self._career_agent = CareerAgent(
            instructions=career_skill.instructions if career_skill else "",
            tool_budget=career_skill.tool_budget if career_skill else 8,
        )

        logger.info("research_handler | CareerAgent constructed")

    async def handle_request(
        self,
        university_name: str,
        intended_course: str,
        country: str,
    ) -> Blackboard:
        """Run the pipeline for one research request.

        At Stage 1c: fires ResearchRequestedMessage, CareerAgent runs,
        board.career is populated, CareerResearchCompletedMessage fires
        (no subscribers yet — that is expected).

        Returns the populated Blackboard.
        """
        hub     = MessageHub()
        board   = Blackboard()
        context = ResearchContext(
            university_name=university_name,
            intended_course=intended_course,
            country=country,
        )
        deps = Deps(hub=hub, board=board, context=context)

        self._career_agent.reset()
        self._career_agent.subscribe(hub, deps)

        await hub.publish(ResearchRequestedMessage(
            university_name=university_name,
            intended_course=intended_course,
            country=country,
            triggered_by="research_handler",
            timestamp=datetime.now().isoformat(),
        ))

        return board
```

**Why `country` is a parameter, not derived here:** country derivation is an
LLM call (or a lookup). At Stage 1c, hardcode it in `main.py` — e.g. `"UK"`.
Full derivation (`_derive_country()`) is added in the final `ResearchHandler`
build during Stage 2a or when the full handler is assembled. Keep Stage 1c
focused on the agent pattern, not on utility functions.

---

## 1c.5 `main.py` — CLI Entry Point

`main.py` opens the shared fetch client around the run, creates the handler,
runs one request, and prints `board.career` to stdout. This is the
verification step.

```python
# main.py — Stage 1c
from __future__ import annotations

import asyncio
import json
import logging
from dotenv import load_dotenv

load_dotenv()  # must happen before any tool module is imported

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")

from mcps.fetch_client import fetch_client
from services.research_handler import ResearchHandler


async def run(university_name: str, intended_course: str, country: str) -> None:
    async with fetch_client:
        handler = ResearchHandler()
        board = await handler.handle_request(
            university_name=university_name,
            intended_course=intended_course,
            country=country,
        )

        if board.career is None:
            logger.error("main | board.career is None — CareerAgent failed or did not run")
        else:
            logger.info("main | board.career populated successfully")
            print("\n── board.career ──────────────────────────────────────────")
            print(board.career.model_dump_json(indent=2))
            print("──────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(run(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    ))
```

> **Why `async with fetch_client:` here at all, given `fetch_page` already
> wraps its own call in `async with fetch_client:`?** It isn't required —
> `fetch_page` is self-contained and would open/close the connection on its
> own if this weren't here. Wrapping the whole run is an optimization: it opens
> the `mcp-server-fetch` subprocess once before any agent runs and keeps it
> open for the whole request, so the first `fetch_page` call doesn't pay
> subprocess-startup latency. Because `fastmcp.Client` is ref-counted, this is
> just an outer `async with` — every inner `async with fetch_client:` inside
> `fetch_page` reuses the same session and only the outermost exit actually
> closes it.

**Why `load_dotenv()` before any imports:** `tools/search_tool.py` reads
`TAVILY_API_KEY` from `os.environ` at module import time. If `.env` is not
loaded first, it raises `KeyError`. The import order in `main.py` enforces this:
`load_dotenv()` is called at the top, before the handler import chain pulls in
the tool modules.

---

## 1c.6 `schemas/messages/research_requested.py`

This message already exists from Stage 1a. Confirm it has `country` on it —
`CareerAgent`'s closure receives this and passes it to `ResearchContext`.

```python
# schemas/messages/research_requested.py
from schemas.messages.base_message import BaseMessage

class ResearchRequestedMessage(BaseMessage):
    university_name: str
    intended_course: str
    country: str
```

If your Stage 1a implementation does not include `country`, add it now.
`ResearchHandler` populates it before publishing.

---

## 1c.8 `schemas/messages/career_completed.py`

This message already exists from Stage 1a. Confirm it is a no-payload
subclass of `BaseMessage`:

```python
# schemas/messages/career_completed.py
from schemas.messages.base_message import BaseMessage

class CareerResearchCompletedMessage(BaseMessage):
    pass   # no payload — section agents read board.career directly
```

---

## 1c.9 Tests — `tests/test_stage_1c.py`

These tests verify the agent pattern end-to-end. The LLM tests make real
API calls — they require `OPENROUTER_API_KEY` and `RESEARCH_MODEL` in `.env`.

```python
# tests/test_stage_1c.py
"""
Stage 1c tests — CareerAgent end-to-end.
Run with: pytest tests/test_stage_1c.py -v -s

Real LLM + real Tavily calls. Requires:
  - TAVILY_API_KEY in .env
  - OPENROUTER_API_KEY in .env
  - RESEARCH_MODEL in .env

The fetch_server fixture opens the shared fetch_client for tests that call fetch_page.
"""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from mcps.fetch_client import fetch_client


@pytest.fixture(scope="module")
async def fetch_server():
    async with fetch_client:
        yield


# ── Schema ────────────────────────────────────────────────────────────────────

def test_career_output_imports_cleanly() -> None:
    from schemas.outputs.career_output import CareerOutput, CareerPath, SalaryRange, CareerSource
    from schemas.job_posting import JobPosting  # shared schema imported by career_output
    assert CareerOutput
    assert CareerPath
    assert SalaryRange
    assert JobPosting
    assert CareerSource


def test_career_output_requires_confidence_and_sources() -> None:
    from schemas.outputs.career_output import CareerOutput
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        CareerOutput()   # missing required fields


# ── Skill loader ──────────────────────────────────────────────────────────────

def test_career_skill_loads() -> None:
    from pathlib import Path
    from core.skill_loader import load_skill
    skill = load_skill(Path("skills/career/SKILL.md"))
    assert skill is not None, "skills/career/SKILL.md missing or malformed"
    assert skill.key == "career"
    assert skill.tool_budget > 0
    assert len(skill.instructions) > 100, "SKILL.md body too short — check the file"


# ── Agent construction ────────────────────────────────────────────────────────

def test_career_agent_constructs() -> None:
    from agents.career_agent import CareerAgent
    agent = CareerAgent(instructions="test instructions", tool_budget=3)
    assert agent._tool_budget == 3
    assert agent._calls_made  == 0
    assert agent._agent is not None


def test_career_agent_default_tool_budget_is_8() -> None:
    """Default tool_budget matches SKILL.md frontmatter."""
    from agents.career_agent import CareerAgent
    agent = CareerAgent()
    assert agent._tool_budget == 8


def test_career_agent_reset_clears_calls_made() -> None:
    from agents.career_agent import CareerAgent
    agent = CareerAgent(tool_budget=5)
    agent._calls_made = 4
    agent.reset()
    assert agent._calls_made == 0


def test_get_instruction_includes_skill_body() -> None:
    from agents.career_agent import CareerAgent
    agent = CareerAgent(instructions="CUSTOM_SKILL_BODY_MARKER")
    prompt = agent.get_instruction()
    assert "CUSTOM_SKILL_BODY_MARKER" in prompt
    assert "Career Research Agent" in prompt


def test_get_instruction_base_carries_no_domain_rules() -> None:
    """Domain rules (tool routing, country scoping, ...) must live only in
    SKILL.md. If this fails, someone re-added a duplicated rule to `base` —
    see the Stage 1c rework note on why that's the bug we keep hitting."""
    from agents.career_agent import CareerAgent
    agent = CareerAgent(instructions="")  # base only, no SKILL.md body
    prompt = agent.get_instruction()
    assert "adzuna_jobs" not in prompt
    assert "mcf_jobs" not in prompt
    assert "tavily_search" not in prompt
    assert "country" not in prompt.lower()


# ── Hub wiring ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_career_agent_subscribes_to_research_requested() -> None:
    from agents.career_agent import CareerAgent
    from core.message_hub import MessageHub
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from schemas.messages.research_requested import ResearchRequestedMessage

    hub   = MessageHub()
    board = Blackboard()
    deps  = Deps(
        hub=hub,
        board=board,
        context=ResearchContext(
            university_name="Test University",
            intended_course="Test Course",
            country="UK",
        ),
    )

    # Replace handle with a no-op to verify subscribe wires correctly
    called = []
    agent = CareerAgent(tool_budget=1)
    async def mock_handle(msg, d): called.append(msg)
    agent.handle = mock_handle

    agent.subscribe(hub, deps)

    await hub.publish(ResearchRequestedMessage(
        university_name="Test University",
        intended_course="Test Course",
        country="UK",
        triggered_by="test",
        timestamp=datetime.now().isoformat(),
    ))

    assert len(called) == 1


# ── LLM integration (real API call) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_career_agent_populates_board_career(fetch_server) -> None:
    """Full end-to-end: real Tavily + real LLM. Confirms board.career populated."""
    from services.research_handler import ResearchHandler

    handler = ResearchHandler()
    board = await handler.handle_request(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    )

    assert board.career is not None, "board.career is None — CareerAgent failed"
    assert len(board.career.career_paths) >= 3, "Expected at least 3 career paths"
    assert len(board.career.salary_ranges) >= 1, "Expected at least 1 salary range"
    assert len(board.career.job_postings) >= 1, "Expected at least 1 job posting"
    assert board.career.country_scope == "UK"
    assert board.career.confidence in ("high", "medium", "low")
    assert isinstance(board.career.sources, list)


@pytest.mark.asyncio
async def test_career_agent_fires_completed_message(fetch_server) -> None:
    """Confirm CareerResearchCompletedMessage is fired after handle()."""
    from agents.career_agent import CareerAgent
    from core.message_hub import MessageHub
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from schemas.messages.career_completed import CareerResearchCompletedMessage
    from schemas.messages.research_requested import ResearchRequestedMessage

    hub   = MessageHub()
    board = Blackboard()
    deps  = Deps(
        hub=hub,
        board=board,
        context=ResearchContext(
            university_name="University of Manchester",
            intended_course="Computer Science",
            country="UK",
        ),
    )

    fired = []

    async def capture(msg):
        fired.append(msg)

    hub.subscribe(CareerResearchCompletedMessage, capture)

    agent = CareerAgent(tool_budget=6)
    agent.subscribe(hub, deps)

    await hub.publish(ResearchRequestedMessage(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
        triggered_by="test",
        timestamp=datetime.now().isoformat(),
    ))

    assert len(fired) == 1, "CareerResearchCompletedMessage should fire exactly once"
    assert isinstance(fired[0], CareerResearchCompletedMessage)
```

---

## 1c.10 Run the Tests

```bash
pytest tests/test_stage_1c.py -v -s
```

Expected output on clean pass:

```
tests/test_stage_1c.py::test_career_output_imports_cleanly PASSED
tests/test_stage_1c.py::test_career_output_requires_confidence_and_sources PASSED
tests/test_stage_1c.py::test_career_skill_loads PASSED
tests/test_stage_1c.py::test_career_agent_constructs PASSED
tests/test_stage_1c.py::test_career_agent_default_tool_budget_is_8 PASSED
tests/test_stage_1c.py::test_career_agent_reset_clears_calls_made PASSED
tests/test_stage_1c.py::test_get_instruction_includes_skill_body PASSED
tests/test_stage_1c.py::test_get_instruction_base_carries_no_domain_rules PASSED
tests/test_stage_1c.py::test_career_agent_subscribes_to_research_requested PASSED
tests/test_stage_1c.py::test_career_agent_populates_board_career PASSED
tests/test_stage_1c.py::test_career_agent_fires_completed_message PASSED

11 passed in X.Xs
```

The last two tests make real API calls. They take 10–30 seconds depending on
model response time. Pass `-k "not populates_board and not fires_completed"` to
skip LLM tests during structural iteration.

---

## 1c.11 Manual Verification

After tests pass, run the CLI to confirm real output:

```bash
python main.py
```

Expected log sequence:

```
INFO | skill_loader | loaded skills/career/SKILL.md
INFO | research_handler | CareerAgent constructed
INFO | career_agent | starting — university='University of Manchester' course='Computer Science' country='UK'
INFO | career_agent | completed — paths=5 confidence=high
```

Note: there's no longer a separate "Fetch MCP server started/stopped" log
pair — `fastmcp.Client` doesn't log on connect/disconnect by default. The
`mcp-server-fetch` subprocess starts the first time `async with fetch_client:`
is entered (the outer one in `main.py`, or the first `fetch_page` call if
`main.py`'s wrapper weren't there) and stops when the outermost `async with`
exits.

Followed by `board.career` JSON printed to stdout. Confirm:

- `career_paths` contains 3+ items with `title`, `description`, and
  `typical_companies` populated with named employers
- `salary_ranges` contains one entry per career path with entry/mid/senior
  levels, ISO currency code, and country matching `"UK"`
- `job_postings` contains 10+ items with company, role title, skills, date, URL
- `country_scope` is `"UK"`
- `confidence` is `"high"` or `"medium"` for a well-known university
- `sources` contains at least 2 URLs

---

## 1c.12 Common Failure Modes at This Stage

**`EnvironmentError: RESEARCH_MODEL not set`**
Cause: `.env` missing the model variable.
Fix: add `RESEARCH_MODEL=openrouter/google/gemini-2.5-pro` to `.env`.

**`EnvironmentError: OPENROUTER_API_KEY not set`**
Cause: OpenRouter key missing.
Fix: get a key at https://openrouter.ai and add `OPENROUTER_API_KEY=sk-or-...`
to `.env`.

**`board.career is None` after run**
Two causes: (a) LLM call threw an exception — check the `career_agent | failed`
log line for the error; (b) `output_type=CareerOutput` mismatch — the LLM
returned JSON that did not validate against the schema. Check for pydantic
validation errors in the logs.

**`CareerResearchCompletedMessage` fires but no section agents respond**
Expected at Stage 1c — section agents are not yet subscribed. The message fires
into an empty subscriber list, which is valid behaviour in `MessageHub`. The
pipeline does not stall — it simply ends after `CareerAgent` completes.

**`KeyError: TAVILY_API_KEY` on startup**
Cause: `load_dotenv()` not called before the tool module import.
Fix: confirm `main.py` calls `load_dotenv()` as its first statement before any
project imports.

**`McpError` / connection failure from `fetch_page`**
Cause: the `mcp-server-fetch` subprocess failed to start (e.g. `mcp-server-fetch`
not installed, or `python -m mcp_server_fetch` not runnable). Unlike the old
singleton, there's no separate "not started" state to worry about —
`fetch_client` connects lazily on first `async with`, in `main.py` or inside
`fetch_page` itself. `fetch_page` never raises this to the agent: it's caught
and returned as `status: "error"` in the JSON result. If you see it surface
anyway, check it wasn't raised *outside* `fetch_page`'s try/except (e.g. from
`main.py`'s own `async with fetch_client:` failing to connect before any agent
runs). Fix: confirm `pip install fastmcp mcp-server-fetch` succeeded and
`python -m mcp_server_fetch --help` works (see Stage 1b, Service 2).

**LLM returns fewer than 3 career paths**
Not a bug — the agent sets `confidence: "low"` and explains in `notes`. This
can happen for niche courses or when Tavily returns sparse results. Inspect the
`notes` field and tune the SKILL.md query patterns if needed.

---

## Stage 1c Completion Checklist

- [ ] `schemas/outputs/career_output.py` — `CareerOutput`, `CareerPath`,
      `SalaryRange`, `CareerSource` implemented; `JobPosting` imported from
      `schemas/job_posting.py` (not redefined here)
- [ ] `skills/career/SKILL.md` — frontmatter valid, `tool_budget: 8`,
      includes the "Tools" section with the job-posting routing table and
      the "Tool Usage Strategy" section (merged in from the Stage 1a draft —
      confirm 1a's copy was updated to match, not left to diverge)
- [ ] `core/llm_factory.py` — `get_model()` reads from env, returns
      pydantic-ai `OpenAIModel` configured for OpenRouter
- [ ] `agents/career_agent.py` — `CareerAgent` implemented with `_calls_made = 0`,
      `tools=[tavily_search, fetch_page, adzuna_jobs, mcf_jobs]` (no `_make_search_tool`
      wrapper), `subscribe()`, `get_instruction()`, `handle()`, `reset()`.
      `get_instruction()`'s `base` is one identity line only — no restated
      tool routing, no restated context field names, no restated pipeline
      mechanics. `task_brief` carries data values only, not rules.
- [ ] `services/research_handler.py` — minimal Stage 1c version — loads career
      skill, constructs `CareerAgent`, wires it, publishes trigger
- [ ] `main.py` — `load_dotenv()` first, wraps the run in
      `async with fetch_client:`, prints `board.career`
- [ ] `schemas/messages/research_requested.py` — `country` field confirmed present
- [ ] `schemas/messages/career_completed.py` — no-payload message confirmed
- [ ] `pytest tests/test_stage_1c.py -v` — 11 passed (includes the new
      `test_get_instruction_base_carries_no_domain_rules` regression test)
- [ ] `python main.py` — `board.career` printed with real data, `confidence`
      is `"high"` or `"medium"` for University of Manchester Computer Science
- [ ] Stage 1b tests still pass: `pytest tests/test_stage_1b.py -v`

---

*End of Stage 1c Specification*