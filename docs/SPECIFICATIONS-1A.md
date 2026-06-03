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

```python
# core/message_hub.py
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, Awaitable, Any

from pydantic import BaseModel


class MessageHub:
    """Pure fan-out message dispatcher.

    One instance per research request — created fresh in
    ResearchHandler.handle_request(). Never reused across requests.
    Reusing accumulates handlers from prior requests.

    Usage:
        hub = MessageHub()
        hub.subscribe(SomeMessage, async_handler_fn)
        await hub.publish(SomeMessage(triggered_by="x", timestamp="..."))
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable[..., Awaitable[Any]]]] = defaultdict(list)

    def subscribe(
        self,
        message_type: type,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register an async handler for a message type.

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
        if handlers:
            await asyncio.gather(*[h(message) for h in handlers])

    def subscriber_count(self, message_type: type) -> int:
        """Return number of registered handlers for a message type.
        Used in tests to verify subscription state."""
        return len(self._subscribers.get(message_type, []))
```

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


class JobPosting(BaseModel):
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
    career_paths:    list[CareerPath]    # minimum 3
    salary_ranges:   list[SalaryRange]  # one per career path
    job_postings:    list[JobPosting]   # 10–15 minimum
    in_demand_skills: list[str]         # top 5–8 extracted across postings
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
    platform:    str    # "reddit", "thestudentroom", "thegradcafe", "quora"
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
| `skills/news/` | `news` | `6` | `news` | DuckDuckGo fallback documented |
| `skills/forum/` | `forum` | `10` | `forum` | Reddit API as source #1 |
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
    """Hub dispatches to registered handler."""
    hub = MessageHub()
    received: list[BaseMessage] = []

    async def handler(msg: BaseMessage) -> None:
        received.append(msg)

    hub.subscribe(SectionCompletedMessage, handler)
    msg = SectionCompletedMessage(
        section_name="forum",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.get_event_loop().run_until_complete(hub.publish(msg))
    assert len(received) == 1
    assert received[0].section_name == "forum"


def test_hub_multiple_handlers() -> None:
    """All handlers for a type fire on publish."""
    hub = MessageHub()
    calls: list[str] = []

    async def h1(msg): calls.append("h1")
    async def h2(msg): calls.append("h2")
    async def h3(msg): calls.append("h3")

    hub.subscribe(SectionCompletedMessage, h1)
    hub.subscribe(SectionCompletedMessage, h2)
    hub.subscribe(SectionCompletedMessage, h3)

    msg = SectionCompletedMessage(
        section_name="background",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.get_event_loop().run_until_complete(hub.publish(msg))
    assert sorted(calls) == ["h1", "h2", "h3"]


def test_hub_no_handlers_is_noop() -> None:
    """Publishing to a type with no subscribers does nothing."""
    hub = MessageHub()
    msg = ScoringCompletedMessage(triggered_by="test", timestamp=TIMESTAMP)
    asyncio.get_event_loop().run_until_complete(hub.publish(msg))  # must not raise


def test_hub_type_isolation() -> None:
    """Handler for type A does not fire when type B is published."""
    hub = MessageHub()
    calls: list[str] = []

    async def handler(msg): calls.append("fired")

    hub.subscribe(SectionCompletedMessage, handler)
    msg = SectionFailedMessage(
        section_name="news",
        reason="timeout",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.get_event_loop().run_until_complete(hub.publish(msg))
    assert calls == []


def test_hub_fresh_instance_isolation() -> None:
    """Two hub instances have separate subscriber lists."""
    hub1 = MessageHub()
    hub2 = MessageHub()
    calls: list[str] = []

    async def handler(msg): calls.append("fired")

    hub1.subscribe(SectionCompletedMessage, handler)
    msg = SectionCompletedMessage(
        section_name="rankings",
        triggered_by="test",
        timestamp=TIMESTAMP,
    )
    asyncio.get_event_loop().run_until_complete(hub2.publish(msg))
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

**`test_hub_subscribe_and_publish FAILED — DeprecationWarning: There is no current event loop`**
Cause: using `asyncio.get_event_loop().run_until_complete()` in Python 3.12.
Fix: replace with `asyncio.run(hub.publish(msg))` in the test.

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
- [ ] Stage 0 tests still pass: `pytest tests/test_env.py -v` — 6 passed