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
from __future__ import annotations1

from pydantic import BaseModel, Field
from typing import Literal

from schemas.job_posting import JobPosting  # shared schema — also used by adzuna_tool and mcf_tool


class CareerPath(BaseModel):
    title: str = Field(
        description=(
            "The job title graduates from this course typically enter. "
            "Use the title as it appears in job postings and industry usage — "
            "not a generic category. "
            "Examples: 'Software Engineer', 'Data Analyst', 'Mechanical Design Engineer'. "
            "Do not write broad sectors like 'Technology' or 'Engineering' — "
            "name the specific role."
        )
    )
    description: str = Field(
        description=(
            "2–4 sentences describing the typical responsibilities of this role and "
            "how graduates progress within it. "
            "Include: what the day-to-day work involves, the typical seniority progression "
            "(e.g. graduate → mid-level → senior over how many years), and any "
            "industry-specific context relevant to the university's country. "
            "Do not describe the course — describe the career. "
            "Example: 'Software Engineers design, build, and maintain software systems. "
            "In the UK, graduates typically start on junior roles and reach mid-level "
            "within 2–3 years. Specialisations include backend, frontend, and DevOps.'"
        )
    )
    typical_companies: list[str] = Field(
        description=(
            "Named employers in the university's country that hire graduates into this role. "
            "Must be real, identifiable company names — not generic sectors or size descriptors. "
            "Examples: ['Google', 'Amazon', 'HSBC', 'Accenture', 'NHS Digital']. "
            "Do not write: 'large tech companies', 'banks', 'public sector'. "
            "Minimum 3 named employers per path. "
            "Scope strictly to the country from context — UK employers for UK universities, "
            "Australian employers for Australian universities."
        )
    )


class SalaryRange(BaseModel):
    career_path: str = Field(
        description=(
            "The job title this salary range applies to — must exactly match a `title` "
            "value in the `career_paths` list. One SalaryRange entry per CareerPath. "
            "Do not create salary entries for career paths not in career_paths."
        )
    )
    entry_level: str = Field(
        description=(
            "Typical salary range for a graduate or junior in this role (0–3 years experience) "
            "in the university's country, in local currency. "
            "Format as a range string: '£28,000–£35,000', 'AUD 70,000–AUD 85,000'. "
            "Do not use a single figure — always a range. "
            "Do not convert to another currency. "
            "Source from a salary survey or job posting data dated within 2 years. "
            "If entry-level data is unavailable, write 'Not available' — do not fabricate."
        )
    )
    mid_level: str = Field(
        description=(
            "Typical salary range for a mid-level professional in this role "
            "(3–7 years experience) in local currency. "
            "Same format as entry_level. "
            "Write 'Not available' if not found — do not estimate from entry_level."
        )
    )
    senior_level: str = Field(
        description=(
            "Typical salary range for a senior professional in this role "
            "(7+ years experience) in local currency. "
            "Same format as entry_level. "
            "Write 'Not available' if not found."
        )
    )
    currency: str = Field(
        description=(
            "ISO 4217 currency code for all salary figures in this entry. "
            "Examples: 'GBP' (UK), 'AUD' (Australia), 'SGD' (Singapore), "
            "'USD' (USA), 'MYR' (Malaysia). "
            "Must match the university's country — do not use USD for a UK university. "
            "This field allows the report renderer to format figures correctly "
            "without guessing from the country name."
        )
    )
    country: str = Field(
        description=(
            "The country these salary figures apply to. "
            "Must exactly match `deps.context.country`. "
            "This is a consistency check — if the country here differs from context, "
            "the salary data was scoped incorrectly."
        )
    )


class CareerSource(BaseModel):
    url: str = Field(
        description=(
            "Full URL of the source page used for career path or salary research. "
            "Must be a real, resolvable URL. Do not truncate or paraphrase. "
            "Do not include job board listing pages (Indeed, LinkedIn, Reed) — "
            "these are accessed via adzuna_jobs or mcf_jobs, not tavily_search. "
            "Acceptable sources: salary surveys (e.g. Glassdoor, Payscale, "
            "Reed salary guide), government labour statistics, industry association "
            "reports, graduate destinations reports."
        )
    )
    date: str = Field(
        description=(
            "Publication or last-updated date of the source in YYYY-MM-DD format. "
            "If only month and year are available, use YYYY-MM. "
            "Only include sources dated within the last 2 years — discard older ones. "
            "Use 'unknown' only if no date is visible anywhere on the page. "
            "Never fabricate a date."
        )
    )
    type: str = Field(
        description=(
            "Category of the source. Must be one of: "
            "'salary_survey' (a dedicated salary benchmarking report or page), "
            "'industry_report' (a sector body or professional association publication), "
            "'job_board' (aggregated job posting data — not individual listings), "
            "'government_statistics' (official labour market data, e.g. ONS, ABS). "
            "Choose the single best-fitting category."
        )
    )


class CareerOutput(BaseModel):
    career_paths: list[CareerPath] = Field(
        description=(
            "The most common graduate career paths from this course at this university, "
            "scoped to the university's country. "
            "Minimum 3 paths required. Maximum 6 — prioritise the most common. "
            "Each path must represent a distinct role, not a variation of the same title. "
            "Prefer paths confirmed by named graduate destination sources or job posting "
            "volume — not inferred from the course name alone. "
            "If fewer than 3 paths can be confirmed from search results, set "
            "confidence to 'low' and explain in notes."
        )
    )
    salary_ranges: list[SalaryRange] = Field(
        description=(
            "One SalaryRange entry for every CareerPath in career_paths. "
            "The career_path field on each SalaryRange must match a title in career_paths exactly. "
            "All salary figures must be in the university's local currency. "
            "Source from salary surveys or job posting data — not from training knowledge. "
            "If a salary range cannot be confirmed from a live source for a particular path, "
            "write 'Not available' for that level rather than omitting the entry."
        )
    )
    job_postings: list[JobPosting] = Field(
        description=(
            "Live job postings retrieved from adzuna_jobs (UK/Australia) or mcf_jobs "
            "(Singapore). These are real postings returned by the tool — do not fabricate "
            "postings from search snippets or training knowledge. "
            "Minimum 10 postings. Target 10–15. "
            "Pass the postings through from the tool response directly — do not filter "
            "or summarise the tool output before writing it here. "
            "If the job posting tool returns fewer than 10 results, include all returned "
            "and note the low volume in notes."
        )
    )
    in_demand_skills: list[str] = Field(
        description=(
            "Top 5–8 skills appearing most frequently across the job postings in "
            "job_postings. Extract from the description and skills fields of each posting. "
            "Include both technical skills (programming languages, tools, frameworks) "
            "and soft skills only if they appear in multiple independent postings. "
            "Deduplicate and normalise: 'Python', 'python', and 'Python 3' → 'Python'. "
            "These skills are read by ProgramAgent to build curriculum-to-career mappings — "
            "be specific (e.g. 'machine learning' not 'AI skills')."
        )
    )
    country_scope: str = Field(
        description=(
            "The country used to scope all salary, employer, and job posting searches "
            "in this run. Copy exactly from deps.context.country — do not derive or "
            "normalise it. "
            "This field is read by downstream agents (EmployabilityAgent) to confirm "
            "they are using the same country scope without re-deriving it from context. "
            "Example: 'UK', 'Australia', 'Singapore'."
        )
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "Researcher's assessment of overall output reliability. "
            "'high': 5 or more independent sources confirm career paths and salary ranges; "
            "10+ job postings retrieved; all career paths have confirmed named employers. "
            "'medium': 3–4 sources; some salary levels missing; job posting volume low "
            "but at least 5 retrieved. "
            "'low': fewer than 3 career paths confirmed; salary data unavailable or "
            "older than 2 years; job posting tool returned 0 results."
        )
    )
    sources: list[CareerSource] = Field(
        description=(
            "All URLs used for career path and salary research in this run. "
            "Every URL used as a source for career_paths or salary_ranges must appear here. "
            "Do not include individual job posting URLs — those are captured in job_postings. "
            "Minimum 2 sources expected for confidence 'high' or 'medium'. "
            "If fewer than 2 sources were found, set confidence to 'low'."
        )
    )
    notes: str = Field(
        description=(
            "Operational caveats, data gaps, or edge cases encountered during research. "
            "Write an empty string '' if there are no caveats. "
            "Examples: 'Salary data for Data Analyst role not found for Australia — "
            "US figures were excluded rather than substituted.', "
            "'Job posting tool returned only 6 results for Singapore — low market volume "
            "for this course.', "
            "'Course name is interdisciplinary — career paths were derived from the "
            "two most common specialisation streams.' "
            "Do not use this field to repeat information already captured in other fields."
        )
    )
```

**Why `JobPosting` is imported from `schemas/job_posting.py` not defined here:**
`adzuna_tool` and `mcf_tool` both return `JobPostingsResponse` containing `JobPosting`
instances from `schemas/job_posting.py`. `CareerAgent` receives those postings and
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

import traceback
from datetime import datetime
from pydantic import ValidationError
from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.career_output import CareerOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search
from tools.adzuna_tool import adzuna_jobs
from tools.mcf_tool import mcf_jobs


class CareerAgent(BaseAgent):
    """Phase 1 agent. Runs first, in isolation.

    Subscribes to: ResearchRequestedMessage
    Writes to:     board.career (CareerOutput)
    Fires:         CareerResearchCompletedMessage (unconditionally — even on failure)

    Tools: tavily_search (budget-capped), fetch_page (uncapped),
           adzuna_jobs (UK/AU), mcf_jobs (Singapore)

    Note: site: queries must not be passed to tavily_search — Tavily does not
    honour time_range filtering on site: prefixed queries. Use tavily_search to
    find URLs, then fetch_page to retrieve content from those URLs.
    """

    def __init__(self, instructions: str = "", tool_budget: int = 8) -> None:
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
                adzuna_jobs,
                mcf_jobs,
            ],
        )

        logger.info("CareerAgent | initialized")


    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.research_requested import ResearchRequestedMessage

        async def handler(message: ResearchRequestedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(ResearchRequestedMessage, handler)
        logger.info("CareerAgent | subscribed to MessageHub")

    def get_instruction(self) -> str:
        base = "You are the Career Research Agent in a university research pipeline."
        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def reset(self) -> None:
        """Reset per-request state. Called by ResearchHandler before each request."""
        self._calls_made = 0


    # ── Core handler ──────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        """Run career research and fire CareerResearchCompletedMessage.

        CareerResearchCompletedMessage is fired unconditionally in the finally
        block — even if the LLM call fails. If it is not fired, the entire
        downstream pipeline stalls because no section agent will receive its
        trigger message.
        """
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

        task_brief = (
            f"University: {deps.context.university_name}\n"
            f"Course: {deps.context.intended_course}\n"
            f"Country: {deps.context.country}\n"
            f"Study level: {deps.context.study_level}"
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.career = result.output

            logger.info(
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

        except ValidationError as exc:
            # LLM returned output that failed schema validation.
            # Log each field violation so the failing field is identifiable
            # without inspecting the raw LLM response.
            logger.error("CareerAgent | schema validation failed:")
            for err in exc.errors():
                logger.error(
                    "  field=%s  error=%s  input=%s",
                    err["loc"], err["msg"], err.get("input"),
                )

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career research produced invalid output: {exc.error_count()} field errors",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            # Catches: FallbackModel exhaustion, ModelHTTPError (429/404),
            # UnexpectedModelBehavior (thinking-model output retries exceeded),
            # tool errors, and any other unexpected failures.
            logger.error("CareerAgent | failed: %s", exc)
            traceback.print_exc()

            # FallbackModel wraps both sub-exceptions — unpack for visibility
            if hasattr(exc, "exceptions"):
                for i, sub in enumerate(exc.exceptions):
                    logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
                    traceback.print_exception(type(sub), sub, sub.__traceback__)

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career research failed: {exc}",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))

        finally:
            # Fire unconditionally. board.career will be None if an exception
            # was raised above. Section agents handle None career gracefully.
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
  before this rework. Five sources of truth for one rule is how instructions
  end up contradicting their own SKILL.md — duplicated instructions don't
  stay in sync.

The fix: `base` carries only agent identity — one sentence. Every domain
rule lives in `skills/career/SKILL.md` exactly once. `task_brief` carries
only per-request data values, not restated rules.

**Why `CareerResearchCompletedMessage` fires in `finally`, not in `try`:**
If the LLM call throws, `board.career` is `None`. The seven section agents
still need to run — they handle a `None` career gracefully, scoping their
own searches without career context. If the message never fires, the entire
pipeline stalls indefinitely. Moving it to `finally` guarantees it fires
regardless of outcome.

**Why `tavily_search`, `adzuna_jobs`, and `mcf_jobs` are registered directly,
not wrapped in a closure:** these are fully-formed pydantic-ai tool functions
with the correct `RunContext[Deps]` signature, docstring, and backing client.
Registering them directly means pydantic-ai surfaces the real function name
and docstring in the LLM tool call schema. A wrapper closure would shadow the
original name with an anonymous inner function, obscuring the tool schema.

---

## 1c.4 Exception Handling

`CareerAgent.handle()` uses a two-layer exception pattern. This pattern
is established here and carried identically into every agent in Stages 1d
and 1e. Understand it once — apply it everywhere.

---

### Why Two Separate Except Blocks

A single `except Exception` catches pydantic `ValidationError` but hides
which field failed. The most common runtime failure at this stage is the LLM
returning a field value that does not match the schema — wrong type, wrong
Literal value, or a missing required field. Without a dedicated `ValidationError`
block, the error log shows only the exception message with no field detail,
making it very difficult to know whether to fix the SKILL.md output rules,
the schema field description, or the prompt.

`ValidationError` is caught first (more specific), then `Exception` catches
everything else.

---

### Layer 1 — `ValidationError` (Schema Mismatch)

**When it fires:** pydantic raises `ValidationError` when the LLM's output
cannot be coerced into `CareerOutput`. Common causes:

| Field | Likely mismatch |
|---|---|
| `SalaryRange.currency` | LLM returns `"UK pounds"` instead of `"GBP"` |
| `CareerOutput.confidence` | LLM returns `"High"` instead of `"high"` (Literal case) |
| Any `list[...]` field | LLM returns `null` instead of `[]` |
| `CareerPath.typical_companies` | LLM returns a string instead of `list[str]` |

**What to do when it fires:**
1. Read the field log — it shows `field`, `error`, and `input` for each
   violation. The `input` value tells you exactly what the LLM returned.
2. Type mismatch (e.g. string for a list): tighten the Field description
   to state the expected type explicitly with an example.
3. Literal violation (e.g. `"High"` for `"high"`): add a note to the Field
   description that casing is significant and list the exact allowed values.
4. `null` for a list field: add a SKILL.md output rule stating the field
   must always be a list, even if empty (`[]`).

---

### Layer 2 — `Exception` (Everything Else)

**When it fires:** any error that is not a schema mismatch.

| Exception | Cause |
|---|---|
| `FallbackModel` exhaustion | Both primary and secondary models failed — read sub-exceptions |
| `ModelHTTPError` (429) | Rate limit hit — check which model via sub-exception |
| `ModelHTTPError` (404) | Model name wrong or deprecated |
| `UnexpectedModelBehavior` | Model exceeded output retry limit — usually a thinking-token model (e.g. deepseek-r1) producing malformed JSON |
| Tool error | `tavily_search`, `adzuna_jobs`, or `fetch_page` raised |

**What to do when it fires:**
1. `traceback.print_exc()` runs unconditionally — read the full stack trace
   before looking at the summary log line.
2. If `hasattr(exc, 'exceptions')` is True: it is a FallbackModel error.
   The first sub-exception is the primary model failure; the second is the
   secondary. Fix whichever is broken.
3. If `UnexpectedModelBehavior: Exceeded maximum output retries`: the model
   is a thinking/reasoning model wrapping output in `<think>` blocks. Switch
   to a non-thinking variant (e.g. `deepseek/deepseek-chat-v3-0324:free`
   instead of `deepseek/deepseek-r1`).
4. If a tool error: confirm the tool client was initialised before the agent
   ran — see Section 14 of the Master Reference.

---

### `finally` — Unconditional Message Fire

`CareerResearchCompletedMessage` fires in `finally`, not inside `try`.
This is the only agent where this matters — all other section agents fire
`SectionCompletedMessage` or `SectionFailedMessage`, and the quorum gate
counts both. `CareerAgent` has no quorum gate — if its completion message
is never published, the pipeline stalls permanently.

The `finally` block has no conditional logic. It fires regardless of whether
`board.career` is populated or `None`.

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
from core.skill_loader import scan_skills_dir
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

## 1c.6 `main.py` — CLI Entry Point

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

**Why `load_dotenv()` before any imports:** `tools/search_tool.py` reads
`TAVILY_API_KEY` from `os.environ` at module import time. If `.env` is not
loaded first, it raises `KeyError`. The import order in `main.py` enforces this:
`load_dotenv()` is called at the top, before the handler import chain pulls in
the tool modules.

**Why `async with fetch_client:` wraps the whole run:** `fetch_page` is
self-contained and opens its own connection on each call. Wrapping the entire
run here is an optimisation — it opens the `mcp-server-fetch` subprocess once
before any agent runs and keeps it alive for the whole request, so the first
`fetch_page` call doesn't pay subprocess-startup latency. Because `fastmcp.Client`
is ref-counted, every inner `async with fetch_client:` inside `fetch_page`
reuses the same session — only the outermost exit actually closes it.

---

## 1c.7 `schemas/messages/research_requested.py`

This message already exists from Stage 1a. Confirm it has `country` on it —
`CareerAgent`'s handler receives this and passes it to `ResearchContext`.

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
    from schemas.job_posting import JobPosting
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
Fix: add `RESEARCH_MODEL=google/gemma-3-27b-it:free` (or your chosen model) to `.env`.

**`EnvironmentError: OPENROUTER_API_KEY not set`**
Cause: OpenRouter key missing.
Fix: get a key at https://openrouter.ai and add `OPENROUTER_API_KEY=sk-or-...` to `.env`.

**`board.career is None` after run**
Two causes: (a) LLM call threw — check logs for `CareerAgent | failed` or
`CareerAgent | schema validation failed`; (b) schema mismatch — the LLM
returned JSON that failed pydantic validation. The `ValidationError` block
logs each field violation. Read those before touching any code.

**`CareerResearchCompletedMessage` fires but no section agents respond**
Expected at Stage 1c — section agents are not yet subscribed. The message
fires into an empty subscriber list, which is valid `MessageHub` behaviour.
The pipeline ends after `CareerAgent` completes.

**`KeyError: TAVILY_API_KEY` on startup**
Cause: `load_dotenv()` not called before the tool module import.
Fix: confirm `main.py` calls `load_dotenv()` as its first statement before
any project imports.

**`McpError` / connection failure from `fetch_page`**
Cause: the `mcp-server-fetch` subprocess failed to start.
Fix: confirm `pip install fastmcp mcp-server-fetch` succeeded and
`python -m mcp_server_fetch --help` works (see Stage 1b, Service 2).

**`UnexpectedModelBehavior: Exceeded maximum output retries`**
Cause: the configured model is a reasoning/thinking model (e.g. deepseek-r1)
that wraps output in `<think>` blocks, breaking pydantic-ai's structured
output parser.
Fix: switch to a non-thinking model variant — e.g.
`deepseek/deepseek-chat-v3-0324:free` instead of `deepseek/deepseek-r1`.

**`ValidationError` on a Literal field**
Cause: LLM returned `"High"` instead of `"high"`, or `"balanced "` with a
trailing space.
Fix: tighten the Field description for that field to include the exact
allowed values with a note that casing and whitespace are significant.

**LLM returns fewer than 3 career paths**
Not a bug — `confidence` is set to `"low"` and the gap is explained in
`notes`. This can happen for niche courses or sparse Tavily results.
Inspect `notes` and tune the SKILL.md query patterns if needed.

---

## Stage 1c Completion Checklist

- [ ] `schemas/outputs/career_output.py` — `CareerOutput`, `CareerPath`,
      `SalaryRange`, `CareerSource` implemented with `Field(description=...)`
      on every field; `JobPosting` imported from `schemas/job_posting.py`
      (not redefined here)
- [ ] `skills/career/SKILL.md` — frontmatter valid, `tool_budget: 8`,
      includes the "Tools" section with the job-posting routing table and
      the "Tool Usage Strategy" section
- [ ] `core/llm_factory.py` — `get_model()` reads from env, returns
      pydantic-ai model configured for OpenRouter + Gemini fallback
- [ ] `agents/career_agent.py` — `CareerAgent` implemented with
      `_calls_made = 0`, all four tools registered directly (no closure
      wrapper), `subscribe()`, `get_instruction()` (one-sentence base only),
      `handle()` with two-layer exception handling and `finally` block,
      `reset()`
- [ ] `services/research_handler.py` — minimal Stage 1c version — loads
      career skill, constructs `CareerAgent`, wires it, publishes trigger
- [ ] `main.py` — `load_dotenv()` first, wraps the run in
      `async with fetch_client:`, prints `board.career`
- [ ] `schemas/messages/research_requested.py` — `country` field confirmed present
- [ ] `schemas/messages/career_completed.py` — no-payload message confirmed
- [ ] `pytest tests/test_stage_1c.py -v -k "not populates_board and not fires_completed"`
      — 9 structural tests pass
- [ ] `pytest tests/test_stage_1c.py -v` — all 11 tests pass including LLM calls
- [ ] `python main.py` — `board.career` printed with real data, `confidence`
      is `"high"` or `"medium"` for University of Manchester Computer Science
- [ ] Stage 1b tests still pass: `pytest tests/test_stage_1b.py -v`

---

*End of Stage 1c Specification*