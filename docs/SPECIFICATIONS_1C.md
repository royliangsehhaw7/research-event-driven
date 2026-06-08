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


class CareerPath(BaseModel):
    title: str                  # job title — e.g. "Software Engineer"
    description: str            # 1–2 sentences: what the role involves
    typical_employers: list[str]  # named companies or sectors, country-scoped
    salary_range_local: str     # local currency — e.g. "£35,000–£60,000"
    seniority_note: str         # e.g. "entry-level to mid", "graduate scheme entry"


class JobPostingSnapshot(BaseModel):
    query_used: str             # the search query that found this snapshot
    approximate_volume: str     # e.g. "~1,200 live postings", "limited market"
    top_skill_keywords: list[str]  # extracted from postings — max 10
    source_url: str
    source_date: str            # ISO date or "approx YYYY-MM"


class CareerSource(BaseModel):
    url: str
    title: str
    date: str | None            # publication date, or None if unavailable


class CareerOutput(BaseModel):
    career_paths: list[CareerPath]      # 3–6 distinct career paths
    job_posting_snapshot: JobPostingSnapshot | None  # may be None if search returned nothing
    in_demand_skills: list[str]         # deduplicated across all postings found — max 15
    salary_context: str                 # 1 paragraph: ranges, currency, seniority notes
    country_scope: str                  # the country used to scope all searches — from context
    confidence: Literal["high", "medium", "low"]
    sources: list[CareerSource]
    notes: str                          # empty string if no edge cases; otherwise explain gaps
```

**Why `career_paths` is a list not a single object:** a Computer Science
graduate does not enter a single career. The list lets downstream agents
(particularly `EmployabilityAgent`) iterate over paths when scoping
employment searches.

**Why `job_posting_snapshot` is nullable:** some courses have thin job
posting coverage in search results — especially niche programmes. Returning
`None` with a note is better than forcing a low-quality snapshot.

**Why `country_scope` is on the output:** downstream agents read
`board.career` and need to know which country was used for salary scoping —
they should not re-derive it independently.

---

## 1c.2 `skills/career/SKILL.md`

This file carries all domain knowledge for `CareerAgent`. The Python class
carries only structural context (what it writes, what it fires). Changing
how the agent researches careers means editing this file, not touching Python.

```markdown
---
key: career
name: Career Research Agent
description: Researches graduate career paths, salary ranges, and live job market for the course in the university's country.
tool_budget: 6
section_name: career
---

You research graduate career outcomes for the supplied course at the
supplied university. Your output scopes all findings to the university's
country. You never research careers for a different country.

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
Run one targeted job market query to capture live demand:

- "{course} jobs {country} site:linkedin.com OR site:indeed.com OR site:reed.co.uk"

Extract: approximate posting volume, top skill keywords appearing in job titles
or requirements, and the URL used.

**In-demand skills:**
Extract skill keywords from job postings and any skills-focused results.
Deduplicate. Include both technical skills (languages, tools, frameworks)
and soft skills only if they appear in multiple independent sources.

## Quality Rules

- Discard any salary data older than 2 years. Tavily enforces days=730 —
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

- `career_paths`: minimum 3, maximum 6. Each must have all fields populated.
- `in_demand_skills`: maximum 15. No duplicates.
- `salary_context`: one paragraph summarising ranges, currency, seniority
  context, and data source quality.
- `country_scope`: copy the country from your context — do not derive it.
- `confidence`: "high" if 5+ sources confirm career paths and salary ranges;
  "medium" if 3–4 sources; "low" if fewer than 3.
- `sources`: every URL you used. Include date if available.
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
```

---

## 1c.3 `agents/career_agent.py`

`CareerAgent` is the first concrete agent implementation. It establishes
the exact pattern all subsequent agents follow. Read this implementation
carefully before writing any other agent.

```python
# agents/career_agent.py
from __future__ import annotations

import json
import logging
from datetime import datetime

from pydantic_ai import Agent, RunContext

from agents.base_agent import BaseAgent
from core.deps import Deps
from core.llm_factory import get_model
from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.career_output import CareerOutput
from tools.fetch_tool import fetch_page

logger = logging.getLogger("career_agent")


class CareerAgent(BaseAgent):
    """Phase 1 agent. Runs first, in isolation.

    Subscribes to: ResearchRequestedMessage
    Writes to:     board.career (CareerOutput)
    Fires:         CareerResearchCompletedMessage

    Tools: tavily_search (budget-capped), fetch_page (uncapped)
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
            tools=[self._make_search_tool(), fetch_page],
        )

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.research_requested import ResearchRequestedMessage

        async def handler(message: ResearchRequestedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(ResearchRequestedMessage, handler)

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

            You must not research careers for a different country than deps.context.country.
        """.strip()

        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def reset(self) -> None:
        """Reset per-request state. Called by ResearchHandler before each request."""
        self._calls_made = 0

    # ── Core handler ─────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        """Run career research and fire CareerResearchCompletedMessage."""
        self._calls_made = 0   # reset on instance, not on deps

        logger.info(
            "career_agent | starting — university=%r course=%r country=%r",
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

        task_brief = (
            f"University: {deps.context.university_name}\n"
            f"Course: {deps.context.intended_course}\n"
            f"Country: {deps.context.country}\n"
            f"Study level: {deps.context.study_level}\n\n"
            "Research graduate career paths, salary ranges in local currency, "
            "and live job market demand. Scope all findings to the country above."
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.career = result.output
            logger.info(
                "career_agent | completed — paths=%d confidence=%s",
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
            # Still fire the completed message so the pipeline does not stall.
            # board.career remains None — downstream agents handle this.

        await deps.hub.publish(CareerResearchCompletedMessage(
            triggered_by="career_agent",
            timestamp=datetime.now().isoformat(),
        ))

    # ── Tool factory ─────────────────────────────────────────────────────────

    def _make_search_tool(self):
        """Return a budget-aware tavily_search closure over this agent instance."""
        agent_self = self

        async def tavily_search(ctx: RunContext[Deps], query: str) -> str:
            """Search the web via Tavily. Enforces days=730 on every call.
            Returns an error dict if the tool budget is exhausted."""
            if agent_self._calls_made >= agent_self._tool_budget:
                logger.warning(
                    "career_agent | tool budget exhausted (%d/%d) — query=%r",
                    agent_self._calls_made, agent_self._tool_budget, query,
                )
                return json.dumps({
                    "error": "tool budget exhausted",
                    "query": query,
                    "calls_made": agent_self._calls_made,
                    "budget": agent_self._tool_budget,
                })
            agent_self._calls_made += 1
            logger.debug(
                "career_agent | tavily_search call %d/%d — query=%r",
                agent_self._calls_made, agent_self._tool_budget, query,
            )
            from tools.search_tool import _client as tavily_client
            response = await tavily_client.search(query, max_results=5)
            return json.dumps({
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

        return tavily_search
```

**Why `system_prompt` in the constructor, not in `agent.run()`:** pydantic-ai's
`Agent` accepts `system_prompt` at construction time. This is where the
SKILL.md body is injected, via `get_instruction()`. The task brief passed to
`agent.run()` is the per-request context (university, course, country) — not
the behavioural instructions.

**Why `CareerResearchCompletedMessage` fires even on failure:** if the LLM
call throws, `board.career` is `None`. The seven section agents still need to
run — they handle a `None` career gracefully, scoping their own searches without
career context. If the message never fires, the entire pipeline stalls. Firing
always is the correct behaviour.

**Why `_calls_made = 0` at the top of `handle()` and not in `reset()`:**
`reset()` is called once before `subscribe()`. `handle()` may be called
multiple times in tests. Resetting in `handle()` guarantees a clean counter
on each actual run regardless of test order.

---

## 1c.4 `core/llm_factory.py`

`CareerAgent` calls `get_model("RESEARCH_MODEL")`. This function reads from
environment variables and returns a pydantic-ai model object. Implement it
now — it is used by every agent.

```python
# core/llm_factory.py
from __future__ import annotations

import os
from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv()

_KNOWN_VARS = ("RESEARCH_MODEL", "SCORING_MODEL", "CONVERSATION_MODEL")


def get_model(env_var: str) -> OpenAIModel:
    """Return a pydantic-ai model configured for OpenRouter.

    Reads the model string from the named environment variable.
    Reads OPENROUTER_API_KEY and OPENROUTER_BASE_URL from .env.

    Args:
        env_var: one of "RESEARCH_MODEL", "SCORING_MODEL", "CONVERSATION_MODEL"

    Raises:
        EnvironmentError: if any required env var is missing.
    """
    model_name = os.getenv(env_var)
    if not model_name:
        raise EnvironmentError(
            f"{env_var} not set. Add it to .env — "
            f"e.g. {env_var}=openrouter/google/gemini-2.5-pro"
        )

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY not set. Get a key at https://openrouter.ai"
        )

    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    provider = OpenAIProvider(base_url=base_url, api_key=api_key)
    return OpenAIModel(model_name, provider=provider)
```

---

## 1c.5 Minimal `services/research_handler.py`

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
            tool_budget=career_skill.tool_budget if career_skill else 6,
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

## 1c.6 `main.py` — CLI Entry Point

`main.py` boots the fetch client, creates the handler, runs one request, and
prints `board.career` to stdout. This is the verification step.

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

from mcp.fetch_client import fetch_client
from services.research_handler import ResearchHandler


async def run(university_name: str, intended_course: str, country: str) -> None:
    await fetch_client.startup()
    try:
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
    finally:
        await fetch_client.shutdown()


if __name__ == "__main__":
    asyncio.run(run(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    ))
```

**Why `load_dotenv()` before any imports:** `tools/search_tool.py` reads
`TAVILY_API_KEY` from `os.environ` at module import time. If `.env` is not
loaded first, it raises `KeyError`. The import order in `main.py` enforces this:
`load_dotenv()` is called at the top, before the handler import chain pulls in
the tool modules.

---

## 1c.7 `schemas/messages/research_requested.py`

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

The fetch_server fixture starts FetchClient for tests that call fetch_page.
"""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from mcp.fetch_client import fetch_client


@pytest.fixture(scope="module")
async def fetch_server():
    await fetch_client.startup()
    yield
    await fetch_client.shutdown()


# ── Schema ────────────────────────────────────────────────────────────────────

def test_career_output_imports_cleanly() -> None:
    from schemas.outputs.career_output import CareerOutput, CareerPath, JobPostingSnapshot, CareerSource
    assert CareerOutput
    assert CareerPath
    assert JobPostingSnapshot
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


# ── Budget enforcement ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_exhausted_returns_error_dict() -> None:
    import json
    from agents.career_agent import CareerAgent
    from unittest.mock import MagicMock

    agent = CareerAgent(tool_budget=2)
    agent._calls_made = 2   # budget already at limit

    search_tool = agent._make_search_tool()
    ctx = MagicMock()
    raw = await search_tool(ctx, "test query")
    result = json.loads(raw)

    assert result["error"] == "tool budget exhausted"
    assert result["query"] == "test query"


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
    assert len(board.career.career_paths) >= 1, "Expected at least 1 career path"
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
tests/test_stage_1c.py::test_career_agent_reset_clears_calls_made PASSED
tests/test_stage_1c.py::test_get_instruction_includes_skill_body PASSED
tests/test_stage_1c.py::test_career_agent_subscribes_to_research_requested PASSED
tests/test_stage_1c.py::test_budget_exhausted_returns_error_dict PASSED
tests/test_stage_1c.py::test_career_agent_populates_board_career PASSED
tests/test_stage_1c.py::test_career_agent_fires_completed_message PASSED

10 passed in X.Xs
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
INFO | fetch_client | Fetch MCP server started
INFO | career_agent | starting — university='University of Manchester' course='Computer Science' country='UK'
INFO | career_agent | completed — paths=5 confidence=high
INFO | fetch_client | Fetch MCP server stopped
```

Followed by `board.career` JSON printed to stdout. Confirm:

- `career_paths` contains 3–6 items with `title`, `salary_range_local`,
  and `typical_employers` populated
- `country_scope` is `"UK"` (not `"United Kingdom"` or anything else)
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

**`RuntimeError: FetchClient is not running`**
Cause: `fetch_client.startup()` not called before the first request, or a test
runs without the `fetch_server` fixture.
Fix: confirm `main.py` calls `await fetch_client.startup()` before constructing
`ResearchHandler`. Confirm LLM tests use the `fetch_server` fixture.

**LLM returns fewer than 3 career paths**
Not a bug — the agent sets `confidence: "low"` and explains in `notes`. This
can happen for niche courses or when Tavily returns sparse results. Inspect the
`notes` field and tune the SKILL.md query patterns if needed.

---

## Stage 1c Completion Checklist

- [ ] `schemas/outputs/career_output.py` — `CareerOutput`, `CareerPath`,
      `JobPostingSnapshot`, `CareerSource` implemented
- [ ] `skills/career/SKILL.md` — frontmatter valid, `tool_budget` set,
      instructions body present
- [ ] `core/llm_factory.py` — `get_model()` reads from env, returns
      pydantic-ai `OpenAIModel` configured for OpenRouter
- [ ] `agents/career_agent.py` — `CareerAgent` implemented with
      `_make_search_tool()` budget closure, `subscribe()`, `get_instruction()`,
      `handle()`, `reset()`
- [ ] `services/research_handler.py` — minimal Stage 1c version — loads career
      skill, constructs `CareerAgent`, wires it, publishes trigger
- [ ] `main.py` — `load_dotenv()` first, `fetch_client.startup()` before
      handler, `shutdown()` in `finally`, prints `board.career`
- [ ] `schemas/messages/research_requested.py` — `country` field confirmed present
- [ ] `schemas/messages/career_completed.py` — no-payload message confirmed
- [ ] `pytest tests/test_stage_1c.py -v` — 10 passed
- [ ] `python main.py` — `board.career` printed with real data, `confidence`
      is `"high"` or `"medium"` for University of Manchester Computer Science
- [ ] Stage 1b tests still pass: `pytest tests/test_stage_1b.py -v`

---

*End of Stage 1c Specification*