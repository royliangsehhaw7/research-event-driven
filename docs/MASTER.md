# University Research Assistant — Multi-Agent System
## Project Specification v0.4

**Purpose**: Bounded research system to help parents evaluate universities for their
children's undergraduate studies  
**Framework**: pydantic-ai  
**UI**: Chainlit  
**Architecture**: Observer / Pub-Sub with Blackboard  
**Reference system**: Customer Service MAS (SPECIFICATIONS_v8.md)  
**Status**: Design Phase — Pre-Development  
**Learning orientation**: Intermediate — assumes prior MAS experience (orchestrator-worker,
broker-auction, event-blackboard)

---

## 1. Problem Statement

Researching a university for an undergraduate course is time-consuming, fragmented, and
often misleading. Official rankings are biased toward research output. Marketing materials
are promotional. The information that actually matters — student experiences, graduate
employment, course-specific reputation, real living costs — is scattered across dozens of
sources and forums.

This system aggregates, filters, and synthesises that information into a structured report
scoped tightly to a specific university and course, presented in a format useful to a parent
making a real decision.

---

## 2. Scope & Boundaries

### In Scope
- Undergraduate programs only
- Single university + course as primary research target
- 2–3 alternative universities as secondary output
- Information dated within the last 2 years only
- Employability data restricted to the university's country
- Forum content scoped strictly to the researched course/department

### Out of Scope
- Postgraduate, Masters, PhD programs
- Cost of living, visa, immigration context
- Real-time monitoring or persistent history across sessions
- Direct application assistance
- Browser automation or scraping

### Fixed Assumptions
- Study level: Undergraduate — hardcoded, not a user input
- University country: derived from university name by the system
- Career goals: researched by the system, not provided by user

---

## 3. User Input

Exactly two fields:

```
1. University name      e.g. "University of Manchester"
2. Intended course      e.g. "Computer Science"
```

Everything else is researched or derived internally.

---

## 4. Architecture

### 4.1 Two-Phase Design

The system is split into two distinct phases with a hard boundary between them.

```
User Input
   │
   │  university_name: "University of Manchester"
   │  intended_course: "Computer Science"
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Phase 1 — Career Research (Sequential Pre-Step)                     │
│                                                                      │
│  CareerResearchAgent runs first. Researches career paths, salary     │
│  ranges, and live job postings for the course in the university's    │
│  country. Writes to board.career. Fires CareerResearchCompleted.     │
│  No section agents run until this completes.                         │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │  CareerResearchCompletedMessage
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Phase 2 — Research Cascade                                          │
│                                                                      │
│  ResearchHandler fires one publish(CareerResearchCompletedMessage).  │
│  Seven section agents fan out concurrently via the MessageHub.       │
│  Each reacts to the message independently. No orchestrator.          │
│  No agent calls another agent directly.                              │
└──────────────────────────────────────────────────────────────────────┘
```

The two phases never overlap. Phase 2 does not start until `CareerResearchAgent`
publishes `CareerResearchCompletedMessage`. Section agents have no knowledge of
Phase 1 internals — they only know the message they subscribe to and their own
blackboard field.

---

### 4.2 Pattern — Observer with Typed Messages and Blackboard Data Sharing

The research cascade implements the **Observer pattern**. Its mechanism is a
`MessageHub` — a dictionary that maps message types to lists of async handler functions.

In the classical Observer pattern, subjects maintain a registry of observers and notify
them when something changes. Here:

- **The subject** is `MessageHub`. It maintains the registry and notifies observers.
- **The observers** are the research agents. Each registers a handler for one or more
  message types via `subscribe()`.
- **The notification** is `hub.publish(message)` — the hub calls all handlers registered
  for that message type, concurrently, via `asyncio.gather()`.

#### Two distinct concerns: outputs and messages

This system maintains a clean separation between what an LLM produces and what the hub routes.

**Output schemas** (`schemas/outputs/`) — what the LLM must produce. Rich, with all fields
the agent needs to complete its section. Stored on `deps.board` for any downstream agent
to read directly.

**Messages** (`schemas/messages/`) — what gets published to the hub. Lean, typed notification
that something has been determined. Carries only `triggered_by` (which agent sent it) and
`timestamp` (when it was sent). Downstream agents do not read data off the message — they
read `deps.board`.

One agent, two distinct steps — every agent in the system follows this exact pattern:

```python
# 1. write full rich output to blackboard
finding: BackgroundOutput = result.output
deps.board.background = finding

# 2. build lean message and publish to hub
await deps.hub.publish(SectionCompletedMessage(
    section_name="background",
    triggered_by="background_agent",
    timestamp=datetime.now().isoformat(),
))
```

This separation means:
- LLM output schemas evolve independently of what the hub routes
- Downstream agents always read full, rich data from `deps.board` — never reconstruct
  it from a message payload
- The hub message is a pure notification: *"this section is done — read the board"*
- `triggered_by` and `timestamp` on every message make the cascade traceable

#### What the MessageHub is

The `MessageHub` is a dictionary and an `asyncio.gather()` call. Nothing more.

```python
# State of the hub after all subscribe() calls:
{
    ResearchRequestedMessage:       [career_agent.handle],

    CareerResearchCompletedMessage: [background_agent.handle,
                                     rankings_agent.handle,
                                     program_agent.handle,
                                     employability_agent.handle,
                                     accommodation_agent.handle,
                                     news_agent.handle,
                                     forum_agent.handle],

    SectionCompletedMessage:        [scoring_agent.handle],
    SectionFailedMessage:           [scoring_agent.handle],

    ScoringCompletedMessage:        [alternatives_agent.handle],
    AlternativesCompletedMessage:   [report_generator.handle],

    ReportReadyMessage:             [chainlit_ui.handle],
    ProgressUpdateMessage:          [chainlit_ui.handle],
}

# publish() does exactly this:
async def publish(self, message: BaseModel) -> None:
    handlers = self._subscribers.get(type(message), [])
    if handlers:
        await asyncio.gather(*[h(message) for h in handlers])
```

The hub has zero domain knowledge. It does not know what a university is, what a course
is, or what any message contains. It only knows message types and handler lists.

The term "event loop" is reserved exclusively for Python's `asyncio` event loop and is
never used to describe the hub's dispatch mechanism.

---

### 4.3 The Blackboard

The `Blackboard` is a typed, per-request result accumulator. It is a plain dataclass on
`Deps` — one instance created fresh for each `ResearchRequestedMessage`, discarded when
the cascade completes.

Agents write their full LLM output to `deps.board` immediately after the LLM call
completes. Downstream agents read from `deps.board` directly — never from the hub
message payload. The hub message is a lean notification only.

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

Field names are short domain nouns. Types use the `Output` suffix, matching
`schemas/outputs/`. Gate conditions in downstream agents check these fields directly —
e.g. `deps.board.career is None`.

---

### 4.4 Responsibility Boundaries

Three classes own the system's top-level concerns. They do not overlap.

| Class | Location | Responsibility |
|---|---|---|
| `ResearchHandler` | `services/research_handler.py` | Initialises search clients, LLM models, and agents once at startup. Per request: creates `MessageHub`, `Blackboard`, `Deps`; subscribes all agents; derives country from university name; fires the single `publish(ResearchRequestedMessage)` call. |
| `MessageHub` | `core/message_hub.py` | Pure fan-out. Maps message types to handler lists. Calls `asyncio.gather()` on publish. Zero domain knowledge. |
| `Blackboard` | `core/blackboard.py` | Typed per-request result accumulator. Written to by agents after LLM calls. Read from by downstream agents. Never passed through message payloads. |

---

### 4.5 Quorum Gate — ScoringAgent

This is the one pattern not present in the reference system.

`ScoringAgent` subscribes to both `SectionCompletedMessage` and `SectionFailedMessage`.
It maintains a counter of received section results. When `received == 7` it proceeds —
regardless of how many failed. Failed sections are marked unavailable on the board.
`ScoringAgent` down-weights or skips unavailable sections and flags gaps in the report
rather than blocking on missing data.

```python
# ScoringAgent internal state (per request):
expected_sections = 7
received_count    = 0   # increments on SectionCompleted or SectionFailed

async def handle(self, message: SectionCompletedMessage | SectionFailedMessage, deps: Deps):
    self.received_count += 1
    if isinstance(message, SectionFailedMessage):
        # mark unavailable on board — do not block
        setattr(deps.board, message.section_name, None)
    if self.received_count < self.expected_sections:
        return  # wait for remaining sections
    # all sections resolved — proceed with whatever is on the board
    await self._score(deps)
```

---

### 4.6 Full Pipeline Flow

```
[ResearchRequestedMessage]
        ↓
[CareerResearchAgent]
  writes: board.career
  fires:  CareerResearchCompletedMessage
        ↓
[BackgroundAgent]   ──┐
[RankingsAgent]       │  all subscribe to CareerResearchCompletedMessage
[ProgramAgent]        │  all run concurrently via asyncio.gather()
[EmployabilityAgent]  │  each writes board.[section]
[AccommodationAgent]  │  each fires SectionCompletedMessage
[NewsAgent]           │        or SectionFailedMessage
[ForumAgent]        ──┘
        ↓
[ScoringAgent]          quorum gate — waits for 7 section results
  writes: board.score
  fires:  ScoringCompletedMessage
        ↓
[AlternativesAgent]     sequential post-step
  reads:  board.score.weaknesses
  writes: board.alternatives
  fires:  AlternativesCompletedMessage
        ↓
[ReportGenerator]       deterministic — no LLM
  reads:  full blackboard
  writes: report.md, summary.md, sources.md, score.json
  fires:  ReportReadyMessage
        ↓
[Chainlit UI]           subscribes to ProgressUpdateMessage + ReportReadyMessage
```

---

## 5. Agent Definitions

### 5.1 CareerResearchAgent
**Phase**: 1 — sequential pre-step  
**Subscribes to**: `ResearchRequestedMessage`  
**Writes**: `board.career`  
**Fires**: `CareerResearchCompletedMessage`  
**Produces**: Career paths from this course, salary ranges (country-scoped),
live job postings snapshot, in-demand skills from postings  
**Tool budget**: 5–8 calls  
**Feeds into**: `EmployabilityAgent` reads `board.career` for context

---

### 5.2 BackgroundAgent
**Phase**: 2 — parallel  
**Subscribes to**: `CareerResearchCompletedMessage`  
**Writes**: `board.background`  
**Fires**: `SectionCompletedMessage(section_name="background")` or `SectionFailedMessage`  
**Produces**: University history, size, public/private, research vs teaching orientation,
known strengths in course/field, relevant accreditations  
**Tool budget**: 3–5 calls

---

### 5.3 RankingsAgent
**Phase**: 2 — parallel  
**Subscribes to**: `CareerResearchCompletedMessage`  
**Writes**: `board.rankings`  
**Fires**: `SectionCompletedMessage(section_name="rankings")` or `SectionFailedMessage`  
**Produces**: Subject-specific ranking (primary), overall ranking (secondary, lower weight),
graduate employability ranking, teaching quality indicators  
**Tool budget**: 4–6 calls  
**Note**: No subject ranking found → `confidence: low`, flagged in report

---

### 5.4 ProgramAgent
**Phase**: 2 — parallel  
**Subscribes to**: `CareerResearchCompletedMessage`  
**Writes**: `board.program`  
**Fires**: `SectionCompletedMessage(section_name="program")` or `SectionFailedMessage`  
**Produces**: Matching undergraduate programs, specialisations/tracks, duration,
delivery format, program features relevant to career outcomes  
**Tool budget**: 4–5 calls

---

### 5.5 EmployabilityAgent
**Phase**: 2 — parallel  
**Subscribes to**: `CareerResearchCompletedMessage`  
**Reads**: `board.career` before searching — uses career paths as search context  
**Writes**: `board.employability`  
**Fires**: `SectionCompletedMessage(section_name="employability")` or `SectionFailedMessage`  
**Produces**: Graduate employment rate, industries/companies entered (country-scoped),
evidence of graduates in careers from `board.career`, industry partnerships, alumni sampling  
**Tool budget**: 6–8 calls  
**Scope**: Country-scoped employment data only

---

### 5.6 AccommodationAgent
**Phase**: 2 — parallel  
**Subscribes to**: `CareerResearchCompletedMessage`  
**Writes**: `board.accommodation`  
**Fires**: `SectionCompletedMessage(section_name="accommodation")` or `SectionFailedMessage`  
**Produces**: On/off-campus cost range, area safety and crime rate,
public transport access to campus  
**Tool budget**: 4–6 calls

---

### 5.7 NewsAgent
**Phase**: 2 — parallel  
**Subscribes to**: `CareerResearchCompletedMessage`  
**Writes**: `board.news`  
**Fires**: `SectionCompletedMessage(section_name="news")` or `SectionFailedMessage`  
**Produces**: Institutional news last 2 years, department-specific news flagged,
sentiment per item (positive / negative / neutral), source URL + date  
**Tool budget**: 4–6 calls  
**Constraint**: 2-year date filter on every query. Older results discarded.

---

### 5.8 ForumAgent
**Phase**: 2 — parallel  
**Subscribes to**: `CareerResearchCompletedMessage`  
**Writes**: `board.forum`  
**Fires**: `SectionCompletedMessage(section_name="forum")` or `SectionFailedMessage`  
**Produces**: Recurring positives (3+ sources to qualify), recurring concerns (3+ sources),
department-specific feedback, paraphrased excerpts with source + year,
signal weighting: current/former student > prospective student posts  
**Tool budget**: 8–10 calls — highest budget  
**Scope**: Every query must include university AND course. Off-topic threads discarded.
Posts older than 2 years discarded.  
**Sources**: `site:reddit.com`, `site:thestudentroom.co.uk`, `site:thegradcafe.com`,
`site:quora.com`

---

### 5.9 ScoringAgent
**Phase**: 3 — quorum gate  
**Subscribes to**: `SectionCompletedMessage` AND `SectionFailedMessage`  
**Proceeds when**: received count reaches 7 (pass or fail)  
**Writes**: `board.score`  
**Fires**: `ScoringCompletedMessage`  
**Produces**: Score per dimension (0–10) with rationale, confidence flag per dimension,
overall weighted score, tiered recommendation, weaknesses list for AlternativesAgent

| Dimension | Weight |
|---|---|
| Employability & outcomes | 25% |
| Program fit | 20% |
| Forum/student sentiment | 20% |
| Subject ranking | 15% |
| Accommodation & living | 10% |
| News sentiment | 5% |
| Overall prestige | 5% |

Tiers: `Strong Consider` / `Consider` / `Proceed with Caution` / `Avoid`  
Low-confidence dimensions: down-weighted and flagged, not scored on thin data

---

### 5.10 AlternativesAgent
**Phase**: 3 — sequential post-step  
**Subscribes to**: `ScoringCompletedMessage`  
**Reads**: `board.score.weaknesses`  
**Writes**: `board.alternatives`  
**Fires**: `AlternativesCompletedMessage`  
**Produces**: 2–3 alternatives — name, country, why it addresses the primary's gaps,
subject ranking, brief program note, one-line employability note  
**Tool budget**: 6–8 calls  
**Scope**: Same course, undergraduate only. Gap-targeted selection.

---

## 6. Scoping Strategy

### Course Context in Every Agent Brief

The orchestrator injects into every agent's task brief:

```python
@dataclass
class ResearchContext:
    university_name:  str    # "University of Manchester"
    intended_course:  str    # "Computer Science"
    country:          str    # "UK" — derived by ResearchHandler
    study_level:      str    # "undergraduate" — hardcoded constant
```

Search query construction — always:
```
[university] + [course/department] + [section-specific terms]
```
Never `[university]` alone.

### Date Filtering — Two Layers

1. **Tool level**: Tavily `days=730`, Brave `freshness` parameter
2. **Prompt level**: agents explicitly instructed to discard results older than 2 years

Every source in every `Output` schema must include a publication date field.

### Tool Call Budgets

Hard limits per agent, not suggestions. Agents are prompted to return on
*sufficiency* — enough to write a solid evidence-backed section — not on
exhaustion of all possible sources.

---

## 7. Tools & MCP Servers

### Primary Search

| Tool | Role | Key Feature |
|---|---|---|
| **Tavily MCP** | Primary — all agents | `days=730` date filter, domain include/exclude |
| **Fetch MCP** | Direct URL fetch | University catalog pages, rankings pages |
| **Brave Search MCP** | Fallback / forum discovery | Freshness filtering |
| **SerpAPI** | Google News (NewsAgent) | Fallback if Tavily misses news results |

### Forum Search — Domain-Scoped Web Search

| Platform | Query Pattern |
|---|---|
| Reddit | `site:reddit.com [university] [course]` |
| The Student Room | `site:thestudentroom.co.uk [university] [course]` |
| Grad Café | `site:thegradcafe.com [university] [course]` |
| Quora | `site:quora.com [university] [course] experience` |

### Employability & Rankings — Web Search Only

No free APIs for QS, THE, ARWU. Web search + Fetch MCP for structured pages.
LinkedIn/Glassdoor via `site:` scoped search queries.

### Not Needed

Vector databases, RAG, persistent memory stores, browser automation.

---

## 8. Output Files

| File | Content | How Generated |
|---|---|---|
| `report.md` | Full structured report, all sections | Jinja2 template over blackboard |
| `summary.md` | One-page executive summary | Jinja2 template over blackboard |
| `sources.md` | Every URL + date + agent — auditable | Iterates all board source fields |
| `score.json` | Machine-readable score breakdown | Serialises `board.score` |

`ReportGenerator` is deterministic Python — no LLM call. `score.json` enables
multi-university comparison: load 3–4 files, generate comparison table without
re-running the pipeline.

---

## 9. Folder Structure

```
university_research/
├── core/
│   ├── message_hub.py          pure fan-out, zero domain knowledge
│   ├── blackboard.py           typed per-request result accumulator
│   ├── deps.py                 hub + board + search clients bundled
│   └── llm_factory.py          model initialisation
│
├── schemas/
│   ├── messages/               lean hub notifications
│   │   ├── research_requested.py       triggered_by, timestamp, university, course
│   │   ├── career_completed.py         triggered_by, timestamp
│   │   ├── section_completed.py        triggered_by, timestamp, section_name
│   │   ├── section_failed.py           triggered_by, timestamp, section_name, reason
│   │   ├── scoring_completed.py        triggered_by, timestamp
│   │   ├── alternatives_completed.py   triggered_by, timestamp
│   │   ├── report_ready.py             triggered_by, timestamp, file_paths[]
│   │   └── progress_update.py          triggered_by, timestamp, status, message
│   │
│   └── outputs/                rich LLM outputs written to blackboard
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
│   ├── base_agent.py           shared: logging, progress publish, error → SectionFailedMessage
│   ├── career_agent.py
│   ├── background_agent.py
│   ├── rankings_agent.py
│   ├── program_agent.py
│   ├── employability_agent.py
│   ├── accommodation_agent.py
│   ├── news_agent.py
│   ├── forum_agent.py
│   ├── scoring_agent.py        quorum gate logic lives here
│   └── alternatives_agent.py
│
├── tools/
│   ├── search_tool.py          Tavily MCP wrapper, days=730 enforced
│   └── fetch_tool.py           Fetch MCP wrapper
│
├── report/
│   ├── generator.py            deterministic MD/JSON writer
│   └── templates/
│       ├── report.md.j2
│       └── summary.md.j2
│
├── services/
│   └── research_handler.py     init deps, subscribe all agents, fire trigger
│
├── ui/
│   └── app.py                  Chainlit entry point
│
└── main.py                     CLI entry — full pipeline without UI
```

---

## 10. Development Stages

Three stages, each with sub-phases. Every sub-phase ends with something running
and verifiable. No sub-phase is purely structural — each one produces observable output.

---

### Stage 1 — Core Infrastructure, Contracts, and First Live Agent

Stage 1 is about getting the foundation exactly right before any research
pipeline exists. Schemas defined as contracts. Core wired and tested in isolation.
MCP tools confirmed against real targets. One agent producing real output.

---

#### Stage 1a — Project Skeleton and Core Infrastructure

**What you build**:

```
core/
  message_hub.py      full implementation — subscribe(), publish(), asyncio.gather()
  blackboard.py       all 10 fields defined, all None, with is_complete() helper
  deps.py             Deps dataclass: hub + board + search clients (stubs for now)
  llm_factory.py      model initialisation, same pattern as reference system

schemas/messages/     all 8 message types defined as Pydantic BaseModels
                      every message carries triggered_by + timestamp
                      ResearchRequestedMessage additionally carries university + course
                      SectionCompletedMessage and SectionFailedMessage carry section_name

schemas/outputs/      all 10 output types defined as Pydantic BaseModels
                      fields can be minimal stubs — they will be fleshed out per agent
                      but the types must exist so the blackboard compiles

agents/
  base_agent.py       abstract base: logging, ProgressUpdateMessage publish on
                      entry/exit, exception handler → SectionFailedMessage pattern
```

**Verify**:

Hub standalone test — same verification as the reference system:
```python
# subscribe 3 dummy handlers to the same message type
# publish one message
# confirm all 3 fired
# confirm handlers for other message types did not fire
# confirm asyncio.gather() ran them concurrently, not sequentially
```

Blackboard instantiation: confirm all fields are None. Confirm field names
match `schemas/outputs/` types exactly.

Message round-trip: instantiate each message schema with dummy data,
`model_dump()`, `model_validate()`. Confirm `triggered_by` and `timestamp`
present on every message type.

**What you should have at the end of 1a**:  
A working `MessageHub`, a typed `Blackboard`, all schema contracts defined,
and `BaseAgent` pattern established. No LLM calls yet. No search tools yet.
The skeleton stands and the core mechanics are verified.

---

#### Stage 1b — MCP Tool Integration and Verification

**What you build**:

```
tools/
  search_tool.py      Tavily MCP wrapper
                      days=730 enforced on every call — not optional
                      domain include/exclude wired
                      returns: list of SearchResult(url, title, snippet, date)

  fetch_tool.py       Fetch MCP wrapper
                      returns: FetchResult(url, content, status)

core/
  deps.py             update: real search clients replace stubs
```

**Verify against real targets** — this is the point of 1b, not unit tests:

```
Search test 1 — date filtering works:
  query: "University of Manchester Computer Science department"
  days=730
  confirm: no results older than 2 years in response

Search test 2 — domain scoping works:
  query: "University of Manchester Computer Science reddit"
  include_domains: ["reddit.com"]
  confirm: all results from reddit.com only

Search test 3 — forum scoping works:
  query: "University of Manchester Computer Science student experience"
  site prefix: "site:reddit.com"
  confirm: results are CS-specific, not generic Manchester threads

Fetch test:
  url: a real university course catalog page
  confirm: readable content returned, not a bot-block response
```

**What you should have at the end of 1b**:  
MCP tools confirmed working with date filtering and domain scoping against
real university targets. Any Tavily configuration issues, API key problems,
or bot-blocking issues discovered and resolved here — not mid-pipeline.

---

#### Stage 1c — First Agent End-to-End

**What you build**:

```
agents/
  career_agent.py     first full agent
                      subscribes to ResearchRequestedMessage
                      calls search_tool with university + course + country
                      produces CareerOutput (careers, salaries, job postings)
                      writes board.career
                      fires CareerResearchCompletedMessage
                      fires ProgressUpdateMessage on entry and exit

services/
  research_handler.py subscribes career_agent only for now
                      creates MessageHub, Blackboard, Deps
                      fires ResearchRequestedMessage
                      returns board after cascade

main.py               CLI: accepts university + course
                      calls ResearchHandler
                      prints board.career to console
```

**Verify**:

```
Input:  university="University of Manchester", course="Computer Science"
Expect: board.career populated with:
          - at least 3 distinct career paths
          - salary ranges scoped to UK (not global)
          - job postings with recency within 2 years
          - skills extracted from postings

Input:  university="University of Sydney", course="Psychology"
Expect: board.career populated with Psychology careers, AU salary ranges
        confirm: no CS careers bleed through — scoping is clean

Failure test:
  break the search tool (bad API key)
  confirm: SectionFailedMessage fires, not an unhandled exception
  confirm: board.career remains None with failure noted
```

**What you should have at the end of 1c**:  
One agent running end-to-end against real search data. The full
`ResearchHandler → MessageHub → Agent → Blackboard → Message` cycle
verified with real output. This is the pattern every subsequent agent
will follow — get it clean here.

---

### Stage 2 — Full Pipeline and Chainlit Conversational UI

Stage 2 completes the research pipeline then builds the conversational
UI layer. Two sub-phases: pipeline first, UI second. Do not start 2b
until the pipeline is verified clean from the CLI.

---

#### Stage 2a — Complete the Research Pipeline

**What you build** (in this order):

Add remaining Phase 2 section agents one at a time:

```
agents/
  background_agent.py     simplest — confirms the section agent pattern
  rankings_agent.py       introduces subject vs overall ranking logic
  program_agent.py
  employability_agent.py  reads board.career before searching — new pattern
  accommodation_agent.py
  news_agent.py           introduces sentiment classification per item
  forum_agent.py          hardest — multi-source, course-scoped, noise filtering
```

Add each to `ResearchHandler` subscriptions as it is built.
Verify each agent individually before adding the next.

Then build Phase 3:

```
agents/
  scoring_agent.py        quorum gate — the new pattern
                          counter logic, partial board handling, confidence flags
  alternatives_agent.py   reads board.score.weaknesses

report/
  generator.py            Jinja2 render of full blackboard to 4 output files
  templates/
    report.md.j2
    summary.md.j2
```

Wire `AlternativesCompletedMessage` → `report_generator.handle`.

**Full pipeline verify from main.py CLI**:

```
Input:  "University of Manchester" + "Computer Science"
Expect: all 4 output files generated in /output/
        report.md: all 10 sections present, course-scoped content
        summary.md: recommendation tier visible, top concerns listed
        sources.md: every URL with date and agent name
        score.json: valid JSON, loads cleanly

Deliberate failure test:
  set ForumAgent to raise an exception
  confirm: SectionFailedMessage fires
  confirm: ScoringAgent proceeds at count=7 with forum section absent
  confirm: report.md generated, forum section marked unavailable
  confirm: score.json reflects down-weighted forum dimension
```

**What you should have at the end of 2a**:  
Full pipeline running. All 4 output files generated with real research data.
Failure resilience confirmed. `score.json` loadable for comparison.

---

#### Stage 2b — Chainlit Conversational UI

Chainlit is chosen over Streamlit for native async support and built-in
step display. The UI has two distinct interaction modes in one session.

**Mode 1 — Research trigger**  
User submits university + course via input form. Pipeline fires.
`ProgressUpdateMessage` events render agent status live.
On `ReportReadyMessage`, summary displays inline and files are offered
for download.

**Mode 2 — Conversational follow-up**  
After the report is generated, the blackboard persists in the Chainlit
session. A lightweight `ConversationAgent` handles natural language
follow-up questions answered from the research data — not new searches.

```python
# Example follow-up questions answered from board, not re-searched:
"Tell me more about the accommodation options"
"Why did it score low on rankings?"
"What are the alternative universities and why were they chosen?"
"Compare the forum sentiment against the news coverage"
```

`ConversationAgent` receives: user question + serialised blackboard as
context + conversation history via pydantic-ai `message_history`.
It answers from what was already found. No search tools. No new LLM
research calls.

**Session state** (Chainlit session-scoped):

```python
@dataclass
class ResearchSession:
    blackboard:           Blackboard           # persisted after pipeline
    report_files:         list[str]            # paths to generated files
    conversation_history: list[ModelMessage]   # grows across follow-up turns
    research_context:     ResearchContext      # university + course for context
```

**What you build**:

```
ui/
  app.py              Chainlit entry point
                      @cl.on_chat_start — init session state
                      @cl.on_message — route to Mode 1 or Mode 2
                      Mode 1: detect university+course input, fire pipeline
                      Mode 2: detect follow-up question, call ConversationAgent

agents/
  conversation_agent.py   reads serialised blackboard as system context
                          maintains message_history across turns
                          no tools — answers from context only
```

**Verify**:

```
Mode 1:
  submit "University of Manchester" + "Computer Science" via UI form
  confirm: agent steps update live as pipeline runs
  confirm: file downloads available on completion
  confirm: summary renders inline in chat

Mode 2:
  ask: "what were the main concerns from the forums?"
  confirm: answer references board.forum content, not generic knowledge
  ask: "what about the accommodation costs?"
  confirm: answer references board.accommodation content
  confirm: conversation history maintained — agent remembers prior turns

Session isolation:
  submit a second research request (different university)
  confirm: fresh blackboard — no data from previous run
  confirm: conversation history resets
```

**What you should have at the end of 2b**:  
Full system running in Chainlit. Research pipeline fires from UI.
Live agent progress visible. Files downloadable. Conversational follow-up
working from persisted blackboard with maintained history.

---

### Stage 3 — Document Quality, Edge Cases, Multi-University Comparison

Stage 3 is about making the outputs genuinely useful and the system
genuinely robust. No new agents. No new patterns. Polish and hardening.

---

#### Stage 3a — Report Quality Pass

The Jinja2 templates from Stage 2a produce structurally correct output.
This stage makes them genuinely readable:

- `report.md`: confidence flags rendered visibly per section,
  low-confidence sections clearly marked with explanation,
  sources inline with each finding, not just in appendix
- `summary.md`: recommendation tier prominent at top,
  top 3 positives + top 3 concerns + alternatives in one page
- `sources.md`: grouped by agent, every URL with date and confidence
- `score.json`: validate against schema, confirm comparison-ready structure

Run pipeline on two different universities for the same course.
Write a small standalone comparison script:

```python
# load score_manchester_cs.json + score_edinburgh_cs.json
# print side-by-side dimension scores
# highlight where they differ most significantly
```

This is the multi-university use case — no new pipeline run needed,
just reading existing `score.json` output.

---

#### Stage 3b — Edge Case Hardening

Test and handle explicitly:

| Scenario | Expected Behaviour |
|---|---|
| University name not recognised | Clear error before pipeline fires, not mid-run |
| No subject ranking found for course | `confidence: low`, score down-weighted, flagged in report |
| Forum agent finds no course-specific threads | Returns empty with explanation, not generic university threads |
| One agent exceeds tool call budget | Stops and returns what it has with `confidence: low` |
| Tavily rate limit hit | Retry with backoff, `SectionFailedMessage` if retries exhausted |
| 3 of 7 section agents fail | Report generated, 3 sections marked unavailable, scoring proceeds |
| ConversationAgent asked something not in the report | Answers honestly: "the research did not cover this" |

---

#### Stage 3c — Conversational UI Refinements

With real data flowing through the UI, identify and fix:

- Does `ConversationAgent` stay grounded in blackboard data or drift toward
  general knowledge? Prompt tuning if needed.
- Context window pressure: serialised full blackboard passed on every turn
  may become large. Introduce a summarised blackboard representation if needed.
- Can the user request a new university mid-session without restarting Chainlit?
  Define and implement session reset behaviour cleanly.

---

## 11. Guardrails & Data Quality

### What the System Will Not Do
- Guarantee information accuracy — outputs are research summaries, not verified facts
- Access paywalled content — skipped and flagged
- Make the final decision — the report informs, the parent decides

### Failure Handling
- Per-agent timeouts — one slow agent does not block the pipeline
- Failed sections → `SectionFailedMessage` → board field remains None
- `ScoringAgent` proceeds with partial data, flags gaps explicitly
- A partial report is always generated — no silent failures

### Rate Limiting
- Tool call budgets per agent: hard limits, not suggestions
- Total expected calls per full run: ~50–70 across all agents
- Expected runtime: 3–8 minutes depending on search API latency

---

## 12. What This System Is Not

It is not a real-time monitoring tool. It is not a recommendation engine that learns
over time. It is not a replacement for visiting the university or speaking to current
students directly.

It is a structured, bounded, time-filtered research aggregator that does in minutes
what a diligent parent would spend days doing — with consistent scope, auditable
sources, and honest confidence flagging.

---

## 13. Reference System

`SPECIFICATIONS_v8.md` is the direct architectural predecessor.
`MessageHub`, `Blackboard`, `Deps`, and the lean message / rich output
separation are identical in both systems.

Two patterns introduced here that do not exist in the reference system:

1. **Quorum gate** on `ScoringAgent` — counter-based aggregator, proceeds
   at N regardless of pass/fail ratio (Section 4.5)
2. **Conversational overlay** on a batch pipeline — `ConversationAgent`
   answering from a persisted blackboard across multi-turn Chainlit history
   (Stage 2b)

Everything else is a translation of the reference system into a new domain.

---

*End of Specification v0.4*