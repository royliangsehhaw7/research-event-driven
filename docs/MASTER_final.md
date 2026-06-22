# University Research Assistant — Master Reference
## Multi-Agent System: Architecture, Patterns, Skills & Setup Guide

**Purpose**: Bounded research system for parents evaluating universities for undergraduate study  
**Framework**: pydantic-ai  
**UI**: Chainlit  
**Architecture**: Observer/Pub-Sub + Blackboard + Quorum Gate + SKILL.md-Driven Agents  
**Status**: Pre-development reference — read this before writing a single line of code

---

## 1. What This System Does and Why

Researching a university for an undergraduate course is fragmented and time-consuming.
Official rankings favour research output. Marketing materials are promotional. The
information that actually matters — student experiences, graduate employment evidence,
course-specific reputation, real living costs — is scattered across dozens of sources
and forums.

This system takes two inputs — a university name and a course — and produces a
structured, sourced, confidence-flagged research report in minutes. A parent making
a real decision gets what a diligent researcher would spend days assembling.

**Two inputs. Everything else is derived or researched internally.**

```
university_name:  "University of Manchester"
intended_course:  "Computer Science"
```

The system derives the country from the university name. Study level is hardcoded
to undergraduate. Career goals are researched, not supplied by the user.

**Two output files per run:**

| File | Content |
|---|---|
| `report.md` | Executive summary at the top, followed by all research sections with confidence flags and inline sources |
| `score.json` | Machine-readable score breakdown — enables multi-university comparison |

**`report.md` structure:**

```
# [University Name] — [Course] Research Report

## Executive Summary
Tier, overall score, top 3 positives, top 3 concerns, alternative universities

---

## 1. Career Landscape
Career paths, salary ranges (country-scoped, local currency), live job snapshot,
in-demand skills extracted from postings.

## 2. University Background
Founding, size, public/private status, research vs teaching orientation,
course-specific accreditations, industry partnerships for the department.

## 3. Subject Rankings
Subject-specific rank (QS/THE/Guardian/Complete University Guide),
graduate employability rank, overall rank (lowest weight, clearly labelled).

## 4. Undergraduate Program
Matching program titles, core modules yr1 and yr2, electives, duration,
sandwich year / study abroad options, curriculum-to-career-skills mapping.

## 5. Graduate Employability
Employment rate, industries and named companies graduates enter,
graduate salary specific to this university, department industry partnerships.

## 6. Accommodation & Living
On-campus cost (weekly, inclusions), off-campus rent (monthly, city-scoped),
area safety (statistics, not opinions), transport routes and journey times.

## 7. Recent News
Institutional and department-level news from the past 2 years,
each item sentiment-classified: positive / negative / neutral.

## 8. Student Forum Findings
Recurring positives (3+ independent sources required),
recurring concerns (3+ independent sources required),
department-specific teaching and course feedback.

## 9. Score & Recommendation
Weighted score (0–10), tier (Strong Consider / Consider / Proceed with Caution / Avoid),
top 3 supporting reasons, top 3 concerns to investigate, per-dimension score breakdown.

## 10. Alternative Universities
2–3 alternatives that address the primary university's weakest dimensions,
each with: subject ranking, program note, employability note, evidence for the gap claim.
```

Every section includes inline sources (URL + date) drawn from the agent output schemas.
Sections where data was unavailable or low-confidence are marked explicitly — the report
never silently omits a section.

**What it will not do:**

- Guarantee accuracy — outputs are research summaries, not verified facts
- Cover postgraduate, Masters, or PhD programs
- Handle visa, immigration, or cost-of-living context
- Access paywalled content
- Make the final decision — it informs, the parent decides

---

## 2. System Boundaries

### In Scope
- Undergraduate programs only
- Single university + course as primary research target
- 2–3 alternative universities as secondary output
- Information dated within the last 2 years only
- Employability data restricted to the university's country
- Forum content scoped strictly to the researched course/department

### Out of Scope
- Postgraduate, Masters, PhD
- Cost of living, visa, immigration
- Real-time monitoring or persistent history across sessions
- Direct application assistance
- Browser automation or scraping

### Fixed Assumptions (not user inputs)
- Study level: undergraduate — hardcoded constant
- University country: derived from university name by the system
- Career goals: researched by the system from the course name

---

## 3. Third-Party Tools and API Keys

### Search Tools

| Tool | Kind | Role | API Key Required |
|---|---|---|---|
| **Tavily** | Python client | Primary search — career paths, salary, forum, news, rankings | `TAVILY_API_KEY` |
| **Fetch MCP** | MCP server | Direct URL fetch — catalog pages, salary surveys | None |
| **Adzuna** | REST API | Live job postings — UK and Australia | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` |
| **MyCareersFuture** | REST API | Live job postings — Singapore only | None — public API |
| **DuckDuckGo** | Python client | NewsAgent fallback — no key, no quota | None |
>[!WARNING]
> DDG will NOT be wired up first as it does NOT filter by dates
>

**Fetch MCP is the only MCP server in the stack.** Tavily, Adzuna, MyCareersFuture,
and DuckDuckGo are plain Python/HTTP clients — no MCP protocol involved.
The connection for Fetch is a shared `fastmcp.Client`, defined once in
`mcps/fetch_client.py` and reused by every agent. The pydantic-ai tool function
that wraps it lives in `tools/fetch_tool.py`.

**Why dedicated job posting tools:** Tavily cannot reliably retrieve live job
postings — job boards (Indeed, Reed, LinkedIn) block fetch-based access and
Tavily's `site:` queries do not honour `time_range` filtering for job boards.
Adzuna (UK + AU) and MyCareersFuture (SG) are purpose-built APIs returning
structured, dated postings. They replace Tavily for the job posting snapshot
in CareerAgent only — Tavily remains the primary tool for all other research.

**Why these tools:**
Tavily handles all general search including `include_domains`-scoped queries
against `thestudentroom.co.uk`, `studentcrowd.com`, `whatuni.com`, and
`quora.com`. ForumAgent uses `include_domains` to restrict searches to specific
confirmed-accessible public student forums — no separate Reddit API client is
required or available (Reddit API access closed May 2026). DuckDuckGo replaces
SerpAPI as a zero-cost news fallback with no monthly quota.

### LLM Provider

All models are accessed via OpenRouter. Set `OPENROUTER_API_KEY` and point pydantic-ai
at the OpenRouter base URL.

| Setting | Environment Variable |
|---|---|
| Research agent model | `RESEARCH_MODEL` (e.g. `openrouter/google/gemini-2.5-pro`) |
| Scoring/alternatives model | `SCORING_MODEL` |
| Conversation agent model | `CONVERSATION_MODEL` |
| OpenRouter base URL | `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1` |

### Getting API Keys

**Tavily** — https://app.tavily.com  
Sign up free. Free tier: 1,000 API credits/month. Paid from $35/month.
A full pipeline run uses approximately 50–70 tool calls total across all agents.

**DuckDuckGo Search** — no signup, no key, no quota.
Install: `pip install ddgs`. Used by NewsAgent as fallback only.

**OpenRouter** — https://openrouter.ai  
Create API key from dashboard. Set `OPENROUTER_API_KEY`.
Choose models via `RESEARCH_MODEL`, `SCORING_MODEL`, `CONVERSATION_MODEL` env vars.

### Environment File

```bash
# .env
TAVILY_API_KEY=tvly-...
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

RESEARCH_MODEL=openrouter/google/gemini-2.5-pro
SCORING_MODEL=openrouter/google/gemini-2.5-pro
CONVERSATION_MODEL=openrouter/google/gemini-2.5-flash
```

### Python Dependencies

```
# requirements.txt
pydantic-ai
pydantic
chainlit
pyyaml                # SKILL.md frontmatter parsing
tavily-python         # Tavily search client
ddgs                  # News fallback — no key needed (NewsAgent)
fastmcp               # Fetch MCP client (shared, reentrant)
mcp-server-fetch      # Fetch MCP Server subprocess
jinja2                # report generation
python-dotenv
pytest                # testing
```

---

## 4. Architecture Overview

### 4.1 Two-Phase Design

The system runs in two sequential phases with a hard boundary between them.
No section agents run until Phase 1 completes.

```
User Input: university_name + intended_course
          │
          ▼
┌─────────────────────────────────────────────────┐
│  Phase 1 — Career Research (Sequential)         │
│                                                 │
│  CareerAgent runs first. Researches career      │
│  paths, salary ranges, job postings for the     │
│  course in the university's country.            │
│  Writes → board.career                          │
│  Fires  → CareerResearchCompletedMessage        │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  Phase 2 — Research Cascade (Concurrent)        │
│                                                 │
│  7 section agents fan out concurrently.         │
│  All subscribe to CareerResearchCompletedMessage│
│  All run via asyncio.gather() — no orchestrator │
│  Each writes its own blackboard field           │
│  Each fires SectionCompletedMessage or          │
│  SectionFailedMessage when done                 │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  Phase 3 — Synthesis (Sequential)               │
│                                                 │
│  ScoringAgent: quorum gate, waits for 7,        │
│  scores all sections, fires ScoringCompleted    │
│                                                 │
│  AlternativesAgent: reads board.score.weaknesses│
│  finds 2–3 gap-targeted alternatives            │
│                                                 │
│  ReportGenerator: deterministic, no LLM         │
│  renders 4 output files from full blackboard    │
└─────────────────────────────────────────────────┘
                     │
                     ▼
              Chainlit UI
         (Mode 1: research display)
         (Mode 2: conversational follow-up)
```

### 4.2 Full Message Flow

```
[ResearchRequestedMessage]
        ↓
[CareerAgent]              Phase 1 — sequential
  writes: board.career
  fires:  CareerResearchCompletedMessage
        ↓
[BackgroundAgent]   ──┐
[RankingsAgent]       │    Phase 2 — all concurrent via asyncio.gather()
[ProgramAgent]        │    all subscribe to CareerResearchCompletedMessage
[EmployabilityAgent]  │    each writes board.<section>
[AccommodationAgent]  │    each fires SectionCompletedMessage
[NewsAgent]           │    or SectionFailedMessage
[ForumAgent]        ──┘
        ↓
[ScoringAgent]             quorum gate — waits for exactly N section results
  writes: board.score      (pass or fail — count is all that matters)
  fires:  ScoringCompletedMessage
        ↓
[AlternativesAgent]        reads board.score.weaknesses
  writes: board.alternatives
  fires:  AlternativesCompletedMessage
        ↓
[ReportGenerator]          deterministic Python, no LLM
  reads:  full blackboard
  writes: report.md, score.json
  fires:  ReportReadyMessage (file_paths: [report.md, score.json])
        ↓
[Chainlit UI]              displays report, offers file downloads
```

---

## 5. Four MAS Design Patterns

This system deliberately combines four patterns. Each governs a distinct
concern. Understanding which pattern does what prevents confusion during
implementation.

---

### Pattern 1 — Observer / Pub-Sub (MessageHub)

The research cascade is an Observer pattern. `MessageHub` is the subject.
Agents are the observers.

**What the hub is:** a dictionary mapping message types to lists of async
handler functions, plus a single `asyncio.gather()` call on publish.

```
MessageHub state after all subscribe() calls:

ResearchRequestedMessage       → [career_agent.handle]
CareerResearchCompletedMessage → [background_agent.handle,
                                  rankings_agent.handle,
                                  program_agent.handle,
                                  employability_agent.handle,
                                  accommodation_agent.handle,
                                  news_agent.handle,
                                  forum_agent.handle]
SectionCompletedMessage        → [scoring_agent.handle]
SectionFailedMessage           → [scoring_agent.handle]
ScoringCompletedMessage        → [alternatives_agent.handle]
AlternativesCompletedMessage   → [report_generator.handle]
ReportReadyMessage             → [chainlit_ui.handle]
ProgressUpdateMessage          → [chainlit_ui.handle]
```

`publish(message)` does exactly this:
```python
handlers = self._subscribers.get(type(message), [])
await asyncio.gather(*[h(message) for h in handlers])
```

**The hub has zero domain knowledge.** It does not know what a university
is, what a course is, or what any message contains. It knows message types
and handler lists only.

**Critical separation — messages vs outputs:**

Messages are lean notifications. They carry only `triggered_by` and
`timestamp` (plus `section_name` for section messages). They signal that
something is done. They carry no research data.

Outputs are rich LLM results. They are written to the blackboard.
Downstream agents read the blackboard directly — never reconstruct
data from a message payload.

```
# One agent, two distinct steps — every agent follows this:

# 1. Write full rich output to blackboard
param.deps.board.forum = forum_result   # ForumOutput — all findings

# 2. Publish lean notification to hub
await param.deps.hub.publish(SectionCompletedMessage(
    section_name="forum",
    triggered_by="forum_agent",
    timestamp=datetime.now().isoformat(),
), param.deps)
```

**Important:** the term "event loop" is reserved for Python's asyncio
event loop. Never use it to describe the hub's dispatch mechanism.

---

### Pattern 2 — Blackboard (Shared Data Store)

The Blackboard is a typed per-request result accumulator. It is a plain
dataclass on `Deps`. One fresh instance per research request — discarded
when the report is generated.

```python
@dataclass
class Blackboard:
    career:         CareerOutput        | None = None
    background:     BackgroundOutput    | None = None
    rankings:       RankingsOutput      | None = None
    program:        ProgramOutput       | None = None
    employability:  EmployabilityOutput | None = None
    accommodation:  AccommodationOutput | None = None
    news:           NewsOutput          | None = None
    forum:          ForumOutput         | None = None
    score:          ScoringOutput       | None = None
    alternatives:   AlternativesOutput  | None = None
```

**What `None` means:** a field is `None` either because the agent hasn't
run yet or because it failed. `ScoringAgent` handles both cases —
a `None` field means the dimension cannot be scored and weight is
redistributed to the remaining sections. It is never an error state
that blocks the pipeline.

**How agents use the blackboard:**

Agents write to their own field after the LLM call completes:
```python
# forum_agent.handle()
result = await self._agent.run(task_brief, deps=deps)
deps.board.forum = result.output   # writes ForumOutput
```

Agents that need upstream data read it directly:
```python
# employability_agent.handle() — reads career context before searching
career_data = deps.board.career    # reads CareerOutput
if career_data:
    career_paths = career_data.career_paths
    # use career_paths to scope employment searches
```

**The blackboard persists in the Chainlit session** after the pipeline
completes. `ConversationAgent` reads from it to answer follow-up questions
without re-running any searches.

---

### Pattern 3 — Quorum Gate (ScoringAgent)

`ScoringAgent` subscribes to both `SectionCompletedMessage` AND
`SectionFailedMessage`. It maintains a counter of received results.
When `received == expected_sections` it proceeds — regardless of
how many passed or failed.

```python
# ScoringAgent internal state (per request):
expected_sections: int   # set at startup from count of registered research agents
received_count: int = 0  # increments on SectionCompleted OR SectionFailed
_lock: asyncio.Lock      # guards the counter — concurrent publishes are safe

async def handle(self, message: SectionCompletedMessage | SectionFailedMessage,
                 deps: Deps) -> None:
    async with self._lock:
        self.received_count += 1
        if isinstance(message, SectionFailedMessage):
            setattr(deps.board, message.section_name, None)
        if self.received_count < self.expected_sections:
            return   # wait for remaining sections
    # gate opens — score whatever is on the board
    await self._score(deps)
```

**Why `asyncio.Lock` is required:** `asyncio.gather()` fires all 7 section
agent handlers concurrently. Multiple `SectionCompletedMessage` publishes
can arrive and trigger `handle()` before any single call finishes. A plain
`received_count += 1` is not safe — the check-and-increment must be atomic.
Without the lock, scoring fires multiple times. This is the most common
implementation bug in this pattern.

**Why `expected_sections` is dynamic, not hardcoded to 7:**
If any SKILL.md fails to load at startup, that agent never registers.
`expected_sections` is set from the actual count of successfully registered
research agents after the startup scan. Hardcoding 7 causes a silent
deadlock when a file is missing.

**What this pattern gives the system:**
- Pipeline always completes — no agent failure causes a deadlock
- Partial results produce a partial report with clear confidence flags
- Pass/fail ratio is irrelevant to gate opening — only count matters

---

### Pattern 4 — SKILL.md-Driven Agent Instructions

Every agent's behavioural instructions — what to research, how to construct
queries, what to discard, how to structure output, how to handle edge cases —
live in a `SKILL.md` file, not in Python strings.

The Python agent class carries only structural context (what blackboard field
it writes, what message it fires, what output schema it produces). Domain
knowledge is entirely in the file. Changing agent behaviour = editing markdown,
restarting. No Python changes. No redeploy of code.

This is covered in detail in Section 7.

---

## 6. Core Infrastructure — Key Files

### `core/message_hub.py`

```python
from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Callable
from pydantic import BaseModel


class MessageHub:
    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, message_type: type, handler: Callable) -> None:
        self._subscribers[message_type].append(handler)

    async def publish(self, message: BaseModel) -> None:
        handlers = self._subscribers.get(type(message), [])
        if not handlers:
            return
        await asyncio.gather(*[h(message) for h in handlers])
```

One instance per research request — created fresh in `ResearchHandler.handle_request()`.
Never reused across requests. Reusing causes handler accumulation from prior requests.

---

### `core/blackboard.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from schemas.outputs.career_output import CareerOutput
from schemas.outputs.background_output import BackgroundOutput
from schemas.outputs.rankings_output import RankingsOutput
from schemas.outputs.program_output import ProgramOutput
from schemas.outputs.employability_output import EmployabilityOutput
from schemas.outputs.accommodation_output import AccommodationOutput
from schemas.outputs.news_output import NewsOutput
from schemas.outputs.forum_output import ForumOutput
from schemas.outputs.scoring_output import ScoringOutput
from schemas.outputs.alternatives_output import AlternativesOutput


@dataclass
class Blackboard:
    career:         CareerOutput        | None = None
    background:     BackgroundOutput    | None = None
    rankings:       RankingsOutput      | None = None
    program:        ProgramOutput       | None = None
    employability:  EmployabilityOutput | None = None
    accommodation:  AccommodationOutput | None = None
    news:           NewsOutput          | None = None
    forum:          ForumOutput         | None = None
    score:          ScoringOutput       | None = None
    alternatives:   AlternativesOutput  | None = None

    def is_complete(self) -> bool:
        """All research sections present — score and alternatives may still be None."""
        research_fields = [
            self.career, self.background, self.rankings, self.program,
            self.employability, self.accommodation, self.news, self.forum,
        ]
        return all(f is not None for f in research_fields)
```

---

### `core/deps.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from core.message_hub import MessageHub
from core.blackboard import Blackboard


@dataclass
class ResearchContext:
    university_name:  str          # "University of Manchester"
    intended_course:  str          # "Computer Science"
    country:          str          # "UK" — derived by ResearchHandler, never None
    study_level:      str = "undergraduate"   # hardcoded constant


@dataclass
class Deps:
    hub:      MessageHub
    board:    Blackboard
    context:  ResearchContext
```

`Deps` contains only per-request state — hub, board, and context. It is created
fresh in `ResearchHandler.handle_request()` and discarded when the report is generated.

Tool clients (Tavily, Fetch MCP, DuckDuckGo) are **not** on `Deps`. Each
tool function owns its own client as a module-level singleton — created once at
import/startup time, reused across all requests. See Section 8 for details.

`tool_budget` and `calls_made` live on each agent instance (`self._tool_budget`,
`self._calls_made`), not on `Deps`. This ensures concurrent section agents each
manage their own counter independently.

---

### `agents/base_agent.py`

```python
from __future__ import annotations

from core.logger import logger
from abc import ABC, abstractmethod

from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelResponse, TextPart

from core.message_hub import MessageHub
from core.deps import Deps



class BaseAgent(ABC):
    """Base class for all research pipeline agents.

    Each subclass:
    - constructs its own pydantic-ai Agent with exactly the tools it needs
    - implements subscribe() to register its handler(s) on the hub via closure
    - implements get_instruction() to return its system prompt (base + SKILL.md body)

    instructions: the full markdown body from the agent's SKILL.md file.
    Injected by ResearchHandler at construction time. Empty string if SKILL.md
    is missing — agent is degraded but functional.
    """

    def __init__(self, instructions: str = "") -> None:
        self.instructions = instructions
        self._agent: Agent | None = None   # constructed by subclass __init__

        # Isolated request session metrics per-agent instance
        self._current_cot_buffer: list[str] = []

    def reset(self) -> None:
        """Called before each request's subscribe loop. No-op by default.
        Subclasses that carry per-request state (e.g. a _fired flag) override this."""
        ...

    def _setup_telemetry_hooks(self) -> Hooks:
        """Helper factory method called by subclasses during Agent construction.
        
        Injects uniform logging behavior across all subclass agents.
        """
        hooks = Hooks()

        @hooks.on.after_model_request
        async def capture_turn_metrics(ctx, response: ModelResponse, **kwargs) -> ModelResponse:
            # 1. Uniform fleet-wide token tracking (CORRECTED ATTRIBUTES)
            if response.usage:
                logger.warning(
                    "[TOKENS] Input=%d | Output=%d | Total=%d",
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.usage.total_tokens,
                )
            
            # 2. Uniform fleet-wide COT harvesting
            for part in response.parts:
                if isinstance(part, TextPart) and part.content:
                    self._current_cot_buffer.append(part.content)
                elif type(part).__name__ == 'ThinkingPart' and hasattr(part, 'content'):
                    thinking_content = getattr(part, 'content', '')
                    self._current_cot_buffer.append(thinking_content)
                    
                    # -> ADD THIS LINE: Log the thinking block immediately for this turn
                    if thinking_content:
                        logger.info("\n[THINKING BLOCK]\n%s\n", thinking_content)
                    
            return response

        return hooks

    def flush_cot_log(self) -> str:
        """Consolidates and returns the full COT buffer compiled across all LLM turns."""
        return "\n".join(self._current_cot_buffer).strip()


    
    @abstractmethod
    def subscribe(self, hub: MessageHub, deps: Deps) -> None:
        """Register this agent's handler(s) on the hub via closure.

        deps is captured at subscription time. The hub never receives deps.

        Example:
            def subscribe(self, hub, deps):
                async def handler(message):
                    await self.handle(message, deps)
                hub.subscribe(SomeMessage, handler)
        """
        ...

    @abstractmethod
    def get_instruction(self) -> str:
        """Return the full system prompt for this agent.

        Combine a short structural preamble (what blackboard field the agent
        writes, what message it fires, what output schema it returns) with
        self.instructions (the SKILL.md body — search strategy, query
        construction, quality filters, edge cases).

        Example:
            def get_instruction(self) -> str:
                base = \"\"\"
                    You are the CareerAgent in a university research pipeline.
                    Write your findings to deps.board.career as a CareerOutput.
                    Fire CareerResearchCompletedMessage when done.
                \"\"\"
                return base + "\\n\\n" + self.instructions if self.instructions else base
        """
        ...

```

**Why `_setup_telemetry_hooks()` and `flush_cot_log()` live here:**
Every agent in the fleet needs uniform token tracking and chain-of-thought
capture without each subclass reimplementing it. `_setup_telemetry_hooks()`
is a factory method called once during each subclass's `__init__`, passed
into the pydantic-ai `Agent` constructor via `capabilities=[...]`. The hook
registers an `after_model_request` callback that fires after every LLM turn —
it logs input/output/total token counts at `WARNING` level (so they surface
regardless of the active log filter), and appends any `TextPart` or
`ThinkingPart` content to `self._current_cot_buffer`. `ThinkingPart` blocks
(extended thinking from supported models) are also logged immediately as
they arrive. `flush_cot_log()` collapses the buffer into a single string
after the run completes — subclasses call it in `handle()` if they want to
persist or log the full reasoning trace. The buffer lives on the agent
instance (`self._current_cot_buffer`), so concurrent section agents each
maintain their own independent trace.

**Why closures instead of passing `deps` through the hub:** the hub's `publish(message)`
signature stays clean — it has no knowledge of `deps`. Each agent's `subscribe()` captures
`deps` in a closure at subscription time. The hub calls `handler(message)`; the handler
calls `self.handle(message, deps)` with the captured deps. This matches the pattern
established in the v7 customer service system.

**Why `reset()` is here:** agents are built once and reused across Chainlit sessions.
Any agent that accumulates per-request state must override `reset()` and be called
before each new request's subscribe loop. ResearchHandler calls `reset()` on every
agent before subscribing.

**The discipline that matters most:** `get_instruction()` structural preamble carries
only pipeline role context. Domain knowledge — what to search, how to construct
queries, what to discard — belongs entirely in SKILL.md. If you find yourself writing
"search for salary ranges" in `get_instruction()`, stop — that belongs in
`skills/career/SKILL.md`.

---

### `schemas/messages/` — All Message Types

Every message carries `triggered_by` and `timestamp`. Nothing else unless required.

```python
# schemas/messages/base_message.py
from pydantic import BaseModel

class BaseMessage(BaseModel):
    triggered_by: str
    timestamp: str

# schemas/messages/research_requested.py
class ResearchRequestedMessage(BaseMessage):
    university_name: str
    intended_course: str
    country: str

# schemas/messages/career_completed.py
class CareerResearchCompletedMessage(BaseMessage):
    pass   # no payload — downstream agents read board.career directly

# schemas/messages/section_completed.py
class SectionCompletedMessage(BaseMessage):
    section_name: str   # "background", "forum", etc. — matches blackboard field name

# schemas/messages/section_failed.py
class SectionFailedMessage(BaseMessage):
    section_name: str
    reason: str

# schemas/messages/scoring_completed.py
class ScoringCompletedMessage(BaseMessage):
    pass

# schemas/messages/alternatives_completed.py
class AlternativesCompletedMessage(BaseMessage):
    pass

# schemas/messages/report_ready.py
class ReportReadyMessage(BaseMessage):
    file_paths: list[str]   # paths to the 2 generated output files: report.md, score.json

# schemas/messages/progress_update.py
class ProgressUpdateMessage(BaseMessage):
    status: str    # "started" | "completed" | "failed"
    message: str   # human-readable — displayed in Chainlit live feed
```

**Why messages carry no research data:** LLM output schemas evolve frequently
as the system is tuned. Message schemas must be stable — they are the routing
contracts. Keeping them separate means output schema changes never break routing.

---

### Output Schema Pattern

Each section has a rich output schema. These go in `schemas/outputs/`.
Every output schema includes a `confidence` field and a `sources` list.

```python
# schemas/outputs/forum_output.py  — illustrative structure
from pydantic import BaseModel
from typing import Literal

class ForumSource(BaseModel):
    url: str
    platform: str   # "thestudentroom", "studentcrowd", "whatuni", "quora"
    year: int
    poster_type: str   # "current_student", "graduate", "prospective"

class ForumFinding(BaseModel):
    summary: str            # paraphrased — never verbatim quotes
    source_count: int       # must be >= 3 to qualify
    sources: list[ForumSource]

class ForumOutput(BaseModel):
    recurring_positives: list[ForumFinding]
    recurring_concerns:  list[ForumFinding]
    department_feedback: list[ForumFinding]
    confidence: Literal["high", "medium", "low"]
    notes: str   # empty results explanation, or edge case notes
```

Every output schema must have:
- `confidence: Literal["high", "medium", "low"]`
- `sources: list[<SourceModel>]` — each source with URL + date minimum
- `notes: str` for edge case explanations

`ScoringAgent` reads `confidence` from every field to down-weight or
redistribute scoring weight. `ReportGenerator` reads `notes` to render
the "unavailable" or "low confidence" section markers.

---

## 7. SKILL.md Pattern — Full Specification

### Why SKILL.md

Without SKILL.md files, agent instructions are strings embedded in Python.
Tuning `ForumAgent` to be stricter about off-topic threads means editing
Python. Changing `ScoringAgent`'s tier thresholds means touching agent logic.
This is the wrong layer for what is essentially configuration.

The fix: each agent's behavioural instructions live in a `SKILL.md` file.
The skill loader reads them at startup. The agent injects them into its system
prompt. Changing behaviour = editing markdown + restart. No Python change.

### File Format

```
skills/<key>/SKILL.md
```

Two parts separated by `---`:

**Part 1 — YAML frontmatter (machine-readable):**

| Field | Required | Type | Description |
|---|---|---|---|
| `key` | yes | string | Unique identifier. Lowercase, no spaces. Must match folder name. |
| `name` | yes | string | Human-readable name. Used in logs. |
| `description` | yes | string | One-line summary. Used in progress messages and report metadata. |
| `tool_budget` | yes | int | Max tool calls per run. `0` for agents that don't use tools (scoring, conversation). |
| `section_name` | no | string | Blackboard field name this agent writes to. Omit for scoring, alternatives, conversation. |

**Part 2 — Markdown body (instructions verbatim into system prompt):**

Written as direct instructions. Contains: what to research, how to construct
queries, what to discard, signal quality rules, output requirements, edge cases.

### `core/skill_loader.py` — Full Implementation

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger("skill_loader")


@dataclass
class SkillMeta:
    key: str
    name: str
    description: str
    tool_budget: int
    section_name: str | None   # None for scoring, alternatives, conversation
    instructions: str          # full markdown body — injected into system prompt


def load_skill(path: Path) -> SkillMeta | None:
    """Parse a single SKILL.md file. Returns None on any parse failure.
    Logs a warning for every skipped file — silent failures are not acceptable."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill_loader | cannot read %s: %s", path, exc)
        return None

    parts = raw.split("---", maxsplit=2)
    if len(parts) < 3:
        logger.warning("skill_loader | %s: missing frontmatter delimiters — skipping", path)
        return None

    yaml_block = parts[1].strip()
    body = parts[2].strip()

    try:
        meta = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        logger.warning("skill_loader | %s: YAML parse error: %s — skipping", path, exc)
        return None

    if not isinstance(meta, dict):
        logger.warning("skill_loader | %s: frontmatter is not a mapping — skipping", path)
        return None

    required = ("key", "name", "description", "tool_budget")
    missing = [f for f in required if f not in meta or meta[f] is None]
    if missing:
        logger.warning("skill_loader | %s: missing required fields %s — skipping", path, missing)
        return None

    try:
        tool_budget = int(meta["tool_budget"])
    except (TypeError, ValueError):
        logger.warning("skill_loader | %s: tool_budget must be an integer — skipping", path)
        return None

    skill = SkillMeta(
        key=str(meta["key"]).lower(),
        name=str(meta["name"]),
        description=str(meta["description"]),
        tool_budget=tool_budget,
        section_name=meta.get("section_name") or None,
        instructions=body,
    )
    logger.info("skill_loader | loaded %s", path)
    return skill


def scan_skills_dir(skills_dir: Path) -> dict[str, SkillMeta]:
    """Scan skills/ directory. Returns dict keyed by skill.key.
    Duplicate keys: first wins, warning logged. Missing SKILL.md: silently skipped."""
    result: dict[str, SkillMeta] = {}

    if not skills_dir.is_dir():
        logger.warning("skill_loader | skills dir %s does not exist — no skills loaded", skills_dir)
        return result

    for subdir in sorted(skills_dir.iterdir()):
        if not subdir.is_dir():
            continue
        skill_file = subdir / "SKILL.md"
        if not skill_file.exists():
            continue
        skill = load_skill(skill_file)
        if skill is None:
            continue
        if skill.key in result:
            logger.warning("skill_loader | duplicate key %r in %s — first entry wins", skill.key, skill_file)
            continue
        result[skill.key] = skill

    return result
```

### How Instructions Flow into Agents

`ResearchHandler` loads all skills at startup, before constructing any agent:

```python
# services/research_handler.py

from core.skill_loader import scan_skills_dir, SkillMeta
from dataclasses import dataclass

@dataclass
class _EmptySkill:
    instructions: str = ""
    tool_budget: int = 0
    description: str = ""

_EMPTY = _EmptySkill()


class ResearchHandler:
    def __init__(self) -> None:
        skills = scan_skills_dir(Path("skills"))

        def _get(key: str) -> SkillMeta | _EmptySkill:
            skill = skills.get(key)
            if skill is None:
                logger.warning("research_handler | no SKILL.md for %r — agent will use base prompt", key)
            return skill or _EMPTY

        self._career_agent        = CareerAgent(instructions=_get("career").instructions)
        self._background_agent    = BackgroundAgent(instructions=_get("background").instructions)
        self._rankings_agent      = RankingsAgent(instructions=_get("rankings").instructions)
        self._program_agent       = ProgramAgent(instructions=_get("program").instructions)
        self._employability_agent = EmployabilityAgent(instructions=_get("employability").instructions)
        self._accommodation_agent = AccommodationAgent(instructions=_get("accommodation").instructions)
        self._news_agent          = NewsAgent(instructions=_get("news").instructions)
        self._forum_agent         = ForumAgent(
                                        instructions=_get("forum").instructions,
                                        tool_budget=_get("forum").tool_budget or 10,
                                    )
        self._scoring_agent       = ScoringAgent(
                                        instructions=_get("scoring").instructions,
                                        expected_sections=len([k for k in skills if k in RESEARCH_AGENT_KEYS]),
                                    )
        self._alternatives_agent  = AlternativesAgent(instructions=_get("alternatives").instructions)
        self._conversation_agent  = ConversationAgent(instructions=_get("conversation").instructions)

        logger.info("research_handler | agents constructed with skill instructions")
```

`RESEARCH_AGENT_KEYS` is the set of keys that register as section agents:
`{"career", "background", "rankings", "program", "employability", "accommodation", "news", "forum"}`.
`ScoringAgent` receives `expected_sections` from this count — not hardcoded to 7.

### What Goes in `get_instruction()` vs SKILL.md

This is the most important discipline in the entire system:

| Belongs in `get_instruction()` structural preamble | Belongs in SKILL.md body |
|---|---|
| "You are the Forum Research Agent in a university research pipeline." | What to search for |
| "You write your findings to deps.board.forum as a ForumOutput." | How to construct queries |
| "You fire SectionCompletedMessage(section_name='forum') on success." | Which sources to use and in what order |
| | What to discard and why |
| | Signal quality thresholds |
| | Output structure requirements |
| | Edge case handling |

The structural preamble describes the agent's pipeline role — it never changes.
SKILL.md describes what the agent should actually do — it changes as the system
is tuned.

---

## 8. Tools — Per-Agent Registration

### 8.1 Design decision

Tools are the **only** mechanism through which research agents access external data.
Each tool is an async function registered on the pydantic-ai `Agent` at construction
time. The LLM calls tools mid-reasoning during `agent.run()` — but it can only call
the tools registered on that specific agent.

This is the key constraint: the tool set assigned at construction time limits what
the LLM can do. There is no free orchestration. A `CareerAgent` cannot call
`ddg_search` because that function was never registered on it.

### 8.2 Folder structure — `mcps/` vs `tools/`

Two folders. One responsibility each.

**`mcps/`** — MCP server connection objects. One file per MCP server. Each file
defines the shared client object for exactly one MCP server. Nothing else
lives here. (Named `mcps/`, not `mcp/` — `mcp` is the name of the underlying
SDK package, and a same-named local folder would shadow it on `sys.path`.)

**`tools/`** — pydantic-ai tool functions. One file per tool. Each file defines
one async tool function that the LLM can call. Each tool owns its own client as
a module-level singleton (or, for Fetch, imports the shared client from `mcps/`).
Nothing else lives here.

```
mcps/
└── fetch_client.py         Fetch MCP — module-level fastmcp.Client (shared, reentrant)

tools/
├── search_tool.py          tavily_search — module-level AsyncTavilyClient singleton
├── fetch_tool.py           fetch_page — calls fetch_client from mcps/fetch_client.py
└── ddg_tool.py              ddg_search — module-level DDGS singleton
```

Tavily and DuckDuckGo are plain Python client libraries — no MCP
protocol. Only Fetch is an MCP server. Its shared client is defined in
`mcps/fetch_client.py`. `tools/fetch_tool.py` imports that client directly and
calls `call_tool()` on it inside its own `async with` block — the tool function
owns its docstring, error handling, and return shape; the client object owns
the connection.

### 8.3 `mcps/fetch_client.py`

```python
# mcps/fetch_client.py
from __future__ import annotations

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

# Single shared client for the Fetch MCP server (mcp-server-fetch, run as a
# subprocess via stdio). Import this instance everywhere it's needed — do not
# construct a new Client.
#
# fastmcp.Client is a reentrant, ref-counted async context manager: `async with
# fetch_client:` can be entered from multiple places (the app entry point, and
# again inside fetch_page) and the underlying subprocess/session is started on
# the first entry and only stopped on the last matching exit. Concurrent
# `call_tool()` calls on the shared session are multiplexed by request ID, so
# this is safe under `asyncio.gather()` across section agents.
fetch_client = Client(
    StdioTransport(command="python", args=["-m", "mcp_server_fetch"])
)
```

One file, one shared object, no custom class. `tools/fetch_tool.py` imports
`fetch_client` and calls `await fetch_client.call_tool(...)` inside its own
`async with fetch_client:` block — it has no knowledge of who else has the
connection open. The app entry point *may* also wrap the whole run in
`async with fetch_client:` to pre-warm the subprocess before the first
`fetch_page` call, but this is an optimization, not a requirement (see 8.9).

### 8.4 Tool budget enforcement

`tool_budget` from SKILL.md is passed to each agent constructor and stored as
`self._tool_budget`. A per-request counter `self._calls_made` is reset to `0`
at the start of each `handle()` call.

Budget is enforced inside each search tool function via a closure over the agent
instance — `fetch_page` is exempt as it is a targeted retrieval, not a search:

```python
# Inside agent __init__, wrap search tools with a budget-aware closure
def _make_search_tool(self):
    agent_self = self
    async def tavily_search(ctx: RunContext[Deps], query: str) -> str:
        if agent_self._calls_made >= agent_self._tool_budget:
            return json.dumps({"error": "tool budget exhausted", "query": query})
        agent_self._calls_made += 1
        from tools.search_tool import _client as tavily_client
        results = await tavily_client.search(query, days=730, max_results=5)
        return json.dumps(results)
    return tavily_search
```

Storing the counter on the agent instance (not on `Deps`) ensures concurrent
section agents each manage their own count independently.

When budget is exhausted the tool returns an error dict — the LLM reads it,
sets `confidence: "low"`, and returns what it has. A partial result with a
low confidence flag is better than a pipeline failure.

### 8.5 Date filtering

Tavily enforces the 2-year window mechanically via `days=730` — stale results
never reach the LLM.

Fetch MCP fetches a specific URL — no date filtering needed, the URL is always
explicit and targeted.

DuckDuckGo has no equivalent API parameter. Its wrapper filters by publication
date before returning results to the LLM:

```python
# ddg_tool.py — filter before returning
cutoff = datetime.now() - timedelta(days=730)
items = [r for r in raw_results if r.get("date") and parse(r["date"]) >= cutoff]
```

The SKILL.md instruction ("discard anything older than 2 years") remains as a
secondary LLM-level check for items with ambiguous or missing dates.

### 8.6 Tool-to-agent mapping

| Tool | career | background | rankings | program | employability | accommodation | news | forum | alternatives | scoring | conversation |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `tavily_search` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `fetch_page` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `ddg_search` | | | | | | |  | | | | |

`scoring` and `conversation` have no tools — they work entirely from the
blackboard. `tool_budget: 0` in their SKILL.md makes this explicit.

### 8.7 Tool implementations

**`tools/search_tool.py`**

```python
import json
import os
from tavily import TavilyClient
from pydantic_ai import RunContext
from core.deps import Deps

_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


async def tavily_search(ctx: RunContext[Deps], query: str) -> str:
    """Search the web via Tavily. Enforces days=730 on every call.
    Budget enforcement is handled by the agent's _make_search_tool() closure.
    This bare function is used only when wrapped by the agent."""
    results = await _client.search(query, days=730, max_results=5)
    return json.dumps(results)
```

**`tools/fetch_tool.py`**

```python
import json
from pydantic_ai import RunContext
from core.deps import Deps
from mcps.fetch_client import fetch_client


async def fetch_page(ctx: RunContext[Deps], url: str) -> str:
    """Fetch a specific URL via the Fetch MCP server.
    Use for university catalog pages, rankings pages, or any URL found in
    search results. Does not count against tool_budget — targeted retrieval,
    not a search."""
    async with fetch_client:
        result = await fetch_client.call_tool("fetch", {"url": url})
    return json.dumps({"url": url, "content": str(result)})
```

> This is the illustrative shape. The full implementation (Stage 1b) wraps the
> result in `FetchResult`, extracts text content from the MCP response, and
> never raises — see `tools/fetch_tool.py` in Stage 1b for the real version.

**`tools/ddg_tool.py`**

```python
import json
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from ddgs import DDGS
from pydantic_ai import RunContext
from core.deps import Deps

_client = DDGS()

async def ddg_search(ctx: RunContext[Deps], query: str) -> str:
    """Search via DuckDuckGo. NewsAgent fallback when Tavily misses news items.
    Filters to last 730 days before returning.
    Budget enforcement handled by agent closure.
    
    CURRENTLY NOT WIRED TO ANY AGENTS
    """
    cutoff = datetime.now() - timedelta(days=730)
    raw = _client.text(query, max_results=10)
    items = []
    for r in raw:
        date_str = r.get("date", "")
        try:
            if date_str and parse_date(date_str) >= cutoff:
                items.append(r)
        except Exception:
            pass   # discard items with unparseable dates
    return json.dumps(items)
```
>[!WARNING]
> DDG will NOT be wired up first as it does NOT filter by dates
>


### 8.8 How tools attach to agents

Tools are registered on the pydantic-ai `Agent` at construction time. Each agent
wraps its search tools in a budget-aware closure via `_make_search_tool()`.
`fetch_page` is registered directly — no budget wrapping needed.

```python
# CareerAgent — Tavily + Fetch only
class CareerAgent(BaseAgent):
    def __init__(self, instructions: str, tool_budget: int) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0
        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=CareerOutput,
            tools=[self._make_search_tool(), fetch_page],
        )

# ForumAgent — Tavily + Fetch (same tool set as all section agents)
class ForumAgent(BaseAgent):
    def __init__(self, instructions: str, tool_budget: int) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0
        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=ForumOutput,
            tools=[self._make_search_tool(), fetch_page],
        )

# NewsAgent — Tavily + Fetch + DuckDuckGo
class NewsAgent(BaseAgent):
    def __init__(self, instructions: str, tool_budget: int) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0
        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=NewsOutput,
            tools=[self._make_search_tool(), fetch_page, self._make_ddg_tool()],
        )
```

### 8.9 Fetch MCP server lifecycle — app entry points

`fetch_client` is a single shared `fastmcp.Client`. Wrapping the application
boundary in `async with fetch_client:` is **optional** — `fetch_page` opens its
own `async with fetch_client:` block on every call and is fully self-contained.
Doing it at the boundary too is purely a latency optimization: it pre-starts
the `mcp-server-fetch` subprocess once, before the first request, so the first
`fetch_page` call doesn't pay subprocess-startup cost. Because the client is
reentrant and ref-counted, the inner and outer `async with` blocks nest safely
— the connection stays open until the outermost one exits. `ResearchHandler`
still has no startup or shutdown responsibilities either way.

**Chainlit (`ui/app.py`):**

```python
from contextlib import AsyncExitStack
from mcps.fetch_client import fetch_client

_stack = AsyncExitStack()

@cl.on_chat_start
async def start():
    await _stack.enter_async_context(fetch_client)

@cl.on_chat_end
async def end():
    await _stack.aclose()
```

**FastAPI (when you expose an endpoint):**

```python
from contextlib import asynccontextmanager
from mcps.fetch_client import fetch_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with fetch_client:
        yield

app = FastAPI(lifespan=lifespan)
```

**CLI (`main.py`):**

```python
from mcps.fetch_client import fetch_client

async def main():
    async with fetch_client:
        result = await handler.handle_request(university_name, course)
```

---

## 9. Handler Pattern — Closures

Every agent's `subscribe()` method registers a closure on the hub. The closure
captures `deps` at subscription time. The hub calls `handler(message)` — it never
receives or knows about `deps`.

```python
# Every agent subscribe() method looks like this
def subscribe(self, hub: MessageHub, deps: Deps) -> None:
    async def handler(message):
        await self.handle(message, deps)   # deps captured here
    hub.subscribe(SomeMessage, handler)
```

Every agent's `handle()` method signature is:

```python
async def handle(self, message: SomeMessage, deps: Deps) -> None:
    # reset budget counter for this request — counter lives on the agent instance
    self._calls_made = 0
    ...
```

`ResearchHandler.handle_request()` creates fresh per-request objects, calls
`reset()` on every agent, subscribes all agents via their `subscribe()` methods,
then fires the single trigger:

```python
async def handle_request(self, university_name: str, intended_course: str) -> Blackboard:
    # 1. Derive country
    country = await self._derive_country(university_name)

    # 2. Create fresh per-request objects
    hub   = MessageHub()
    board = Blackboard()
    context = ResearchContext(
        university_name=university_name,
        intended_course=intended_course,
        country=country,
    )
    deps = Deps(
        hub=hub,
        board=board,
        context=context,
    )

    # 3. Reset stateful agents, then subscribe all — deps captured in closures
    for agent in self._all_agents:
        agent.reset()

    self._career_agent.subscribe(hub, deps)

    self._background_agent.subscribe(hub, deps)
    self._rankings_agent.subscribe(hub, deps)
    self._program_agent.subscribe(hub, deps)
    self._employability_agent.subscribe(hub, deps)
    self._accommodation_agent.subscribe(hub, deps)
    self._news_agent.subscribe(hub, deps)
    self._forum_agent.subscribe(hub, deps)

    self._scoring_agent.subscribe(hub, deps)
    self._alternatives_agent.subscribe(hub, deps)
    self._report_generator.subscribe(hub, deps)

    # 4. Fire the single trigger
    await hub.publish(ResearchRequestedMessage(
        university_name=university_name,
        intended_course=intended_course,
        country=country,
        triggered_by="research_handler",
        timestamp=datetime.now().isoformat(),
    ))

    return board
```

**Why closures instead of passing `deps` through `publish()`:** the hub's
`publish(message)` signature stays clean — it has no knowledge of `deps`.
Each agent captures `deps` once at subscription time. This matches the pattern
from the v7 customer service system and is the idiomatic pydantic-ai approach.

**Why `reset()` before subscribe:** agents are built once and reused across
Chainlit sessions. Any per-request state (e.g. `_fired` flags on agents that
must not run twice) must be cleared before a new request's subscribe loop.

**How `tool_budget` reaches each agent's tool:** each agent resets
`self._calls_made = 0` at the start of its `handle()` call. The budget-aware
closure over `self` checks and increments this counter before calling the
module-level client directly. Since `asyncio.gather()` interleaves at `await`
points, two concurrent agents could theoretically read each other's counter if
it lived on shared `Deps`. Keeping it on the agent instance prevents this:

```python
async def handle(self, message, deps: Deps) -> None:
    self._calls_made = 0   # reset on agent instance, not on deps
    ...
```

And inside each tool function, the closure reaches the module-level client
directly — no `ctx.deps` needed for the client:

```python
# Inside agent __init__, wrap the tool with a budget-aware closure
def _make_search_tool(self):
    agent_self = self
    async def tavily_search(ctx: RunContext[Deps], query: str) -> str:
        if agent_self._calls_made >= agent_self._tool_budget:
            return json.dumps({"error": "tool budget exhausted"})
        agent_self._calls_made += 1
        from tools.search_tool import _client as tavily_client
        results = await tavily_client.search(query, days=730, max_results=5)
        return json.dumps(results)
    return tavily_search
```

This keeps `Deps` clean — only `hub`, `board`, `context` — and each concurrent
agent manages its own counter independently.

---

## 10. Chainlit — UI Layer

### 10.1 Two Modes

The UI has exactly two modes. Mode is determined by whether a research run has
completed in the current session — not by a user setting or a keyword.

**Mode 1 — Research Trigger**
The user has not yet submitted a research request in this session, or has
started a new one. Any message that looks like a university + course input
triggers the pipeline. `ProgressUpdateMessage` events render live agent
status as the pipeline runs. On `ReportReadyMessage`, the report renders
inline and both output files are offered for download.

**Mode 2 — Conversational Follow-Up**
A research run has completed. The blackboard is populated and stored in
the Chainlit session. Any subsequent message is treated as a follow-up
question. `ConversationAgent` answers from the blackboard — no new searches,
no new pipeline run. Mode 2 ends when the user submits a new research
request (explicit re-trigger), which resets the session state.

---

### 10.2 Session State

One dataclass holds all per-session state. It is stored in the Chainlit
user session dict and is `None` until a research run completes.

```python
# ui/app.py
from __future__ import annotations
from dataclasses import dataclass, field
from core.blackboard import Blackboard
from core.deps import ResearchContext

@dataclass
class ResearchSession:
    blackboard:           Blackboard
    report_files:         list[str]          # [path/to/report.md, path/to/score.json]
    conversation_history: list = field(default_factory=list)   # pydantic-ai ModelMessage list
    context:              ResearchContext = None
```

**Session isolation:** each new research request creates a fresh `ResearchSession`
and overwrites the previous one. Data from a prior run never bleeds into a
new one. The Chainlit session dict key is `"research_session"`.

```python
# Store after pipeline completes
cl.user_session.set("research_session", ResearchSession(
    blackboard=board,
    report_files=message.file_paths,
    context=deps.context,
))

# Read in Mode 2
session: ResearchSession | None = cl.user_session.get("research_session")
```

---

### 10.3 `ui/app.py` — Full Structure

```python
# ui/app.py
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path

import chainlit as cl
from dotenv import load_dotenv

load_dotenv()

from mcps.fetch_client import fetch_client
from services.research_handler import ResearchHandler
from agents.conversation_agent import ConversationAgent
from core.skill_loader import scan_skills_dir
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.messages.report_ready import ReportReadyMessage

_stack = AsyncExitStack()
_handler: ResearchHandler | None = None


# ── Lifecycle ──────────────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_chat_start() -> None:
    """Boot fetch client and handler once per session."""
    global _handler
    await _stack.enter_async_context(fetch_client)
    if _handler is None:
        _handler = ResearchHandler()
    cl.user_session.set("research_session", None)
    await cl.Message(
        content=(
            "Welcome. Enter a university name and course to begin research.\n\n"
            "Example: *University of Manchester — Computer Science*"
        )
    ).send()


@cl.on_chat_end
async def on_chat_end() -> None:
    await _stack.aclose()


# ── Message routing ───────────────────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message) -> None:
    session = cl.user_session.get("research_session")

    if session is None or _is_new_research_request(message.content):
        await _run_research(message.content)
    else:
        await _run_conversation(message.content, session)


def _is_new_research_request(text: str) -> bool:
    """Heuristic: does this look like a university + course pair?
    Any message containing ' — ' or matching known trigger patterns resets the session.
    Keeps Mode 2 from accidentally re-triggering the pipeline on a follow-up question."""
    return " — " in text or text.strip().lower().startswith("research ")


# ── Mode 1 — Research pipeline ────────────────────────────────────────────────

async def _run_research(user_input: str) -> None:
    """Parse input, run pipeline, render report, store session."""
    cl.user_session.set("research_session", None)   # clear any prior session

    university_name, intended_course = _parse_input(user_input)
    if not university_name or not intended_course:
        await cl.Message(
            content=(
                "Please enter a university name and course separated by ' — '\n"
                "Example: *University of Manchester — Computer Science*"
            )
        ).send()
        return

    # Register progress handler BEFORE starting pipeline
    progress_msg = await cl.Message(content="Starting research pipeline…").send()
    step_lines: list[str] = []

    async def on_progress(msg: ProgressUpdateMessage) -> None:
        icon = {"started": "🔍", "completed": "✅", "failed": "❌"}.get(msg.status, "•")
        step_lines.append(f"{icon} {msg.message}")
        await progress_msg.update(content="\n".join(step_lines))

    async def on_report_ready(msg: ReportReadyMessage) -> None:
        pass   # handled after handle_request() returns

    board = await _handler.handle_request(
        university_name=university_name,
        intended_course=intended_course,
        on_progress=on_progress,
        on_report_ready=on_report_ready,
    )

    # Render report inline
    report_path = Path("outputs") / f"{university_name}_{intended_course}_report.md"
    score_path  = Path("outputs") / f"{university_name}_{intended_course}_score.json"

    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")
        await cl.Message(content=report_text).send()
        await cl.Message(
            content="Download your research files:",
            elements=[
                cl.File(name="report.md",   path=str(report_path), display="inline"),
                cl.File(name="score.json",  path=str(score_path),  display="inline"),
            ],
        ).send()
    else:
        await cl.Message(content="⚠️ Report generation failed — check logs.").send()
        return

    # Persist session for Mode 2
    from core.deps import ResearchContext
    cl.user_session.set("research_session", ResearchSession(
        blackboard=board,
        report_files=[str(report_path), str(score_path)],
        context=ResearchContext(
            university_name=university_name,
            intended_course=intended_course,
            country=board.career.country_scope if board.career else "unknown",
        ),
    ))

    await cl.Message(
        content="Research complete. Ask any follow-up questions about this university and course."
    ).send()


def _parse_input(text: str) -> tuple[str, str]:
    """Split 'University Name — Course Name' into two strings.
    Returns ('', '') if the format is not recognised."""
    if " — " in text:
        parts = text.split(" — ", maxsplit=1)
        return parts[0].strip(), parts[1].strip()
    if " - " in text:
        parts = text.split(" - ", maxsplit=1)
        return parts[0].strip(), parts[1].strip()
    return "", ""


# ── Mode 2 — Conversational follow-up ────────────────────────────────────────

async def _run_conversation(question: str, session: ResearchSession) -> None:
    """Answer a follow-up question from the blackboard via ConversationAgent."""
    skills = scan_skills_dir(Path("skills"))
    conv_skill = skills.get("conversation")
    agent = ConversationAgent(
        instructions=conv_skill.instructions if conv_skill else ""
    )

    thinking_msg = await cl.Message(content="Thinking…").send()

    answer, updated_history = await agent.run(
        question=question,
        blackboard=session.blackboard,
        context=session.context,
        history=session.conversation_history,
    )

    session.conversation_history = updated_history
    cl.user_session.set("research_session", session)

    await thinking_msg.update(content=answer)
```

**Why `ConversationAgent` is constructed per-question rather than once at startup:**
`ConversationAgent` holds no per-request state — it carries no `_calls_made`
counter and no `_fired` flag. Constructing it fresh each time avoids any risk
of history contamination between sessions. The cost is negligible since it
makes no tool calls.

**Why progress messages are a running log, not individual Chainlit steps:**
Chainlit steps (`async with cl.Step(...)`) require knowing the step name at
entry time. Agent progress arrives asynchronously as `ProgressUpdateMessage`
events — we don't know which agent will report next. Appending to a single
message and calling `update()` gives a clean live feed without needing step
nesting or ordering.

**Why `_is_new_research_request()` uses ` — ` as the signal:**
The canonical input format is `University Name — Course`. A follow-up
question like "what are the top employers?" will never contain that separator.
This heuristic is intentionally simple — the alternative is an intent
classifier LLM call, which adds latency and a new failure mode.

---

### 10.4 `ConversationAgent`

`ConversationAgent` is the only agent that is not wired into the pub-sub
pipeline. It has no `subscribe()` call and fires no messages. It is called
directly by `ui/app.py` in Mode 2.

```python
# agents/conversation_agent.py
from __future__ import annotations

from pydantic_ai import Agent
from agents.base_agent import BaseAgent
from core.blackboard import Blackboard
from core.deps import ResearchContext
from core.llm_factory import get_model
from core.logger import logger


class ConversationAgent(BaseAgent):
    """Answers follow-up questions from the blackboard. No tools. No pub-sub.

    Called directly by ui/app.py — not subscribed to any hub message.
    Uses CONVERSATION_MODEL (typically a faster/cheaper model than RESEARCH_MODEL).
    """

    def __init__(self, instructions: str = "") -> None:
        super().__init__(instructions=instructions)
        self._agent = Agent(
            model=get_model("CONVERSATION_MODEL"),
            capabilities=[self._setup_telemetry_hooks()],
        )
        logger.info("ConversationAgent | initialized")

    def subscribe(self, hub, deps) -> None:
        pass   # ConversationAgent is never subscribed to the hub

    def get_instruction(self) -> str:
        base = "You are the Conversation Agent in a university research pipeline."
        return base + "\n\n" + self.instructions if self.instructions else base

    async def run(
        self,
        question:   str,
        blackboard: Blackboard,
        context:    ResearchContext,
        history:    list,
    ) -> tuple[str, list]:
        """Answer a follow-up question using only the blackboard data.

        Returns (answer_text, updated_message_history).
        Never makes tool calls — all data is in the blackboard context.
        """
        board_summary = _serialise_blackboard(blackboard)

        system_prompt = (
            self.get_instruction() + "\n\n"
            f"University: {context.university_name}\n"
            f"Course: {context.intended_course}\n"
            f"Country: {context.country}\n\n"
            "Research data (answer only from this — do not invent):\n"
            f"{board_summary}"
        )

        result = await self._agent.run(
            question,
            system_prompt=system_prompt,
            message_history=history,
        )
        return result.output, result.all_messages()


def _serialise_blackboard(board: Blackboard) -> str:
    """Convert populated blackboard fields to compact JSON string for context injection."""
    import json
    sections = {}
    for field_name in [
        "career", "background", "rankings", "program",
        "employability", "accommodation", "news", "forum",
        "score", "alternatives",
    ]:
        value = getattr(board, field_name)
        if value is not None:
            sections[field_name] = value.model_dump()
    return json.dumps(sections, indent=2, default=str)
```

**Why `system_prompt` is passed per-call rather than at construction:**
The blackboard content is per-session and changes between sessions. Passing
it at construction would bind the agent to one session's data permanently.
Passing it per-call keeps the agent stateless and safely reusable.

**Why `_serialise_blackboard()` uses `model_dump()` not `model_dump_json()`:**
`json.dumps(..., default=str)` handles any non-serialisable types (dates,
custom objects) gracefully. `model_dump_json()` would raise on the same inputs.

---

## 11. ReportGenerator — Deterministic Rendering

### 11.1 Role and Constraints

`ReportGenerator` is not an agent. It makes no LLM calls. It subscribes to
`AlternativesCompletedMessage`, reads the full blackboard, renders two output
files using Jinja2, then fires `ReportReadyMessage`. It is pure deterministic
Python — the same blackboard always produces the same files.

This is a deliberate constraint. LLM-generated report prose drifts between
runs and is hard to test. Jinja2 templates are version-controlled, reviewable,
and produce consistent structure. Quality tuning means editing the template —
not re-prompting.

`ReportGenerator` lives in `report/generator.py`. The Jinja2 template lives in
`report/templates/report.md.j2`. Both are loaded at runtime — the generator
has no hardcoded strings beyond section headers.

---

### 11.2 Output Files

Two files are written per run, into an `outputs/` directory at the project root.
Filenames are slugified from the university name and course.

| File | Format | Purpose |
|---|---|---|
| `{slug}_report.md` | Markdown | Human-readable report — all 10 sections, inline sources, confidence flags |
| `{slug}_score.json` | JSON | Machine-readable scores — enables multi-university comparison |

Filename slug example: `university_of_manchester_computer_science_report.md`

---

### 11.3 `report/generator.py`

```python
# report/generator.py
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from core.blackboard import Blackboard
from core.deps import ResearchContext
from core.logger import logger
from schemas.messages.alternatives_completed import AlternativesCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.messages.report_ready import ReportReadyMessage


TEMPLATE_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR   = Path("outputs")


class ReportGenerator:
    """Subscribes to AlternativesCompletedMessage. Renders report.md and score.json.
    Fires ReportReadyMessage with file paths on completion.
    No LLM calls. No tool calls. Pure Jinja2 + JSON serialisation.
    """

    def subscribe(self, hub, deps) -> None:
        async def handler(message: AlternativesCompletedMessage) -> None:
            await self.handle(message, deps)
        hub.subscribe(AlternativesCompletedMessage, handler)

    def reset(self) -> None:
        pass   # no per-request state

    async def handle(self, message: AlternativesCompletedMessage, deps) -> None:
        logger.info("ReportGenerator | starting")

        await deps.hub.publish(ProgressUpdateMessage(
            status="started",
            message="Generating report files…",
            triggered_by="report_generator",
            timestamp=datetime.now().isoformat(),
        ))

        OUTPUT_DIR.mkdir(exist_ok=True)
        slug = _slugify(
            f"{deps.context.university_name}_{deps.context.intended_course}"
        )

        try:
            report_path = OUTPUT_DIR / f"{slug}_report.md"
            score_path  = OUTPUT_DIR / f"{slug}_score.json"

            _render_report(deps.board, deps.context, report_path)
            _render_score(deps.board, deps.context, score_path)

            logger.info(
                "ReportGenerator | completed — report=%s score=%s",
                report_path, score_path,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="Report files ready.",
                triggered_by="report_generator",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(ReportReadyMessage(
                file_paths=[str(report_path), str(score_path)],
                triggered_by="report_generator",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            logger.error("ReportGenerator | failed: %s", exc)
            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Report generation failed: {exc}",
                triggered_by="report_generator",
                timestamp=datetime.now().isoformat(),
            ))


def _render_report(board: Blackboard, context: ResearchContext, path: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.md.j2")
    rendered = template.render(board=board, context=context)
    path.write_text(rendered, encoding="utf-8")


def _render_score(board: Blackboard, context: ResearchContext, path: Path) -> None:
    if board.score is None:
        score_data = {"error": "scoring did not complete"}
    else:
        score_data = {
            "university":      context.university_name,
            "course":          context.intended_course,
            "country":         context.country,
            "generated_at":    datetime.now().isoformat(),
            "overall_score":   board.score.overall_score,
            "tier":            board.score.tier,
            "dimension_scores": board.score.dimension_scores,
            "top_positives":   board.score.top_positives,
            "top_concerns":    board.score.top_concerns,
            "alternatives": [
                {
                    "name":               alt.university_name,
                    "subject_rank":       alt.subject_rank,
                    "gap_addressed":      alt.gap_addressed,
                    "employability_note": alt.employability_note,
                    "program_note":       alt.program_note,
                }
                for alt in (board.alternatives.alternatives if board.alternatives else [])
            ],
        }
    path.write_text(json.dumps(score_data, indent=2, default=str), encoding="utf-8")


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
```

---

### 11.4 `score.json` Schema

The score file is the machine-readable output designed for multi-university
comparison. Its structure is fixed — do not add LLM-generated prose to it.

```json
{
  "university":    "University of Manchester",
  "course":        "Computer Science",
  "country":       "UK",
  "generated_at":  "2025-10-01T14:23:00",
  "overall_score": 7.4,
  "tier":          "Strong Consider",
  "dimension_scores": {
    "career":          8.0,
    "background":      7.5,
    "rankings":        8.5,
    "program":         7.0,
    "employability":   8.0,
    "accommodation":   6.5,
    "news":            7.0,
    "forum":           6.5
  },
  "top_positives": [
    "Top-10 UK subject ranking for Computer Science (QS 2024)",
    "Strong graduate employment rate — 92% within 6 months",
    "Named partnerships with Amazon, ThoughtWorks, and BAE Systems"
  ],
  "top_concerns": [
    "Accommodation costs among highest in UK outside London",
    "Forum feedback flags large class sizes in Year 1",
    "Limited sandwich year uptake reported by students"
  ],
  "alternatives": [
    {
      "name":               "University of Edinburgh",
      "subject_rank":       "Top 50 QS CS 2024",
      "gap_addressed":      "accommodation",
      "employability_note": "Strong fintech and startup pipeline",
      "program_note":       "MEng option available"
    }
  ]
}
```

**Why `dimension_scores` uses blackboard field names as keys:** `ScoringAgent`
writes scores keyed to section names that match the blackboard fields exactly.
The renderer copies them directly. Any mismatch between `ScoringOutput` field
names and blackboard field names surfaces immediately as a `KeyError` in tests.

---

### 11.5 `report.md.j2` — Template Structure

The Jinja2 template renders all 10 sections in fixed order. Each section
block is wrapped in a `{% if board.<field> %}` guard — if the agent failed,
the section renders a `> ⚠️ Data unavailable` notice instead of being silently
omitted. This is the "never silently omit a section" guarantee from Section 1.

**Confidence flag convention used throughout the template:**

| `confidence` value | Flag rendered |
|---|---|
| `"high"` | *(no flag — high confidence is the default)* |
| `"medium"` | `> 📊 Medium confidence — some sources limited` |
| `"low"` | `> ⚠️ Low confidence — treat findings as indicative only` |

**Source citation convention:** every source renders as
`([domain](url), date)` inline — extracted from each output schema's
`sources` list. The template never renders raw URLs without anchor text.

```jinja
{# report/templates/report.md.j2 #}
# {{ context.university_name }} — {{ context.intended_course }} Research Report
*Generated {{ now }}*

---

## Executive Summary

{% if board.score %}
**Overall Score:** {{ board.score.overall_score }}/10 — **{{ board.score.tier }}**

**Top 3 Strengths:**
{% for p in board.score.top_positives %}
- {{ p }}
{% endfor %}

**Top 3 Concerns:**
{% for c in board.score.top_concerns %}
- {{ c }}
{% endfor %}

**Alternative Universities:** See Section 10.
{% else %}
> ⚠️ Scoring did not complete — executive summary unavailable.
{% endif %}

---

## 1. Career Landscape

{% if board.career %}
{% if board.career.confidence != "high" %}
> {{ board.career.confidence | confidence_flag }}
{% endif %}

**Country scope:** {{ board.career.country_scope }}

**Graduate Career Paths:**
{% for path in board.career.career_paths %}
- **{{ path.title }}** — {{ path.description }}
  *Typical employers: {{ path.typical_companies | join(", ") }}*
{% endfor %}

**Salary Ranges ({{ board.career.salary_ranges[0].currency if board.career.salary_ranges }}):**
| Role | Entry | Mid | Senior |
|---|---|---|---|
{% for s in board.career.salary_ranges %}
| {{ s.career_path }} | {{ s.entry_level }} | {{ s.mid_level }} | {{ s.senior_level }} |
{% endfor %}

**In-Demand Skills:** {{ board.career.in_demand_skills | join(", ") }}

**Live Job Postings Snapshot ({{ board.career.job_postings | length }} postings):**
{% for job in board.career.job_postings[:5] %}
- {{ job.title }} @ {{ job.company }} — {{ job.location }} ([link]({{ job.url }}), {{ job.date_posted }})
{% endfor %}
{% if board.career.job_postings | length > 5 %}
*…and {{ board.career.job_postings | length - 5 }} more postings retrieved.*
{% endif %}

{% if board.career.notes %}*Note: {{ board.career.notes }}*{% endif %}

*Sources: {% for s in board.career.sources %}([{{ s.url | domain }}]({{ s.url }}), {{ s.date }}){% if not loop.last %}, {% endif %}{% endfor %}*

{% else %}
> ⚠️ Career landscape data unavailable — CareerAgent did not complete.
{% endif %}

---

## 2. University Background

{% if board.background %}
{% if board.background.confidence != "high" %}
> {{ board.background.confidence | confidence_flag }}
{% endif %}

| | |
|---|---|
| **Founded** | {{ board.background.founded }} |
| **Size** | {{ board.background.size_students }} students |
| **Status** | {{ board.background.public_or_private | title }} |
| **Orientation** | {{ board.background.research_orientation | replace("-", " ") | title }} |
| **Campus** | {{ board.background.campus_setting | title }} |

{% if board.background.accreditations %}
**Course Accreditations:**
{% for acc in board.background.accreditations %}
- {{ acc.body }} — *{{ acc.scope }}* ({{ acc.year_listed }})
{% endfor %}
{% else %}
*No course-specific accreditations found.*
{% endif %}

{% if board.background.industry_partnerships %}
**Department Industry Partnerships:**
{% for p in board.background.industry_partnerships %}
- **{{ p.partner }}** — {{ p.nature }} ({{ p.department }})
{% endfor %}
{% else %}
*No named department-level industry partnerships found.*
{% endif %}

{% if board.background.notes %}*Note: {{ board.background.notes }}*{% endif %}

{% else %}
> ⚠️ University background data unavailable.
{% endif %}

---

## 3. Subject Rankings

{% if board.rankings %}
{% if board.rankings.confidence != "high" %}
> {{ board.rankings.confidence | confidence_flag }}
{% endif %}

{{ board.rankings.ranking_summary }}

**Subject-Specific Rankings:**
{% for r in board.rankings.subject_rankings %}
- **{{ r.source }}** ({{ r.year }}): {{ r.rank }} for {{ r.subject_scope }} — [source]({{ r.url }})
{% endfor %}

{% if board.rankings.employability_rankings %}
**Graduate Employability Rankings:**
{% for r in board.rankings.employability_rankings %}
- **{{ r.source }}** ({{ r.year }}): {{ r.rank }} — [source]({{ r.url }})
{% endfor %}
{% endif %}

**Overall University Rankings** *(low weight — not subject-specific):*
{% for r in board.rankings.overall_rankings %}
- **{{ r.source }}** ({{ r.year }}): {{ r.rank }}
{% endfor %}

{% if board.rankings.notes %}*Note: {{ board.rankings.notes }}*{% endif %}

{% else %}
> ⚠️ Rankings data unavailable.
{% endif %}

---

## 4. Undergraduate Program

{% if board.program %}
{% if board.program.confidence != "high" %}
> {{ board.program.confidence | confidence_flag }}
{% endif %}

**Matching Programs:**
{% for prog in board.program.matching_programs %}
- **{{ prog.title }}** ({{ prog.degree_type }}, {{ prog.duration_years }} years)
  UCAS: {{ prog.ucas_code if prog.ucas_code else "not found" }} |
  Sandwich year: {{ "yes" if prog.sandwich_year else "no" }} |
  Study abroad: {{ "yes" if prog.study_abroad else "no" }}
{% endfor %}

**Core Modules (Year 1 & 2):**
{% for mod in board.program.core_modules %}
- {{ mod.name }} ({{ mod.year }})
{% endfor %}

{% if board.program.electives %}
**Elective Modules:**
{% for mod in board.program.electives %}
- {{ mod.name }}
{% endfor %}
{% endif %}

{% if board.program.skill_mappings %}
**Curriculum → Career Skills Mapping:**
{% for mapping in board.program.skill_mappings %}
- **{{ mapping.career_skill }}**: {{ mapping.modules | join(", ") if mapping.modules else "No direct module found" }}
{% endfor %}
{% endif %}

{% if board.program.curriculum_notes %}*Note: {{ board.program.curriculum_notes }}*{% endif %}

{% else %}
> ⚠️ Program data unavailable.
{% endif %}

---

## 5. Graduate Employability
{# ...same pattern — renders board.employability fields #}

## 6. Accommodation & Living
{# ...renders board.accommodation fields #}

## 7. Recent News
{# ...renders board.news.items with sentiment labels #}

## 8. Student Forum Findings
{# ...renders board.forum.recurring_positives, recurring_concerns, department_feedback #}

---

## 9. Score & Recommendation

{% if board.score %}
**Overall Score: {{ board.score.overall_score }}/10 — {{ board.score.tier }}**

| Dimension | Score |
|---|---|
{% for dim, score in board.score.dimension_scores.items() %}
| {{ dim | title }} | {{ score }}/10 |
{% endfor %}

**Why this tier:**
{% for reason in board.score.top_positives %}
- ✅ {{ reason }}
{% endfor %}

**What to investigate further:**
{% for concern in board.score.top_concerns %}
- ⚠️ {{ concern }}
{% endfor %}

{% else %}
> ⚠️ Scoring did not complete.
{% endif %}

---

## 10. Alternative Universities

{% if board.alternatives and board.alternatives.alternatives %}
{% for alt in board.alternatives.alternatives %}
### {{ alt.university_name }}

- **Subject rank:** {{ alt.subject_rank }}
- **Why listed:** {{ alt.gap_addressed }}
- **Program note:** {{ alt.program_note }}
- **Employability note:** {{ alt.employability_note }}

{% endfor %}
{% else %}
> ⚠️ Alternatives data unavailable.
{% endif %}
```

**Why `StrictUndefined` in the Jinja2 environment:** any template variable
that references a missing field raises immediately at render time rather than
silently rendering as an empty string. This surfaces schema mismatches (e.g.
a field renamed in the output schema but not updated in the template) as an
explicit error rather than a silently broken report section.

**Why sections 5–8 are abbreviated in the template above:** they follow the
identical `{% if board.<field> %}` / confidence flag / field rendering / `{% else %}` unavailable notice pattern as sections 1–4. The full template in
`report/templates/report.md.j2` must implement all 10 sections completely.
The abbreviation here is documentation economy only.

**Why `| domain` is a custom filter:** Jinja2 has no built-in URL parser.
A custom filter `domain(url)` extracts the hostname from a URL for use as
link anchor text. Register it on the `Environment` object:
```python
env.filters["domain"] = lambda url: url.split("/")[2] if "//" in url else url
env.filters["confidence_flag"] = lambda c: {
    "medium": "📊 Medium confidence — some sources limited",
    "low":    "⚠️ Low confidence — treat findings as indicative only",
}.get(c, "")
```

## 12. Startup Log Sequence (Expected)

When the system starts, logs must appear in this order:

```
skill_loader | loaded skills/accommodation/SKILL.md
skill_loader | loaded skills/alternatives/SKILL.md
skill_loader | loaded skills/background/SKILL.md
skill_loader | loaded skills/career/SKILL.md
skill_loader | loaded skills/conversation/SKILL.md
skill_loader | loaded skills/employability/SKILL.md
skill_loader | loaded skills/forum/SKILL.md
skill_loader | loaded skills/news/SKILL.md
skill_loader | loaded skills/program/SKILL.md
skill_loader | loaded skills/rankings/SKILL.md
skill_loader | loaded skills/scoring/SKILL.md
research_handler | agents constructed with skill instructions
```

Note: there's no separate "Fetch MCP server started" log line — `fastmcp.Client`
doesn't log on connect by default. The `mcp-server-fetch` subprocess starts
lazily on the first `async with fetch_client:` (the entry-point wrapper from
8.9, if used, or the first `fetch_page` call otherwise).

Files load alphabetically (`sorted(skills_dir.iterdir())`). If any file
is missing a warning appears instead — no crash:

```
skill_loader | cannot read skills/forum/SKILL.md: [Errno 2] No such file or directory
research_handler | no SKILL.md for 'forum' — agent will use base prompt
```

---

## 13. Project Folder Structure

```
university_research/
│
├── skills/                          SKILL.md files — one per agent
│   ├── accommodation/SKILL.md
│   ├── alternatives/SKILL.md
│   ├── background/SKILL.md
│   ├── career/SKILL.md
│   ├── conversation/SKILL.md
│   ├── employability/SKILL.md
│   ├── forum/SKILL.md
│   ├── news/SKILL.md
│   ├── program/SKILL.md
│   ├── rankings/SKILL.md
│   └── scoring/SKILL.md
│
├── core/
│   ├── message_hub.py              pure fan-out — subscribe() + publish(message)
│   ├── blackboard.py               typed per-request result accumulator
│   ├── deps.py                     Deps + ResearchContext dataclasses
│   ├── llm_factory.py              model initialisation from env vars
│   └── skill_loader.py             SkillMeta + load_skill() + scan_skills_dir()
│
├── mcps/
│   └── fetch_client.py             Fetch MCP — module-level fastmcp.Client (shared, reentrant)
│
├── schemas/
│   ├── messages/                   lean hub notifications
│   │   ├── base_message.py
│   │   ├── research_requested.py
│   │   ├── career_completed.py
│   │   ├── section_completed.py    carries section_name
│   │   ├── section_failed.py       carries section_name + reason
│   │   ├── scoring_completed.py
│   │   ├── alternatives_completed.py
│   │   ├── report_ready.py         carries file_paths[]
│   │   └── progress_update.py      carries status + message
│   │
│   └── outputs/                    rich LLM outputs written to blackboard
│       ├── career_output.py
│       ├── background_output.py
│       ├── rankings_output.py
│       ├── program_output.py
│       ├── employability_output.py
│       ├── accommodation_output.py
│       ├── news_output.py
│       ├── forum_output.py
│       ├── scoring_output.py
│       └── alternatives_output.py
│   ├── search_result.py            SearchResult, SearchResponse
│   ├── fetch_result.py             FetchResult
│   └── job_posting.py              JobPosting, JobPostingsResponse — shared schema for Adzuna + MCF
│
├── agents/
│   ├── base_agent.py               ABC: subscribe(), get_instruction(), reset()
│   ├── career_agent.py
│   ├── background_agent.py
│   ├── rankings_agent.py
│   ├── program_agent.py
│   ├── employability_agent.py
│   ├── accommodation_agent.py
│   ├── news_agent.py
│   ├── forum_agent.py
│   ├── scoring_agent.py            quorum gate + asyncio.Lock
│   ├── alternatives_agent.py
│   └── conversation_agent.py       reads blackboard, no tools
│
├── tools/
│   ├── search_tool.py              tavily_search — module-level AsyncTavilyClient singleton, await search()
│   ├── fetch_tool.py               fetch_page — calls shared fastmcp.Client fetch_client, never raises
│   ├── ddg_tool.py                 ddg_search — module-level DDGS singleton, date-filtered (NewsAgent only)
│   ├── adzuna_tool.py              adzuna_jobs — httpx REST, UK + AU, routes by deps.context.country
│   └── mcf_tool.py                 mcf_jobs — httpx REST, Singapore only, no auth required
│
├── report/
│   ├── generator.py                deterministic Jinja2 renderer, no LLM
│   └── templates/
│       └── report.md.j2            single template — executive summary + all sections
│
├── services/
│   └── research_handler.py         loads skills, constructs agents, handles requests
│
├── ui/
│   └── app.py                      Chainlit entry point — Mode 1 + Mode 2
│
├── tests/
│   └── test_skill_loader.py
│
├── main.py                         CLI entry — full pipeline without UI
├── .env                            API keys — never commit
└── requirements.txt
```

---

## 14. Known Implementation Pitfalls

These are issues that caused real debugging time in prior projects. Know
them before building.

**Quorum gate race condition (most common bug)**
`asyncio.gather()` fires all 7 section handlers concurrently. Plain
`received_count += 1` is not safe. Wrap the increment-and-check in
`asyncio.Lock`. Without the lock, scoring fires multiple times.

**Hub and Deps must be created fresh per request**
If the hub is shared across requests, handlers from previous requests
accumulate. Each call to `handle_request()` must create a new
`MessageHub()`, `Blackboard()`, and `Deps` instance. Tool client singletons
are intentionally reused — they carry no per-request state.

**Fetch MCP server must be started before the first request**
`fetch_client.startup()` must be called at application boot — in the Chainlit
`on_chat_start` hook, the FastAPI `lifespan`, or the CLI `main()`. If a request
arrives before startup, `fetch_tool.py` raises `RuntimeError` immediately.
`ResearchHandler` has no lifecycle responsibilities — it just handles requests.

**Tool client singletons initialise at import time (Tavily, DDGS)**
These clients read from `os.environ` when their modules are imported.
If `.env` is not loaded before the modules are imported, they will raise
`KeyError`. Always call `load_dotenv()` before any tool module is imported.

**Skills load before agents are constructed**
`scan_skills_dir()` must complete before any agent constructor is called.
If agents are constructed before skills are loaded, they receive empty
instructions. The startup log sequence (Section 12) confirms correct ordering.

**`expected_sections` is set from loaded skill count, not hardcoded**
Count only the keys in `RESEARCH_AGENT_KEYS` that successfully loaded from
disk. If a SKILL.md is missing, that agent doesn't register, and the
quorum gate adjusts. Hardcoding 7 causes a silent deadlock.

**`module_path` must be exact (if used)**
`importlib.import_module` raises `ModuleNotFoundError` at startup if the
path is wrong. This surfaces immediately — which is correct. Fix it before
the system is considered running.

**SKILL.md edits require restart**
Skill files load once at startup. In development, changing only a markdown
file may not trigger a hot-reload watcher. Restart explicitly after any
SKILL.md edit.

**`section_name` on messages must match blackboard field names exactly**
`ScoringAgent` uses `setattr(deps.board, message.section_name, None)` for
failed sections. If `section_name` in a SKILL.md frontmatter says `"forums"`
but the blackboard field is `forum`, the setattr silently does nothing.

**`tool_budget: 0` in SKILL.md must not be treated as missing**
The `load_skill()` check uses `f not in meta or meta[f] is None` — not
`not meta.get(f)`. The old form treats `0` as falsy and drops scoring,
alternatives, and conversation skills entirely.

**Tool budget counter must live on the agent instance, not on `Deps`**
`asyncio.gather()` runs section agents concurrently. If `calls_made` is on
shared `Deps`, two agents increment the same counter. Each agent must own
`self._calls_made` and reset it to `0` at the start of its `handle()` call.
The budget closure captures `self` — incrementing `self._calls_made` inside
`_make_search_tool()` is safe across the closure boundary.

**`ddg_tool` must filter by date before returning**
Tavily enforces `days=730` mechanically. DuckDuckGo does not.
The wrapper must filter results by publication date before returning to the LLM
— not rely solely on the SKILL.md instruction to discard old results.

**DuckDuckGo** date filtering is unreliable — do not wire to any agent
DDG has no API-level date range parameter equivalent to Tavily's days=730. Post-call filtering on the date field is insufficient — results with missing or unparseable dates pass through silently, and the LLM cannot reliably distinguish a 2009 post from a 2024 one when no date is present. `ddg_tool.py` is retained for future use if a reliable date-filtering solution becomes available, but must not be registered on any agent until that guarantee exists. NewsAgent handles sparse Tavily results via confidence: "low" — not by falling back to DDG.

---

## 15. Development Stage Summary

These stages are implemented in order. Each ends with something running and
verifiable. No stage is purely structural.

| Stage | What you build | Files created or changed | Ends with |
|---|---|---|---|
| 0 | Repo scaffold, env setup, dependencies, `.env` template | `requirements.txt`, `.env`, `pytest.ini`, folder skeleton | `pip install -r requirements.txt` succeeds; `python -c "import pydantic_ai"` passes |
| 1a | `MessageHub`, `Blackboard`, `Deps`, all message schemas, all output schemas, `SkillLoader`, all 11 `SKILL.md` files | `core/`, `schemas/`, `skills/` | `pytest tests/test_stage_1a.py` — 17 tests pass; skill scan returns 11 keys |
| 1b | Fetch MCP client, all 5 tool functions (`tavily_search`, `fetch_page`, `ddg_tool`, `adzuna_jobs`, `mcf_jobs`), shared `JobPosting` schema | `mcps/fetch_client.py`, `tools/`, `schemas/job_posting.py` | Real job postings confirmed for UK, AU, SG; all 5 tools pass live tests; 26 tests pass |
| 1c | `CareerAgent` end-to-end — `BaseAgent` ABC, pydantic-ai `Agent` with telemetry hooks, budget-aware tools, `subscribe()`, `get_instruction()`, `handle()`. Minimal `ResearchHandler` + `main.py` | `agents/base_agent.py`, `agents/career_agent.py`, `services/research_handler.py`, `main.py` | `board.career` populated from real data via `python main.py`; 11 tests pass |
| 1d | `BackgroundAgent` + `RankingsAgent` + `ProgramAgent` — same Tavily + Fetch tool set, subscribe to `CareerResearchCompletedMessage`, fire `SectionCompletedMessage` | `agents/background_agent.py`, `agents/rankings_agent.py`, `agents/program_agent.py`, updated `research_handler.py`, updated `main.py` | All three board fields populated concurrently via CLI; 13 structural tests pass |
| 1e | `EmployabilityAgent` + `AccommodationAgent` + `NewsAgent` — Tavily + Fetch, `NewsAgent` sets `confidence: "low"` when Tavily returns sparse results (DDG not wired) | `agents/employability_agent.py`, `agents/accommodation_agent.py`, `agents/news_agent.py` | `board.employability`, `board.accommodation`, `board.news` populated in a single pipeline run |
| 1f | `ForumAgent` — Tavily + Fetch, highest budget (10), strict scope rules, `include_domains` for TSR/StudentCrowd/WhatUni/Quora | `agents/forum_agent.py`, `skills/forum/SKILL.md` | `board.forum` populated via CLI with findings from ≥2 confirmed forum sources |
| 2a | `ScoringAgent` — quorum gate, `asyncio.Lock`, no tools, reads full blackboard, fires `ScoringCompletedMessage` | `agents/scoring_agent.py`, `schemas/outputs/scoring_output.py`, `skills/scoring/SKILL.md` | `board.score` populated after all 7 section agents complete; lock race verified; partial blackboard handled |
| 2b | `AlternativesAgent` (Tavily + Fetch) + `ReportGenerator` (Jinja2, no LLM) — renders `report.md` + `score.json`, fires `ReportReadyMessage` | `agents/alternatives_agent.py`, `report/generator.py`, `report/templates/report.md.j2`, `schemas/outputs/alternatives_output.py` | `score.json` and `report.md` written to `outputs/` from CLI for a real university; all 10 sections render; unavailable sections show notice |
| 2c | `ConversationAgent` (no tools, reads blackboard) + `ui/app.py` (Chainlit Mode 1 + Mode 2) | `agents/conversation_agent.py`, `ui/app.py`, `skills/conversation/SKILL.md` | Full pipeline runs from Chainlit UI; live progress renders; report appears inline; files downloadable; follow-up questions answered from blackboard |
| 3a | Report quality pass — template refinement, confidence flag rendering, `score.json` comparison script | `report/templates/report.md.j2`, `scripts/compare_scores.py` | Side-by-side `score.json` comparison between two universities works; report renders cleanly for ≥3 real universities |
| 3b | Edge case hardening — all `None` blackboard fields, all agents fail, malformed input, oversized results | `tests/test_edge_cases.py` | All failure scenarios exit cleanly with a degraded report rather than a crash |

### Stage Dependency Map

```
0 → 1a → 1b → 1c → 1d ─┐
                    1e ──┼→ 1f → 2a → 2b → 2c → 3a → 3b
                         ┘
```

Each stage has a hard dependency on all stages above it. Never skip a stage
to implement a later one — the pattern established in each stage is the
foundation the next builds on. In particular:

- **1c before 1d–1f**: the BaseAgent hooks pattern, `get_instruction()` discipline,
  and `handle()` reset contract are all established in 1c. Stages 1d–1f are
  direct copies of that pattern.
- **1f before 2a**: the quorum gate count (`expected_sections`) is set from the
  number of successfully registered research agents. All 7 must be registered
  before `ScoringAgent` is wired.
- **2a before 2b**: `AlternativesAgent` reads `board.score.weaknesses`. If
  `ScoringAgent` hasn't run, there is nothing to read.
- **2b before 2c**: the Chainlit UI subscribes to `ReportReadyMessage` to
  render the report. `ReportGenerator` fires that message. Without 2b, the
  UI has nothing to display.

---

*End of MASTER Reference*