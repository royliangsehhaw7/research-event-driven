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

| Tool | Role | API Key Required |
|---|---|---|
| **Tavily** | Primary search — all agents. Key feature: `days=730` date filter | `TAVILY_API_KEY` |
| **Fetch MCP** | Direct URL fetch for university catalog pages, rankings pages | None — open |
| **Reddit API (PRAW)** | ForumAgent — subreddit search, post bodies, comment scores. Richer than `site:reddit.com` via Tavily | `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| **DuckDuckGo Search** | NewsAgent fallback when Tavily misses news. No key, no quota | None — no key needed |

**Why these tools:**
Tavily handles all general search including `site:thestudentroom.co.uk`, `site:quora.com`,
and `site:reddit.com` queries. Reddit API is added for ForumAgent specifically because it
returns full post bodies, comment threads, upvote scores, and subreddit context — signal
quality that Tavily `site:` queries cannot match. DuckDuckGo replaces SerpAPI as a
zero-cost news fallback with no monthly quota.

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

**Reddit API** — https://www.reddit.com/prefs/apps  
Create a "script" app. Free. Returns `client_id` and `client_secret`.
Used by ForumAgent only — stays well within free tier limits.

**DuckDuckGo Search** — no signup, no key, no quota.
Install: `pip install duckduckgo-search`. Used by NewsAgent as fallback only.

**OpenRouter** — https://openrouter.ai  
Create API key from dashboard. Set `OPENROUTER_API_KEY`.
Choose models via `RESEARCH_MODEL`, `SCORING_MODEL`, `CONVERSATION_MODEL` env vars.

### Environment File

```bash
# .env
TAVILY_API_KEY=tvly-...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
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
praw                  # Reddit API client (ForumAgent)
duckduckgo-search     # News fallback — no key needed (NewsAgent)
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
deps.board.forum = forum_result   # ForumOutput — all findings

# 2. Publish lean notification to hub
await deps.hub.publish(SectionCompletedMessage(
    section_name="forum",
    triggered_by="forum_agent",
    timestamp=datetime.now().isoformat(),
))
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
from typing import Callable, Awaitable
from pydantic import BaseModel


class MessageHub:
    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, message_type: type, handler: Callable[..., Awaitable[None]]) -> None:
        self._subscribers[message_type].append(handler)

    async def publish(self, message: BaseModel) -> None:
        handlers = self._subscribers.get(type(message), [])
        if handlers:
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
from dataclasses import dataclass, field
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
    # search clients added here as the project grows
    # tavily_client: TavilyClient | None = None
```

`Deps` is created fresh per request in `ResearchHandler.handle_request()`.
It bundles the three per-request objects that agents need. Agents receive
`deps` via their `handle()` method — they never construct it themselves.

---

### `agents/base_agent.py`

```python
from __future__ import annotations
import logging
from pydantic_ai import Agent


class BaseAgent:
    def __init__(self, instructions: str = "") -> None:
        self.instructions = instructions
        self._agent: Agent | None = None   # set by subclass __init__
        self._logger = logging.getLogger(self.__class__.__name__)

    def _base_prompt(self) -> str:
        """Override in subclass. Structural context only — no domain knowledge."""
        return ""

    def _build_system_prompt(self) -> str:
        """Combines structural base prompt with SKILL.md instructions.

        Base prompt: what blackboard field the agent writes, what message it fires,
                     what output schema it produces.
        Instructions: everything from the SKILL.md body — search strategy,
                      query construction, quality filters, edge cases.

        If instructions is empty (missing SKILL.md), the base prompt runs alone.
        The agent is degraded but functional — it knows its structural role.
        """
        base = self._base_prompt()
        if self.instructions:
            return base + "\n\n" + self.instructions
        return base
```

**The discipline that matters most:** `_base_prompt()` carries only structural
context. It never contains domain knowledge. Domain knowledge belongs in
SKILL.md. If you find yourself writing "search for salary ranges" in
`_base_prompt()`, stop — that belongs in `skills/career/SKILL.md`.

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
    platform: str   # "reddit", "thestudentroom", etc.
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
    missing = [f for f in required if not meta.get(f)]
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

### What Goes in `_base_prompt()` vs SKILL.md

This is the most important discipline in the entire system:

| Belongs in `_base_prompt()` — Python | Belongs in SKILL.md body |
|---|---|
| "You are the Forum Research Agent in a university research pipeline." | What to search for |
| "You write your findings to deps.board.forum as a ForumOutput." | How to construct queries |
| "You fire SectionCompletedMessage(section_name='forum') on success." | Which sources to use and in what order |
| "Your tool budget is enforced by the pipeline." | What to discard and why |
| | Signal quality thresholds |
| | Output structure requirements |
| | Edge case handling |

The base prompt describes the agent's structural role in the pipeline — it
never changes. SKILL.md describes what the agent should actually do — it
changes as the system is tuned.

---

## 8. All Eleven SKILL.md Files

### `skills/career/SKILL.md`

```markdown
---
key: career
name: Career Research Agent
description: Researches career paths, salary ranges, and live job postings for the given course in the university's country.
tool_budget: 8
section_name: career
---

## Role

You are the first agent to run. Every other agent depends on the career
context you establish. Research thoroughly before returning.

## What to research

- Realistic career paths a graduate of this course typically enters
- Salary ranges for those careers in the university's country (not global)
- A snapshot of live job postings matching those careers (10–15 minimum)
- In-demand skills extracted from the postings

## Query construction

Always include: [course] + [career/jobs/salary] + [country]
Never query on [university name] alone — career paths are course-level.

Examples:
- "Computer Science graduate careers UK salary 2024"
- "Computer Science jobs London entry level 2024"
- "Psychology graduate employment Australia salary range"

## Date filter

All results must be within 2 years. Discard anything older.

## What to return

- At least 3 distinct career paths with titles and typical progression
- Salary ranges: entry level, mid, senior — country-scoped, in local currency
- Job posting snapshot: company, role title, required skills, date posted
- Top 5–8 in-demand skills extracted across postings
- Sources: URL + date for every data point

## Quality bar

Salary data without country scoping is not acceptable. Return with
confidence: low and flag it rather than present global averages as local.
```

---

### `skills/background/SKILL.md`

```markdown
---
key: background
name: Background Agent
description: Researches the university's institutional profile — history, size, orientation, and course-specific strengths.
tool_budget: 5
section_name: background
---

## What to research

- University founding date, size (student population), public or private status
- Research-intensive vs teaching-focused orientation
- Known strengths in the specific course or department being researched
- Relevant accreditations for the course (e.g. AACSB for business, BCS for CS)
- Any notable alumni or industry partnerships tied to the specific course

## Query construction

Always include: [university name] + [course/department]
Never: [university name] alone

Examples:
- "University of Manchester Computer Science department profile"
- "University of Manchester research teaching focus"
- "University of Manchester Computer Science accreditation"

## Date filter

Institutional facts (founding date, size) may use older sources.
Accreditation status, department orientation: 2-year filter applies.

## What to return

- Factual profile: founded, size, public/private, research vs teaching label
- Course-specific strengths: what is this department known for?
- Accreditations: name, body, scope, date last confirmed
- Industry connections specific to the course (not generic partnerships)
- Sources: URL + date

## Quality bar

Do not summarise the university's general reputation. Stay scoped to what
matters for the specific course. A strong law school is irrelevant when
researching Computer Science.
```

---

### `skills/rankings/SKILL.md`

```markdown
---
key: rankings
name: Rankings Agent
description: Researches subject-specific and employability rankings for the given university and course.
tool_budget: 6
section_name: rankings
---

## Priority order

1. Subject-specific ranking for this course (QS by Subject, THE by Subject,
   Guardian Subject Rankings, Complete University Guide)
2. Graduate employability ranking (QS Graduate Employability)
3. Overall university ranking (QS World, THE World) — lowest weight, last resort

Overall ranking is a proxy and is explicitly down-weighted in scoring.
Subject ranking is what matters.

## Query construction

Always include: [university name] + [course/subject] + [ranking year]

Examples:
- "QS World University Rankings Computer Science University of Manchester 2024"
- "Times Higher Education Psychology rankings 2024"
- "Guardian University Guide Computer Science 2024"

## Date filter

Rankings change annually. Use the most recent published edition only.
Do not mix years.

## Confidence handling

If no subject-specific ranking is found for this course:
- Set confidence: low
- Return overall ranking only with a clear note
- Do not substitute a general department rank for a subject rank

ScoringAgent will down-weight this dimension if confidence is low.
```

---

### `skills/program/SKILL.md`

```markdown
---
key: program
name: Program Agent
description: Researches the specific undergraduate programs, modules, and delivery format for the given course.
tool_budget: 5
section_name: program
---

## What to research

- Available undergraduate programs matching the course name
- Specialisations or pathways within the program
- Core modules in years 1 and 2
- Optional modules and electives
- Duration in years, delivery format
- Any program features directly relevant to career outcomes from board.career

## Query construction

Always include: [university name] + [course] + undergraduate

Examples:
- "University of Manchester Computer Science undergraduate program modules"
- "University of Edinburgh Psychology undergraduate pathways"

## Date filter

Use current academic year only. Prefer official university catalog pages.

## What to return

- List of matching undergraduate programs with full titles
- Core modules yr1, core modules yr2, electives
- Duration, delivery options (sandwich year? study abroad?)
- Curriculum elements that map to in-demand skills from board.career
- Official source URL for the course catalog page

## Quality bar

Return factual module names and structure. Marketing language is not
acceptable output. If the catalog is behind a login, return what is
publicly available and note the limitation.
```

---

### `skills/employability/SKILL.md`

```markdown
---
key: employability
name: Employability Agent
description: Researches graduate employment outcomes, industry partnerships, and alumni trajectories for the given course.
tool_budget: 8
section_name: employability
---

## Dependency

Read board.career before beginning any searches. The career paths and
in-demand skills already found there define what counts as a relevant
graduate outcome. Find evidence that this university's graduates actually
reach those careers.

## What to research

- Graduate employment rate (% employed within 6 months, if available)
- Industries and companies graduates enter — country-scoped
- Direct evidence of graduates in career paths from board.career
- Industry partnerships specific to the department
- Graduate salary data specific to this university

## Query construction

Always include: [university name] + [course] + graduates/employment/alumni
Always scope to the university's country.

Examples:
- "University of Manchester Computer Science graduates employment rate"
- "University of Manchester CS alumni careers LinkedIn"
- "site:linkedin.com University of Manchester Computer Science graduate"

## Date filter

Employment statistics older than 2 years are not acceptable.

## Quality bar

Generic statements like "graduates go on to successful careers" are not
acceptable. Return evidence — named companies, percentage figures with sources.
```

---

### `skills/accommodation/SKILL.md`

```markdown
---
key: accommodation
name: Accommodation Agent
description: Researches on-campus and off-campus accommodation costs, area safety, and transport access.
tool_budget: 6
section_name: accommodation
---

## What to research

- On-campus accommodation: cost range per week, what is included
- Off-campus private accommodation: typical rent range per month in the
  university's city (not national averages)
- Area safety: crime statistics or student safety reputation for the campus area
- Public transport: routes and journey time from student areas to campus

## Query construction

Always include: [university name] + [accommodation/rent/safety]
For off-campus, include the city name.

Examples:
- "University of Manchester student accommodation cost 2024"
- "Manchester city centre student rent per month 2024"
- "University of Manchester campus area safety crime rate"

## What to return

- On-campus cost range: weekly cost, what is included
- Off-campus cost range: monthly rent, area of city, bills typically separate
- Area safety: factual — cite statistics, not forum opinions
- Transport: named routes, frequency, journey time
- Sources: URL + date

## Quality bar

Return student-specific figures. Do not conflate city cost-of-living
with student accommodation costs.
```

---

### `skills/news/SKILL.md`

```markdown
---
key: news
name: News Agent
description: Researches institutional and department-level news from the past 2 years, with sentiment classification per item.
tool_budget: 6
section_name: news
---

## Search tool order

1. Tavily — primary. Use `days=730` filter.
2. DuckDuckGo (`ddg_tool`) — fallback if Tavily returns fewer than 3 news items.
   Use only for news queries, not general search.

## What to research
  controversies, award wins, ranking changes, closures
- Department-specific news: events, research breakthroughs, grant wins,
  staff departures, course changes — higher weight than institutional news

## Sentiment classification

Classify each item as:
- positive: award, grant, investment, ranking improvement, new facility
- negative: strike, controversy, scandal, funding cut, course closure
- neutral: leadership change, restructure, policy update

Neutral is not a default — it requires an actual neutral item.

## Date filter

This is the strictest filter in the pipeline. Discard any item older
than 2 years from today without exception. Items without a clear
publication date are discarded.

## What to return

- List of news items: headline (paraphrased), sentiment, source URL, date
- Department-specific items flagged separately
- If no department-specific news found, state this explicitly
```

---

### `skills/forum/SKILL.md`

```markdown
---
key: forum
name: Forum Agent
description: Researches student forum discussions about the specific course at the specific university, filtering strictly for course-level signal.
tool_budget: 10
section_name: forum
---

## This agent has the highest tool budget and the strictest scope rules.

## Scope rules — enforced on every query and every result

Every query must include both the university name AND the course name.
Every result that does not mention the specific course or department is discarded.
Generic university experience threads are not acceptable output.

## Sources — search in this order

1. **Reddit API** — search r/UniUK, r/AskUK, r/ApplyingToCollege, university-specific subreddits
   directly via PRAW. Returns full post bodies and comment threads — higher signal than site: queries.
2. `site:thestudentroom.co.uk` via Tavily — course-specific threads
3. `site:thegradcafe.com` via Tavily — applicant and student discussion
4. `site:quora.com` via Tavily — student experience questions

## Query construction

Always: [university name] + [course name] + [signal type]

Examples:
- "site:reddit.com University of Manchester Computer Science student experience"
- "site:thestudentroom.co.uk University of Manchester Computer Science review"
- "site:quora.com University of Manchester Computer Science worth it"

## Signal weighting

1. Current student (enrolled now) — highest weight
2. Recent graduate (graduated within 2 years) — high weight
3. Former student (2–4 years ago) — medium weight
4. Prospective student asking questions — lowest weight, anecdote only

## Qualification threshold

A recurring positive or concern must appear across 3 or more independent
sources to qualify as a finding. One post does not make a pattern.

## Date filter

Discard posts older than 2 years from today without exception.

## What to return

- Recurring positives: 3+ sources required, paraphrased, source + year each
- Recurring concerns: 3+ sources required, paraphrased, source + year each
- Department-specific feedback: teaching quality, lecturers, course content
- If no course-specific threads found: return empty with explanation.
  Do not substitute generic university threads.

## What not to return

- Verbatim quotes from forum posts — paraphrase only
- Single-source opinions presented as patterns
```

---

### `skills/scoring/SKILL.md`

```markdown
---
key: scoring
name: Scoring Agent
description: Produces a weighted score across 7 dimensions and a tiered recommendation after all section agents complete.
tool_budget: 0
---

## Role

You receive the full blackboard — all 7 research sections — and produce
a score. You do not search. You do not call tools. You synthesise.

## Scoring dimensions and weights

| Dimension | Blackboard field | Weight |
|---|---|---|
| Employability and outcomes | board.employability + board.career | 25% |
| Program fit | board.program | 20% |
| Forum and student sentiment | board.forum | 20% |
| Subject ranking | board.rankings | 15% |
| Accommodation and living | board.accommodation | 10% |
| News sentiment | board.news | 5% |
| Overall prestige | board.background + board.rankings | 5% |

## Scoring rules

Score each dimension 0–10. Provide 1–2 sentences of rationale per dimension
citing specific evidence from the blackboard. Not generic statements.

Down-weight any dimension where the board field has confidence: low.
A None field means the dimension cannot be scored — redistribute its
weight proportionally to remaining dimensions. Flag every missing section.

## Tiered recommendation

| Score | Tier |
|---|---|
| 7.5–10 | Strong Consider |
| 5.5–7.4 | Consider |
| 3.5–5.4 | Proceed with Caution |
| 0–3.4 | Avoid |

Accompany the tier with the top 3 reasons supporting it and the top 3
concerns to investigate further — drawn from evidence, not invented.

## Weaknesses output

Return a `weaknesses` list of 2–3 dimensions where score is lowest
relative to expectation. AlternativesAgent reads this list verbatim
to target its search. Be specific: "Subject ranking not found —
confidence low" not "ranking data weak".
```

---

### `skills/alternatives/SKILL.md`

```markdown
---
key: alternatives
name: Alternatives Agent
description: Researches 2–3 alternative universities that address the specific weaknesses identified by the scoring agent.
tool_budget: 8
---

## Dependency

Read board.score.weaknesses before beginning any searches. Alternatives
must directly address the gaps identified there — not general reputation.

## Selection criteria

- Same course, undergraduate only
- Same country as primary, or a country the parent would consider equivalent
- Must demonstrably perform better on the weakness dimensions — cite evidence

## For each alternative, research

- Subject-specific ranking (most commonly in weaknesses)
- Brief program note: does it address the curriculum gap?
- One-line employability note: evidence of outcomes in careers from board.career
- Why this alternative addresses the specific weakness — explicit and evidenced

## What to return

2–3 alternatives. For each:
- University name and country
- Why it addresses the primary's weakness (evidence required)
- Subject ranking: position, body, year
- Program note: one sentence on curriculum fit
- Employability note: one sentence on graduate outcomes
- Source URL for each claim

## Quality bar

An alternative with no evidence it addresses the weakness is not acceptable.
If no suitable alternatives found, return an empty list with explanation.
```

---

### `skills/conversation/SKILL.md`

```markdown
---
key: conversation
name: Conversation Agent
description: Answers follow-up questions from the parent after the report is generated, using only the research data already on the blackboard.
tool_budget: 0
---

## Role

The research pipeline has completed. The parent is asking follow-up
questions. You answer from what was found — not from general knowledge,
not from new searches.

## What you can answer

Any question answerable from the blackboard:
- Elaboration on any section (forum concerns, accommodation details, salary ranges)
- Comparisons between primary university and alternatives in board.alternatives
- Explanation of scoring rationale from board.score
- Questions about what was and was not found during research

## What you must not do

- Search for new information
- Answer questions about topics not in the research (visa, postgraduate, other universities)
- Present general knowledge as if it came from the research

## When you cannot answer

Say so clearly: "The research didn't cover this — check directly with the university."
Do not guess. Do not substitute general knowledge.

## Tone

You are speaking to a parent making a real decision about their child's
future. Be direct, factual, and honest about what the research found
and what it didn't. Do not oversell the report.

## Scope boundaries

- Study level: undergraduate only — hardcoded, never change this
- The report is a point-in-time snapshot — say so if asked about current availability
- The report summarises research, it does not verify facts — tell the parent
  to confirm critical decisions directly with the university
```

---

## 9. Deps Threading — Handler Closure Pattern

This is the pattern that handles how `Deps` reaches each agent's handler.
In pydantic-ai, `agent.run()` takes `deps` as a parameter. But the handler
registered on the hub receives only the message. The solution: close over
`deps` at subscription time.

```python
# In ResearchHandler.handle_request() — called once per research request

async def handle_request(self, university_name: str, intended_course: str) -> Blackboard:
    # 1. Derive country
    country = await self._derive_country(university_name)

    # 2. Create fresh per-request objects
    hub = MessageHub()
    board = Blackboard()
    context = ResearchContext(
        university_name=university_name,
        intended_course=intended_course,
        country=country,
    )
    deps = Deps(hub=hub, board=board, context=context)

    # 3. Subscribe all agents — close over deps in each handler
    async def career_handle(msg):
        await self._career_agent.handle(msg, deps)

    async def background_handle(msg):
        await self._background_agent.handle(msg, deps)

    # ... same pattern for all agents

    hub.subscribe(ResearchRequestedMessage, career_handle)
    hub.subscribe(CareerResearchCompletedMessage, background_handle)
    hub.subscribe(CareerResearchCompletedMessage, rankings_handle)
    # ... etc.

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

The closure pattern is the reason `MessageHub` and `Deps` are both created
fresh per request. If the hub were shared across requests, subscriptions
from previous requests would accumulate and fire again.

---

## 10. Chainlit — Two Modes

### Mode 1 — Research Trigger

User submits university + course. The pipeline fires. `ProgressUpdateMessage`
events render live agent status in the Chainlit step display. On
`ReportReadyMessage`, the report renders inline and both files (`report.md`,
`score.json`) are offered for download.

### Mode 2 — Conversational Follow-Up

After the report is generated, the blackboard persists in the Chainlit
session. `ConversationAgent` handles natural language follow-up answered
from research data — no new searches.

```python
# Session state — Chainlit session-scoped
@dataclass
class ResearchSession:
    blackboard:           Blackboard
    report_files:         list[str]
    conversation_history: list        # pydantic-ai ModelMessage list
    context:              ResearchContext
```

`ConversationAgent.run()` receives: user question + serialised blackboard
as context + `message_history`. It returns an answer and the updated history.
History grows across turns and is stored in the session.

**Session isolation:** each new research request creates a fresh blackboard and
clears the conversation history. Data from a previous run never bleeds into
a new one.

---

## 11. Startup Log Sequence (Expected)

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

Files load alphabetically (`sorted(skills_dir.iterdir())`). If any file
is missing a warning appears instead — no crash:

```
skill_loader | cannot read skills/forum/SKILL.md: [Errno 2] No such file or directory
research_handler | no SKILL.md for 'forum' — agent will use base prompt
```

---

## 12. Project Folder Structure

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
│   ├── message_hub.py              pure fan-out — subscribe() + publish()
│   ├── blackboard.py               typed per-request result accumulator
│   ├── deps.py                     Deps + ResearchContext dataclasses
│   ├── llm_factory.py              model initialisation from env vars
│   └── skill_loader.py             SkillMeta + load_skill() + scan_skills_dir()
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
│
├── agents/
│   ├── base_agent.py               instructions field + _build_system_prompt()
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
│   └── conversation_agent.py       reads serialised blackboard, no tools
│
├── tools/
│   ├── search_tool.py              Tavily wrapper — days=730 enforced
│   ├── fetch_tool.py               Fetch MCP wrapper
│   ├── reddit_tool.py              PRAW wrapper — ForumAgent subreddit search
│   └── ddg_tool.py                 DuckDuckGo wrapper — NewsAgent fallback
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

## 13. Known Implementation Pitfalls

These are issues that caused real debugging time in prior projects. Know
them before building.

**Quorum gate race condition (most common bug)**
`asyncio.gather()` fires all 7 section handlers concurrently. Plain
`received_count += 1` is not safe. Wrap the increment-and-check in
`asyncio.Lock`. Without the lock, scoring fires multiple times.

**Hub and Deps must be created fresh per request**
If the hub is shared across requests, handlers from previous requests
accumulate. Each call to `handle_request()` must create a new
`MessageHub()`, `Blackboard()`, and `Deps` instance.

**Skills load before agents are constructed**
`scan_skills_dir()` must complete before any agent constructor is called.
If agents are constructed before skills are loaded, they receive empty
instructions. The startup log sequence (Section 11) confirms correct ordering.

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

---

## 14. Development Stage Summary

These stages are implemented in order. Each ends with something running and
verifiable. No stage is purely structural.

| Stage | What you build | Ends with |
|---|---|---|
| 0 | Repo scaffold, env setup, dependencies | Clean install, `.env` validated |
| 1a | MessageHub, Blackboard, Deps, all schemas, SkillLoader + all 11 SKILL.md files | Hub test passing, skill scan returning 11 keys |
| 1b | Tavily + Fetch MCP + Reddit API (PRAW) + DuckDuckGo tool wrappers | Real searches against university targets confirmed |
| 1c | CareerAgent end-to-end | `board.career` populated from real data via CLI |
| 2a | All 7 section agents + ScoringAgent + AlternativesAgent + ReportGenerator | 2 output files generated from CLI for real university |
| 2b | Chainlit UI — Mode 1 research trigger | Full pipeline firing from UI with live progress |
| 2c | ConversationAgent + Chainlit Mode 2 | Follow-up questions answered from blackboard |
| 3a | Report quality pass — template, confidence flags, comparison script | Side-by-side score.json comparison working |
| 3b | Edge case hardening | All failure scenarios handled without crash |

---

*End of MASTER Reference*