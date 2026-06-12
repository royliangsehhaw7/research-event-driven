# Stage 1f — ForumAgent End-to-End
## Implementation Specification

**Goal:** `ForumAgent` is fully implemented, wired into the pipeline, and
confirmed to populate `board.forum` with real, corroborated student experience
data drawn from at least 4 of the 6 designated forum sources. No report is
generated. No scoring runs. Pure agent output — one agent, one blackboard
field, one section message.

**Ends with:** `python main.py` runs, logs show `ForumAgent` completing, and
`board.forum` is printed to stdout containing real findings with source URLs
traceable to TSR, StudentCrowd, WhatUni, Unibuddy, Prospects, or Reddit — each
dated within the last 18 months.

---

## Why ForumAgent Is the Most Critical Section Agent

Every other section agent in this pipeline reads official or semi-official
sources: rankings tables, university web pages, graduate salary surveys, job
boards. These sources are either curated, promotional, or aggregated.
They describe universities as institutions want to be described.

`ForumAgent` is the only agent that fishes for candid, unmediated student
voice. A parent reading the final report needs to know what current students
actually say about the teaching quality, the department culture, the jump
between year 1 and year 2, the responsiveness of lecturers. None of that
appears in a Guardian ranking or a UCAS course page.

This makes `ForumAgent` uniquely difficult:

- **Signal is buried.** Forum threads contain noise (applicant chatter,
  off-topic replies, jokes) alongside genuine experience reports. The LLM
  must be instructed to distinguish them precisely.
- **Recency is unreliable.** Tavily's `days=730` filter applies at the query
  level, but a thread started in 2018 with a single reply in 2024 passes
  that filter. Post-level date verification is required in the SKILL.md
  instructions.
- **Cross-platform corroboration is the quality gate.** One student on TSR
  saying "the lecturers are great" is anecdote. The same sentiment appearing
  independently on TSR, StudentCrowd, and Reddit is a finding. The output
  schema enforces this — no finding qualifies with fewer than 3 independent
  sources, and at least 2 of those sources must be on different platforms.
- **Scope discipline is strict.** A complaint about university accommodation
  or the student union is out of scope. Only content explicitly about the
  researched department, course modules, teaching, or programme experience
  qualifies. Off-topic content must be discarded, not summarised.

These constraints are enforced via SKILL.md instructions (what the LLM does)
and the output schema (what shape the result must take). The Python class
is structurally identical to every other section agent.

---

## What This Stage Builds

| File | Purpose |
|---|---|
| `schemas/outputs/forum_output.py` | Typed output schema — `ForumOutput` and sub-models |
| `skills/forum/SKILL.md` | All domain instructions — sources, query patterns, recency rules, scope gates, corroboration threshold |
| `agents/forum_agent.py` | The agent class — subscribe, handle, fire |
| `services/research_handler.py` | Updated to add `ForumAgent` alongside the Stage 1e agents |
| `main.py` | Updated to print `board.forum` in addition to prior board fields |

`ForumAgent` subscribes to `CareerResearchCompletedMessage` — the same
trigger as all six other section agents. It runs concurrently with them via
`asyncio.gather()`. It writes to `board.forum`. It fires
`SectionCompletedMessage(section_name="forum")` on success and
`SectionFailedMessage(section_name="forum")` on failure.

---

## 1f.1 Forum Source Registry

These are the six designated sources for `ForumAgent`. Each has a different
signal profile, a different domain, and different query reliability via Tavily.
The SKILL.md instructs the LLM to use all six, but findings that cannot be
corroborated across platforms do not qualify as output.

---

### Source 1 — The Student Room (TSR)
**Domain:** `thestudentroom.co.uk`
**Signal profile:** Highest volume of UK undergraduate discussion. Contains
both applicant threads (low value) and current student experience threads
(high value). Threads are long-lived — a 2019 thread may still receive
replies in 2024. Post-level date verification is essential.
**Best content:** Year-in-review posts, "what is [university] [course] really
like" threads, module feedback threads, teaching quality discussions.
**Noise:** "What are my chances?" applicant posts, grade prediction threads,
accommodation comparison threads unrelated to the course.
**Query pattern:**
```
"{university} {course} student experience" site:thestudentroom.co.uk
"{university} {course} teaching quality" site:thestudentroom.co.uk
"{university} {course} first year second year" site:thestudentroom.co.uk
"{university} {department} lecturers modules" site:thestudentroom.co.uk
```
**Recency rule:** Accept posts dated within 18 months only. If Tavily
returns a URL for a thread, `fetch_page` the URL and check visible post
dates before extracting content. Discard the entire thread if the most
recent substantive post (not a one-liner) is older than 18 months.

---

### Source 2 — StudentCrowd
**Domain:** `studentcrowd.com`
**Signal profile:** Structured review platform. Students submit ratings and
written reviews by university and course. Reviews are individually dated.
Closer to Trustpilot than to a forum — shorter, more structured, less
nuanced than TSR threads. Good for corroborating TSR findings.
**Best content:** Course-specific star ratings with written justification,
"what I wish I had known" reviews, teaching quality ratings.
**Noise:** Very short one-line reviews with no justification ("great uni,
loved it") — these carry no signal and must be discarded.
**Query pattern:**
```
"{university} {course} reviews" site:studentcrowd.com
"{university} {course} student review teaching" site:studentcrowd.com
```
**Recency rule:** StudentCrowd displays review dates. Accept reviews dated
within 18 months. If `fetch_page` returns a review page, extract only
reviews with visible dates within the window.

---

### Source 3 — WhatUni
**Domain:** `whatuni.com`
**Signal profile:** Similar to StudentCrowd — structured review platform with
course-level reviews, ratings, and date stamps. Owned by UCAS. Reviews tend
to be slightly longer than StudentCrowd and more narrative.
**Best content:** Structured course reviews covering teaching, workload,
facilities, and career support. The "course content" and "teaching quality"
categories are specifically relevant.
**Noise:** University-level reviews that do not reference the specific course
or department — these must be discarded if they do not name the course.
**Query pattern:**
```
"{university} {course} review" site:whatuni.com
"{university} {course} student review" site:whatuni.com
```
**Recency rule:** WhatUni displays review dates. Accept reviews dated within
18 months only.

---

### Source 4 — Unibuddy (Community Blogs)
**Domain:** `unibuddy.com`
**Signal profile:** Student ambassador blogs and Q&A threads. Less candid
than TSR because contributors are university-selected ambassadors — content
leans positive. However, the Q&A format often contains frank answers to
prospective student questions, and module-level detail is frequently accurate
because ambassadors know their courses well.
**Best content:** Q&A responses about specific modules, workload descriptions,
department culture from current students, "a week in my life" style posts
that reveal course structure.
**Noise:** Pure promotional content, welcome posts with no specific course
information, purely social content.
**Weighting:** Treat Unibuddy content as corroborating evidence only — never
as a primary source for a concern. A positive finding from Unibuddy
corroborates a positive finding from TSR; it does not independently establish
a finding.
**Query pattern:**
```
"{university} {course} student blog" site:unibuddy.com
"{university} {course} modules teaching" site:unibuddy.com
```
**Recency rule:** Accept posts within 18 months. Many Unibuddy posts are
undated — if no date is visible on the page after `fetch_page`, discard the
content.

---

### Source 5 — Prospects.ac.uk (Graduate Profiles)
**Domain:** `prospects.ac.uk`
**Signal profile:** The UK's largest graduate careers site. Contains graduate
profiles — first-person accounts from graduates describing their degree
experience and how it led to their current role. Less about teaching quality,
more about retrospective degree value. Useful for corroborating employability
and course reputation findings from `board.career` and `board.employability`.
**Best content:** "What I do now" graduate profile narratives that reference
the university and course by name, descriptions of how specific modules or
projects translated to career outcomes.
**Noise:** Generic careers advice articles, job listing pages, salary
survey summaries not referencing the specific university.
**Weighting:** Prospects content provides retrospective graduate voice —
weight it for career-outcomes corroboration, not for current teaching
experience. Do not use it as a source for claims about current course
delivery.
**Query pattern:**
```
"{university} {course} graduate profile" site:prospects.ac.uk
"{university} {course} what I do now" site:prospects.ac.uk
```
**Recency rule:** Graduate profile dates are usually the publication year.
Accept profiles published within 24 months (relaxed from 18 — graduate
profiles are sparse and retrospective, so a slightly wider window is
justified). Note the relaxed window in the output `notes` field if used.

---

### Source 6 — Reddit
**Domain:** `reddit.com` — specifically subreddits:
`r/UniUK`, `r/6thForm`, `r/ApplyingToCollege` (UK context threads),
and university-specific subreddits where they exist (e.g. `r/manchester`).
**Signal profile:** The most candid source in the set. No moderation bias,
no promotional incentive. Reddit posters are direct and often specific.
However, Tavily returns only snippets from Reddit — full comment threads
are not accessible. This limits depth but not breadth.
**Best content:** "What is [university] [course] actually like?" threads,
"is [university] good for [course]?" posts, AMA-style threads from current
students.
**Noise:** Meme posts, off-topic threads, posts about university life that
do not reference the course or department.
**Weighting:** Reddit snippets carry high credibility for negative findings
(no promotional incentive) but lower depth (snippets only, no full thread).
Weight Reddit corroboration for concerns more heavily than for positives.
**Query pattern:**
```
"{university} {course} reddit"
"site:reddit.com {university} {course} experience"
"site:reddit.com/r/UniUK {university} {course}"
"site:reddit.com {university} {department} teaching"
```
**Recency rule:** Reddit posts include dates. Tavily snippets sometimes
include the post date. If a date is visible and older than 18 months,
discard. If no date is visible in the snippet, attempt `fetch_page` on the
thread URL — if date still cannot be confirmed, discard.

---

### Source Coverage Summary

| Source | Platform type | Candour level | Recency window | Weighting |
|---|---|---|---|---|
| The Student Room | Open forum | High | 18 months | Primary |
| StudentCrowd | Structured review | Medium-High | 18 months | Primary |
| WhatUni | Structured review | Medium-High | 18 months | Primary |
| Unibuddy | Ambassador blog/Q&A | Medium (ambassador-selected) | 18 months | Corroborating only |
| Prospects.ac.uk | Graduate profiles | Medium | 24 months | Corroborating, career-outcomes only |
| Reddit | Open forum | Highest | 18 months | Primary (especially for concerns) |

A finding qualifies for output only if it is corroborated by **3 or more
independent sources**, of which **at least 2 must be on different platforms**.
Three TSR posts from the same thread do not constitute 3 independent sources.
Three separate TSR threads do — they are independent posts, but only count
as one platform toward the 2-platform minimum.

---

## 1f.2 `schemas/outputs/forum_output.py`

`ForumOutput` is the typed result `ForumAgent` writes to `board.forum`.
The schema enforces the corroboration rule structurally — every finding
carries its source list and source count, making it impossible to output
an uncorroborated finding without the validator catching it.

```python
# schemas/outputs/forum_output.py
from __future__ import annotations

from pydantic import BaseModel, field_validator
from typing import Literal


class ForumSource(BaseModel):
    url:         str   # full URL of the specific page or thread
    platform:    str   # one of: "thestudentroom", "studentcrowd", "whatuni",
                       #         "unibuddy", "prospects", "reddit"
    date_str:    str   # ISO date string or "YYYY-MM" if exact date unavailable
    poster_type: str   # "current_student" | "graduate" | "ambassador" | "unknown"
    snippet:     str   # verbatim 1–2 sentence extract used as evidence
                       # (internal use only — not rendered in report)


class ForumFinding(BaseModel):
    theme:          str              # one-line label, e.g. "Responsive lecturers"
    summary:        str              # paraphrased synthesis — never verbatim quote
    sentiment:      Literal["positive", "negative", "mixed"]
    source_count:   int              # total number of sources corroborating this finding
    platform_count: int              # number of distinct platforms represented
    sources:        list[ForumSource]

    @field_validator("source_count")
    @classmethod
    def minimum_three_sources(cls, v: int) -> int:
        if v < 3:
            raise ValueError(
                f"source_count must be >= 3 to qualify as a finding (got {v}). "
                "Do not include findings that cannot be corroborated across 3 "
                "independent sources."
            )
        return v

    @field_validator("platform_count")
    @classmethod
    def minimum_two_platforms(cls, v: int) -> int:
        if v < 2:
            raise ValueError(
                f"platform_count must be >= 2 (got {v}). "
                "A finding must be corroborated across at least 2 different platforms."
            )
        return v


class ForumOutput(BaseModel):
    recurring_positives:  list[ForumFinding]   # things consistently praised
    recurring_concerns:   list[ForumFinding]   # things consistently criticised
    department_feedback:  list[ForumFinding]   # course/department-specific feedback
                                               # (teaching, modules, workload, staff)
    sources_searched:     list[str]            # all platforms attempted, regardless of yield
    sources_yielded:      list[str]            # platforms that returned qualifying content
    staleness_discards:   int                  # count of results discarded for being outside window
    scope_discards:       int                  # count of results discarded as off-topic
    confidence:           Literal["high", "medium", "low"]
    notes:                str                  # empty string if no edge cases; otherwise explain
```

**Why `source_count` and `platform_count` are validated on the model:**
The LLM cannot be fully trusted to enforce its own corroboration rules.
Schema-level validators catch any finding that slips through with fewer than
3 sources or only 1 platform — pydantic raises `ValidationError` before the
output reaches the blackboard. The agent catches this and retries or falls
back to `confidence: "low"`.

**Why `snippet` is on `ForumSource` rather than on `ForumFinding`:**
Each source may support multiple findings. The snippet is the raw evidence
at the source level — the summary on `ForumFinding` is the synthesised
interpretation across all sources. Keeping them separate prevents the LLM
from conflating a single post's words with a cross-platform consensus.

**Why `sources_searched` and `sources_yielded` are on the output:**
`ScoringAgent` and `ReportGenerator` need to know which platforms were
attempted. If Tavily returned no qualifying content from StudentCrowd for a
niche course, that is a data gap — not a sign that students have no opinions.
The report renders this gap explicitly rather than silently omitting it.

**Why `staleness_discards` and `scope_discards` are counted:**
These counters make the agent's filtering work auditable. If `staleness_discards`
is 0 for a well-known university, the LLM probably did not verify dates.
If `scope_discards` is 0 for a university with a large general student forum
presence, the LLM probably kept off-topic content. Non-zero values confirm
the filtering instructions were followed.

---

## 1f.3 `skills/forum/SKILL.md`

This file is the core of `ForumAgent`. The Python class is structural
scaffolding. The SKILL.md is the research brain. Every decision about what
to search, what to accept, what to reject, and how to synthesise lives here.
Tuning `ForumAgent` means editing this file, not touching Python.

```markdown
---
key: forum
name: Forum Research Agent
description: Researches candid student experience for the specific course and department across 6 designated student forum and review platforms.
tool_budget: 14
section_name: forum
---

You are the Forum Research Agent. Your job is to find what current students
and recent graduates actually say about the specific course at the specific
university — not what the university says about itself.

You have access to `board.career` (via deps.board.career) which contains
the career paths and context for this course. You may use this to scope
your searches to the correct department and discipline.

## The Corroboration Rule — Read This First

A finding only qualifies for output if it is supported by **3 or more
independent sources**, of which **at least 2 are on different platforms**.

Independent means: different posts, different threads, different reviews —
not multiple replies in the same thread. Three replies in one TSR thread
are one source. Three separate TSR threads are three sources but only one
platform.

If you cannot corroborate a finding to this standard, do not include it.
A shorter output with high-confidence findings is better than a long output
padded with anecdote.

## The Recency Rule — Read This Second

Discard any content where the post, review, or profile date is older than
18 months from today. The one exception is Prospects.ac.uk graduate profiles,
where the window is 24 months.

Tavily's `days=730` filter reduces stale results at the query level but
does not eliminate them. Forum threads started years ago may still rank in
Tavily results if they received recent replies. You must verify dates at the
content level after fetching.

When you call `fetch_page` on a TSR thread or Reddit post, check the dates
of individual posts visible on the page. If the most recent substantive post
(more than one sentence) is older than 18 months, discard the entire thread.
Count each discarded result in `staleness_discards`.

## The Scope Rule — Read This Third

Only content that explicitly references the researched course, department,
or specific modules qualifies. Discard anything that does not name the
course or department — even if it is about the same university.

Acceptable scope: "The Computer Science lecturers at Manchester are
generally approachable", "the algorithms module in year 2 is intense",
"the CS department at [university] has good industry links".

Out of scope: "Manchester is a great city", "the library is always busy",
"student union events are fun", "accommodation is expensive" — discard
all of these. Count each in `scope_discards`.

## Poster Credibility — Read This Fourth

Weight content by poster type:

- **current_student** — highest weight. Direct, present-tense experience.
  Look for phrases like "I'm in second year", "this year we had", "my
  lecturer said". Classify as current_student.
- **graduate** — high weight for retrospective course assessment.
  Look for "when I was at [university]", "I graduated last year",
  "looking back on my degree". Classify as graduate.
- **ambassador** — medium weight, corroborating only. Unibuddy contributors
  are university-selected. Their content leans positive by design.
  Never use an ambassador post as the sole source for a positive finding.
  Classify as ambassador.
- **unknown** — low weight. Include only if the content is specific enough
  to be credible and it is corroborated by higher-credibility sources.
  Classify as unknown.

Discard: prospective applicants asking about entry requirements, grade
predictions, general "is this uni good?" questions with no substantive
answer from a current student or graduate.

## Research Strategy — Six Sources in Order

Work through all six sources. Allocate your tool budget proportionally —
do not exhaust it on TSR alone. Aim for at least 2 Tavily queries and
1–2 `fetch_page` calls per source.

### Step 1 — The Student Room (TSR)
Query patterns (run 2–3 of these, not all):
- `"{university} {course} student experience" site:thestudentroom.co.uk`
- `"{university} {course} teaching quality lecturers" site:thestudentroom.co.uk`
- `"{university} {course} first year second year modules" site:thestudentroom.co.uk`
- `"{university} {department} what is it like" site:thestudentroom.co.uk`

For any URL returned by Tavily:
- Call `fetch_page` to retrieve the thread content.
- Read the page, check dates of individual posts.
- Extract only posts from current students or graduates dated within 18 months.
- Discard applicant posts, one-liners, and off-topic replies.

### Step 2 — StudentCrowd
Query patterns (run 1–2):
- `"{university} {course} reviews" site:studentcrowd.com`
- `"{university} {course} teaching" site:studentcrowd.com`

Fetch the review page. Extract reviews with visible dates within 18 months.
Discard reviews shorter than 2 sentences — they carry no actionable signal.

### Step 3 — WhatUni
Query patterns (run 1–2):
- `"{university} {course} review" site:whatuni.com`
- `"{university} {course} student review" site:whatuni.com`

Fetch the review page. Extract course-specific reviews dated within 18 months.
Focus on "course content" and "teaching quality" categories if visible.

### Step 4 — Unibuddy
Query patterns (run 1):
- `"{university} {course} student blog modules" site:unibuddy.com`

Unibuddy posts are often undated. If no date is visible after fetching,
discard. Use Unibuddy content for corroboration only — never as a primary
source for any finding, positive or negative.

### Step 5 — Prospects.ac.uk
Query patterns (run 1):
- `"{university} {course} graduate profile" site:prospects.ac.uk`

Extract graduate profiles that name the specific university and course.
Use for retrospective course-value and career-outcome corroboration.
Recency window: 24 months for this source only.

### Step 6 — Reddit
Query patterns (run 2–3):
- `"{university} {course} experience reddit"`
- `"site:reddit.com/r/UniUK {university} {course}"`
- `"site:reddit.com {university} {department} honest review"`

Reddit snippets from Tavily are often partial. For any high-signal snippet,
fetch the thread URL to retrieve fuller context. Verify post dates.
If date is unverifiable, discard.

## Budget Allocation

Your tool budget is 14. Allocate as follows:

| Source | Tavily queries | fetch_page calls | Total |
|---|---|---|---|
| TSR | 3 | 2 | 5 |
| StudentCrowd | 1 | 1 | 2 |
| WhatUni | 1 | 1 | 2 |
| Unibuddy | 1 | 0–1 | 1–2 |
| Prospects | 1 | 0–1 | 1–2 |
| Reddit | 2 | 1 | 3 |

`fetch_page` calls do not count against your budget (they are targeted
retrieval, not searches). The 14-call budget covers Tavily calls only.
Adjust proportionally if a source yields nothing after 1 query — do not
waste further calls on a dry source.

## Synthesising Findings

After collecting raw content, synthesise into `ForumFinding` entries:

1. Group raw observations by theme — "lecturer quality", "workload",
   "module content", "industry links", "pastoral support", etc.
2. For each theme, count independent sources and distinct platforms.
3. If a theme has 3+ sources across 2+ platforms, it qualifies.
4. Write `summary` as a paraphrased synthesis — never copy verbatim text.
   The summary must be your synthesis, not a quote.
5. Assign `sentiment`: positive if the finding is consistently favourable;
   negative if consistently critical; mixed if sources conflict.
6. Assign the finding to the correct output list:
   - General praise/criticism → `recurring_positives` or `recurring_concerns`
   - Department/course/module/teaching specific → `department_feedback`

## Confidence Assignment

- `"high"`: 4+ sources per qualifying finding, coverage from 4+ platforms,
  both positives and concerns found.
- `"medium"`: 3 sources per finding, coverage from 2–3 platforms, either
  positives or concerns found but not both.
- `"low"`: fewer than 3 sources for most findings, coverage from 1–2
  platforms, or the course is niche and forum presence is sparse.

## Edge Cases

**Niche or small course:**
Some courses have very little forum presence. If you exhaust your budget
and cannot reach 3-source corroboration for any finding, return empty lists
with `confidence: "low"` and explain in `notes`. Do not invent findings.

**University in a non-UK country:**
TSR, StudentCrowd, and WhatUni are predominantly UK-focused. For non-UK
universities, prioritise Reddit and Prospects, and search for country-
appropriate equivalents (e.g. for Australian universities:
`site:reddit.com/r/AusUni`). Note the reduced platform coverage in `notes`.

**Thread dominated by a single controversial event:**
If the majority of recent posts are about a specific event (strike, scandal,
campus closure) rather than ongoing course experience, note this in `notes`
and do not present event-driven sentiment as a recurring finding unless it
is course-relevant and persistent.

**Conflicting signals between platforms:**
If TSR is predominantly negative and WhatUni is predominantly positive for
the same theme, do not average them. Report the conflict in `department_feedback`
as a `mixed` sentiment finding and list sources from both sides.
```

---

## 1f.4 `agents/forum_agent.py`

`ForumAgent` follows the identical structural pattern as all section agents
from Stage 1d onward. The differences from earlier agents are:
- It reads `board.career` at the start of `handle()` to scope queries.
- Its tool budget is higher (14 vs 6 for CareerAgent).
- Its `task_brief` includes career context extracted from the blackboard.

`tavily_search` and `fetch_page` are imported from `tools/` and registered
directly on the Agent. No wrapper. No closure. No method on the class.

```python
# agents/forum_agent.py
from __future__ import annotations

import logging
from datetime import datetime

from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.deps import Deps
from core.llm_factory import get_model
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.messages.section_completed import SectionCompletedMessage
from schemas.messages.section_failed import SectionFailedMessage
from schemas.outputs.forum_output import ForumOutput
from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search

logger = logging.getLogger("forum_agent")


class ForumAgent(BaseAgent):
    """Phase 2 section agent. Runs concurrently with 6 other section agents.

    Subscribes to: CareerResearchCompletedMessage
    Reads:         board.career (for career path context to scope queries)
    Writes to:     board.forum (ForumOutput)
    Fires:         SectionCompletedMessage(section_name="forum") on success
                   SectionFailedMessage(section_name="forum") on failure

    Tools: tavily_search, fetch_page — registered directly, no wrappers.
    """

    def __init__(self, instructions: str = "", tool_budget: int = 14) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=ForumOutput,
            system_prompt=self.get_instruction(),
            tools=[tavily_search, fetch_page],
        )

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.career_completed import CareerResearchCompletedMessage

        async def handler(message: CareerResearchCompletedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(CareerResearchCompletedMessage, handler)

    def get_instruction(self) -> str:
        base = """
            You are the Forum Research Agent in a university research pipeline.

            Your job: search for candid student experience content about the specific
            course at the specific university across 6 designated forum and review
            platforms. You apply strict recency, scope, and corroboration rules before
            including any finding in your output.

            Pipeline role:
            - You run concurrently with 6 other section agents after CareerAgent completes.
            - You subscribe to CareerResearchCompletedMessage.
            - You read deps.board.career to get career context for query scoping.
            - You write your findings to deps.board.forum as a ForumOutput.
            - You fire SectionCompletedMessage(section_name="forum") on success.
            - You fire SectionFailedMessage(section_name="forum") on any exception.
            - You must always fire one of these two messages — even if output is low
              confidence. Failing to fire either message stalls the scoring gate.

            Context you receive (from deps.context):
            - university_name: the university being researched
            - intended_course: the undergraduate course
            - country: the university's country
            - study_level: always "undergraduate"

            Blackboard data available to you:
            - deps.board.career: CareerOutput — read this for career paths and
              department context to scope your forum queries.

            Tool usage rules:
            - Use tavily_search for all platform queries.
            - Use fetch_page to retrieve full thread or review page content after
              Tavily returns a URL.
            - Never pass site: prefixed queries to tavily_search — Tavily does not
              honour time_range on site: queries. Use tavily_search to find URLs,
              then fetch_page those URLs to retrieve and date-verify content.
        """.strip()

        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def reset(self) -> None:
        """Reset per-request state. Called by ResearchHandler before each request."""
        pass

    # ── Core handler ─────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        """Run forum research and fire SectionCompleted or SectionFailed."""
        logger.info(
            "forum_agent | starting — university=%r course=%r",
            deps.context.university_name,
            deps.context.intended_course,
        )

        await deps.hub.publish(ProgressUpdateMessage(
            status="started",
            message=f"Researching student forum experience for {deps.context.intended_course}…",
            triggered_by="forum_agent",
            timestamp=datetime.now().isoformat(),
        ))

        if deps.board.career is not None:
            paths = [p.title for p in deps.board.career.career_paths]
            career_context = (
                f"Career paths for this course: {', '.join(paths)}. "
                f"Use these to scope department references in your queries."
            )
        else:
            career_context = (
                "Career data is unavailable. Scope queries to the course name "
                "and department name only."
            )

        task_brief = f"""
                    University: {deps.context.university_name}
                    Course: {deps.context.intended_course}
                    Country: {deps.context.country}
                    Study level: {deps.context.study_level}

                    Career context (from board.career):
                    {career_context}

                    Search all 6 designated forum sources as instructed. Apply the recency,
                    scope, and corroboration rules strictly. Return a ForumOutput.
                """.strip()

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.forum = result.output

            logger.info(
                "forum_agent | completed — positives=%d concerns=%d "
                "department_feedback=%d confidence=%s platforms=%s",
                len(result.output.recurring_positives),
                len(result.output.recurring_concerns),
                len(result.output.department_feedback),
                result.output.confidence,
                result.output.sources_yielded,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message=(
                    f"Forum research complete — "
                    f"{len(result.output.recurring_positives)} positives, "
                    f"{len(result.output.recurring_concerns)} concerns found."
                ),
                triggered_by="forum_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionCompletedMessage(
                section_name="forum",
                triggered_by="forum_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            logger.error("forum_agent | failed: %s", exc)

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Forum research failed: {exc}",
                triggered_by="forum_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="forum",
                reason=str(exc),
                triggered_by="forum_agent",
                timestamp=datetime.now().isoformat(),
            ))
```

**Why `board.career` is read before building the task brief:**
`board.career` has already mapped the course to specific career paths — this
lets the LLM construct more precise department-scoped queries without burning
extra tool calls on broad searches.

**Why `SectionFailedMessage` always fires on exception:**
The quorum gate in `ScoringAgent` counts both completed and failed messages.
If neither fires, the gate never opens and the pipeline deadlocks.

---

## 1f.5 `services/research_handler.py` — Simulation with two agents (CareerAgent and ForumAgent)

Add `ForumAgent` to the handler. At Stage 1f, all seven section agents are
registered and will run concurrently when `CareerResearchCompletedMessage`
fires.

```python
# services/research_handler.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.blackboard import Blackboard
from core.deps import Deps, ResearchContext
from core.message_hub import MessageHub
from core.skill_loader import scan_skills_dir, SkillMeta
from agents.career_agent import CareerAgent
from agents.forum_agent import ForumAgent
from schemas.messages.research_requested import ResearchRequestedMessage
from schemas.messages.career_completed import CareerResearchCompletedMessage

logger = logging.getLogger("research_handler")


@dataclass
class _EmptySkill:
    instructions: str = ""
    tool_budget: int = 0

_EMPTY = _EmptySkill()


class ResearchHandler:
    def __init__(self) -> None:
        skills = scan_skills_dir(Path("skills"))

        def _get(key: str) -> SkillMeta | _EmptySkill:
            skill = skills.get(key)
            if skill is None:
                logger.warning("research_handler | no SKILL.md for %r — agent uses base prompt", key)
            return skill or _EMPTY

        # -- initialize all agents
        self._career_agent = CareerAgent(
            instructions=_get("career").instructions,
            tool_budget=_get("career").tool_budget or 6,
        )
        self._forum_agent = ForumAgent(
            instructions=_get("forum").instructions,
            tool_budget=_get("forum").tool_budget or 14,
        )

        logger.info("research_handler | CareerAgent and ForumAgent constructed")

    async def handle_request(
        self,
        university_name: str,
        intended_course: str,
        country: str,
    ) -> Blackboard:
        hub     = MessageHub()
        board   = Blackboard()
        context = ResearchContext(
            university_name=university_name,
            intended_course=intended_course,
            country=country,
        )
        deps = Deps(hub=hub, board=board, context=context)

        self._career_agent.reset()
        self._forum_agent.reset()

        # --- OPTION 1
        # -- Phase 1 — CareerAgent runs on the initial trigger
        hub.subscribe(ResearchRequestedMessage, self._career_agent.handle)
        # -- Phase 2 — ForumAgent runs after career completes
        hub.subscribe(CareerResearchCompletedMessage, self._forum_agent.handle)

        # # --- OPTION 2
        # # Phase 1 - CareerAgent subscribes to ResearchRequestedMessage — runs first
        # self._career_agent.subscribe(hub, deps)
        # # Phase 2 - ForumAgent subscribes to CareerResearchCompletedMessage — runs after career
        # self._forum_agent.subscribe(hub, deps)

        # --- s t a r t ---
        await hub.publish(ResearchRequestedMessage(
            university_name=university_name,
            intended_course=intended_course,
            country=country,
            triggered_by="research_handler",
            timestamp=datetime.now().isoformat(),
        ))

        return board
```

**Why `tool_budget` defaults to 14 if skill is missing:**
ForumAgent must search 6 platforms — a lower budget (e.g. 6, same as
CareerAgent) would mean only 1 Tavily query per platform with no room for
follow-up. 14 is the minimum for useful multi-platform coverage. The default
is a safeguard, not a substitute for having the SKILL.md present.

---

## 1f.6 `main.py` — Simulation with two agents (CareerAgent and ForumAgent)

Add `board.forum` to the stdout output block alongside the existing board
fields from prior stages.

```python
# main.py
from __future__ import annotations

import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

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
            logger.error("main | board.career is None — CareerAgent failed")
        else:
            logger.info("main | board.career populated")
            print("\n── board.career ──────────────────────────────────────────")
            print(board.career.model_dump_json(indent=2))

        if board.forum is None:
            logger.error("main | board.forum is None — ForumAgent failed")
        else:
            logger.info("main | board.forum populated")
            print("\n── board.forum ───────────────────────────────────────────")
            print(board.forum.model_dump_json(indent=2))

    finally:
        await fetch_client.shutdown()


if __name__ == "__main__":
    asyncio.run(run(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    ))
```

---

## 1f.7 `schemas/messages/` — No New Messages Required

`ForumAgent` fires `SectionCompletedMessage` and `SectionFailedMessage` —
both already exist from Stage 1a. Confirm:
- `SectionCompletedMessage` has `section_name: str`
- `SectionFailedMessage` has `section_name: str` and `reason: str`
- Both are subclasses of `BaseMessage` with `triggered_by` and `timestamp`

No new message schema is needed at Stage 1f.

---

## 1f.8 Tests — `tests/test_stage_1f.py`

```python
# tests/test_stage_1f.py
"""
Stage 1f tests — ForumAgent end-to-end.
Run with: pytest tests/test_stage_1f.py -v -s

Real LLM + real Tavily calls. Requires:
  - TAVILY_API_KEY in .env
  - OPENROUTER_API_KEY in .env
  - RESEARCH_MODEL in .env

The fetch_server fixture starts FetchClient for tests that call fetch_page.
"""
from __future__ import annotations

import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from dotenv import load_dotenv
load_dotenv()

from mcp.fetch_client import fetch_client


@pytest.fixture(scope="module")
async def fetch_server():
    await fetch_client.startup()
    yield
    await fetch_client.shutdown()


# ── Schema ────────────────────────────────────────────────────────────────────

def test_forum_output_imports_cleanly() -> None:
    from schemas.outputs.forum_output import (
        ForumOutput, ForumFinding, ForumSource
    )
    assert ForumOutput
    assert ForumFinding
    assert ForumSource


def test_forum_output_requires_confidence_and_sources() -> None:
    from schemas.outputs.forum_output import ForumOutput
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        ForumOutput()


def test_forum_finding_rejects_fewer_than_three_sources() -> None:
    """schema-level validator must reject source_count < 3."""
    from schemas.outputs.forum_output import ForumFinding, ForumSource
    import pydantic
    source = ForumSource(
        url="https://thestudentroom.co.uk/test",
        platform="thestudentroom",
        date_str="2025-01-01",
        poster_type="current_student",
        snippet="Test snippet.",
    )
    with pytest.raises(pydantic.ValidationError):
        ForumFinding(
            theme="Test",
            summary="Test summary",
            sentiment="positive",
            source_count=2,         # below minimum — must raise
            platform_count=2,
            sources=[source, source],
        )


def test_forum_finding_rejects_single_platform() -> None:
    """platform_count < 2 must raise ValidationError."""
    from schemas.outputs.forum_output import ForumFinding, ForumSource
    import pydantic
    source = ForumSource(
        url="https://thestudentroom.co.uk/test",
        platform="thestudentroom",
        date_str="2025-01-01",
        poster_type="current_student",
        snippet="Test snippet.",
    )
    with pytest.raises(pydantic.ValidationError):
        ForumFinding(
            theme="Test",
            summary="Test summary",
            sentiment="positive",
            source_count=3,
            platform_count=1,       # below minimum — must raise
            sources=[source, source, source],
        )


def test_forum_finding_accepts_valid_finding() -> None:
    """A finding with 3 sources across 2 platforms must pass validation."""
    from schemas.outputs.forum_output import ForumFinding, ForumSource
    s1 = ForumSource(
        url="https://thestudentroom.co.uk/test1",
        platform="thestudentroom",
        date_str="2025-01-01",
        poster_type="current_student",
        snippet="Good lectures.",
    )
    s2 = ForumSource(
        url="https://thestudentroom.co.uk/test2",
        platform="thestudentroom",
        date_str="2025-02-01",
        poster_type="current_student",
        snippet="Staff are helpful.",
    )
    s3 = ForumSource(
        url="https://studentcrowd.com/test",
        platform="studentcrowd",
        date_str="2025-03-01",
        poster_type="current_student",
        snippet="Great department.",
    )
    finding = ForumFinding(
        theme="Responsive staff",
        summary="Students consistently describe staff as approachable.",
        sentiment="positive",
        source_count=3,
        platform_count=2,
        sources=[s1, s2, s3],
    )
    assert finding.theme == "Responsive staff"


# ── Skill loader ──────────────────────────────────────────────────────────────

def test_forum_skill_loads() -> None:
    from pathlib import Path
    from core.skill_loader import load_skill
    skill = load_skill(Path("skills/forum/SKILL.md"))
    assert skill is not None, "skills/forum/SKILL.md missing or malformed"
    assert skill.key == "forum"
    assert skill.tool_budget >= 10, "ForumAgent tool_budget must be >= 10"
    assert skill.section_name == "forum"
    assert len(skill.instructions) > 500, "SKILL.md body seems too short"


def test_forum_skill_contains_all_six_sources() -> None:
    """SKILL.md must reference all 6 designated forum sources."""
    from pathlib import Path
    from core.skill_loader import load_skill
    skill = load_skill(Path("skills/forum/SKILL.md"))
    assert skill is not None
    body = skill.instructions.lower()
    for source in [
        "thestudentroom",
        "studentcrowd",
        "whatuni",
        "unibuddy",
        "prospects",
        "reddit",
    ]:
        assert source in body, f"SKILL.md does not mention source: {source}"


def test_forum_skill_contains_recency_rule() -> None:
    """SKILL.md must specify the 18-month recency rule."""
    from pathlib import Path
    from core.skill_loader import load_skill
    skill = load_skill(Path("skills/forum/SKILL.md"))
    assert skill is not None
    assert "18" in skill.instructions, "SKILL.md must specify 18-month recency window"


def test_forum_skill_contains_corroboration_rule() -> None:
    """SKILL.md must specify the 3-source corroboration rule."""
    from pathlib import Path
    from core.skill_loader import load_skill
    skill = load_skill(Path("skills/forum/SKILL.md"))
    assert skill is not None
    assert "3" in skill.instructions
    assert "corrobor" in skill.instructions.lower()


# ── Agent construction ────────────────────────────────────────────────────────

def test_forum_agent_constructs() -> None:
    from agents.forum_agent import ForumAgent
    agent = ForumAgent(instructions="test instructions", tool_budget=14)
    assert agent._tool_budget == 14
    assert agent._calls_made  == 0
    assert agent._agent is not None


def test_forum_agent_default_budget_is_14() -> None:
    from agents.forum_agent import ForumAgent
    agent = ForumAgent()
    assert agent._tool_budget == 14


def test_forum_agent_reset_clears_calls_made() -> None:
    from agents.forum_agent import ForumAgent
    agent = ForumAgent(tool_budget=14)
    agent._calls_made = 10
    agent.reset()
    assert agent._calls_made == 0


def test_get_instruction_includes_skill_body() -> None:
    from agents.forum_agent import ForumAgent
    agent = ForumAgent(instructions="FORUM_SKILL_MARKER")
    prompt = agent.get_instruction()
    assert "FORUM_SKILL_MARKER" in prompt
    assert "Forum Research Agent" in prompt


def test_get_instruction_includes_site_query_warning() -> None:
    from agents.forum_agent import ForumAgent
    agent = ForumAgent()
    prompt = agent.get_instruction()
    assert "site:" in prompt
    assert "fetch_page" in prompt


def test_get_instruction_mentions_career_blackboard() -> None:
    """System prompt must tell the LLM to read board.career for scoping."""
    from agents.forum_agent import ForumAgent
    agent = ForumAgent()
    prompt = agent.get_instruction()
    assert "board.career" in prompt


# ── Budget enforcement ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forum_search_budget_exhausted_returns_error_dict() -> None:
    from agents.forum_agent import ForumAgent
    agent = ForumAgent(tool_budget=3)
    agent._calls_made = 3
    tool = agent._make_search_tool()
    ctx = MagicMock()
    raw = await tool(ctx, "test query")
    result = json.loads(raw)
    assert result["error"] == "tool budget exhausted"
    assert result["calls_made"] == 3
    assert result["budget"] == 3


@pytest.mark.asyncio
async def test_forum_search_tool_increments_counter() -> None:
    from agents.forum_agent import ForumAgent
    agent = ForumAgent(tool_budget=14)
    tool = agent._make_search_tool()
    ctx = MagicMock()
    with patch("tools.search_tool.tavily_search",
               new=AsyncMock(return_value='{"query":"q","results":[]}')):
        await tool(ctx, "query one")
        await tool(ctx, "query two")
        await tool(ctx, "query three")
    assert agent._calls_made == 3


# ── Hub subscription ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forum_agent_subscribes_to_career_completed() -> None:
    """ForumAgent must subscribe to CareerResearchCompletedMessage, not ResearchRequestedMessage."""
    from agents.forum_agent import ForumAgent
    from core.message_hub import MessageHub
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from schemas.messages.career_completed import CareerResearchCompletedMessage

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

    called = []
    agent = ForumAgent(tool_budget=1)
    async def mock_handle(msg, d): called.append(msg)
    agent.handle = mock_handle

    agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test",
        timestamp=datetime.now().isoformat(),
    ))

    assert len(called) == 1


@pytest.mark.asyncio
async def test_forum_agent_does_not_subscribe_to_research_requested() -> None:
    """ForumAgent must NOT fire on ResearchRequestedMessage — that is CareerAgent's trigger."""
    from agents.forum_agent import ForumAgent
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
            university_name="University of Manchester",
            intended_course="Computer Science",
            country="UK",
        ),
    )

    called = []
    agent = ForumAgent(tool_budget=1)
    async def mock_handle(msg, d): called.append(msg)
    agent.handle = mock_handle

    agent.subscribe(hub, deps)

    await hub.publish(ResearchRequestedMessage(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
        triggered_by="test",
        timestamp=datetime.now().isoformat(),
    ))

    assert len(called) == 0, "ForumAgent must not respond to ResearchRequestedMessage"


# ── Section message firing ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forum_agent_fires_section_completed_on_success(fetch_server) -> None:
    """On successful handle(), SectionCompletedMessage with section_name='forum' must fire."""
    from agents.forum_agent import ForumAgent
    from core.message_hub import MessageHub
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from schemas.messages.career_completed import CareerResearchCompletedMessage
    from schemas.messages.section_completed import SectionCompletedMessage

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
    async def capture(msg): fired.append(msg)
    hub.subscribe(SectionCompletedMessage, capture)

    agent = ForumAgent(tool_budget=14)
    agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test",
        timestamp=datetime.now().isoformat(),
    ))

    assert len(fired) == 1
    assert isinstance(fired[0], SectionCompletedMessage)
    assert fired[0].section_name == "forum"


@pytest.mark.asyncio
async def test_forum_agent_fires_section_failed_on_exception() -> None:
    """If handle() raises, SectionFailedMessage must fire — pipeline must not deadlock."""
    from agents.forum_agent import ForumAgent
    from core.message_hub import MessageHub
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from schemas.messages.career_completed import CareerResearchCompletedMessage
    from schemas.messages.section_failed import SectionFailedMessage

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
    async def capture(msg): fired.append(msg)
    hub.subscribe(SectionFailedMessage, capture)

    agent = ForumAgent(tool_budget=14)

    async def exploding_run(*args, **kwargs):
        raise RuntimeError("simulated LLM failure")

    agent._agent.run = exploding_run
    agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test",
        timestamp=datetime.now().isoformat(),
    ))

    assert len(fired) == 1
    assert isinstance(fired[0], SectionFailedMessage)
    assert fired[0].section_name == "forum"


# ── Career context reading ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forum_agent_uses_career_context_when_available() -> None:
    """handle() must include career path names in task_brief when board.career is populated."""
    from agents.forum_agent import ForumAgent
    from core.message_hub import MessageHub
    from core.blackboard import Blackboard
    from core.deps import Deps, ResearchContext
    from schemas.messages.career_completed import CareerResearchCompletedMessage
    from schemas.outputs.career_output import CareerOutput, CareerPath, SalaryRange, CareerSource

    hub   = MessageHub()
    board = Blackboard()

    # Populate board.career with a minimal valid CareerOutput
    board.career = CareerOutput(
        career_paths=[
            CareerPath(title="Software Engineer", description="Builds software",
                       typical_companies=["Google"]),
        ],
        salary_ranges=[
            SalaryRange(career_path="Software Engineer", entry_level="£28k",
                        mid_level="£45k", senior_level="£70k",
                        currency="GBP", country="UK"),
        ],
        job_postings=[],
        in_demand_skills=["Python"],
        country_scope="UK",
        confidence="high",
        sources=[CareerSource(url="https://example.com", date="2025-01-01",
                              type="salary_survey")],
        notes="",
    )

    deps  = Deps(
        hub=hub,
        board=board,
        context=ResearchContext(
            university_name="University of Manchester",
            intended_course="Computer Science",
            country="UK",
        ),
    )

    captured_briefs = []

    async def mock_run(task_brief, deps):
        captured_briefs.append(task_brief)
        raise RuntimeError("stop after capturing brief")

    agent = ForumAgent(tool_budget=14)
    agent._agent.run = mock_run
    agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test",
        timestamp=datetime.now().isoformat(),
    ))

    assert len(captured_briefs) == 1
    assert "Software Engineer" in captured_briefs[0]


# ── LLM integration (real API call) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_forum_agent_populates_board_forum(fetch_server) -> None:
    """Full end-to-end: real Tavily + real LLM. Confirms board.forum populated."""
    from services.research_handler import ResearchHandler

    handler = ResearchHandler()
    board = await handler.handle_request(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    )

    assert board.forum is not None, "board.forum is None — ForumAgent failed"
    assert isinstance(board.forum.recurring_positives, list)
    assert isinstance(board.forum.recurring_concerns, list)
    assert isinstance(board.forum.department_feedback, list)
    assert board.forum.confidence in ("high", "medium", "low")
    assert len(board.forum.sources_searched) > 0
    assert board.forum.staleness_discards >= 0
    assert board.forum.scope_discards >= 0


@pytest.mark.asyncio
async def test_forum_agent_sources_include_multiple_platforms(fetch_server) -> None:
    """For a well-known university, sources should span at least 2 platforms."""
    from services.research_handler import ResearchHandler

    handler = ResearchHandler()
    board = await handler.handle_request(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    )

    assert board.forum is not None
    all_findings = (
        board.forum.recurring_positives
        + board.forum.recurring_concerns
        + board.forum.department_feedback
    )
    if all_findings:
        platforms = set()
        for finding in all_findings:
            for source in finding.sources:
                platforms.add(source.platform)
        assert len(platforms) >= 2, (
            f"Expected findings from >= 2 platforms, got: {platforms}"
        )


@pytest.mark.asyncio
async def test_forum_agent_findings_meet_corroboration_threshold(fetch_server) -> None:
    """All findings in output must have source_count >= 3 and platform_count >= 2."""
    from services.research_handler import ResearchHandler

    handler = ResearchHandler()
    board = await handler.handle_request(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    )

    assert board.forum is not None
    all_findings = (
        board.forum.recurring_positives
        + board.forum.recurring_concerns
        + board.forum.department_feedback
    )
    for finding in all_findings:
        assert finding.source_count >= 3, (
            f"Finding '{finding.theme}' has source_count={finding.source_count} — "
            f"below the 3-source minimum"
        )
        assert finding.platform_count >= 2, (
            f"Finding '{finding.theme}' has platform_count={finding.platform_count} — "
            f"must span >= 2 platforms"
        )
```

---

## 1f.9 Run the Tests

```bash
pytest tests/test_stage_1f.py -v -s
```

Expected output on clean pass:

```
tests/test_stage_1f.py::test_forum_output_imports_cleanly PASSED
tests/test_stage_1f.py::test_forum_output_requires_confidence_and_sources PASSED
tests/test_stage_1f.py::test_forum_finding_rejects_fewer_than_three_sources PASSED
tests/test_stage_1f.py::test_forum_finding_rejects_single_platform PASSED
tests/test_stage_1f.py::test_forum_finding_accepts_valid_finding PASSED
tests/test_stage_1f.py::test_forum_skill_loads PASSED
tests/test_stage_1f.py::test_forum_skill_contains_all_six_sources PASSED
tests/test_stage_1f.py::test_forum_skill_contains_recency_rule PASSED
tests/test_stage_1f.py::test_forum_skill_contains_corroboration_rule PASSED
tests/test_stage_1f.py::test_forum_agent_constructs PASSED
tests/test_stage_1f.py::test_forum_agent_default_budget_is_14 PASSED
tests/test_stage_1f.py::test_forum_agent_reset_clears_calls_made PASSED
tests/test_stage_1f.py::test_get_instruction_includes_skill_body PASSED
tests/test_stage_1f.py::test_get_instruction_includes_site_query_warning PASSED
tests/test_stage_1f.py::test_get_instruction_mentions_career_blackboard PASSED
tests/test_stage_1f.py::test_forum_search_budget_exhausted_returns_error_dict PASSED
tests/test_stage_1f.py::test_forum_search_tool_increments_counter PASSED
tests/test_stage_1f.py::test_forum_agent_subscribes_to_career_completed PASSED
tests/test_stage_1f.py::test_forum_agent_does_not_subscribe_to_research_requested PASSED
tests/test_stage_1f.py::test_forum_agent_fires_section_completed_on_success PASSED
tests/test_stage_1f.py::test_forum_agent_fires_section_failed_on_exception PASSED
tests/test_stage_1f.py::test_forum_agent_uses_career_context_when_available PASSED
tests/test_stage_1f.py::test_forum_agent_populates_board_forum PASSED
tests/test_stage_1f.py::test_forum_agent_sources_include_multiple_platforms PASSED
tests/test_stage_1f.py::test_forum_agent_findings_meet_corroboration_threshold PASSED

25 passed in X.Xs
```

---

## 1f.10 Manual Verification

After all tests pass, run the full pipeline from the terminal:

```bash
python main.py
```

Expected log sequence:

```
INFO | skill_loader     | loaded skills/forum/SKILL.md
INFO | research_handler | ForumAgent constructed
INFO | fetch_client     | Fetch MCP server started
INFO | career_agent     | starting — university='University of Manchester' course='Computer Science' country='UK'
INFO | career_agent     | completed — paths=5 confidence=high
INFO | forum_agent      | starting — university='University of Manchester' course='Computer Science'
INFO | background_agent | starting — ...
INFO | rankings_agent   | starting — ...
... (all 7 section agents start concurrently) ...
INFO | forum_agent      | completed — positives=3 concerns=2 department_feedback=4 confidence=medium platforms=['thestudentroom', 'studentcrowd', 'reddit']
INFO | fetch_client     | Fetch MCP server stopped
```

Followed by `board.forum` JSON printed to stdout. Confirm:

- `recurring_positives` contains at least 1 finding with `source_count >= 3`
  and `platform_count >= 2`
- `recurring_concerns` contains at least 1 finding (absence means the LLM
  did not search for negatives — recheck SKILL.md scope instructions)
- `department_feedback` contains at least 1 course-specific finding
- `sources_searched` lists at least 4 of the 6 platform names
- `sources_yielded` lists the platforms that actually returned qualifying content
- `staleness_discards` is non-zero for a well-known university (confirms date
  filtering is running)
- `scope_discards` is non-zero (confirms off-topic filtering is running)
- `confidence` is `"medium"` or `"high"` for University of Manchester CS
- All source URLs in findings are traceable to the platform named in
  `ForumSource.platform`

---

## 1f.11 Common Failure Modes at This Stage

**`board.forum is None` after run**
Two causes: (a) LLM raised — check the `forum_agent | failed` log line;
(b) pydantic `ValidationError` on `ForumOutput` — the LLM returned a finding
with `source_count < 3` or `platform_count < 2`. Check logs for the
validation error. Fix: tighten the SKILL.md instruction on corroboration
to make the rule more explicit to the LLM.

**`staleness_discards = 0` for a well-known university**
The LLM is probably not verifying post dates after fetching threads.
Fix: add a more explicit instruction in SKILL.md — "After calling fetch_page
on a TSR thread, check the date of each visible post before extracting
content. If the date is not visible, discard."

**`scope_discards = 0` for a large university**
Large universities have abundant general forum content that is not course-
specific. A `scope_discards` of 0 almost certainly means the LLM is keeping
off-topic content. Fix: add examples of out-of-scope content to the SKILL.md
edge case section.

**All findings come from TSR only (`platform_count = 1`)**
The LLM exhausted its budget on TSR and did not reach the other sources.
Fix: add an explicit budget-allocation instruction in SKILL.md — "Do not
use more than 5 Tavily calls on TSR. Move to the next source after 5 calls
regardless of yield."

**`ForumAgent` fires before `CareerAgent` completes**
Not possible by design — `ForumAgent` subscribes to
`CareerResearchCompletedMessage`, which fires only after `CareerAgent`
completes. If this appears to happen in logs, check that `subscribe()`
is called on `CareerResearchCompletedMessage` and not `ResearchRequestedMessage`.
The test `test_forum_agent_does_not_subscribe_to_research_requested` catches
this regression.

**`SectionCompletedMessage` fires but `section_name` is wrong**
`ScoringAgent` uses `section_name` to identify which blackboard field the
section result belongs to. If `section_name` is `"forums"` instead of
`"forum"`, `ScoringAgent`'s `setattr` does nothing and the forum dimension
is silently unscored. The blackboard field is `forum` — match it exactly.

**No findings for a niche course**
Expected behaviour. The agent sets `confidence: "low"` and returns empty
lists with an explanation in `notes`. This is not a bug — it is a valid
data-sparse result. The report renders it as "Insufficient forum data
available for this course."

---

## Stage 1f Completion Checklist

- [ ] `schemas/outputs/forum_output.py` — `ForumOutput`, `ForumFinding`,
      `ForumSource` implemented with `field_validator` on `source_count`
      and `platform_count`
- [ ] `skills/forum/SKILL.md` — frontmatter valid, `tool_budget: 14`,
      `section_name: forum`, all 6 sources documented, recency and
      corroboration rules explicit, budget allocation table present
- [ ] `agents/forum_agent.py` — subscribes to `CareerResearchCompletedMessage`,
      reads `board.career` in `handle()`, fires `SectionCompletedMessage` or
      `SectionFailedMessage`, `_make_search_tool()` closes over `self`
- [ ] `services/research_handler.py` — `ForumAgent` constructed and wired,
      `tool_budget` sourced from SKILL.md with fallback to 14
- [ ] `main.py` — `board.forum` printed to stdout
- [ ] `pytest tests/test_stage_1f.py -v` — 25 passed
- [ ] `python main.py` — `board.forum` printed with real data containing
      findings from at least 2 distinct platforms, `staleness_discards > 0`,
      `scope_discards > 0`
- [ ] All prior stage tests still pass: `pytest tests/ -v --ignore=tests/test_stage_1f.py`

---

*End of Stage 1f Specification*