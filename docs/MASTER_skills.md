# University Research Assistant — Skill-Loader Specification
## Specification — Skill-Based Agent Architecture

> **Assumes:** MASTER.md v0.4 is the base design. The pipeline architecture
> (MessageHub, Blackboard, Deps, Observer pattern, quorum gate) is unchanged.
> This specification describes one structural addition only: every agent's
> behavioural instructions are loaded from a `SKILL.md` file at startup rather
> than hardcoded as strings in Python.
>
> **When to apply:** Apply this before writing any agent. The skill loader and
> all SKILL.md files are created in Stage 1a alongside the core infrastructure —
> not retrofitted later. Every agent that follows is built to accept `instructions`
> from the loader from the start.
>
> **Done when:** All 11 SKILL.md files exist. `core/skill_loader.py` parses them
> at startup. Every agent's `_build_system_prompt()` injects the loaded body.
> Changing any agent's research scope, search strategy, output guidance, scoring
> weights, or conversational boundaries requires editing a markdown file only —
> no Python changes, no redeploy.

---

## 1. What This Adds and Why

The MASTER.md design is correct architecturally. The one structural weakness is
that every agent's behavioural instructions — what to research, how to search,
what to discard, how to structure findings — are embedded as strings inside
Python agent files. This means:

- Tuning `ForumAgent` to be more aggressive about discarding off-topic threads
  requires editing Python, not a text file.
- Changing `ScoringAgent`'s tier thresholds or weighting rationale means touching
  agent logic.
- Understanding what `ConversationAgent` will and will not answer from the
  blackboard requires reading code, not a document.

The fix is the same pattern used in the Telegram assistant's Stage 3a: each
agent's behavioural instructions live in a `SKILL.md` file under `skills/`.
The skill loader reads these files at startup and passes the body as
`instructions` to the agent constructor. The agent injects `instructions` into
its system prompt. The Python never changes when instructions change.

**What changes at the code level:**

| File | Change |
|---|---|
| `skills/career/SKILL.md` | NEW |
| `skills/background/SKILL.md` | NEW |
| `skills/rankings/SKILL.md` | NEW |
| `skills/program/SKILL.md` | NEW |
| `skills/employability/SKILL.md` | NEW |
| `skills/accommodation/SKILL.md` | NEW |
| `skills/news/SKILL.md` | NEW |
| `skills/forum/SKILL.md` | NEW |
| `skills/scoring/SKILL.md` | NEW |
| `skills/alternatives/SKILL.md` | NEW |
| `skills/conversation/SKILL.md` | NEW |
| `core/skill_loader.py` | NEW |
| `agents/base_agent.py` | UPDATED — `instructions` field + `_build_system_prompt()` pattern |
| `services/research_handler.py` | UPDATED — loads skills at startup, passes to agent constructors |

**What does not change:**

`core/message_hub.py`, `core/blackboard.py`, `core/deps.py`, `core/llm_factory.py`,
all `schemas/messages/`, all `schemas/outputs/`, individual agent `handle()` logic,
quorum gate in `ScoringAgent`, `ReportGenerator`, `ui/app.py`, `main.py` — none
of these are touched. The pipeline mechanics are identical to MASTER.md.

---

## 2. One Agent Type

The Telegram assistant distinguishes MCP agents (fully constructable from a skill
file) from tool agents (hardcoded Python, skill file governs behaviour only).
The research pipeline has no equivalent split. Every research agent has
non-trivial Python mechanics — `handle()`, blackboard writes, message publishing,
quorum counting — that cannot live in a file.

Every agent in this system is therefore the equivalent of a **tool agent** in the
Telegram model: the Python constructs the agent, and the skill file governs its
behaviour. There is no registry scan that auto-constructs agents from files. There
is no `type: mcp` vs `type: tool` distinction in frontmatter.

This simplifies both the loader and the frontmatter schema.

---

## 3. SKILL.md Format — Full Specification

Every agent has a `SKILL.md` file under `skills/<key>/SKILL.md`. The file has
two parts: a YAML frontmatter block and a markdown body.

### Frontmatter

The frontmatter is delimited by `---` on its own line at the top of the file and
after the last field. It is machine-readable — parsed by `core/skill_loader.py`.

```
---
key: <string>
name: <string>
description: <string>
tool_budget: <int>
section_name: <string | null>
---
```

| Field | Required | Description |
|---|---|---|
| `key` | yes | Unique agent identifier. Must match the folder name. Lowercase, no spaces. |
| `name` | yes | Human-readable display name. Used in logs. |
| `description` | yes | One-line summary of what this agent researches. Used in progress messages and report metadata. |
| `tool_budget` | yes | Maximum tool calls this agent is permitted per run. Injected into the system prompt. |
| `section_name` | no | The blackboard field this agent writes to. Used for progress logging. Omit for agents that do not write a named section (scoring, alternatives, conversation). |

### Markdown body

The body begins immediately after the closing `---` of the frontmatter. Write it
as direct instructions to the agent. This is the full behavioural specification —
what to research, how to construct queries, what to discard, what to return.

The body is injected verbatim into the agent's system prompt. It is loaded once
at startup and held in memory for the lifetime of the process. It is not reloaded
per request.

A malformed skill file — missing frontmatter, unparseable YAML, missing required
fields — does not crash startup. The agent receives empty instructions and falls
back to its hardcoded base prompt. A warning is logged. Silent failures are
never acceptable.

---

## 4. `core/skill_loader.py` — Full Implementation

Responsible for one thing: reading a `SKILL.md` file and returning its parsed
contents. Called by `ResearchHandler` at startup only. Never called at request
time.

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
    section_name: str | None    # None for scoring, alternatives, conversation
    instructions: str           # full markdown body, injected into system prompt


def load_skill(path: Path) -> SkillMeta | None:
    """Parse a SKILL.md file.

    Returns a SkillMeta if the file is valid, or None if it should be skipped.
    Logs a warning for every skipped file — silent failures are not acceptable.

    The file must begin with a YAML frontmatter block delimited by '---'.
    Any content after the second '---' is treated as the markdown body.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill_loader | cannot read %s: %s", path, exc)
        return None

    # Split on frontmatter delimiters.
    # A valid file looks like: "---\n<yaml>\n---\n<body>"
    # Split into at most 3 parts: ["", yaml_block, body]
    parts = raw.split("---", maxsplit=2)
    if len(parts) < 3:
        logger.warning(
            "skill_loader | %s: missing frontmatter delimiters — skipping", path
        )
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

    # Validate required fields.
    required = ("key", "name", "description", "tool_budget")
    missing = [f for f in required if not meta.get(f)]
    if missing:
        logger.warning(
            "skill_loader | %s: missing required fields %s — skipping", path, missing
        )
        return None

    try:
        tool_budget = int(meta["tool_budget"])
    except (TypeError, ValueError):
        logger.warning(
            "skill_loader | %s: tool_budget must be an integer — skipping", path
        )
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
    """Scan the skills/ directory and return all valid SkillMeta entries.

    Each immediate subdirectory of skills_dir is expected to contain a SKILL.md.
    Subdirectories without a SKILL.md are silently skipped.

    Returns a dict keyed by skill.key. Duplicate keys emit a warning; the first
    entry found wins.
    """
    result: dict[str, SkillMeta] = {}

    if not skills_dir.is_dir():
        logger.warning(
            "skill_loader | skills dir %s does not exist — no skills loaded", skills_dir
        )
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
            logger.warning(
                "skill_loader | duplicate key %r in %s — first entry wins",
                skill.key, skill_file,
            )
            continue
        result[skill.key] = skill

    return result
```

**Why `yaml.safe_load` and not `yaml.load`?** `yaml.load` can execute arbitrary
Python constructors embedded in YAML. `safe_load` restricts parsing to basic
types. Skill files will be edited by hand during tuning — safe parsing prevents
a typo or accidental injection from executing code at startup.

**Why log warnings instead of raising?** A broken skill file should degrade
gracefully. The agent it described runs without custom instructions — its
hardcoded base prompt takes over. Raising would crash the entire startup because
of one malformed file. The developer sees the warning and fixes it.

**Why load at startup and not per request?** Skill files do not change at runtime.
Loading once at startup is correct. Loading per request would add file I/O to
every pipeline run with no benefit.

---

## 5. How Instructions Flow into Agents

Every agent in the pipeline follows the same two-step pattern.

### Step 1 — Constructor accepts `instructions`

```python
class ForumAgent(BaseAgent):
    def __init__(self, instructions: str = "") -> None:
        super().__init__(instructions=instructions)
```

### Step 2 — `_build_system_prompt()` injects them

In `agents/base_agent.py`, the base class defines the injection pattern:

```python
class BaseAgent:
    def __init__(self, instructions: str = "") -> None:
        self.instructions = instructions

    def _build_system_prompt(self) -> str:
        """Build the full system prompt for this agent.

        Subclasses define _base_prompt() with hardcoded structural context.
        The loaded SKILL.md body is appended after the base if present.
        If SKILL.md is missing or empty, the base prompt runs unchanged —
        no behaviour difference, just less specific instructions.
        """
        base = self._base_prompt()
        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def _base_prompt(self) -> str:
        """Override in each subclass. Minimal structural context only."""
        return ""
```

The base prompt in each subclass carries only structural context — what
blackboard fields the agent reads, what output schema it must produce, what
message it fires. Domain knowledge — search strategy, scope rules, quality
filters — belongs entirely in the SKILL.md body.

### Step 3 — `ResearchHandler` loads and passes skills

```python
# services/research_handler.py

from core.skill_loader import scan_skills_dir

skills = scan_skills_dir(Path("skills"))

# Each agent receives its loaded instructions at construction.
# If a SKILL.md is missing, the agent receives an empty string
# and falls back to its base prompt.
forum_agent    = ForumAgent(instructions=skills.get("forum", _empty).instructions)
career_agent   = CareerAgent(instructions=skills.get("career", _empty).instructions)
scoring_agent  = ScoringAgent(instructions=skills.get("scoring", _empty).instructions)
# ... and so on for all 11 agents
```

Where `_empty` is a sentinel with an empty `instructions` field — avoids
repeated `if skill else ""` checks at construction time.

---

## 6. Updated Folder Structure

The structure from MASTER.md Section 9 gains one new top-level directory:

```
university_research/
├── skills/                          NEW
│   ├── career/
│   │   └── SKILL.md
│   ├── background/
│   │   └── SKILL.md
│   ├── rankings/
│   │   └── SKILL.md
│   ├── program/
│   │   └── SKILL.md
│   ├── employability/
│   │   └── SKILL.md
│   ├── accommodation/
│   │   └── SKILL.md
│   ├── news/
│   │   └── SKILL.md
│   ├── forum/
│   │   └── SKILL.md
│   ├── scoring/
│   │   └── SKILL.md
│   ├── alternatives/
│   │   └── SKILL.md
│   └── conversation/
│       └── SKILL.md
│
├── core/
│   ├── message_hub.py              unchanged
│   ├── blackboard.py               unchanged
│   ├── deps.py                     unchanged
│   ├── llm_factory.py              unchanged
│   └── skill_loader.py             NEW
│
├── schemas/                        unchanged
├── tools/                          unchanged
├── report/                         unchanged
│
├── agents/
│   ├── base_agent.py               UPDATED — instructions field + _build_system_prompt
│   ├── career_agent.py             UPDATED — constructor accepts instructions
│   ├── background_agent.py         UPDATED — constructor accepts instructions
│   ├── rankings_agent.py           UPDATED — constructor accepts instructions
│   ├── program_agent.py            UPDATED — constructor accepts instructions
│   ├── employability_agent.py      UPDATED — constructor accepts instructions
│   ├── accommodation_agent.py      UPDATED — constructor accepts instructions
│   ├── news_agent.py               UPDATED — constructor accepts instructions
│   ├── forum_agent.py              UPDATED — constructor accepts instructions
│   ├── scoring_agent.py            UPDATED — constructor accepts instructions
│   ├── alternatives_agent.py       UPDATED — constructor accepts instructions
│   └── conversation_agent.py       UPDATED — constructor accepts instructions
│
├── services/
│   └── research_handler.py         UPDATED — scans skills/ at startup
│
├── ui/
│   └── app.py                      unchanged
│
└── main.py                         unchanged
```

---

## 7. The Eleven SKILL.md Files

Create these files exactly. They are the operational specification for each
agent's research behaviour. Edit them freely as the system matures — no Python
changes required.

---

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

You are the first agent to run. Every other agent depends on the career context
you establish. Research thoroughly before returning.

## What to research

- Realistic career paths a graduate of this course typically enters
- Salary ranges for those careers in the university's country (not global)
- A snapshot of live job postings that match those careers (10–15 postings minimum)
- In-demand skills extracted from the postings — these inform what makes a
  graduate employable, not just what the course teaches

## Query construction

Always include: [course] + [career/jobs/salary] + [country]
Never query on [university name] alone — career paths are course-level, not
institution-level.

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
- "University of Manchester graduate employability ranking"

## Date filter

Rankings change annually. Use the most recent published edition only.
Confirm the year of any ranking cited. Do not mix years.

## What to return

- Subject ranking: position, ranking body, year, source URL
- Overall ranking: position, ranking body, year, source URL
- Graduate employability ranking: position, ranking body, year, source URL
- Where rankings differ significantly across bodies, note this and explain why

## Confidence handling

If no subject-specific ranking is found for this course at this university:
- Set confidence: low
- Return overall ranking only with a clear note that subject ranking was unavailable
- Do not substitute a general department rank for a subject rank

The ScoringAgent will down-weight this dimension if confidence is low.
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

- Available undergraduate programs matching the course name (there may be
  multiple — e.g. BSc Computer Science, BSc Computer Science with AI,
  MEng Computer Science)
- Specialisations or pathways within the program
- Core modules in years 1 and 2 (these are fixed and reveal the program's
  actual content)
- Optional modules and electives (these reveal the program's breadth)
- Duration in years
- Delivery format: full-time, part-time, sandwich year, study abroad option
- Any program features directly relevant to career outcomes from board.career

## Query construction

Always include: [university name] + [course] + undergraduate

Examples:
- "University of Manchester Computer Science undergraduate program modules"
- "University of Manchester BSc Computer Science course structure 2024"
- "University of Edinburgh Psychology undergraduate pathways"

## Date filter

Program content can change yearly. Use current academic year only.
Check for a "2024/25" or "2025/26" course page — prefer the official
university catalog page over third-party summaries.

## What to return

- List of matching undergraduate programs with full titles
- For the best-matched program: core modules yr1, core modules yr2, electives
- Duration, delivery options (sandwich year? study abroad?)
- Any curriculum elements that map to in-demand skills from board.career
- Official source URL for the course catalog page

## Quality bar

Do not describe the program in marketing language. Return factual module
names and structure. If the course catalog is behind a login or not
accessible, note this and return what is publicly available.
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

Read board.career before beginning any searches. The career paths, in-demand
skills, and job posting data already collected there define what counts as a
relevant graduate outcome. Your job is to find evidence that this university's
graduates actually reach those careers.

## What to research

- Graduate employment rate (% employed within 6 months of graduation, if available)
- Industries and companies that graduates from this course enter — country-scoped
- Direct evidence of graduates in the career paths from board.career
  (LinkedIn profiles, alumni spotlights, company recruitment pages)
- Industry partnerships specific to the department (placement schemes, sponsored
  projects, named employer relationships)
- Graduate salary data specific to this university if available — compare to
  the ranges in board.career

## Query construction

Always include: [university name] + [course] + graduates/employment/alumni
Always scope to the university's country.

Examples:
- "University of Manchester Computer Science graduates employment rate"
- "University of Manchester CS alumni careers LinkedIn"
- "Manchester Computer Science industry partners placement"
- "site:linkedin.com University of Manchester Computer Science graduate"

## Date filter

Employment statistics older than 2 years are not acceptable. Graduate profiles
may be older but must be identified as such.

## What to return

- Employment rate: figure, source, year
- Top industries entered: ranked by frequency if data supports it
- Named companies known to recruit from this program
- Alumni trajectory examples (paraphrased — never reproduce profile text)
- Industry partnerships: company names, nature of partnership
- Sources: URL + date for every data point

## Quality bar

Generic statements like "graduates go on to successful careers" are not
acceptable output. Return evidence — named companies, named programs,
percentage figures with sources.
```

---

### `skills/accommodation/SKILL.md`

```markdown
---
key: accommodation
name: Accommodation Agent
description: Researches on-campus and off-campus accommodation costs, area safety, and transport access for the university.
tool_budget: 6
section_name: accommodation
---

## What to research

- On-campus accommodation: cost range per week, what is included (bills, meals)
- Off-campus private accommodation: typical rent range per month in the
  university's city/area (not national averages)
- Area safety: crime statistics or student safety reputation for the campus
  area specifically
- Public transport: routes and journey time from student accommodation areas
  to campus

## Query construction

Always include: [university name] + [accommodation/rent/safety]
For off-campus costs, include the city name, not just the university name.

Examples:
- "University of Manchester student accommodation cost 2024"
- "Manchester city centre student rent per month 2024"
- "University of Manchester campus area safety crime rate"
- "Manchester student transport campus bus tram"

## Date filter

Rental costs and safety data: 2-year filter applies strictly.
Transport routes: use current timetable information.

## What to return

- On-campus cost range: weekly cost, what is included, application deadline
  if relevant
- Off-campus cost range: monthly rent, area of city, bills typically separate
- Area safety summary: factual — cite crime statistics or official sources,
  not forum opinions
- Transport: named routes, frequency, journey time to campus
- Sources: URL + date

## Quality bar

Do not conflate city cost of living with student accommodation costs. Return
student-specific figures. If on-campus accommodation is fully allocated and
most students live off-campus, state this clearly.
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

## What to research

- Institutional news: strikes, leadership changes, funding announcements,
  controversies, award wins, rankings changes, closures, new buildings
- Department-specific news: events, research breakthroughs, grant wins,
  staff departures, course changes — these carry more weight than
  institutional news for a parent's decision

## Sentiment classification

Classify each news item as:
- positive: award, grant, investment, ranking improvement, new facility
- negative: strike, controversy, scandal, funding cut, course closure
- neutral: leadership change, restructure, policy update

Neutral is not a default — it requires an actual neutral item.

## Query construction

Always include: [university name] + [news/announcement]
For department news: [university name] + [course/department] + news

Examples:
- "University of Manchester news 2024"
- "University of Manchester Computer Science department news 2024"
- "University of Manchester strike controversy 2023 2024"

## Date filter

This is the strictest date filter in the pipeline. Discard any item
older than 2 years from today without exception. Items without a
clear publication date are discarded.

## What to return

- List of news items: headline (paraphrased), sentiment, source URL, date
- Department-specific items flagged separately — they carry more weight
- If no department-specific news is found, state this explicitly
- If all news is neutral or positive, note this as a positive signal
- If negative items dominate, summarise the pattern

## Quality bar

Do not summarise the university's general reputation. Return only
news items with a source URL and date. Opinion pieces and rankings
commentary are not news items.
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

## Sources

Search these platforms in order. Do not substitute other sources.

1. `site:reddit.com` — r/UniUK, r/AskUK, university subreddits
2. `site:thestudentroom.co.uk` — course-specific threads
3. `site:thegradcafe.com` — applicant and student discussion
4. `site:quora.com` — student experience questions

## Query construction

Always: [university name] + [course name] + [signal type]

Examples:
- "site:reddit.com University of Manchester Computer Science student experience"
- "site:thestudentroom.co.uk University of Manchester Computer Science review"
- "site:reddit.com Manchester CS course quality teaching"
- "site:quora.com University of Manchester Computer Science worth it"

## Signal weighting

Weight signals in this order:
1. Current student (enrolled now) — highest weight
2. Recent graduate (graduated within 2 years) — high weight
3. Former student (graduated 2–4 years ago) — medium weight
4. Prospective student asking questions — lowest weight, treat as anecdote only

## Qualification threshold

A recurring positive or concern must appear across 3 or more independent
sources to qualify as a finding. One enthusiastic post does not make a
positive. One complaint does not make a concern.

## Date filter

Discard posts older than 2 years from today without exception.

## What to return

- Recurring positives: 3+ sources required, paraphrased, source + year each
- Recurring concerns: 3+ sources required, paraphrased, source + year each
- Department-specific feedback: anything about teaching quality, lecturers,
  course content, labs, support — flagged as higher signal
- If no course-specific threads are found: return empty with explanation.
  Do not substitute generic university threads.

## What not to return

- Verbatim quotes from forum posts — paraphrase only
- Single-source opinions presented as patterns
- Posts about other courses at the same university
- Posts about the university's social life unless directly linked to
  the course experience
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

You receive the full blackboard — all 7 research sections — and produce a
score. You do not search. You do not call tools. You synthesise.

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

Score each dimension from 0 to 10. Provide a 1–2 sentence rationale per
dimension explaining the score. The rationale must cite specific evidence
from the blackboard — not generic statements.

Down-weight any dimension where the corresponding blackboard field has
confidence: low. A low-confidence score should not carry the same weight
as a fully evidenced one. Flag the gap explicitly in your output.

A missing section (board field is None) is not the same as a low score.
A missing section means the dimension cannot be scored — weight is
redistributed to the remaining dimensions proportionally. Flag every
missing section in the output.

## Tiered recommendation

Calculate a weighted overall score. Map to a tier:

| Score | Tier |
|---|---|
| 7.5 – 10 | Strong Consider |
| 5.5 – 7.4 | Consider |
| 3.5 – 5.4 | Proceed with Caution |
| 0 – 3.4 | Avoid |

The tier is a recommendation, not a verdict. It must be accompanied by
the top 3 reasons supporting it and the top 3 concerns to investigate
further — drawn from the evidence, not invented.

## Weaknesses output

Return a `weaknesses` list of the 2–3 dimensions where the score is
lowest relative to expectation. This list feeds directly into
AlternativesAgent — it uses these weaknesses to select alternatives
that address the specific gaps.

Be specific: "Subject ranking not found — confidence low" is better
than "ranking data weak". The alternatives agent reads this list
verbatim.
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

Read board.score.weaknesses before beginning any searches. The alternatives
you find must directly address the gaps identified there. Do not suggest
alternatives based on general reputation — target the weaknesses.

## Selection criteria

- Same course, undergraduate only
- Same country as the primary university, or a country the user's parent
  would consider equivalent (use country from ResearchContext)
- The alternative must demonstrably perform better on the identified weakness
  dimensions — cite the evidence

## For each alternative, research

- Subject-specific ranking (the dimension most often in weaknesses)
- Brief program note: does the course structure address the gap?
- One-line employability note: evidence of outcomes in the careers from
  board.career
- Why this alternative addresses the specific weakness — this must be
  explicit and evidenced, not implied

## Query construction

Target the weakness dimensions specifically.

Examples (if weakness is "subject ranking not found"):
- "QS Computer Science ranking UK universities 2024"
- "top Computer Science universities UK subject ranking 2024"

Examples (if weakness is "forum sentiment concerns about teaching quality"):
- "UK Computer Science universities student satisfaction teaching quality"
- "site:thestudentroom.co.uk Computer Science best teaching UK university"

## What to return

2–3 alternatives. For each:
- University name and country
- Why it addresses the primary's weakness (specific evidence required)
- Subject ranking: position, body, year
- Program note: one sentence on curriculum fit
- Employability note: one sentence on graduate outcomes
- Source URL for each claim

## Quality bar

An alternative with no evidence that it addresses the weakness is not
acceptable. If research returns no suitable alternatives, return an empty
list with explanation rather than invent weak suggestions.
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

The research pipeline has completed. The parent is reading the report and
asking follow-up questions. You answer from what was found — not from
general knowledge, not from new searches.

## What you can answer

Any question that can be answered from the blackboard contents:
- Elaboration on any section (forum concerns, accommodation details,
  specific ranking positions, career salary ranges)
- Comparisons between the primary university and the alternatives
  in board.alternatives
- Explanation of the scoring rationale from board.score
- Questions about what was and was not found during research

## What you must not do

- Search for new information
- Answer questions about topics not covered in the research
  (e.g. visa requirements, postgraduate options, other universities
  not in board.alternatives)
- Present general knowledge as if it came from the research

## When you cannot answer

If a question requires information not present on the blackboard, say so
clearly: "The research didn't cover this — you would need to check directly
with the university." Do not guess. Do not substitute general knowledge.

## Tone

You are speaking to a parent making a real decision about their child's
future. Be direct, factual, and honest about what the research found and
what it didn't. Do not oversell the report. If a section had low confidence
or was missing, say so when it is relevant to the question.

## Scope boundaries

- Study level: undergraduate only — hardcoded, never change this
- Timeframe: the research is a point-in-time snapshot; say so if the parent
  asks about current availability or this year's entry requirements
- Accuracy: the report summarises research, it does not verify facts —
  tell the parent to confirm critical decisions directly with the university
```

---

## 8. How `ResearchHandler` Changes

`services/research_handler.py` gains one responsibility: loading all skills at
startup before constructing agents. This happens once when the handler is
initialised — not per request.

```python
# services/research_handler.py (startup changes only)

from pathlib import Path
from core.skill_loader import scan_skills_dir, SkillMeta
from dataclasses import dataclass, field

@dataclass
class _EmptySkill:
    """Sentinel used when a SKILL.md is missing for an agent key."""
    instructions: str = ""
    tool_budget: int = 0
    description: str = ""

_EMPTY = _EmptySkill()


class ResearchHandler:
    def __init__(self) -> None:
        # Load all skill files once at startup.
        # Missing files produce warnings, not errors.
        skills: dict[str, SkillMeta] = scan_skills_dir(Path("skills"))

        def _get(key: str) -> SkillMeta | _EmptySkill:
            skill = skills.get(key)
            if skill is None:
                logger.warning(
                    "research_handler | no SKILL.md for %r — agent will use base prompt", key
                )
            return skill or _EMPTY

        # Construct all agents with their loaded instructions.
        # Pipeline mechanics (handle(), blackboard writes, message publishing)
        # are unchanged — only the instructions argument is new.
        self._career_agent       = CareerAgent(instructions=_get("career").instructions)
        self._background_agent   = BackgroundAgent(instructions=_get("background").instructions)
        self._rankings_agent     = RankingsAgent(instructions=_get("rankings").instructions)
        self._program_agent      = ProgramAgent(instructions=_get("program").instructions)
        self._employability_agent = EmployabilityAgent(instructions=_get("employability").instructions)
        self._accommodation_agent = AccommodationAgent(instructions=_get("accommodation").instructions)
        self._news_agent         = NewsAgent(instructions=_get("news").instructions)
        self._forum_agent        = ForumAgent(instructions=_get("forum").instructions)
        self._scoring_agent      = ScoringAgent(instructions=_get("scoring").instructions)
        self._alternatives_agent = AlternativesAgent(instructions=_get("alternatives").instructions)
        self._conversation_agent = ConversationAgent(instructions=_get("conversation").instructions)

        logger.info("research_handler | agents constructed with skill instructions")
```

The `handle_request()` method and all subscription logic are unchanged from
MASTER.md. Only `__init__` gains the skill loading block above.

---

## 9. What Goes in `_base_prompt()` vs SKILL.md

This is the critical discipline. Get it wrong and either the Python becomes
hard to maintain (too much domain knowledge) or the skill file becomes
unreliable (too much structural context in markdown that might drift).

**`_base_prompt()` in Python — structural context only:**

```python
# agents/forum_agent.py

def _base_prompt(self) -> str:
    return (
        "You are the Forum Research Agent in a university research pipeline.\n"
        "You subscribe to CareerResearchCompletedMessage.\n"
        "You write your findings to deps.board.forum as a ForumOutput.\n"
        "You fire SectionCompletedMessage(section_name='forum') on success "
        "or SectionFailedMessage on failure.\n"
        "Your tool budget is enforced by the pipeline — stop when you reach it."
    )
```

This never changes. It describes the agent's structural role in the pipeline.

**SKILL.md body — everything else:**

- What to search for
- How to construct queries
- What sources to use and in what order
- What to discard and why
- How to assess signal quality
- What the output must contain
- Edge case handling

This changes as the system is tuned. No Python edit required.

---

## 10. Startup Log Sequence

When `ResearchHandler` initialises, the following log lines must appear in
this order:

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

Files load in alphabetical order (from `sorted(skills_dir.iterdir())`).
If any file is missing, a warning appears instead of its load line:

```
skill_loader | cannot read skills/forum/SKILL.md: [Errno 2] No such file or directory
research_handler | no SKILL.md for 'forum' — agent will use base prompt
```

The app does not crash. ForumAgent runs with base prompt only. All other
agents are unaffected.

---

## 11. Unit Tests for `core/skill_loader.py`

Create `tests/test_skill_loader.py`:

```python
import pytest
from pathlib import Path
from core.skill_loader import load_skill, scan_skills_dir, SkillMeta


# ── load_skill tests ──────────────────────────────────────────────────────────

def test_load_skill_valid(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text(
        "---\n"
        "key: forum\n"
        "name: Forum Agent\n"
        "description: Researches forums.\n"
        "tool_budget: 10\n"
        "section_name: forum\n"
        "---\n\n"
        "## Instructions\nSearch reddit carefully.\n"
    )
    skill = load_skill(f)
    assert skill is not None
    assert skill.key == "forum"
    assert skill.tool_budget == 10
    assert skill.section_name == "forum"
    assert "Search reddit carefully." in skill.instructions


def test_load_skill_no_section_name(tmp_path):
    """Agents like scoring and conversation have no section_name."""
    f = tmp_path / "SKILL.md"
    f.write_text(
        "---\n"
        "key: scoring\n"
        "name: Scoring Agent\n"
        "description: Scores the research.\n"
        "tool_budget: 0\n"
        "---\n\n"
        "Score carefully.\n"
    )
    skill = load_skill(f)
    assert skill is not None
    assert skill.section_name is None


def test_load_skill_missing_frontmatter(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("No frontmatter here at all.")
    assert load_skill(f) is None


def test_load_skill_missing_required_field(tmp_path):
    f = tmp_path / "SKILL.md"
    # Missing 'description'
    f.write_text(
        "---\nkey: foo\nname: Foo\ntool_budget: 5\n---\n\nbody\n"
    )
    assert load_skill(f) is None


def test_load_skill_tool_budget_not_integer(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text(
        "---\n"
        "key: forum\nname: Forum\ndescription: x\ntool_budget: many\n"
        "---\n\nbody\n"
    )
    assert load_skill(f) is None


def test_load_skill_malformed_yaml(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("---\nkey: [unclosed\n---\nbody\n")
    assert load_skill(f) is None


def test_load_skill_unreadable_file(tmp_path):
    result = load_skill(tmp_path / "nonexistent.md")
    assert result is None


# ── scan_skills_dir tests ─────────────────────────────────────────────────────

def _make_skill(base: Path, key: str, budget: int = 5) -> None:
    d = base / key
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\nkey: {key}\nname: {key.title()}\n"
        f"description: Does {key}.\ntool_budget: {budget}\n---\n\ninstructions\n"
    )


def test_scan_skills_dir_returns_all_valid(tmp_path):
    _make_skill(tmp_path, "forum", 10)
    _make_skill(tmp_path, "career", 8)
    result = scan_skills_dir(tmp_path)
    assert set(result.keys()) == {"forum", "career"}


def test_scan_skills_dir_skips_missing_skill_md(tmp_path):
    d = tmp_path / "empty_agent"
    d.mkdir()
    # No SKILL.md inside
    result = scan_skills_dir(tmp_path)
    assert result == {}


def test_scan_skills_dir_nonexistent_dir(tmp_path):
    result = scan_skills_dir(tmp_path / "does_not_exist")
    assert result == {}


def test_scan_skills_dir_deduplicates_same_key(tmp_path):
    """Two folders with the same key in frontmatter — first wins."""
    for folder in ("folder_a", "folder_b"):
        d = tmp_path / folder
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nkey: forum\nname: Forum\n"
            "description: x.\ntool_budget: 5\n---\n\nbody\n"
        )
    result = scan_skills_dir(tmp_path)
    assert len(result) == 1
    assert "forum" in result
```

Run:

```bash
pytest tests/test_skill_loader.py -v
```

Expected: all tests pass.

---

## 12. Integration into Development Stages

The skill loader is not a separate stage — it is woven into Stage 1a from the
MASTER.md development plan. The integration points are:

**Stage 1a — add alongside core infrastructure:**

- Create `core/skill_loader.py` from Section 4 exactly.
- Create the `skills/` directory.
- Create all 11 `SKILL.md` files from Section 7.
- Write and pass `tests/test_skill_loader.py` from Section 11.
- Confirm the scan manually:

```python
from pathlib import Path
from core.skill_loader import scan_skills_dir
skills = scan_skills_dir(Path("skills"))
print(sorted(skills.keys()))
# Expected: ['accommodation', 'alternatives', 'background', 'career',
#            'conversation', 'employability', 'forum', 'news',
#            'program', 'rankings', 'scoring']
```

**Stage 1c — update `BaseAgent` before writing `CareerAgent`:**

- Add `instructions` field and `_build_system_prompt()` pattern to `base_agent.py`
  as shown in Section 5.
- Update `ResearchHandler.__init__` to load skills before constructing agents
  as shown in Section 8.
- `CareerAgent` is the first agent written — verify that its skill instructions
  appear in its system prompt before any other agent is built.

```python
# Quick verification — CareerAgent contains its SKILL.md body:
from pathlib import Path
from core.skill_loader import scan_skills_dir
from agents.career_agent import CareerAgent

skills = scan_skills_dir(Path("skills"))
agent = CareerAgent(instructions=skills["career"].instructions)
prompt = agent._build_system_prompt()
assert "salary ranges" in prompt   # text from skills/career/SKILL.md
assert "board.career" in prompt    # text from CareerAgent._base_prompt()
```

Every subsequent agent follows the same verification pattern — the system prompt
must contain both the structural base and the SKILL.md instructions.

**Stage 2a — each new agent is built with instructions from the start:**

No retrofitting. Each section agent is written with the `instructions` constructor
argument and `_build_system_prompt()` injection already in place. The skill file
for each agent is already written (Stage 1a) — it just begins producing observable
effect as the agent is activated.

---

## 13. Why `tool_budget` Is in the Frontmatter

MASTER.md defines tool call budgets per agent as constants (e.g. ForumAgent: 8–10).
Those constants currently live either in the system prompt string or as Python
class attributes.

Putting `tool_budget` in the frontmatter means:

- The budget is machine-readable and co-located with the instructions that
  reference it. The skill file says "your budget is 10" and the instruction
  body tells the agent what to do within that budget — they are consistent
  by construction.
- `ResearchHandler` can read the budget from `skill.tool_budget` and pass it
  to the agent constructor as a validated integer rather than trusting that the
  prompt string and the Python constant agree.
- Changing a budget requires editing one file — the SKILL.md — not finding and
  updating both a constant and a prompt string.

The agent constructor accepts both:

```python
class ForumAgent(BaseAgent):
    def __init__(self, instructions: str = "", tool_budget: int = 10) -> None:
        super().__init__(instructions=instructions)
        self.tool_budget = tool_budget
```

And `ResearchHandler` passes both from the loaded skill:

```python
skill = _get("forum")
self._forum_agent = ForumAgent(
    instructions=skill.instructions,
    tool_budget=skill.tool_budget if skill.tool_budget else 10,
)
```

---

## 14. New Dependency

`pyyaml` is the only new dependency introduced by this specification.

```
# requirements.txt — add to existing:
pyyaml
```

After adding:

```bash
pip install pyyaml
pip freeze > requirements.txt
```

`pyyaml` is a pure Python package with no binary extensions. No platform issues.

---

## 15. Troubleshooting

**Skill file not loaded — warning in logs**

Confirm the file is named exactly `SKILL.md` (case-sensitive on Linux/macOS).
Confirm the YAML frontmatter is delimited by `---` on its own line at the top
and after the last field. Any YAML parse error causes the file to be skipped —
check logs for `skill_loader | ... YAML parse error`.

**Agent running without instructions despite SKILL.md existing**

Check that `ResearchHandler.__init__` calls `scan_skills_dir` before constructing
agents. If skills are loaded after agent construction, the agents receive empty
instructions. The startup log should show `skill_loader | loaded ...` lines
appearing before `research_handler | agents constructed`.

**`_build_system_prompt()` returns base prompt only**

Confirm `instructions` is non-empty. Print `agent.instructions` immediately after
construction — if it is an empty string, the SKILL.md either failed to load or
the wrong key was used in the `skills.get()` call. Key must match the folder name
and the `key:` field in frontmatter exactly.

**`tool_budget` in frontmatter is being ignored**

Confirm `research_handler.py` passes `tool_budget=skill.tool_budget` to the agent
constructor. If only `instructions` is passed, the budget falls back to the Python
default. Add a log line in the agent constructor to confirm:
`logger.info("%s | tool_budget=%d", self.__class__.__name__, self.tool_budget)`

**SKILL.md edits have no effect at runtime**

Skill files are loaded once at startup. Changes to SKILL.md require a process
restart. In development with `--reload`, touching any Python file will trigger
a reload — but if only the markdown file changes, the watcher may not trigger.
Restart explicitly after editing a skill file.

---

## 16. Done When

- `core/skill_loader.py` exists and all unit tests in `tests/test_skill_loader.py` pass
- All 11 `SKILL.md` files exist under `skills/`
- `scan_skills_dir(Path("skills"))` returns all 11 keys
- `ResearchHandler.__init__` loads skills before constructing any agent
- Startup logs show all 11 skill files loaded before `agents constructed`
- Every agent's `_build_system_prompt()` returns a string containing both
  the base structural prompt and the SKILL.md body
- Changing any SKILL.md and restarting produces different agent behaviour
  with no Python file changes
- Removing any SKILL.md produces a warning log and the agent continues
  running on base prompt — no crash, no silent failure
- All MASTER.md Stage 1a verification steps pass unchanged

---

*End of Skill-Loader Specification*