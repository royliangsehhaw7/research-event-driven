# Stage 1a — MessageHub, Blackboard, Deps, All Schemas, SkillLoader & All 11 SKILL.md Files
## Implementation Specification

**Goal:** Every piece of core infrastructure and all data contracts exist and
are tested. No agents, no LLM calls, no searches. Pure Python.

**Ends with:** `pytest tests/test_stage_1a.py -v` passes. The hub dispatches
messages correctly. The skill loader scans `skills/` and returns exactly 11
keys. All output schemas instantiate without error.

---

## What This Stage Builds and Why It Comes First

Every other part of the system depends on the things built here:

- Agents need message types to subscribe to and fire
- Agents need the blackboard to write results into
- Agents need `Deps` to receive hub + board + context
- The skill loader must exist before agents are constructed
- Output schemas must exist before agents can declare their return types

Building these first means when agent code is written in Stage 1c and 2a,
the import paths are already correct, the schemas are already defined, and
the hub is already tested. No guessing.

---

## 1a.1 `core/message_hub.py`

The hub is a pure fan-out dispatcher. It has no domain knowledge. It maps
message types to lists of async handler functions and calls them all concurrently.
Handlers are registered as closures that capture `deps` at subscription time —
the hub never receives or knows about `deps`.

```python
# core/message_hub.py
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable

from pydantic import BaseModel


class MessageHub:
    """Pure fan-out message dispatcher.

    One instance per research request — created fresh in
    ResearchHandler.handle_request(). Never reused across requests.
    Reusing accumulates handlers from prior requests.

    Usage:
        hub = MessageHub()
        hub.subscribe(SomeMessage, handler)   # handler is a closure capturing deps
        await hub.publish(SomeMessage(triggered_by="x", timestamp="..."))
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, message_type: type, handler: Callable) -> None:
        """Register an async handler for a message type.

        The handler must be a closure that already captures deps.
        Multiple handlers per type are allowed — all fire concurrently
        on publish. Same handler registered twice will fire twice.
        """
        self._subscribers[message_type].append(handler)

    async def publish(self, message: BaseModel) -> None:
        """Dispatch message to all registered handlers concurrently.

        Uses asyncio.gather() — all handlers start simultaneously.
        If no handlers are registered for the message type, does nothing.
        Handler exceptions are not caught here — they propagate to the caller.
        """
        handlers = self._subscribers.get(type(message), [])
        if not handlers:
            return
        await asyncio.gather(*[h(message) for h in handlers])

    def subscriber_count(self, message_type: type) -> int:
        """Return number of registered handlers for a message type.
        Used in tests to verify subscription state."""
        return len(self._subscribers.get(message_type, []))
```

**Why closures instead of passing `deps` through `publish()`:** the hub's
`publish(message)` signature stays clean — it has no knowledge of `deps`.
Each agent's `subscribe()` method captures `deps` in a closure at subscription
time. The hub calls `handler(message)`; the handler calls
`self.handle(message, deps)` with the captured deps. This is the pattern
established in the master reference and used throughout all agents.

**Why `defaultdict(list)`:** accessing an unregistered message type returns
an empty list rather than raising `KeyError`. This means publishing to a
message type with no subscribers is a no-op, not an error. That is the
correct behaviour — some messages (like `ProgressUpdateMessage`) may have
no subscribers during testing.

**Why handler exceptions propagate:** the hub has no business catching them.
Individual agents handle their own failures and publish `SectionFailedMessage`
as a result. The hub is infrastructure, not error handling.

**Why `subscriber_count()`:** not needed at runtime, but invaluable in tests
to assert that the subscription wiring is correct without needing to fire
actual messages.

---

## 1a.2 `core/blackboard.py`

The blackboard is a typed per-request accumulator. It is a plain dataclass —
no methods except `is_complete()`. Agents write to it directly via `deps.board.<field>`.

```python
# core/blackboard.py
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
    """Per-request result accumulator. One fresh instance per research run.

    Fields are None until the corresponding agent completes.
    None means either: agent hasn't run yet, or agent failed.
    ScoringAgent treats both cases identically — redistribute weight.

    Never share a Blackboard instance across requests.
    """

    career:        CareerOutput        | None = None
    background:    BackgroundOutput    | None = None
    rankings:      RankingsOutput      | None = None
    program:       ProgramOutput       | None = None
    employability: EmployabilityOutput | None = None
    accommodation: AccommodationOutput | None = None
    news:          NewsOutput          | None = None
    forum:         ForumOutput         | None = None
    score:         ScoringOutput       | None = None
    alternatives:  AlternativesOutput  | None = None

    def is_complete(self) -> bool:
        """True when all 8 research sections are populated.

        score and alternatives may still be None — they run after sections.
        Used by tests to verify a full research run completed.
        """
        return all([
            self.career       is not None,
            self.background   is not None,
            self.rankings     is not None,
            self.program      is not None,
            self.employability is not None,
            self.accommodation is not None,
            self.news         is not None,
            self.forum        is not None,
        ])

    def section_count(self) -> int:
        """Count of non-None research sections (excludes score and alternatives).
        Used by ScoringAgent to understand what it has to work with."""
        fields = [
            self.career, self.background, self.rankings, self.program,
            self.employability, self.accommodation, self.news, self.forum,
        ]
        return sum(1 for f in fields if f is not None)
```

**Why `is_complete()` excludes score and alternatives:** those fields are
populated after the section agents finish. `is_complete()` answers "did all
research agents run?" — not "is the entire pipeline done?". Keeping the
semantics precise avoids confusion in ScoringAgent's quorum gate logic.

**Why `section_count()`:** ScoringAgent needs to know how many sections it
has to score so it can redistribute weight from missing sections. A helper
is cleaner than repeating the count logic.

---

## 1a.3 `core/deps.py`

`Deps` bundles the three per-request objects every agent needs. Agents receive
`deps` as a parameter — they never construct it themselves.

```python
# core/deps.py
from __future__ import annotations

from dataclasses import dataclass

from core.message_hub import MessageHub
from core.blackboard import Blackboard


@dataclass
class ResearchContext:
    """Immutable context for a single research request.

    Set once by ResearchHandler. Never mutated by agents.

    Attributes:
        university_name: Exact name as supplied by the user.
                         e.g. "University of Manchester"
        intended_course: Exact course name as supplied by the user.
                         e.g. "Computer Science"
        country:         Derived by ResearchHandler from university_name.
                         Never None — derivation happens before pipeline starts.
                         e.g. "UK", "Australia", "USA"
        study_level:     Hardcoded to "undergraduate". Never changes.
    """
    university_name: str
    intended_course: str
    country:         str
    study_level:     str = "undergraduate"


@dataclass
class Deps:
    """Per-request dependency bundle. One fresh instance per research run.

    Passed to every agent handler via closure (see ResearchHandler).
    Agents read context, write to board, publish via hub.
    Never share a Deps instance across requests.

    Tool clients (Tavily, Fetch MCP) are NOT on Deps.
    Each tool owns its own client:
      - Tavily: module-level AsyncTavilyClient singleton in tools/search_tool.py
      - Fetch MCP: module-level fastmcp.Client singleton in mcps/fetch_client.py,
        exposed as the module-level `fetch_client` instance

    tool_budget and calls_made are NOT on Deps — they live on each agent
    instance so concurrent agents manage their own counters independently.
    """
    hub:     MessageHub
    board:   Blackboard
    context: ResearchContext
```

**Why `study_level` is on `ResearchContext` not hardcoded in agents:**
keeping it here means the constraint is visible and searchable. When a future
developer asks "where does undergrad-only get enforced?", the answer is a
grep for `study_level`, not a hunt through 11 agent files.

**Why country derivation happens before `Deps` is created:** agents must never
derive country themselves — different agents could derive it differently.
ResearchHandler derives it once, sets it on `ResearchContext`, and all agents
read the same value.

**Why tool clients are not on `Deps`:** Tavily is a module-level singleton
in `tools/search_tool.py` — stateless across requests, no lifecycle needed.
Fetch MCP is a `FetchClient` class singleton in `mcp/fetch_client.py` — it
requires async lifecycle management (`startup()` / `shutdown()`), which is
the app entry point's responsibility, not `Deps`. Keeping all clients off
`Deps` also makes the per-agent tool set explicit: `CareerAgent` registers
`tavily_search` and `fetch_page` at construction time; it cannot call a tool
that was never registered on it, regardless of what exists elsewhere.

**Why `tool_budget`/`calls_made` are not on `Deps`:**
budget counters are per-agent state — if they lived on shared `Deps`, concurrent
section agents would corrupt each other's counts via `asyncio.gather()`.

---

## 1a.4 `schemas/messages/` — All Message Types

Eight message types. Create one file per message type. Every message carries
`triggered_by` (who fired it) and `timestamp` (ISO format string). Nothing
else unless the routing contract requires it.

### `schemas/messages/base_message.py`

```python
from __future__ import annotations
from pydantic import BaseModel


class BaseMessage(BaseModel):
    """All messages inherit from this.

    triggered_by: identifier of the component that fired the message.
                  Use class name: "career_agent", "research_handler".
    timestamp:    ISO 8601 string. datetime.now().isoformat() is acceptable.
    """
    triggered_by: str
    timestamp:    str
```

### `schemas/messages/research_requested.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ResearchRequestedMessage(BaseMessage):
    """Fired by ResearchHandler to start the pipeline.

    Carries the three inputs that define a research run.
    CareerAgent subscribes to this — it is the pipeline trigger.
    """
    university_name: str
    intended_course: str
    country:         str   # already derived by ResearchHandler
```

### `schemas/messages/career_completed.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class CareerResearchCompletedMessage(BaseMessage):
    """Fired by CareerAgent when board.career is populated.

    Carries no payload — all 7 section agents read board.career directly.
    This message is the signal that Phase 2 can begin.
    """
    pass
```

### `schemas/messages/section_completed.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class SectionCompletedMessage(BaseMessage):
    """Fired by any of the 7 section agents on successful completion.

    section_name must match the blackboard field name exactly.
    ScoringAgent uses this name with setattr() to check board state.

    Valid values: "background", "rankings", "program", "employability",
                  "accommodation", "news", "forum"
    """
    section_name: str
```

### `schemas/messages/section_failed.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class SectionFailedMessage(BaseMessage):
    """Fired by any of the 7 section agents on failure.

    ScoringAgent handles this identically to SectionCompletedMessage
    for quorum counting — it increments received_count regardless.
    The difference: ScoringAgent calls setattr(board, section_name, None)
    to ensure the field is None before scoring.

    section_name must match blackboard field name exactly.
    reason is a human-readable string for logging and report notes.
    """
    section_name: str
    reason:       str
```

### `schemas/messages/scoring_completed.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ScoringCompletedMessage(BaseMessage):
    """Fired by ScoringAgent when board.score is populated.
    AlternativesAgent subscribes to this.
    """
    pass
```

### `schemas/messages/alternatives_completed.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class AlternativesCompletedMessage(BaseMessage):
    """Fired by AlternativesAgent when board.alternatives is populated.
    ReportGenerator subscribes to this.
    """
    pass
```

### `schemas/messages/report_ready.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ReportReadyMessage(BaseMessage):
    """Fired by ReportGenerator when both output files are written.

    file_paths contains paths to the 2 output files:
      [0] report.md  — full report with executive summary
      [1] score.json — machine-readable score breakdown
    Chainlit UI subscribes to this to trigger download links.
    """
    file_paths: list[str]
```

### `schemas/messages/progress_update.py`

```python
from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ProgressUpdateMessage(BaseMessage):
    """Fired by any agent to report live status to the Chainlit UI.

    status values:
      "started"   — agent has begun working
      "completed" — agent finished successfully
      "failed"    — agent encountered an unrecoverable error

    message is a human-readable string shown in the Chainlit step display.
    Example: "Forum Agent: found 12 relevant threads across 3 platforms"
    """
    status:  str   # "started" | "completed" | "failed"
    message: str
```

---

## 1a.5 `schemas/outputs/` — All 10 Output Schemas

Every output schema must have three things:
- `confidence: Literal["high", "medium", "low"]`
- A `sources` list (each source has URL + date at minimum)
- `notes: str` for explaining gaps, caveats, or edge case handling

These are the contracts between agents and the report generator. Define them
completely now — changing them later means updating both the agent and the
report template.

### `schemas/outputs/career_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class CareerPath(BaseModel):
    title:       str          # e.g. "Software Engineer"
    description: str          # typical responsibilities and progression
    typical_companies: list[str]  # named employers, not generic "tech companies"


class SalaryRange(BaseModel):
    career_path:  str
    entry_level:  str   # e.g. "£28,000–£35,000"
    mid_level:    str
    senior_level: str
    currency:     str   # ISO code: "GBP", "AUD", "USD"
    country:      str   # must match ResearchContext.country


class JobPostingSnapshot(BaseModel):
    company:        str
    role_title:     str
    required_skills: list[str]
    date_posted:    str   # ISO date string
    source_url:     str


class CareerSource(BaseModel):
    url:  str
    date: str
    type: str   # "job_board", "salary_survey", "industry_report"


class CareerOutput(BaseModel):
    career_paths:    list[CareerPath]          # minimum 3
    salary_ranges:   list[SalaryRange]         # one per career path
    job_postings:    list[JobPostingSnapshot]  # 10–15 minimum, normalised from adzuna/mcf tools
    in_demand_skills: list[str]               # top 5–8 extracted across postings
    sources:         list[CareerSource]
    confidence:      Literal["high", "medium", "low"]
    notes:           str
```

### `schemas/outputs/background_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class Accreditation(BaseModel):
    name:           str   # e.g. "BCS Accreditation"
    awarding_body:  str
    scope:          str   # what it covers
    confirmed_date: str   # when last verified


class BackgroundSource(BaseModel):
    url:  str
    date: str


class BackgroundOutput(BaseModel):
    founded:          str    # year as string, e.g. "1824"
    student_population: str  # approximate, e.g. "40,000"
    institution_type: str    # "public" | "private"
    orientation:      str    # "research-intensive" | "teaching-focused" | "balanced"
    course_strengths: list[str]   # what this dept is known for — specific, not generic
    accreditations:   list[Accreditation]
    industry_connections: list[str]  # named partnerships specific to the course/dept
    sources:          list[BackgroundSource]
    confidence:       Literal["high", "medium", "low"]
    notes:            str
```

### `schemas/outputs/rankings_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class RankingEntry(BaseModel):
    body:       str    # e.g. "QS World University Rankings by Subject"
    subject:    str    # e.g. "Computer Science & Information Systems"
    position:   str    # e.g. "Top 50" or "32" — string to handle ranges
    year:       str
    scope:      str    # "subject" | "employability" | "overall"
    source_url: str


class RankingsOutput(BaseModel):
    subject_rankings:      list[RankingEntry]  # highest priority
    employability_rankings: list[RankingEntry]
    overall_rankings:      list[RankingEntry]  # lowest weight
    confidence:            Literal["high", "medium", "low"]
    notes:                 str   # explain if no subject ranking found
```

### `schemas/outputs/program_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class ProgramOption(BaseModel):
    full_title:     str          # official program name
    duration_years: int
    has_sandwich_year: bool
    has_study_abroad:  bool


class ModuleList(BaseModel):
    year:    int
    modules: list[str]   # official module names — no paraphrase


class CareerSkillMapping(BaseModel):
    skill:   str   # from CareerOutput.in_demand_skills
    modules: list[str]   # which modules develop this skill


class ProgramSource(BaseModel):
    url:  str
    date: str
    type: str   # "catalog", "department_page", "prospectus"


class ProgramOutput(BaseModel):
    programs:              list[ProgramOption]
    core_modules:          list[ModuleList]   # yr1 and yr2 minimum
    elective_modules:      list[str]
    career_skill_mappings: list[CareerSkillMapping]
    sources:               list[ProgramSource]
    confidence:            Literal["high", "medium", "low"]
    notes:                 str
```

### `schemas/outputs/employability_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class EmploymentStat(BaseModel):
    metric:      str   # e.g. "% employed or in further study within 6 months"
    value:       str   # e.g. "94%"
    source_url:  str
    year:        str


class GraduateDestination(BaseModel):
    company:     str
    role_titles: list[str]
    evidence:    str   # how we know — LinkedIn, graduate survey, etc.


class EmployabilitySource(BaseModel):
    url:  str
    date: str


class EmployabilityOutput(BaseModel):
    employment_stats:      list[EmploymentStat]
    graduate_destinations: list[GraduateDestination]  # named companies required
    graduate_salary:       str   # this-university-specific, with source
    industry_partnerships: list[str]   # dept-specific
    sources:               list[EmployabilitySource]
    confidence:            Literal["high", "medium", "low"]
    notes:                 str
```

### `schemas/outputs/accommodation_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class OnCampusAccommodation(BaseModel):
    weekly_cost_range: str   # e.g. "£130–£210 per week"
    inclusions:        list[str]   # bills, WiFi, cleaning, etc.
    source_url:        str
    year:              str


class OffCampusAccommodation(BaseModel):
    monthly_rent_range: str   # e.g. "£700–£1,100 per month"
    area_description:   str   # which areas near campus
    bills_included:     bool
    source_url:         str
    year:               str


class TransportRoute(BaseModel):
    route:        str   # e.g. "Bus 142 from Fallowfield"
    journey_time: str   # e.g. "15–20 minutes"
    frequency:    str   # e.g. "every 10 minutes"


class AccommodationOutput(BaseModel):
    on_campus:   list[OnCampusAccommodation]
    off_campus:  list[OffCampusAccommodation]
    area_safety: str   # factual — cite statistics if available
    transport:   list[TransportRoute]
    confidence:  Literal["high", "medium", "low"]
    notes:       str
```

### `schemas/outputs/news_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class NewsItem(BaseModel):
    headline:     str    # paraphrased — not verbatim
    sentiment:    Literal["positive", "negative", "neutral"]
    date:         str    # must have a date — items without are discarded
    source_url:   str
    is_dept_specific: bool   # True if about the specific department/course


class NewsOutput(BaseModel):
    items:      list[NewsItem]
    confidence: Literal["high", "medium", "low"]
    notes:      str   # note if no dept-specific news found
```

### `schemas/outputs/forum_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class ForumSource(BaseModel):
    url:         str
    platform:    str    # "thestudentroom", "studentcrowd", "whatuni", "quora", "reddit"
    year:        int
    poster_type: str    # "current_student" | "recent_graduate" | "former_student" | "prospective"


class ForumFinding(BaseModel):
    summary:      str             # paraphrased — never verbatim quotes
    source_count: int             # must be >= 3 to qualify as a finding
    sources:      list[ForumSource]


class ForumOutput(BaseModel):
    recurring_positives:  list[ForumFinding]   # 3+ sources each
    recurring_concerns:   list[ForumFinding]   # 3+ sources each
    department_feedback:  list[ForumFinding]   # teaching quality, lecturers
    confidence:           Literal["high", "medium", "low"]
    notes:                str   # explain if no course-specific threads found
```

### `schemas/outputs/scoring_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class DimensionScore(BaseModel):
    dimension:  str    # human-readable name
    score:      float  # 0.0–10.0
    weight:     float  # 0.0–1.0, redistributed if source field is None
    rationale:  str    # 1–2 sentences citing specific blackboard evidence


class ScoringOutput(BaseModel):
    dimension_scores: list[DimensionScore]
    overall_score:    float   # weighted sum, 0.0–10.0
    tier:             Literal["Strong Consider", "Consider", "Proceed with Caution", "Avoid"]
    top_reasons:      list[str]   # top 3 reasons supporting the tier — evidence-based
    top_concerns:     list[str]   # top 3 concerns to investigate further
    weaknesses:       list[str]   # 2–3 lowest-scoring dimensions — read by AlternativesAgent
    missing_sections: list[str]   # section names that were None — flagged in report
```

### `schemas/outputs/alternatives_output.py`

```python
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal


class AlternativeUniversity(BaseModel):
    university_name:   str
    country:           str
    weakness_addressed: str   # which weakness from ScoringOutput.weaknesses it targets
    evidence:          str    # specific evidence it performs better on that dimension
    subject_ranking:   str    # position, body, year
    program_note:      str    # one sentence on curriculum fit
    employability_note: str   # one sentence on graduate outcomes
    source_urls:       list[str]


class AlternativesOutput(BaseModel):
    alternatives: list[AlternativeUniversity]   # 2–3 entries
    confidence:   Literal["high", "medium", "low"]
    notes:        str   # explain if no suitable alternatives found
```

---

## 1a.6 `core/skill_loader.py`

The skill loader reads SKILL.md files at startup and returns typed metadata
objects. It is called once by `ResearchHandler` before any agent is constructed.

The full implementation is given in the master reference (Section 7). Reproduce
it exactly. Key behaviours to understand:

**`load_skill(path)`** — parses one file. Returns `SkillMeta` on success,
`None` on any failure. Logs a warning for every failure — silent failures
are not acceptable. The split on `"---"` uses `maxsplit=2` so `---` inside
the body text does not break parsing.

**`scan_skills_dir(skills_dir)`** — iterates all subdirectories alphabetically.
Looks for `SKILL.md` inside each. Builds a `dict[str, SkillMeta]` keyed by
`skill.key`. Duplicate keys: first wins, warning logged.

**`SkillMeta`** fields:

| Field | Type | Purpose |
|---|---|---|
| `key` | `str` | Matches folder name. Used to look up skill by agent. |
| `name` | `str` | Human-readable. Used in logs and progress messages. |
| `description` | `str` | One line. Used in `ProgressUpdateMessage.message`. |
| `tool_budget` | `int` | Max tool calls. `0` for scoring/alternatives/conversation. |
| `section_name` | `str \| None` | Blackboard field name. `None` for non-section agents. |
| `instructions` | `str` | Full markdown body. Injected into agent system prompt. |

---

## 1a.7 All 11 SKILL.md Files

Create one file per skill folder. The full content of all 11 files is in the
master reference (Section 8). Below is a summary of each file's key
parameters and any implementation notes.

**Format reminder:** every SKILL.md begins with `---`, then YAML frontmatter,
then `---`, then the markdown body. The `---` delimiters must be on their own
lines. The `key` field must match the folder name exactly.

### File creation summary

| Folder | `key` | `tool_budget` | `section_name` | Notes |
|---|---|---|---|---|
| `skills/career/` | `career` | `8` | `career` | Runs first — Phase 1 |
| `skills/background/` | `background` | `5` | `background` | |
| `skills/rankings/` | `rankings` | `6` | `rankings` | |
| `skills/program/` | `program` | `5` | `program` | |
| `skills/employability/` | `employability` | `8` | `employability` | Reads `board.career` |
| `skills/accommodation/` | `accommodation` | `6` | `accommodation` | |
| `skills/news/` | `news` | `6` | `news` | Tavily only — sets confidence: low if sparse |
| `skills/forum/` | `forum` | `10` | `forum` | TSR + StudentCrowd + WhatUni as primary sources |
| `skills/scoring/` | `scoring` | `0` | *(omit)* | No tools, no section_name |
| `skills/alternatives/` | `alternatives` | `8` | *(omit)* | No section_name |
| `skills/conversation/` | `conversation` | `0` | *(omit)* | No tools, no section_name |

**Why `tool_budget: 0` for scoring, alternatives, and conversation:**
These agents do not call search tools. Setting budget to `0` makes this
explicit and allows the pipeline to catch any accidental tool registration
at startup.

**Why `section_name` is omitted for scoring/alternatives/conversation:**
`SkillMeta.section_name` defaults to `None`. Only agents that write to a
blackboard research field carry a `section_name`. The `ScoringAgent` writes
to `board.score`, but that field is not part of the research section count —
it is synthesis, not a section.

### **SKILL Implementations**

#### `skills/career/SKILL.md`
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

## Tools
You have four tools. Use each only for its designated purpose:

- `tavily_search` — web search. Use for career paths, salary ranges, and
  general labour market research. Every call costs 1 tool budget credit.
  Budget: 8 total across all tavily_search calls this run.
- `fetch_page` — fetches a specific URL. Use after tavily_search returns
  a promising URL you need to read in full (e.g. a salary survey page,
  a graduate destinations report). Does NOT count against tool_budget.
  Do NOT use for Reddit URLs — Reddit blocks this tool.
- `adzuna_jobs` — live job postings API for UK and Australia. Call this
  instead of tavily_search when you need job posting data for UK or AU.
  Does NOT count against tool_budget.
- `mcf_jobs` — live job postings API for Singapore only. Call this instead
  of tavily_search when you need job posting data for SG.
  Does NOT count against tool_budget.

**Tool selection for job postings — mandatory routing:**
- country is "UK" or "Australia" → call `adzuna_jobs`
- country is "Singapore" → call `mcf_jobs`
- Never use `tavily_search` for job postings — job boards block Tavily
  and results will be empty or stale.

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

#### `skills/background/SKILL.md`
```markdown
---
key: background
name: Background Agent
description: Researches the university's institutional profile — history, size, orientation, and course-specific strengths.
tool_budget: 5
section_name: background
---

## Tools
You have two tools:

- `tavily_search` — web search. Use for all background research queries.
  Every call costs 1 tool budget credit. Budget: 5 total.
- `fetch_page` — fetches a specific URL in full. Use when tavily_search
  returns a URL you need to read completely (e.g. an accreditation body
  page, the university's about page, a department profile).
  Does NOT count against tool_budget.

**Decision rule:** search first with `tavily_search`, then fetch the
most relevant URL with `fetch_page` if the snippet is insufficient.
Never call `fetch_page` on a URL you haven't found via search first.

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

#### `skills/rankings/SKILL.md`
```markdown
---
key: rankings
name: Rankings Agent
description: Researches subject-specific and employability rankings for the given university and course.
tool_budget: 6
section_name: rankings
---

## Tools
You have two tools:

- `tavily_search` — web search. Use to find ranking table pages and
  subject-specific positions. Every call costs 1 tool budget credit.
  Budget: 6 total.
- `fetch_page` — fetches a specific URL in full. Use when a ranking table
  page found by tavily_search needs to be read in full to extract the
  exact position (snippets often truncate tables).
  Does NOT count against tool_budget.

**Decision rule:** use `tavily_search` to locate the ranking source,
then `fetch_page` on the ranking page URL if the snippet does not include
the specific position for this university.

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

#### `skills/program/SKILL.md`
```markdown
---
key: program
name: Program Agent
description: Researches the specific undergraduate programs, modules, and delivery format for the given course.
tool_budget: 5
section_name: program
---

## Tools
You have two tools:

- `tavily_search` — web search. Use to locate the university's course
  catalog page and any program structure documents.
  Every call costs 1 tool budget credit. Budget: 5 total.
- `fetch_page` — fetches a specific URL in full. The university's official
  course catalog page is the primary source for module names and structure —
  always fetch it once you have the URL. Snippets from search results
  never contain the full module list.
  Does NOT count against tool_budget.

**Recommended sequence:** 1 tavily_search to find the catalog URL,
then 1 fetch_page to read the full page. Use remaining tavily_search
budget for specialisation pathways or sandwich year details if needed.

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

#### `skills/employability/SKILL.md`

```markdown
---
key: employability
name: Employability Agent
description: Researches graduate employment outcomes, industry partnerships, and alumni trajectories for the given course.
tool_budget: 8
section_name: employability
---

## Tools
You have two tools:

- `tavily_search` — web search. Use for all employment statistics, alumni
  destination searches, and industry partnership queries.
  Every call costs 1 tool budget credit. Budget: 8 total.
- `fetch_page` — fetches a specific URL in full. Use when a graduate
  outcomes report, HESA data page, or employer partnership page found
  by tavily_search needs to be read fully.
  Does NOT count against tool_budget.

**Decision rule:** search first, then fetch the single most data-rich
URL per topic. Do not fetch speculatively — only fetch URLs that
tavily_search snippets confirm contain the specific data you need.

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

#### `skills/accommodation/SKILL.md`

```markdown
---
key: accommodation
name: Accommodation Agent
description: Researches on-campus and off-campus accommodation costs, area safety, and transport access.
tool_budget: 6
section_name: accommodation
---

## Tools
You have two tools:

- `tavily_search` — web search. Use for accommodation cost queries, safety
  statistics, and transport route lookups.
  Every call costs 1 tool budget credit. Budget: 6 total.
- `fetch_page` — fetches a specific URL in full. Use when the university's
  official accommodation page or a local transport authority page needs
  to be read in full for current pricing or route details.
  Does NOT count against tool_budget.

**Recommended allocation:** 1 search + 1 fetch for on-campus costs,
1 search for off-campus rents, 1 search for area safety, 1 search for
transport. Fetch the university accommodation page if pricing is not
in the search snippet.

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

#### `skills/news/SKILL.md`
```markdown
---
key: news
name: News Agent
description: Researches institutional and department-level news from the past 2 years, with sentiment classification per item.
tool_budget: 6
section_name: news
---

## Tools
You have two tools:

- `tavily_search` — web search with `time_range="year"` enforced on every
  call. This is the primary and only search tool for this agent.
  Every call costs 1 tool budget credit. Budget: 6 total.
  If results are sparse after 3–4 queries, set `confidence: "low"` and
  explain in `notes` — do not keep searching beyond budget.
- `fetch_page` — fetches a specific URL in full. Use only when a news
  article found by tavily_search requires the full text to extract a
  publication date or confirm it is department-specific.
  Does NOT count against tool_budget.

**Do NOT use** `fetch_page` speculatively. Fetch only when the snippet
is insufficient to determine date or relevance.

## What to research
- Institutional news: significant events from the past 2 years — strikes,
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

#### `skills/forum/SKILL.md`
```markdown
---
key: forum
name: Forum Agent
description: Researches student forum discussions about the specific course at the specific university, filtering strictly for course-level signal.
tool_budget: 10
section_name: forum
---

## This agent has the highest tool budget and the strictest scope rules.

## Tools
You have three tools. Each has a specific role — do not substitute one for another:

- `tavily_search` — web search. Use for all forum source discovery: finding
  TSR threads, StudentCrowd pages, WhatUni pages, Quora threads, and Reddit
  post URLs. Every call costs 1 tool budget credit. Budget: 10 total.
- `fetch_page` — fetches a specific URL in full. Use for StudentCrowd and
  WhatUni course pages once tavily_search returns the URL. Gives you the
  full review text that snippets truncate.
  Does NOT count against tool_budget.
  **NEVER use fetch_page for Reddit URLs** — Reddit blocks this tool with
  a robots.txt error. Use reddit_fetch_thread instead.
- `reddit_fetch_thread` — fetches the full comment thread for a Reddit post
  via Reddit's public JSON API. Use this after tavily_search returns a
  Reddit post URL. Returns the post title, body, and all top-level comments
  with score ≥ 1, already parsed — no manual JSON extraction needed.
  Does NOT count against tool_budget.

**Tool routing by source:**
| Source | Find URL with | Read content with |
|---|---|---|
| The Student Room | `tavily_search` | snippet is usually sufficient; skip fetch |
| StudentCrowd | `tavily_search` | `fetch_page` for full review text |
| WhatUni | `tavily_search` | `fetch_page` for full review text |
| Quora | `tavily_search` | snippet is usually sufficient; skip fetch |
| Reddit | `tavily_search` | `reddit_fetch_thread` — never fetch_page |
| College Confidential | `tavily_search` | snippet is usually sufficient |

## Scope rules — enforced on every query and every result
Every query must include both the university name AND the course name.
Every result that does not mention the specific course or department is discarded.
Generic university experience threads are not acceptable output.

## Sources — search in this order
1. `site:thestudentroom.co.uk` via tavily_search — primary source. Deep UK
   student forum, course-specific threads, high signal. Use for course
   experience, teaching quality, and student life feedback.
2. `site:studentcrowd.com` via tavily_search — verified student reviews per
   course with structured ratings. Fetch the course-specific page via
   fetch_page for full reviews.
3. `site:whatuni.com` via tavily_search — student ratings and reviews per
   course. Fetch the course page via fetch_page for full review text.
4. `site:quora.com` via tavily_search — student Q&A threads, useful for
   international student perspectives and course comparisons.
5. `site:reddit.com` via tavily_search — finds Reddit post URLs. After
   getting a URL from tavily_search, call reddit_fetch_thread with that URL
   to get the full thread. Do NOT call fetch_page on Reddit URLs.
   Discard threads with fewer than 3 substantive comments (score ≥ 1).
   For non-UK universities, promote this to source 2 if TSR coverage is sparse.
6. `site:collegeconfidential.com` via tavily_search — use for US and
   international universities only. Skip for UK-only queries where TSR
   and StudentCrowd suffice.

## Query construction
Always: [university name] + [course name] + [signal type]

Examples:
- "site:thestudentroom.co.uk University of Manchester Computer Science student experience"
- "site:studentcrowd.com University of Manchester Computer Science review"
- "site:whatuni.com University of Manchester Computer Science student review"
- "site:quora.com University of Manchester Computer Science worth it"
- "site:reddit.com University of Manchester Computer Science undergraduate"

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

#### `skills/scoring/SKILL.md`

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

#### `skills/alternatives/SKILL.md`

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

#### `skills/conversation/SKILL.md`

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

## 1a.7a `tool_budget` — What It Is and How It Gets Enforced

### What it is
`tool_budget` is the maximum number of external tool calls an agent is
allowed to make in a single pipeline run. It is declared in each SKILL.md
frontmatter, read by `SkillMeta` at startup, and passed to the agent
constructor by `ResearchHandler`.

It exists for three reasons:

**Cost control.** Every Tavily call costs 1 API credit. A hard cap makes worst-case API spend
per pipeline run predictable. With the values in this spec, a full run
across all agents costs at most 50–70 Tavily calls — within the free tier.

**Query discipline.** An agent with an unlimited budget can afford to be
lazy — fire broad queries and sift results. An agent with 5 calls must
construct precise queries from the start. The budget forces the agent to
prioritise signal over volume.

**Pipeline stability.** An agent that loops or retries excessively blocks
the concurrent phase. A hard cap prevents one misbehaving agent from
stalling the others.

### Why the values are what they are

| Agent | `tool_budget` | Why |
|---|---|---|
| `forum` | 10 | Highest — 5 forum sources × tavily_search `site:` queries, plus fetch_page for StudentCrowd/WhatUni pages, plus reddit_fetch_thread for Reddit threads (fetch_page cannot be used for Reddit) |
| `career` | 8 | Salary + career path research via tavily_search; job postings via adzuna_jobs or mcf_jobs (not counted against budget) |
| `employability` | 8 | Named company evidence requires multiple targeted tavily_search queries |
| `alternatives` | 8 | 2–3 universities × multiple tavily_search queries each |
| `rankings` | 6 | Multiple ranking bodies — QS, THE, Guardian, Complete University Guide |
| `accommodation` | 6 | On-campus + off-campus + safety + transport — four distinct tavily_search calls |
| `news` | 6 | tavily_search only — institutional + department-specific news queries |
| `background` | 5 | Institutional facts — fewer tavily_search queries needed |
| `program` | 5 | 1–2 tavily_search calls to locate catalog URL, then fetch_page for full content |
| `scoring` | 0 | No tools — synthesises from blackboard only, never searches |
| `conversation` | 0 | No tools — answers follow-up questions from blackboard only |

`scoring` and `conversation` having `tool_budget: 0` is an explicit
contract, not a default. It makes it immediately visible in the SKILL.md
that these agents must never call search tools.

### How it gets enforced — Stage 1c and 2a
`tool_budget` is stored on `SkillMeta` and passed to each agent constructor
at startup. The enforcement is implemented when agents are built in Stage 1c
(`CareerAgent`) and Stage 2a (all remaining section agents).

The pattern every agent follows (implemented in Stage 1c and 2a via `_make_search_tool()`):

```python
class CareerAgent(BaseAgent):
    def __init__(self, instructions: str, tool_budget: int) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0        # reset per request in handle()

    def _make_search_tool(self):1
        """Wrap tavily_search with a budget-aware closure over this agent instance."""
        agent_self = self
        async def tavily_search(ctx: RunContext[Deps], query: str) -> str:
            if agent_self._calls_made >= agent_self._tool_budget:
                agent_self._logger.warning(
                    "%s | tool budget exhausted (%d calls) — skipping: %r",
                    agent_self.__class__.__name__, agent_self._tool_budget, query,
                )
                return json.dumps({"error": "tool budget exhausted", "query": query})
            agent_self._calls_made += 1
            from tools.search_tool import _client as tavily_client   # module-level singleton
            results = await tavily_client.search(query, max_results=5, time_range="year")
            return json.dumps(results)
        return tavily_search
```

The Tavily client is the module-level `AsyncTavilyClient` singleton in `tools/search_tool.py` —
it is **not** on `Deps`. The budget closure reaches it via a direct module import inside the
wrapper function. `fetch_page` and job posting tools (`adzuna_jobs`, `mcf_jobs`) are registered
directly without budget wrapping — they are targeted retrieval calls, not searches.

`_calls_made` is reset at the start of each `handle()` call — not in
`__init__()` — so the same agent instance handles multiple requests across
sessions without carrying over a previous run's count.

### What happens when the budget is exhausted
The agent does not raise or fail. It logs a warning, skips remaining
queries, and returns whatever it gathered so far. The output schema's
`confidence` field is set to `"low"` if the agent could not complete all
intended searches. `ScoringAgent` reads `confidence` and redistributes
weight accordingly.

A partial result with a low confidence flag is more useful than a
pipeline failure.

### Why `tool_budget` lives in SKILL.md and not in Python
Budget values change as the system is tuned. `ForumAgent` might need 12
calls for certain universities. `BackgroundAgent` might only ever need 3.
Keeping the value in SKILL.md means adjusting the budget is a markdown
edit and restart — no Python change, no redeploy.

---

## 1a.8 `core/llm_factory.py`

Creates pydantic-ai model instances from environment variables. Called once
by `ResearchHandler` at startup.

```python
# core/llm_factory.py
from __future__ import annotations

import os
from dotenv import load_dotenv


def get_model(env_key: str):
    """Return a pydantic-ai model instance for the given env var key.

    Uses OpenRouter via the OpenAI-compatible provider.
    OPENROUTER_BASE_URL and OPENROUTER_API_KEY must be set in .env.

    Args:
        env_key: environment variable name, e.g. "RESEARCH_MODEL"

    Returns:
        A pydantic-ai OpenAIModel configured for OpenRouter.

    Raises:
        EnvironmentError: if the env var or API key is not set.
    """
    load_dotenv()

    model_string = os.getenv(env_key)
    if not model_string:
        raise EnvironmentError(
            f"Environment variable {env_key!r} is not set. "
            "Check your .env file."
        )

    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. Check your .env file."
        )

    # pydantic-ai OpenAI-compatible provider
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=base_url,
        api_key=api_key,
    )
    return OpenAIModel(model_name=model_string, provider=provider)
```

**Why a factory function instead of module-level constants:** environment
variables may not be loaded when the module is imported. The factory calls
`load_dotenv()` itself, so it works regardless of import order.

**Why `base_url` has a default:** defensive — if `OPENROUTER_BASE_URL` is
accidentally omitted from `.env`, the system falls back to the correct URL
rather than crashing with a confusing error.

---

## 1a.9 `tests/test_stage_1a.py`

```python
# tests/test_stage_1a.py
"""
Stage 1a tests.

Verifies:
1. MessageHub subscribes and dispatches correctly.
2. Blackboard initialises with all None fields.
3. Deps bundles hub + board + context correctly.
4. All message types instantiate without error.
5. All output schemas instantiate without error.
6. SkillLoader scans skills/ and returns exactly 11 keys.
7. Each loaded SkillMeta has required fields populated.

No LLM calls. No network calls. Pure Python.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from core.message_hub import MessageHub
from core.blackboard import Blackboard
from core.deps import Deps, ResearchContext

# Messages
from schemas.messages.base_message import BaseMessage
from schemas.messages.research_requested import ResearchRequestedMessage
from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.section_completed import SectionCompletedMessage
from schemas.messages.section_failed import SectionFailedMessage
from schemas.messages.scoring_completed import ScoringCompletedMessage
from schemas.messages.alternatives_completed import AlternativesCompletedMessage
from schemas.messages.report_ready import ReportReadyMessage
from schemas.messages.progress_update import ProgressUpdateMessage

# Skill loader
from core.skill_loader import scan_skills_dir, SkillMeta

TIMESTAMP = datetime.now().isoformat()

# ── MessageHub ────────────────────────────────────────────────────────────────

def test_hub_subscribe_and_publish() -> None:
    """Hub dispatches to registered handler via closure capturing deps."""
    hub = MessageHub()
    received: list = []

    deps = Deps(hub=hub, board=Blackboard(), context=ResearchContext(
        university_name="U", intended_course="CS", country="UK"
    ))

    # Handlers are closures that capture deps at subscription time
    async def handler(message: SectionCompletedMessage) -> None:
        received.append(message)

    hub.subscribe(SectionCompletedMessage, handler)
    msg = SectionCompletedMessage(
        section_name="forum",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.run(hub.publish(msg))
    assert len(received) == 1
    assert received[0].section_name == "forum"


def test_hub_multiple_handlers() -> None:
    """All handlers for a type fire on publish."""
    hub = MessageHub()
    calls: list[str] = []

    async def h1(message): calls.append("h1")
    async def h2(message): calls.append("h2")
    async def h3(message): calls.append("h3")

    hub.subscribe(SectionCompletedMessage, h1)
    hub.subscribe(SectionCompletedMessage, h2)
    hub.subscribe(SectionCompletedMessage, h3)

    msg = SectionCompletedMessage(
        section_name="background",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.run(hub.publish(msg))
    assert sorted(calls) == ["h1", "h2", "h3"]


def test_hub_no_handlers_is_noop() -> None:
    """Publishing to a type with no subscribers does nothing."""
    hub = MessageHub()
    msg = ScoringCompletedMessage(triggered_by="test", timestamp=TIMESTAMP)
    asyncio.run(hub.publish(msg))  # must not raise


def test_hub_type_isolation() -> None:
    """Handler for type A does not fire when type B is published."""
    hub = MessageHub()
    calls: list[str] = []

    async def handler(message): calls.append("fired")

    hub.subscribe(SectionCompletedMessage, handler)
    msg = SectionFailedMessage(
        section_name="news",
        reason="timeout",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.run(hub.publish(msg))
    assert calls == []


def test_hub_fresh_instance_isolation() -> None:
    """Two hub instances have separate subscriber lists."""
    hub1 = MessageHub()
    hub2 = MessageHub()
    calls: list[str] = []

    async def handler(message): calls.append("fired")

    hub1.subscribe(SectionCompletedMessage, handler)
    msg = SectionCompletedMessage(
        section_name="rankings",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.run(hub2.publish(msg))
    assert calls == []   # hub2 has no subscribers


# ── Blackboard ────────────────────────────────────────────────────────────────

def test_blackboard_initial_state() -> None:
    """All fields start as None."""
    board = Blackboard()
    assert board.career is None
    assert board.background is None
    assert board.rankings is None
    assert board.program is None
    assert board.employability is None
    assert board.accommodation is None
    assert board.news is None
    assert board.forum is None
    assert board.score is None
    assert board.alternatives is None


def test_blackboard_is_complete_false_when_empty() -> None:
    assert Blackboard().is_complete() is False


def test_blackboard_section_count_zero_when_empty() -> None:
    assert Blackboard().section_count() == 0


# ── Deps ──────────────────────────────────────────────────────────────────────

def test_deps_bundles_correctly() -> None:
    hub = MessageHub()
    board = Blackboard()
    context = ResearchContext(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    )
    deps = Deps(hub=hub, board=board, context=context)
    assert deps.hub is hub
    assert deps.board is board
    assert deps.context.study_level == "undergraduate"


# ── Message types ─────────────────────────────────────────────────────────────

def test_all_message_types_instantiate() -> None:
    """Every message type constructs without error."""
    msgs = [
        ResearchRequestedMessage(
            university_name="U", intended_course="CS", country="UK",
            triggered_by="t", timestamp=TIMESTAMP,
        ),
        CareerResearchCompletedMessage(triggered_by="t", timestamp=TIMESTAMP),
        SectionCompletedMessage(section_name="forum", triggered_by="t", timestamp=TIMESTAMP),
        SectionFailedMessage(section_name="news", reason="timeout", triggered_by="t", timestamp=TIMESTAMP),
        ScoringCompletedMessage(triggered_by="t", timestamp=TIMESTAMP),
        AlternativesCompletedMessage(triggered_by="t", timestamp=TIMESTAMP),
        ReportReadyMessage(file_paths=["report.md", "score.json"], triggered_by="t", timestamp=TIMESTAMP),
        ProgressUpdateMessage(status="started", message="Running", triggered_by="t", timestamp=TIMESTAMP),
    ]
    assert len(msgs) == 8


# ── Output schemas ────────────────────────────────────────────────────────────

def test_output_schemas_importable() -> None:
    """All 10 output schema modules import without error."""
    from schemas.outputs import (  # noqa: F401
        career_output,
        background_output,
        rankings_output,
        program_output,
        employability_output,
        accommodation_output,
        news_output,
        forum_output,
        scoring_output,
        alternatives_output,
    )


# ── SkillLoader ───────────────────────────────────────────────────────────────

EXPECTED_SKILL_KEYS = {
    "accommodation", "alternatives", "background", "career",
    "conversation", "employability", "forum", "news",
    "program", "rankings", "scoring",
}


def test_skill_loader_finds_all_11_skills() -> None:
    """scan_skills_dir returns exactly 11 keys matching expected set."""
    skills = scan_skills_dir(Path("skills"))
    assert set(skills.keys()) == EXPECTED_SKILL_KEYS, (
        f"Expected {EXPECTED_SKILL_KEYS}\nGot {set(skills.keys())}"
    )


def test_skill_loader_all_have_required_fields() -> None:
    """Every loaded SkillMeta has key, name, description, tool_budget, instructions."""
    skills = scan_skills_dir(Path("skills"))
    for key, skill in skills.items():
        assert skill.key,          f"{key}: key is empty"
        assert skill.name,         f"{key}: name is empty"
        assert skill.description,  f"{key}: description is empty"
        assert isinstance(skill.tool_budget, int), f"{key}: tool_budget must be int"
        assert skill.instructions, f"{key}: instructions (markdown body) is empty"


def test_skill_loader_section_names_match_blackboard() -> None:
    """Skills with section_name must match Blackboard field names."""
    valid_section_names = {
        "career", "background", "rankings", "program",
        "employability", "accommodation", "news", "forum",
    }
    skills = scan_skills_dir(Path("skills"))
    for key, skill in skills.items():
        if skill.section_name is not None:
            assert skill.section_name in valid_section_names, (
                f"{key}: section_name {skill.section_name!r} not a valid blackboard field"
            )


def test_skill_loader_scoring_has_zero_budget() -> None:
    skills = scan_skills_dir(Path("skills"))
    assert skills["scoring"].tool_budget == 0


def test_skill_loader_forum_has_highest_budget() -> None:
    skills = scan_skills_dir(Path("skills"))
    budgets = {k: v.tool_budget for k, v in skills.items()}
    assert budgets["forum"] == max(budgets.values()), (
        "forum should have the highest tool_budget"
    )


def test_skill_loader_no_section_name_for_synthesis_agents() -> None:
    """scoring, alternatives, conversation must not have a section_name."""
    skills = scan_skills_dir(Path("skills"))
    for key in ("scoring", "alternatives", "conversation"):
        assert skills[key].section_name is None, (
            f"{key}: should not have section_name"
        )
```

---

## 1a.10 Run the Tests

```bash
pytest tests/test_stage_1a.py -v
python -m pytest tests/1a/test_hub_subscribe_and_publish.py (USE THIS !!!)
```

Expected output:

```
tests/test_stage_1a.py::test_hub_subscribe_and_publish PASSED
tests/test_stage_1a.py::test_hub_multiple_handlers PASSED
tests/test_stage_1a.py::test_hub_no_handlers_is_noop PASSED
tests/test_stage_1a.py::test_hub_type_isolation PASSED
tests/test_stage_1a.py::test_hub_fresh_instance_isolation PASSED
tests/test_stage_1a.py::test_blackboard_initial_state PASSED
tests/test_stage_1a.py::test_blackboard_is_complete_false_when_empty PASSED
tests/test_stage_1a.py::test_blackboard_section_count_zero_when_empty PASSED
tests/test_stage_1a.py::test_deps_bundles_correctly PASSED
tests/test_stage_1a.py::test_all_message_types_instantiate PASSED
tests/test_stage_1a.py::test_output_schemas_importable PASSED
tests/test_stage_1a.py::test_skill_loader_finds_all_11_skills PASSED
tests/test_stage_1a.py::test_skill_loader_all_have_required_fields PASSED
tests/test_stage_1a.py::test_skill_loader_section_names_match_blackboard PASSED
tests/test_stage_1a.py::test_skill_loader_scoring_has_zero_budget PASSED
tests/test_stage_1a.py::test_skill_loader_forum_has_highest_budget PASSED
tests/test_stage_1a.py::test_skill_loader_no_section_name_for_synthesis_agents PASSED

17 passed in 0.XXs
```

---

## 1a.11 Common Failure Modes at This Stage

**`ModuleNotFoundError: schemas.outputs`**
Cause: missing `schemas/outputs/__init__.py`.
Fix: create it as an empty file.

**`test_skill_loader_finds_all_11_skills FAILED — Got 0 keys`**
Cause: SKILL.md files are empty or missing frontmatter delimiters.
The loader returns `None` for any file that does not parse. Check that
each SKILL.md has `---` on line 1, YAML block, `---`, then body text.

**`test_skill_loader_all_have_required_fields FAILED — instructions is empty`**
Cause: the markdown body after the second `---` is empty.
The body does not need to be complete at this stage, but it must not be blank.
Add at least a one-line placeholder if the full content is not written yet.

**`test_hub_subscribe_and_publish FAILED — handler not called`**
Cause: handler signature is wrong or `hub.publish(msg, deps)` was called with two args.
`hub.publish(message)` takes only the message — `deps` is captured by closure at subscription
time, not passed through the hub. Fix: ensure `hub.subscribe(MsgType, handler)` is called
before `hub.publish(msg)`, and that the handler accepts a single message argument.

**`AssertionError: forum should have the highest tool_budget`**
Cause: `forum/SKILL.md` has `tool_budget: 8` instead of `10`.
Fix: set `tool_budget: 10` in `skills/forum/SKILL.md`.

---

## Stage 1a Completion Checklist

- [ ] `core/message_hub.py` implemented and imported cleanly
- [ ] `core/blackboard.py` implemented with all 10 fields
- [ ] `core/deps.py` implemented with `ResearchContext` and `Deps`
- [ ] `core/skill_loader.py` implemented (exact copy from master reference)
- [ ] `core/llm_factory.py` implemented
- [ ] All 8 message schema files created in `schemas/messages/`
- [ ] All 10 output schema files created in `schemas/outputs/`
- [ ] All 11 SKILL.md files created with correct frontmatter and non-empty body
- [ ] `pytest tests/test_stage_1a.py -v` — 17 passed, 0 failed
- [ ] Stage 0 tests still pass: `pytest tests/test_env.py -v` — 6 passed31