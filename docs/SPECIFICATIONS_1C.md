# Stage 1c — CareerAgent End-to-End
## Implementation Specification

**Goal:** `CareerAgent` is fully implemented and verified against a real
university and course. It subscribes to `ResearchRequestedMessage`, calls
Tavily to research career paths, salary ranges, and job postings, writes
a `CareerOutput` to `board.career`, and fires `CareerResearchCompletedMessage`.

**Ends with:** running `python main.py` with a real university and course
populates `board.career` with real data and logs
`career_agent | completed — board.career populated`. All Stage 1c tests pass.

---

## What This Stage Builds and Why It Comes Before All Other Agents

`CareerAgent` is Phase 1. Every other section agent waits for it. It
establishes the career context — paths, salary ranges, in-demand skills —
that `EmployabilityAgent` and `ProgramAgent` read directly from
`board.career` to scope their own searches.

If `CareerAgent` is broken, the entire pipeline is broken. Implementing
and verifying it in isolation before building any section agent means that
when Phase 2 agents are built in Stage 1d onwards, `board.career` is a
known-good dependency.

This stage also establishes the agent pattern that every subsequent agent
follows. Get it right here and the remaining agents are repetitions of the
same structure with different output schemas and SKILL.md files.

---

## 1c.1 `agents/base_agent.py`

`BaseAgent` is the parent class for every agent in the system. Implement
it exactly as specified. Every agent inherits from it.

```python
# agents/base_agent.py
from __future__ import annotations

import logging
from pydantic_ai import Agent


class BaseAgent:
    """Parent class for all research agents.

    Subclasses override _base_prompt() with structural context only.
    Domain knowledge — what to search, how to construct queries, what to
    discard — lives exclusively in the SKILL.md body passed as instructions.

    Attributes:
        instructions: full markdown body from the agent's SKILL.md file.
                      Injected into the system prompt by _build_system_prompt().
                      Empty string if SKILL.md was missing at startup —
                      agent is degraded but functional.
        _agent:       pydantic-ai Agent instance. Set by subclass __init__.
        _logger:      standard logger named after the subclass.
    """

    def __init__(self, instructions: str = "") -> None:
        self.instructions = instructions
        self._agent: Agent | None = None
        self._logger = logging.getLogger(self.__class__.__name__)

    def _base_prompt(self) -> str:
        """Structural context for this agent. Override in every subclass.

        What belongs here:
        - Which blackboard field this agent writes to
        - Which message it fires on success and on failure
        - Which output schema it produces
        - What deps fields it reads (e.g. deps.tavily, deps.board.career)

        What does NOT belong here:
        - What to search for
        - How to construct queries
        - Which sources to prefer
        - Quality thresholds
        - Edge case handling
        All of the above belongs in SKILL.md.
        """
        return ""

    def _build_system_prompt(self) -> str:
        """Combine structural base prompt with SKILL.md instructions.

        Called once during agent construction. The result is passed as
        the system_prompt to the pydantic-ai Agent.

        If instructions is empty (SKILL.md missing), the base prompt
        runs alone. The agent knows its structural role but has no
        domain guidance — it will produce degraded but non-crashing output.
        """
        base = self._base_prompt()
        if self.instructions:
            return base + "\n\n" + self.instructions
        return base
```

**The discipline that matters most:** `_base_prompt()` must never contain
domain knowledge. If you find yourself writing anything about what to search
for in `_base_prompt()`, stop — that belongs in SKILL.md. This separation
is what makes agent behaviour tunable without Python changes.

---

## 1c.2 `agents/career_agent.py`

`CareerAgent` is the first agent to run. It subscribes to
`ResearchRequestedMessage` and fires `CareerResearchCompletedMessage` when
done. It is the only agent that fires this message — all 7 section agents
depend on it as their start signal.

```python
# agents/career_agent.py
from __future__ import annotations

import logging
from datetime import datetime

from pydantic_ai import Agent, RunContext

from agents.base_agent import BaseAgent
from core.deps import Deps
from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.career_output import CareerOutput
from tools.search_tool import _client as tavily_client

logger = logging.getLogger("career_agent")


class CareerAgent(BaseAgent):
    """Phase 1 agent. Runs first. All section agents depend on its output.

    Subscribes to: ResearchRequestedMessage
    Writes to:     deps.board.career  (CareerOutput)
    Fires on success: CareerResearchCompletedMessage
    Fires on failure: CareerResearchCompletedMessage (still fires — pipeline must not stall)

    tool_budget enforced via _search() gate. Counter resets on each handle() call.
    """

    def __init__(self, instructions: str, tool_budget: int = 8) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget  = tool_budget
        self._calls_made   = 0

        self._agent = Agent(
            model=None,           # set by ResearchHandler via llm_factory
            output_type=CareerOutput,
            system_prompt=self._build_system_prompt(),
        )

    def _base_prompt(self) -> str:
        return (
            "You are CareerAgent in a university research pipeline.\n"
            "You run first. Every other agent depends on the context you establish.\n\n"
            "YOUR ROLE:\n"
            "- Research career paths, salary ranges, and live job postings for the given course.\n"
            "- Scope everything to the university's country — not global averages.\n\n"
            "YOUR OUTPUT:\n"
            "- Write a CareerOutput to deps.board.career.\n"
            "- CareerOutput requires: career_paths (min 3), salary_ranges, "
            "job_postings (min 10), in_demand_skills (5-8), sources, confidence, notes.\n\n"
            "YOUR SIGNAL:\n"
            "- Fire CareerResearchCompletedMessage when done — success or failure.\n"
            "- Never leave the pipeline waiting. If research fails, fire the message "
            "with board.career = None and log the reason.\n\n"
            "TOOL BUDGET:\n"
            f"- You have {self._tool_budget} tool calls. Use them precisely.\n"
            "- All calls go through the gated search_web tool — never search directly."
        )

    async def handle(self, param: AgentParam) -> None:
        """Handle ResearchRequestedMessage. Research careers, populate board, fire signal."""
        context = param.deps.context
        board   = param.deps.board
        hub     = param.deps.hub

        # Reset call counter for this request
        self._calls_made = 0

        logger.info(
            "career_agent | started — university=%r course=%r country=%r",
            context.university_name, context.intended_course, context.country,
        )

        # Fire progress update for Chainlit UI
        await hub.publish(ProgressUpdateMessage(
            status="started",
            message=f"Career Agent: researching {context.intended_course} "
                    f"careers in {context.country}",
            triggered_by="career_agent",
            timestamp=datetime.now().isoformat(),
        ), param.deps)

        try:
            result = await self._run_research(param)
            board.career = result

            logger.info(
                "career_agent | completed — %d career paths, %d job postings, "
                "%d in-demand skills",
                len(result.career_paths),
                len(result.job_postings),
                len(result.in_demand_skills),
            )

            await hub.publish(ProgressUpdateMessage(
                status="completed",
                message=f"Career Agent: found {len(result.career_paths)} career paths, "
                        f"{len(result.job_postings)} job postings",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ), param.deps)

        except Exception as exc:
            logger.error("career_agent | failed: %s", exc, exc_info=True)
            board.career = None

            await hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career Agent: failed — {exc}",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ), param.deps)

        finally:
            # Always fire — pipeline must never stall waiting for this signal
            await hub.publish(CareerResearchCompletedMessage(
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ), param.deps)

    async def _run_research(self, param: AgentParam) -> CareerOutput:
        """Build task brief and run the pydantic-ai agent."""
        context = param.deps.context

        task_brief = (
            f"University: {context.university_name}\n"
            f"Course: {context.intended_course}\n"
            f"Country: {context.country}\n"
            f"Study level: {context.study_level}\n\n"
            f"Research career paths, salary ranges, and live job postings for "
            f"{context.intended_course} graduates in {context.country}. "
            f"Tool budget: {self._tool_budget} calls."
        )

        result = await self._agent.run(
            task_brief,
            deps=param.deps,
        )
        return result.output

    async def _search(
        self,
        deps,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
    ):
        """Gated Tavily search. Enforces tool_budget. Returns None if exhausted.

        Every Tavily call in this agent goes through here — never call
        deps.tavily.search() directly.
        """
        if self._calls_made >= self._tool_budget:
            logger.warning(
                "career_agent | tool budget exhausted (%d/%d) — skipping: %r",
                self._calls_made, self._tool_budget, query,
            )
            return None
        self._calls_made += 1
        logger.debug(
            "career_agent | search %d/%d: %r",
            self._calls_made, self._tool_budget, query,
        )
        return await deps.tavily.search(
            query, max_results=max_results, search_depth=search_depth
        )
```

**Why `CareerResearchCompletedMessage` fires in `finally`:** the 7 section
agents are waiting for this signal. If it does not fire — because of an
exception that skips the normal flow — the entire pipeline deadlocks silently.
`finally` guarantees it fires regardless of success or failure.

**Why `board.career = None` on failure is acceptable:** `ScoringAgent`
treats a `None` field as a missing section and redistributes weight. The
pipeline completes with a degraded report rather than crashing.

**Why `_calls_made` resets in `handle()` not `__init__()`:** the same
`CareerAgent` instance handles multiple requests across Chainlit sessions.
Resetting in `__init__()` would carry over the previous run's count.

---

## 1c.3 Registering Tools as pydantic-ai Agent Tools

`CareerAgent`'s pydantic-ai `Agent` needs access to `deps.tavily` as a
registered tool so the LLM can call it during the run. Tools are registered
on the agent using the `@agent.tool` decorator pattern.

Add tool registration in `CareerAgent.__init__()` after the agent is created:

```python
# agents/career_agent.py — __init__ continued

        # Register Tavily search as a callable tool for the LLM
        @self._agent.tool
        async def search_web(ctx, query: str, max_results: int = 5) -> str:
            """Search the web for career information.

            Args:
                query: search query — always include course name and country
                max_results: number of results (default 5, max 10)

            Returns:
                Formatted search results as text.
            """
            response = await self._search(
                ctx.deps, query, max_results=max_results
            )
            if response is None:
                return "Tool budget exhausted — no more searches available."
            if not response.results:
                return f"No results found for: {query}"

            lines = [f"Query: {query}\n"]
            for i, r in enumerate(response.results, 1):
                lines.append(
                    f"{i}. {r.title}\n"
                    f"   URL: {r.url}\n"
                    f"   Date: {r.date or 'unknown'}\n"
                    f"   {r.content}\n"
                )
            return "\n".join(lines)
```

**Why the tool returns a formatted string rather than the raw `SearchResponse`:**
pydantic-ai tools return data that the LLM reads as text in its context window.
A formatted string is more token-efficient and easier for the LLM to parse
than a serialised dataclass.

**Why `max_results` is exposed as a tool parameter:** the LLM can request
more results for broad queries (salary surveys) and fewer for targeted ones
(specific company job postings). This flexibility is worth the slight
increase in tool interface complexity.

---

## 1c.4 Model Injection — `ResearchHandler` Update

`CareerAgent` is constructed with `model=None` in Stage 1c. `ResearchHandler`
injects the model after construction using `llm_factory.get_model()`.

Update `services/research_handler.py`:

```python
# services/research_handler.py — model injection
from core.llm_factory import get_model

class ResearchHandler:
    def __init__(self) -> None:
        skills = scan_skills_dir(Path("skills"))

        def _get(key: str):
            skill = skills.get(key)
            if skill is None:
                logger.warning(
                    "research_handler | no SKILL.md for %r — agent will use base prompt", key
                )
            return skill or _EMPTY

        # Get models from env
        research_model     = get_model("RESEARCH_MODEL")

        # Construct CareerAgent — only agent needed at Stage 1c
        self._career_agent = CareerAgent(
            instructions=_get("career").instructions,
            tool_budget=_get("career").tool_budget or 8,
        )
        # Inject model after construction
        self._career_agent._agent.model = research_model

        logger.info("research_handler | CareerAgent constructed with skill instructions")
```

**Why model=None at construction and injected after:** this keeps the agent
constructor independent of the LLM provider. In tests, the model can be
swapped for a mock without changing the agent constructor.

---

## 1c.5 `main.py` — CLI Entry Point

`main.py` runs the pipeline from the command line without the Chainlit UI.
At Stage 1c it only needs to fire `ResearchRequestedMessage` and confirm
`board.career` is populated.

```python
# main.py
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-25s %(message)s",
    datefmt="%H:%M:%S",
)

from core.blackboard import Blackboard
from core.deps import Deps, ResearchContext
from core.message_hub import MessageHub
from schemas.messages.research_requested import ResearchRequestedMessage
from services.research_handler import ResearchHandler


async def run(university_name: str, intended_course: str) -> None:
    handler = ResearchHandler()

    hub     = MessageHub()
    board   = Blackboard()
    context = ResearchContext(
        university_name=university_name,
        intended_course=intended_course,
        country=await handler._derive_country(university_name),
    )
    deps = Deps(
        hub=hub,
        board=board,
        context=context,
        tavily=handler._tavily,
        fetch=handler._fetch,
        reddit=handler._reddit,
        ddg=handler._ddg,
    )

    hub.subscribe(ResearchRequestedMessage, handler._career_agent.handle)

    await hub.publish(ResearchRequestedMessage(
        university_name=university_name,
        intended_course=intended_course,
        country=context.country,
        triggered_by="main",
        timestamp=datetime.now().isoformat(),
    ), deps)

    # Print result
    if board.career:
        print("\n=== board.career populated ===")
        print(f"Career paths:    {len(board.career.career_paths)}")
        print(f"Job postings:    {len(board.career.job_postings)}")
        print(f"In-demand skills:{board.career.in_demand_skills}")
        print(f"Confidence:      {board.career.confidence}")
        print(f"Sources:         {len(board.career.sources)}")
    else:
        print("\n=== board.career is None — CareerAgent failed ===")


if __name__ == "__main__":
    asyncio.run(run(
        university_name="University of Manchester",
        intended_course="Computer Science",
    ))
```

**Why `_derive_country` is called here:** at Stage 1c `ResearchHandler`
has a `_derive_country` method that uses the LLM to derive country from
university name. It is exposed on the handler for CLI use. In later stages
`handle_request()` does this internally.

---

## 1c.6 `_derive_country` on `ResearchHandler`

Country derivation uses a lightweight LLM call — not a search. It maps a
university name to a country string that all agents use to scope their queries.

Add this method to `ResearchHandler`:

```python
# services/research_handler.py

async def _derive_country(self, university_name: str) -> str:
    """Derive country from university name using a single LLM call.

    Returns a short country name: "UK", "Australia", "USA", "Canada", etc.
    Falls back to "Unknown" if derivation fails — agents handle this gracefully.
    """
    from pydantic_ai import Agent
    from pydantic import BaseModel

    class CountryResult(BaseModel):
        country: str   # short name: "UK", "Australia", "USA", etc.

    agent = Agent(
        model=get_model("RESEARCH_MODEL"),
        output_type=CountryResult,
        system_prompt=(
            "You derive the country a university is located in from its name. "
            "Return a short country name: UK, Australia, USA, Canada, Germany, etc. "
            "If uncertain, return 'Unknown'."
        ),
    )
    try:
        result = await agent.run(
            f"What country is this university in: {university_name}"
        )
        country = result.output.country
        logger.info("research_handler | derived country=%r for %r", country, university_name)
        return country
    except Exception as exc:
        logger.warning(
            "research_handler | country derivation failed for %r: %s — using 'Unknown'",
            university_name, exc,
        )
        return "Unknown"
```

---

## 1c.7 Tests — `tests/test_stage_1c.py`

These tests make **real LLM and API calls**. They require valid keys in `.env`.
Run time is approximately 30–60 seconds per test depending on model latency.

```python
# tests/test_stage_1c.py
"""
Stage 1c integration tests.
Run with: pytest tests/test_stage_1c.py -v -s

These tests make REAL LLM calls via OpenRouter and REAL Tavily searches.
You need OPENROUTER_API_KEY, RESEARCH_MODEL, and TAVILY_API_KEY in .env.
Expected run time: 30–90 seconds.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from dotenv import load_dotenv

load_dotenv()

TIMESTAMP = datetime.now().isoformat()
TEST_UNIVERSITY = "University of Manchester"
TEST_COURSE     = "Computer Science"
TEST_COUNTRY    = "UK"


# ── BaseAgent ─────────────────────────────────────────────────────────────────

def test_base_agent_imports_cleanly() -> None:
    from agents.base_agent import BaseAgent
    assert BaseAgent


def test_base_agent_build_system_prompt_with_instructions() -> None:
    from agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        def _base_prompt(self) -> str:
            return "Base context."

    agent = TestAgent(instructions="Domain knowledge.")
    prompt = agent._build_system_prompt()
    assert "Base context." in prompt
    assert "Domain knowledge." in prompt


def test_base_agent_build_system_prompt_without_instructions() -> None:
    from agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        def _base_prompt(self) -> str:
            return "Base context only."

    agent = TestAgent(instructions="")
    prompt = agent._build_system_prompt()
    assert prompt == "Base context only."


# ── CareerAgent construction ──────────────────────────────────────────────────

def test_career_agent_imports_cleanly() -> None:
    from agents.career_agent import CareerAgent
    assert CareerAgent


def test_career_agent_constructs_with_instructions() -> None:
    from agents.career_agent import CareerAgent
    agent = CareerAgent(instructions="Test instructions.", tool_budget=8)
    assert agent.instructions == "Test instructions."
    assert agent._tool_budget == 8
    assert agent._calls_made == 0
    assert agent._agent is not None


def test_career_agent_system_prompt_contains_base_and_instructions() -> None:
    from agents.career_agent import CareerAgent
    agent = CareerAgent(instructions="Custom skill instructions.", tool_budget=8)
    prompt = agent._build_system_prompt()
    assert "CareerAgent" in prompt
    assert "Custom skill instructions." in prompt


def test_career_agent_tool_budget_default() -> None:
    from agents.career_agent import CareerAgent
    agent = CareerAgent(instructions="")
    assert agent._tool_budget == 8


# ── Tool budget gate ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_career_agent_search_gate_blocks_over_budget() -> None:
    """_search() returns None when budget is exhausted."""
    from agents.career_agent import CareerAgent
    from unittest.mock import AsyncMock, MagicMock

    agent = CareerAgent(instructions="", tool_budget=2)

    mock_deps = MagicMock()
    mock_deps.tavily.search = AsyncMock(return_value=MagicMock(results=[]))

    # First two calls should go through
    await agent._search(mock_deps, "query 1")
    await agent._search(mock_deps, "query 2")
    assert agent._calls_made == 2

    # Third call should be blocked
    result = await agent._search(mock_deps, "query 3")
    assert result is None
    assert agent._calls_made == 2   # counter did not increment


@pytest.mark.asyncio
async def test_career_agent_calls_made_resets_each_handle() -> None:
    """_calls_made resets at the start of handle() — not carried across requests."""
    from agents.career_agent import CareerAgent
    from unittest.mock import AsyncMock, MagicMock, patch

    agent = CareerAgent(instructions="", tool_budget=8)
    agent._calls_made = 7   # simulate near-exhausted budget from a previous run

    # Simulate handle() being called — it should reset _calls_made to 0
    # We test this by checking the reset happens before _run_research
    mock_param = MagicMock()
    mock_param.deps.context.university_name = TEST_UNIVERSITY
    mock_param.deps.context.intended_course = TEST_COURSE
    mock_param.deps.context.country = TEST_COUNTRY
    mock_param.deps.context.study_level = "undergraduate"
    mock_param.deps.hub.publish = AsyncMock()
    mock_param.deps.board = MagicMock()

    with patch.object(agent, '_run_research', new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = Exception("abort after reset check")
        try:
            await agent.handle(mock_param)
        except Exception:
            pass

    assert agent._calls_made == 0   # reset happened before the exception


# ── Message firing ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_career_agent_always_fires_completed_message() -> None:
    """CareerResearchCompletedMessage fires even when research fails."""
    from agents.career_agent import CareerAgent
    from schemas.messages.career_completed import CareerResearchCompletedMessage
    from unittest.mock import AsyncMock, MagicMock, patch

    agent = CareerAgent(instructions="", tool_budget=8)

    fired_messages = []

    async def capture_publish(message, deps):
        fired_messages.append(type(message))

    mock_param = MagicMock()
    mock_param.deps.context.university_name = TEST_UNIVERSITY
    mock_param.deps.context.intended_course = TEST_COURSE
    mock_param.deps.context.country = TEST_COUNTRY
    mock_param.deps.context.study_level = "undergraduate"
    mock_param.deps.hub.publish = capture_publish
    mock_param.deps.board = MagicMock()

    with patch.object(agent, '_run_research', new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = RuntimeError("simulated LLM failure")
        await agent.handle(mock_param)

    assert CareerResearchCompletedMessage in fired_messages, (
        "CareerResearchCompletedMessage must fire even on failure"
    )
    assert mock_param.deps.board.career is None


# ── Full integration — real LLM + real Tavily ─────────────────────────────────

@pytest.mark.asyncio
async def test_career_agent_full_run_populates_board() -> None:
    """Full end-to-end: real LLM + real Tavily. board.career populated."""
    from agents.career_agent import CareerAgent
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from core.message_hub import MessageHub
    from core.llm_factory import get_model
    from schemas.messages.research_requested import ResearchRequestedMessage
    from schemas.outputs.career_output import CareerOutput
    from tools.search_tool import TavilySearchTool

    # Load skill instructions
    from core.skill_loader import scan_skills_dir
    from pathlib import Path
    skills = scan_skills_dir(Path("skills"))
    instructions = skills["career"].instructions if "career" in skills else ""

    agent = CareerAgent(instructions=instructions, tool_budget=8)
    agent._agent.model = get_model("RESEARCH_MODEL")

    hub     = MessageHub()
    board   = Blackboard()
    context = ResearchContext(
        university_name=TEST_UNIVERSITY,
        intended_course=TEST_COURSE,
        country=TEST_COUNTRY,
    )
    deps = Deps(
        hub=hub,
        board=board,
        context=context,
        tavily=TavilySearchTool(),
    )

    hub.subscribe(ResearchRequestedMessage, agent.handle)

    await hub.publish(ResearchRequestedMessage(
        university_name=TEST_UNIVERSITY,
        intended_course=TEST_COURSE,
        country=TEST_COUNTRY,
        triggered_by="test",
        timestamp=TIMESTAMP,
    ), deps)

    # Assert board.career is populated
    assert board.career is not None, (
        "board.career is None — CareerAgent failed. Check logs for details."
    )
    assert isinstance(board.career, CareerOutput)
    assert len(board.career.career_paths) >= 1, "Expected at least 1 career path"
    assert len(board.career.job_postings) >= 1, "Expected at least 1 job posting"
    assert len(board.career.in_demand_skills) >= 1, "Expected at least 1 in-demand skill"
    assert board.career.confidence in ("high", "medium", "low")
    assert len(board.career.sources) >= 1, "Expected at least 1 source"


@pytest.mark.asyncio
async def test_country_derivation() -> None:
    """_derive_country returns a non-empty string for a known university."""
    from services.research_handler import ResearchHandler

    handler = ResearchHandler()
    country = await handler._derive_country("University of Manchester")
    assert isinstance(country, str)
    assert len(country) > 0
    assert country != "Unknown", f"Expected a real country, got: {country!r}"
```

---

## 1c.8 Run the Tests

Unit tests (fast, no API calls):

```bash
pytest tests/test_stage_1c.py -v -k "not full_run and not country_derivation"
```

Full integration test (slow, real API calls — ~60 seconds):

```bash
pytest tests/test_stage_1c.py -v -s
```

Expected output:

```
tests/test_stage_1c.py::test_base_agent_imports_cleanly PASSED
tests/test_stage_1c.py::test_base_agent_build_system_prompt_with_instructions PASSED
tests/test_stage_1c.py::test_base_agent_build_system_prompt_without_instructions PASSED
tests/test_stage_1c.py::test_career_agent_imports_cleanly PASSED
tests/test_stage_1c.py::test_career_agent_constructs_with_instructions PASSED
tests/test_stage_1c.py::test_career_agent_system_prompt_contains_base_and_instructions PASSED
tests/test_stage_1c.py::test_career_agent_tool_budget_default PASSED
tests/test_stage_1c.py::test_career_agent_search_gate_blocks_over_budget PASSED
tests/test_stage_1c.py::test_career_agent_calls_made_resets_each_handle PASSED
tests/test_stage_1c.py::test_career_agent_always_fires_completed_message PASSED
tests/test_stage_1c.py::test_career_agent_full_run_populates_board PASSED
tests/test_stage_1c.py::test_country_derivation PASSED

12 passed in X.Xs
```

Verify the CLI also works:

```bash
python main.py
```

Expected log output:

```
HH:MM:SS  skill_loader              loaded skills/career/SKILL.md
HH:MM:SS  research_handler          CareerAgent constructed with skill instructions
HH:MM:SS  career_agent              started — university='University of Manchester' course='Computer Science' country='UK'
HH:MM:SS  career_agent              search 1/8: 'Computer Science graduate careers UK salary 2024'
HH:MM:SS  career_agent              search 2/8: 'Computer Science jobs London entry level 2024'
...
HH:MM:SS  career_agent              completed — 4 career paths, 12 job postings, 7 in-demand skills

=== board.career populated ===
Career paths:     4
Job postings:     12
In-demand skills: ['Python', 'Machine Learning', 'Cloud', ...]
Confidence:       high
Sources:          8
```

---

## 1c.9 Common Failure Modes at This Stage

**`board.career is None` after full run**
Cause: LLM returned output that failed pydantic-ai's `CareerOutput` validation.
Fix: check the logs for a validation error. The most common cause is the LLM
returning `null` for a required field like `career_paths`. Add a note to the
SKILL.md body requiring the LLM to always return at least one entry per list.

**`CareerResearchCompletedMessage` not fired**
Cause: exception raised before the `finally` block — this should not happen
with the implementation above. If it does, check that `finally` is not inside
a nested try/except that swallows the exception before it reaches the outer
`finally`.

**`tool_budget exhausted` warnings on every run**
Cause: `tool_budget: 8` in `skills/career/SKILL.md` is too low for the queries
the LLM is constructing. Fix: increase `tool_budget` in the SKILL.md file and
restart. No Python change needed.

**`EnvironmentError: RESEARCH_MODEL not set`**
Cause: `.env` missing `RESEARCH_MODEL` key.
Fix: add `RESEARCH_MODEL=openrouter/google/gemini-2.5-pro` to `.env`.

**`model=None` error from pydantic-ai**
Cause: model not injected before `handle()` is called.
Fix: confirm `agent._agent.model = get_model("RESEARCH_MODEL")` runs in
`ResearchHandler.__init__()` before any `handle_request()` call.

---

## Stage 1c Completion Checklist

- [ ] `agents/base_agent.py` implemented — `_build_system_prompt()` working
- [ ] `agents/career_agent.py` implemented — `handle()`, `_search()` gate, `finally` block
- [ ] `search_web` tool registered on pydantic-ai Agent
- [ ] `_derive_country()` implemented on `ResearchHandler`
- [ ] Model injected via `llm_factory.get_model("RESEARCH_MODEL")` in `ResearchHandler.__init__()`
- [ ] `main.py` CLI entry point runs without error
- [ ] `python main.py` — `board.career` populated with real data logged
- [ ] `pytest tests/test_stage_1c.py -v` — 12 passed, 0 failed
- [ ] All prior stage tests still pass: `pytest tests/` — no regressions

---

*End of Stage 1c Specification*