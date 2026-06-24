# Stage 1d — BackgroundAgent, RankingsAgent, ProgramAgent
## Implementation Specification

**Goal:** Three section agents are fully implemented, subscribe to
`CareerResearchCompletedMessage`, and populate their respective blackboard
fields from real data via a single CLI run.

**Ends with:** `python main.py` logs all three agents completing, and
`board.background`, `board.rankings`, and `board.program` are printed to
stdout with real data for the supplied university and course.

---

## What This Stage Builds and Why It Comes After 1c

Stage 1c established the exact agent pattern: pydantic-ai `Agent` with
`capabilities=[self._setup_telemetry_hooks()]`, `subscribe()` + `get_instruction()`,
`handle()` that resets `_calls_made`, a typed output schema, and a SKILL.md
carrying all domain knowledge.

Stage 1d applies that pattern to three section agents. These agents all share the
same tool set as `CareerAgent` (Tavily + Fetch), subscribe to the same trigger
message (`CareerResearchCompletedMessage`), run concurrently via `asyncio.gather()`,
and each write one blackboard field before firing `SectionCompletedMessage`.

The only structural difference from `CareerAgent`:
- They subscribe to `CareerResearchCompletedMessage`, not `ResearchRequestedMessage`
- They fire `SectionCompletedMessage(section_name=<field>)` on success and
  `SectionFailedMessage` on error, not `CareerResearchCompletedMessage`
- Their `handle()` can optionally read `deps.board.career` for context scoping

Getting these three right means Stage 1e (Employability, Accommodation, News)
is a direct repetition of the same pattern.

**What this stage builds:**

| File | Purpose |
|---|---|
| `schemas/outputs/background_output.py` | `BackgroundOutput` schema |
| `schemas/outputs/rankings_output.py` | `RankingsOutput` schema |
| `schemas/outputs/program_output.py` | `ProgramOutput` schema |
| `skills/background/SKILL.md` | Domain instructions for BackgroundAgent |
| `skills/rankings/SKILL.md` | Domain instructions for RankingsAgent |
| `skills/program/SKILL.md` | Domain instructions for ProgramAgent |
| `agents/background_agent.py` | BackgroundAgent class |
| `agents/rankings_agent.py` | RankingsAgent class |
| `agents/program_agent.py` | ProgramAgent class |
| `services/research_handler.py` | Updated — adds all three agents |
| `main.py` | Updated — prints all three board fields |

---

## 1d.1 Output Schemas

### `schemas/outputs/background_output.py`

`BackgroundOutput` is what `BackgroundAgent` writes to `board.background`.
It covers institutional facts: founding, size, status, research orientation,
course-specific accreditations, and named industry partnerships for the department.

```python
# schemas/outputs/background_output.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class AccreditationItem(BaseModel):
    body: str = Field(
        description=(
            "Full official name of the accrediting body. "
            "Example: 'BCS — The Chartered Institute for IT', "
            "'ABET', 'Engineering Council UK'. Never abbreviate without the expansion."
        )
    )
    scope: str = Field(
        description=(
            "Exact programmes or degrees covered by the accreditation. "
            "Example: 'BEng Computer Science', 'All undergraduate CS programmes'. "
            "Do not write 'all programmes' unless the source explicitly states that."
        )
    )
    year_listed: str = Field(
        description=(
            "Year the accreditation was granted or last confirmed as current. "
            "Use the 4-digit year string if available, e.g. '2023'. "
            "Use 'current' only when the source says it is active but gives no year. "
            "Never leave blank — use 'unknown' as a last resort."
        )
    )


class IndustryPartnership(BaseModel):
    partner: str = Field(
        description=(
            "Named company or organisation. Must be a real, identifiable entity. "
            "Do not write generic placeholders like 'a major bank' or 'tech company'. "
            "If the source names the partner, use that name exactly."
        )
    )
    nature: str = Field(
        description=(
            "Specific nature of the partnership with this department. "
            "Examples: 'sponsored final-year projects', 'graduate placement provider', "
            "'joint research lab', 'curriculum advisory board member'. "
            "Be specific — do not write 'collaboration' alone."
        )
    )
    department: str = Field(
        description=(
            "The specific school, department, or faculty this partnership covers. "
            "Example: 'School of Computer Science', 'Department of Electrical Engineering'. "
            "Do not write 'university-wide' unless the source confirms that scope."
        )
    )
    source_url: str = Field(
        description=(
            "Direct URL to the page where this partnership is documented. "
            "Must be a real, fetchable URL from the university website, company site, "
            "or credible news source. Do not fabricate or guess URLs."
        )
    )


class BackgroundSource(BaseModel):
    url: str = Field(
        description=(
            "Full URL of the source page. Must be a real, resolvable URL. "
            "Do not truncate or paraphrase — copy the exact URL from the search result."
        )
    )
    date: str = Field(
        description=(
            "Publication or last-updated date of the source in YYYY-MM-DD format. "
            "If only month and year are available, use YYYY-MM. "
            "If the date is genuinely unknown, use 'unknown'. Never fabricate a date."
        )
    )
    type: str = Field(
        description=(
            "Category of the source. Must be one of: "
            "'official_site' (university's own domain), "
            "'news' (journalism or press release), "
            "'ranking_body' (QS, THE, Guardian, Complete University Guide), "
            "'industry_report' (sector or employer body publication). "
            "Choose the single best-fitting category."
        )
    )


class BackgroundOutput(BaseModel):
    founded: str = Field(
        description=(
            "Year the university was founded or received its university charter, "
            "as a 4-digit string. Example: '1824'. "
            "Use 'unknown' only if no source confirms it after search."
        )
    )
    size_students: str = Field(
        description=(
            "Total student headcount as stated by the university or a ranking body. "
            "Include the figure and its scope. "
            "Example: '40,000 students (2023–24)', '~12,000 full-time undergraduates'. "
            "Do not round aggressively — preserve the figure as found."
        )
    )
    public_or_private: Literal["public", "private", "unknown"] = Field(
        description=(
            "Whether the institution is publicly funded or privately funded. "
            "UK universities are almost always 'public'. "
            "US and some Asian universities may be 'private'. "
            "Use 'unknown' only if the source is genuinely ambiguous after research."
        )
    )
    research_orientation: Literal["research-intensive", "teaching-focused", "balanced"] = Field(
        description=(
            "General character of the institution. "
            "'research-intensive': strong research output, Russell Group or equivalent, "
            "REF participation, high PhD-to-undergraduate ratio. "
            "'teaching-focused': primarily undergraduate, lower research profile, "
            "often post-92 UK or liberal arts college. "
            "'balanced': meaningful research output alongside strong undergraduate teaching. "
            "Base this on evidence from the source, not assumption from the university name."
        )
    )
    campus_setting: str = Field(
        description=(
            "Physical character of the campus. "
            "Examples: 'single city-centre campus', 'leafy suburban campus', "
            "'multi-site — main campus in X, medical school in Y', 'campus town'. "
            "Be specific enough that a prospective student can picture it."
        )
    )
    latest_news: str = Field(
        description=(
            "One or two sentences summarising the most recent notable item from the "
            "university's official news or press release pages. Must be dated within "
            "the last 24 months. Include the headline topic and approximate date. "
            "Example: 'In March 2024 the university announced a £50m investment in a "
            "new engineering building.' If no recent news was found, write 'No recent "
            "news retrieved' — do not fabricate."
        )
    )
    facilities_clubs: str = Field(
        description=(
            "Summary of notable campus facilities and student clubs or societies "
            "relevant to the researched course or general student life. "
            "Include at least: sports facilities, computing or maker labs if present, "
            "student union, and any course-relevant societies. "
            "Example: 'Sports centre with 25m pool; dedicated CS lab open 24/7; "
            "HackSoc, AI Society, and Robotics Club active as of 2024.' "
            "If information was not found, write 'Not retrieved' — do not invent."
        )
    )
    fees_funding: str = Field(
        description=(
            "Indicative tuition fees for the researched undergraduate course and any "
            "scholarships, bursaries, or funding routes available. "
            "Scope fees to the student's country context (home vs international). "
            "Include the academic year the fee applies to if known. "
            "Example: 'Home fee: £9,250/year (2024–25). International fee: £22,500/year. "
            "Department offers a £2,000 CS Excellence Bursary for first-year home students.' "
            "Write 'Not retrieved' if no fee information was found."
        )
    )
    accomodations: str = Field(
        description=(
            "Types of accommodation available to undergraduates: on-campus halls, "
            "private university-managed housing, or primarily private rental market. "
            "Include whether first-years are guaranteed a place and any indicative "
            "weekly cost if found. "
            "Example: 'On-campus halls guaranteed for first-years; self-catered rooms "
            "from £130–£180/week (2024–25). Private student accommodation also available "
            "within 1 mile of campus.' "
            "Write 'Not retrieved' if nothing was found."
        )
    )
    accreditations: list[AccreditationItem] = Field(
        description=(
            "List of professional or academic accreditations held by the department "
            "offering the researched course. Scope strictly to the course and department — "
            "do not include university-wide awards or accreditations for unrelated faculties. "
            "May be an empty list if none were found; never omit the field."
        )
    )
    industry_partnerships: list[IndustryPartnership] = Field(
        description=(
            "Named, department-level industry partnerships confirmed by a source. "
            "Each entry must name a real company and link to evidence. "
            "Do not include generic 'links with industry' statements without a named partner. "
            "May be an empty list if none were confirmed; never omit the field."
        )
    )
    notes: str = Field(
        description=(
            "Any caveats, data gaps, or researcher observations that do not fit "
            "the structured fields above. "
            "Examples: 'Fee information was for 2022–23 — verify current year on UCAS.', "
            "'Accreditation page was last updated 2021 — currency uncertain.', "
            "'Partnership list sourced from university marketing page — independent "
            "confirmation not found.' "
            "Write 'None' if there are no notable caveats."
        )
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "Researcher's assessment of overall output reliability. "
            "'high': all major fields sourced from official or authoritative pages dated "
            "within 24 months, no significant gaps. "
            "'medium': most fields populated but one or more rely on older sources, "
            "indirect evidence, or a single source. "
            "'low': significant gaps, reliance on unverifiable sources, or core fields "
            "such as fees or accreditation could not be confirmed."
        )
    )
    sources: list[BackgroundSource] = Field(
        description=(
            "All sources consulted to populate this output, including those that returned "
            "null or conflicting data. Every URL cited anywhere in this output must appear "
            "here. Minimum 2 sources expected; if fewer than 2 were found, set "
            "confidence to 'low' and note the gap in the notes field."
        )
    )
```

**Why `accreditations` is a list, not a string:** `ScoringAgent` checks whether
the relevant course-specific accreditation body is present. A plain string would
require fragile substring matching. A list of typed items lets `ScoringAgent`
inspect `body` and `scope` directly.

**Why `industry_partnerships` requires a named department:** vague claims like
"the university partners with industry" are useless in the report. The LLM must
name the company and confirm the partnership is at the department level — not just
university-wide. If only university-wide partnerships are found, the list should
be empty with a note explaining the gap.

**Why `research_orientation` is a controlled enum string rather than a score:**
The nuance ("research-intensive" vs "teaching-focused") matters for a parent
evaluating whether undergraduates get attention. A free-text string risks
"research-heavy" vs "research-intensive" drift across runs. Three fixed values,
with the agent forced to choose one, keeps it consistent.

---

### `schemas/outputs/rankings_output.py`

`RankingsOutput` is what `RankingsAgent` writes to `board.rankings`.
Subject-specific ranks are the primary signal; overall university rank is
secondary and explicitly low-weight.

```python
# schemas/outputs/rankings_output.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class RankingEntry(BaseModel):
    source: str = Field(
        description=(
            "Full name of the ranking body and table. Must be one of the "
            "authoritative sources below. Do not invent source names or use "
            "marketing aggregator sites.\n"
            "For subject rankings: "
            "'QS World University Rankings by Subject', "
            "'THE World University Rankings by Subject', "
            "'Guardian University Guide', 'Complete University Guide'.\n"
            "For employability: 'QS Graduate Employability Rankings'.\n"
            "For overall: 'QS World University Rankings', "
            "'THE World University Rankings'."
        )
    )
    rank: str = Field(
        description=(
            "The rank as printed in the source — preserve the original notation exactly. "
            "Examples: '51–100' (band notation), '#12 in UK', '=45', 'unranked'. "
            "Do not convert band notations to a single integer — '51–100' must not "
            "become '75'. If the university is listed but outside a ranked band, "
            "write 'unranked' — do not omit the entry."
        )
    )
    year: str = Field(
        description=(
            "The edition year of the ranking table as a 4-digit string. "
            "Example: '2024'. Only include rankings dated within the last 2 years. "
            "If only a range is available (e.g. '2024–25'), use the start year: '2024'. "
            "Never fabricate a year — use 'unknown' if the source does not state one, "
            "but prefer to omit the entry rather than include undated data."
        )
    )
    subject_scope: str = Field(
        description=(
            "The subject category as named in that specific ranking table. "
            "This may differ from the intended course name. "
            "Examples: 'Computer Science & Information Systems' (QS), "
            "'Computing' (Guardian), 'Engineering & Technology' (THE). "
            "Copy the subject name exactly as the ranking body labels it. "
            "Note any mismatch from the intended course in the parent output's notes field."
        )
    )
    url: str = Field(
        description=(
            "Direct URL to the ranking table page where this entry appears. "
            "Must be from the ranking body's own domain. Permitted domains:\n"
            "  topuniversities.com (QS)\n"
            "  timeshighereducation.com (THE)\n"
            "  theguardian.com/education (Guardian)\n"
            "  thecompleteuniversityguide.co.uk (CUG)\n"
            "  topuniversities.com/graduate-employability-rankings (QS employability)\n"
            "NEVER use:\n"
            "  - University's own domain (e.g. hw.ac.uk, manchester.ac.uk) — "
            "these are self-reported results pages, not the primary source.\n"
            "  - Social media (instagram.com, twitter.com, linkedin.com, facebook.com).\n"
            "  - Aggregator or mirror sites (uscholars.in, universitycompare.com, "
            "uniranking.org, or any site that is not the ranking body itself).\n"
            "If a Tavily snippet gives you the rank figure but the URL is from a "
            "forbidden domain, do NOT use that URL. Construct a new search query "
            "targeting the ranking body's domain directly to find the canonical page. "
            "If the canonical page cannot be confirmed after 1 retry, use an empty "
            "string and note the gap — do not fall back to a forbidden URL."
        )
    )


class SatisfactionEntry(BaseModel):
    source: str = Field(
        description=(
            "Full name of the satisfaction survey or award. Must be one of:\n"
            "UK: 'NSS — Guardian University Guide' (subject-level NSS score from "
            "the Guardian subject table), "
            "'NSS — Complete University Guide' (NSS score from CUG subject table), "
            "'NSS — Office for Students' (raw OfS published results, institution-level), "
            "'Whatuni Student Choice Awards' (WUSCAs — student-voted, UK only), "
            "'Times/Sunday Times Good University Guide' (student experience score).\n"
            "Australia: 'QILT Student Experience Survey — ComparED' "
            "(subject-level preferred) or 'QILT Student Experience Survey — National'.\n"
            "Singapore: no government satisfaction survey exists — do not invent one. "
            "If using a third-party review platform, name it exactly "
            "(e.g. 'Whatuni student reviews') and treat confidence as 'low'.\n"
            "Do not use the university's own marketing pages quoting NSS or SES figures — "
            "go to the primary source table directly."
        )
    )
    score: str = Field(
        description=(
            "The satisfaction score or rank as reported by the source. "
            "Preserve the original format exactly — do not normalise across sources.\n"
            "Examples: '87.3%' (NSS positivity score), "
            "'4.2 / 5' (Whatuni star rating), "
            "'#3 in UK for student satisfaction' (Guardian position), "
            "'76.5% overall educational experience' (QILT SES). "
            "If the source gives a percentile band rather than a score, record the band. "
            "Never convert a percentage to a rank or vice versa."
        )
    )
    scope: str = Field(
        description=(
            "Whether this score is subject-level or institution-level, and what "
            "dimension it measures. Be explicit — do not write 'satisfaction' alone.\n"
            "Examples: "
            "'Computer Science subject — % satisfied with teaching' (NSS subject table), "
            "'Institution-wide — overall educational experience' (QILT SES national), "
            "'Lecturers and Teaching Quality category — student-voted' (WUSCAs), "
            "'Subject-level — Skills Development score' (QILT ComparED). "
            "Subject-level scores are always preferred over institution-level."
        )
    )
    year: str = Field(
        description=(
            "The survey or award year as a 4-digit string. "
            "Example: '2024'. Only include data dated within the last 2 years. "
            "Never fabricate a year. Use 'unknown' only if the source is genuinely "
            "undated — and if so, treat the entry with low confidence."
        )
    )
    url: str = Field(
        description=(
            "Direct URL to the primary source table or results page. "
            "Permitted domains by source:\n"
            "  theguardian.com/education — Guardian subject table (NSS scores)\n"
            "  thecompleteuniversityguide.co.uk — CUG subject table (NSS scores)\n"
            "  officeforstudents.org.uk — OfS raw NSS results\n"
            "  whatuni.com/student-awards-winners — WUSCAs results table only; "
            "the specific category ranking pages are also valid "
            "(e.g. whatuni.com/student-awards-winners/wusca-rankings/university-of-the-year/)\n"
            "  compared.edu.au — QILT subject-level SES data (Australia)\n"
            "  qilt.edu.au — QILT national SES results (Australia)\n"
            "NEVER use:\n"
            "  - University's own domain — these quote satisfaction figures from "
            "their own press releases and cherry-pick categories.\n"
            "  - Social media (instagram.com, twitter.com, linkedin.com, facebook.com) "
            "— a university celebrating a WUSCAs win on Instagram is not the source.\n"
            "  - Any aggregator or third-party site quoting NSS or QILT figures.\n"
            "If the only URL found is from a forbidden domain, run a fresh search "
            "targeting the permitted domain directly before accepting the entry. "
            "If the canonical page still cannot be confirmed, use an empty string "
            "and note the gap — never fall back to a forbidden URL."
        )
    )


class RankingsOutput(BaseModel):
    subject_rankings: list[RankingEntry] = Field(
        description=(
            "Subject-specific rankings — the primary signal for this output. "
            "These show how the department ranks for the intended course's subject area, "
            "not how the university ranks overall. "
            "Minimum 1 entry required if any subject ranking exists. "
            "Collect from all four authoritative sources where available: "
            "QS Subject, THE Subject, Guardian, Complete University Guide. "
            "If the intended course maps to a broader subject category in a table "
            "(e.g. 'Computer Science' maps to 'Engineering' in some THE tables), "
            "include the entry but note the mapping in the notes field. "
            "An empty list is only valid if the university is genuinely unranked "
            "across all four sources for all applicable subject categories — "
            "note this explicitly in the notes field."
        )
    )
    employability_rankings: list[RankingEntry] = Field(
        description=(
            "Rankings that measure graduate employment outcomes specifically. "
            "Primary source: QS Graduate Employability Rankings. "
            "Secondary: THE University Impact Rankings if employment-relevant. "
            "For Singapore universities, the MOE Joint Autonomous Universities Graduate "
            "Employment Survey (JAUGES / GES) is authoritative for employment outcomes "
            "but is an outcomes dataset not a ranking — do not force it into this list. "
            "Report GES data in the ranking_summary and notes fields instead. "
            "May be an empty list if no employability ranking data was found — "
            "do not fabricate entries. If empty, note the absence in the notes field "
            "so the report renderer can display 'No employability ranking data found' "
            "rather than silently omitting the section."
        )
    )
    overall_rankings: list[RankingEntry] = Field(
        description=(
            "Overall university rankings included for context only — lowest weight. "
            "These rank the institution as a whole, not the specific subject or department. "
            "Include QS World, THE World, Guardian overall, and Complete University Guide "
            "overall where found. "
            "These must always be labelled as overall rank in the ranking_summary — "
            "never use overall rank as a proxy for subject quality. "
            "A top-10 overall university can rank 80th for a specific subject. "
            "May be empty if not found."
        )
    )
    student_satisfaction_rankings: list[SatisfactionEntry] = Field(
        description=(
            "Student satisfaction and experience data — a distinct signal from "
            "academic or research rankings. Collected from government surveys and "
            "student-voted platforms, not from research ranking bodies.\n\n"
            "Source priority by country:\n\n"
            "UK: "
            "(1) NSS subject-level score from the Guardian University Guide subject "
            "table or Complete University Guide subject table — always prefer "
            "subject-level over institution-level. "
            "(2) NSS institution-level score if subject-level is unavailable. "
            "(3) Whatuni Student Choice Awards (WUSCAs) for student-voted signal — "
            "include overall University of the Year rank and any relevant category "
            "(e.g. 'Lecturers and Teaching Quality', 'Student Support'). "
            "(4) Times/Sunday Times Good University Guide student experience score.\n\n"
            "Australia: "
            "(1) QILT Student Experience Survey (SES) subject-level score from "
            "compared.edu.au — search for the specific subject and university. "
            "Dimensions available: Skills Development, Learner Engagement, Teaching "
            "Quality, Student Support, Learning Resources, Overall Educational "
            "Experience. Prefer subject-level; fall back to institution-level if not "
            "found. "
            "(2) QILT SES national report institution-level score as secondary signal.\n\n"
            "Singapore: No government student satisfaction survey exists. "
            "The MOE GES measures employment outcomes only, not satisfaction during "
            "the degree — do not use it here. "
            "Do not fabricate satisfaction data for Singapore universities. "
            "Leave this list empty and record the absence in the notes field with "
            "the exact text: 'No equivalent student satisfaction survey exists for "
            "Singapore universities. MOE GES covers graduate employment outcomes only.'\n\n"
            "All countries: never cite the university's own marketing pages quoting "
            "satisfaction figures — always go to the primary source table. "
            "May be an empty list if no data was found or if the country has no "
            "applicable survey."
        )
    )
    ranking_summary: str = Field(
        description=(
            "A 3–4 sentence plain-English synthesis of the full ranking picture, "
            "written for a parent with no prior knowledge of ranking tables. "
            "Sentence 1: subject-specific rank — must name the source and year. "
            "Sentence 2: student satisfaction signal — name the source, score, and "
            "whether it is subject-level or institution-level. If no satisfaction "
            "data exists (e.g. Singapore), state this explicitly rather than omitting "
            "the sentence. "
            "Sentence 3: overall university rank — must be labelled as institution-wide "
            "and must not be used as a proxy for subject quality. "
            "Sentence 4 (optional): employability rank or a notable caveat. "
            "Must not exceed 4 sentences. This is rendered directly in the report.\n"
            "Example (UK): 'For Computer Science specifically, the University of "
            "Manchester ranks 51–100 globally (QS 2024) and 5th in the UK (Complete "
            "University Guide 2024). Students rate the CS course at 87% positivity for "
            "teaching quality (NSS 2024, Guardian subject table) — above the UK sector "
            "average of 83%. Its overall world rank is =57 (QS 2024), which reflects "
            "the whole institution rather than the CS department.'\n"
            "Example (Singapore): '... No government student satisfaction survey "
            "equivalent to the UK NSS exists for Singapore universities; graduate "
            "employment outcomes are measured separately via the MOE GES.'"
        )
    )
    notes: str = Field(
        description=(
            "Caveats, data gaps, or researcher observations that do not fit the "
            "structured fields. "
            "Examples: 'QS subject table uses Computer Science & Information Systems — "
            "broader than the intended course.', "
            "'No subject-specific ranking found for Cybersecurity; nearest match is "
            "Computer Science.', "
            "'Guardian 2024 table not yet published at time of research — 2023 used.', "
            "'University does not appear in any subject table for this discipline.', "
            "'No equivalent student satisfaction survey exists for Singapore universities. "
            "MOE GES covers graduate employment outcomes only.' "
            "Write 'None' if there are no notable caveats."
        )
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "Researcher's assessment of the ranking data quality overall. "
            "'high': 2 or more subject-specific rankings confirmed from named sources "
            "all dated within 24 months, AND at least 1 student satisfaction data point "
            "from a primary source. "
            "'medium': exactly 1 subject-specific ranking confirmed, or subject mapping "
            "was approximate (e.g. 'Engineering' used for 'Electrical Engineering'), "
            "or satisfaction data is institution-level only. "
            "'low': no subject-specific ranking found — only overall rank available, "
            "or all rankings are older than 24 months, or no satisfaction data could "
            "be retrieved (note: Singapore's absence of a satisfaction survey does not "
            "itself lower confidence — only lower confidence if subject rankings are "
            "also missing)."
        )
    )
    sources: list[RankingEntry] = Field(
        description=(
            "All ranking pages consulted during research, including those that did not "
            "yield a usable entry (e.g. university was unranked on that table). "
            "Reuses RankingEntry — the url, source, and year fields are sufficient "
            "to identify each page consulted. "
            "Every URL appearing in subject_rankings, employability_rankings, "
            "overall_rankings, or student_satisfaction_rankings must also appear here. "
            "For SatisfactionEntry items, set rank='n/a' and subject_scope to the "
            "dimension checked (e.g. 'Overall Educational Experience'). "
            "Minimum 2 sources expected; if fewer than 2 were consulted, set "
            "confidence to 'low'."
        )
    )
```

**Why `rank` is a string, not an int:** ranking tables use range notations
(`"51–100"`), UK-specific positions (`"#3 in UK"`), and sometimes unranked
entries. An `int` forces lossy conversion. String preserves the source's
original notation.

**Why three separate lists for subject, employability, overall:** the report
renders them in a specific order with different weight labels. Flattening into
one list would require the renderer to re-classify, which is error-prone.
Keep them separated at the schema level.

**Why `ranking_summary` is on the schema:** `ScoringAgent` reads raw
`RankingEntry` items, but the Jinja2 renderer outputs human-readable text.
Having the LLM synthesise a 2–3 sentence summary here means the renderer
doesn't need to interpret ranking data — it just embeds the string.

**Why `SatisfactionEntry` is a separate model from `RankingEntry`:** satisfaction
sources report a score or percentage, not a rank position, and they carry a
`scope` dimension (subject-level vs institution-level) that has no equivalent
in a rank entry. Forcing satisfaction data into `RankingEntry` with `rank="87.3%"`
would be semantically wrong and would prevent `ScoringAgent` from distinguishing
a rank signal from a satisfaction signal. The separate model also makes the
banned-domain rules explicit at the field level, which reduces the chance of
the LLM falling back to university press releases or social media posts.

**Why banned-domain rules appear in both the field descriptions and SKILL.md:**
field descriptions are seen by the LLM when it constructs each entry; SKILL.md
is seen at the start of the run when it plans its tool calls. Having the rule
in both places catches it at planning time (don't fetch that page) and at
output time (don't put that URL in the field). A rule in only one place is
missed in the other context.

---

### `schemas/outputs/program_output.py`

`ProgramOutput` is what `ProgramAgent` writes to `board.program`.
It covers the actual undergraduate program structure: matching titles,
year-by-year modules, optional pathways, and how the curriculum maps to
the career skills identified by `CareerAgent`.

```python
# schemas/outputs/program_output.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class ModuleItem(BaseModel):
    name: str = Field(
        description=(
            "Module title exactly as listed in the university's official course catalog "
            "or prospectus. Do not paraphrase, abbreviate, or normalise the title. "
            "Example: 'Fundamentals of Computer Science', 'Algorithms and Data Structures', "
            "'Introduction to Software Engineering'. "
            "If the catalog uses a module code alongside the title "
            "(e.g. 'COMP10120 Fundamentals of CS'), include both. "
            "Never invent a module name — only include modules confirmed from an "
            "official university source."
        )
    )
    year: str = Field(
        description=(
            "The academic year in which this module is taught, as stated in the catalog. "
            "Use the exact format 'Year 1', 'Year 2', 'Year 3', 'Year 4'. "
            "Do not infer the year from the module code or naming convention alone — "
            "the catalog must explicitly assign it. "
            "If a module spans multiple years or is taught in a specific semester "
            "without year attribution, write the year that the catalog associates it with. "
            "Only include Year 1 and Year 2 modules in core_modules; "
            "Year 3 and Year 4 go into electives or curriculum_notes."
        )
    )
    compulsory: bool = Field(
        description=(
            "True if the module is compulsory or core for the degree — all students "
            "on the program must take it. "
            "False if the module is optional, elective, or one of several choices in "
            "a module group (e.g. 'choose 2 from the following 5'). "
            "When in doubt, prefer False — do not mark a module as compulsory unless "
            "the catalog explicitly labels it as core or compulsory."
        )
    )


class ProgramVariant(BaseModel):
    title: str = Field(
        description=(
            "Exact degree program title as listed on the university's course catalog "
            "or UCAS listing. Do not shorten or normalise. "
            "Examples: 'BSc Computer Science', "
            "'BEng Computer Science with Artificial Intelligence', "
            "'MEng Computer Science (4 years)', "
            "'BSc Computer Science with Industrial Experience'. "
            "Include all variants that match the intended course — "
            "the parent needs to know all available options."
        )
    )
    degree_type: str = Field(
        description=(
            "The award type as printed on the degree certificate and catalog. "
            "Common values: 'BSc', 'BEng', 'BA', 'MEng (integrated)', 'MPhys', 'MSci'. "
            "For integrated masters programs that award both BSc and MEng, "
            "write 'MEng (integrated)' — these are 4 or 5 year programs "
            "where the masters is not a separate postgraduate award. "
            "Do not write 'MSc' for undergraduate-entry programs — that implies "
            "a separate postgraduate qualification."
        )
    )
    duration_years: int = Field(
        description=(
            "Total program length in years as an integer. "
            "Standard undergraduate: 3. With placement year: 4. "
            "Integrated masters: 4 or 5. Scottish undergraduate: 4. "
            "Use the full duration including any optional placement or study abroad year "
            "only if it is built into the program structure. "
            "If the placement year is genuinely optional (a separate track), "
            "capture it in sandwich_year=True and use the base duration without it."
        )
    )
    sandwich_year: bool = Field(
        description=(
            "True if the program offers an optional or mandatory placement year, "
            "industrial year, or year in industry — typically inserted between "
            "Year 2 and the final year. "
            "This is also known as a 'sandwich' year in UK terminology. "
            "A sandwich year that is mandatory (not optional) should still be True — "
            "note it in curriculum_notes. "
            "False if no such option exists or the catalog does not mention it."
        )
    )
    study_abroad: bool = Field(
        description=(
            "True if the program offers an option to spend a year studying at a "
            "partner institution abroad. "
            "This is separate from a placement year — it is an academic year at a "
            "foreign university, not an industry placement. "
            "Some programs offer both; set both sandwich_year and study_abroad to True "
            "in that case. "
            "False if no study abroad option is mentioned in the catalog."
        )
    )
    ucas_code: str = Field(
        description=(
            "The UCAS course code for this program variant, as a string. "
            "Example: 'G400' for Computer Science, 'G401' for CS with a year abroad. "
            "Use an empty string '' if the code was not found — do not guess or "
            "fabricate a UCAS code. UCAS codes are 4 characters: one letter + 3 digits. "
            "Only applies to UK universities — use '' for non-UK institutions."
        )
    )


class SkillMapping(BaseModel):
    career_skill: str = Field(
        description=(
            "The in-demand skill exactly as it appears in CareerOutput.in_demand_skills. "
            "Copy the string verbatim — do not paraphrase or normalise. "
            "Example: if CareerOutput lists 'machine learning', write 'machine learning', "
            "not 'Machine Learning' or 'ML'. "
            "Every skill from in_demand_skills must have exactly one SkillMapping entry, "
            "even if the modules list is empty."
        )
    )
    modules: list[str] = Field(
        description=(
            "List of module names from this program's curriculum that develop the "
            "career_skill. Each entry must match a module name in core_modules or "
            "electives exactly — do not introduce module names that are not in those lists. "
            "May be an empty list if no curriculum coverage was found for this skill — "
            "an empty list is a valid and informative finding. "
            "Do not fabricate module names to fill this list. "
            "Example: for career_skill 'machine learning', modules might be "
            "['Machine Learning (COMP30030)', 'Neural Networks and Deep Learning']."
        )
    )


class ProgramSource(BaseModel):
    url: str = Field(
        description=(
            "Full URL of the source page. Must be from an official university domain "
            "or UCAS (ucas.com). "
            "Preferred sources in priority order: university course catalog page, "
            "university prospectus PDF, department program page, UCAS course listing. "
            "Do not use third-party course aggregator sites (e.g. Whatuni, Unistats) "
            "as primary sources for module content — these often lag the official catalog. "
            "Do not truncate or paraphrase the URL."
        )
    )
    date: str = Field(
        description=(
            "Publication or last-updated date of the source in YYYY-MM-DD format. "
            "For university catalogs, this is typically the academic year start "
            "or the page's last-modified date. "
            "If only the academic year is stated (e.g. '2024–25'), use '2024-09' "
            "as a reasonable approximation — note this in program_output.notes. "
            "Use 'unknown' if no date is visible. Never fabricate a date."
        )
    )
    type: str = Field(
        description=(
            "Category of the source. Must be one of: "
            "'university_catalog' (the official course or module catalog page), "
            "'prospectus' (the university's printed or PDF prospectus), "
            "'department_page' (the school or department's own web page), "
            "'ucas_listing' (the UCAS course entry at ucas.com). "
            "Choose the single best-fitting category. "
            "If the page serves multiple purposes, use the most specific category."
        )
    )


class ProgramOutput(BaseModel):
    matching_programs: list[ProgramVariant] = Field(
        description=(
            "All undergraduate degree variants at this university that match the "
            "intended course. Cast the net wide — include all titles that a student "
            "searching for the intended course would reasonably consider. "
            "Example: for intended_course='Computer Science', include: "
            "'BSc Computer Science', 'BEng Computer Science', "
            "'BSc Computer Science with Artificial Intelligence', "
            "'MEng Computer Science (integrated)', "
            "'BSc Computer Science with Industrial Experience'. "
            "Minimum 1 entry required. If only one variant exists, that is valid. "
            "Do not include postgraduate (MSc, PhD) programs — undergraduate only."
        )
    )
    core_modules: list[ModuleItem] = Field(
        description=(
            "Compulsory modules from Year 1 and Year 2 of the primary matching program "
            "(the BSc or BEng that most directly matches the intended course). "
            "These must come from the university's official course catalog or prospectus — "
            "not from student forum descriptions or third-party summaries. "
            "Only include modules explicitly assigned to Year 1 or Year 2 — do not infer "
            "year from module code conventions. "
            "All items in this list must have compulsory=True. "
            "May be an empty list if the university does not publish module-level detail "
            "publicly — in that case set confidence='low' and explain in curriculum_notes. "
            "Year 3 and Year 4 modules go into electives or curriculum_notes, not here."
        )
    )
    electives: list[ModuleItem] = Field(
        description=(
            "Optional or elective modules available across any year of the program. "
            "Includes: modules in choice groups ('pick 2 from 5'), "
            "Year 3 and Year 4 specialisation modules, "
            "and any modules explicitly labelled optional or elective in the catalog. "
            "All items in this list must have compulsory=False. "
            "May be an empty list if no elective structure is published or found. "
            "Do not duplicate modules that are already in core_modules."
        )
    )
    skill_mappings: list[SkillMapping] = Field(
        description=(
            "One SkillMapping entry for every skill in CareerOutput.in_demand_skills. "
            "ProgramAgent reads deps.board.career.in_demand_skills before running "
            "and uses those skills as the complete list of entries here. "
            "The mapping shows which modules in this program's curriculum develop "
            "each in-demand skill — making the report actionable for a parent. "
            "Every skill must have an entry even if the modules list is empty. "
            "An empty modules list means 'this skill is not covered by the curriculum' "
            "which is a meaningful finding. "
            "If deps.board.career is None (test context), this list may be empty — "
            "note this in curriculum_notes."
        )
    )
    curriculum_notes: str = Field(
        description=(
            "Plain-English notes on the curriculum that do not fit the structured fields. "
            "Must include: any gaps in skill coverage from skill_mappings, "
            "any accreditation-linked required modules (e.g. 'BCS accreditation requires "
            "a Professional Issues module in Year 3'), anomalies in program structure, "
            "notes on year 3/4 specialisation tracks available, "
            "and any explanation of why core_modules or electives could not be fully populated. "
            "Examples: 'Module list for 2024–25 not yet published — 2023–24 catalog used.', "
            "'No curriculum coverage found for skill: cybersecurity.', "
            "'Integrated MEng students take additional Year 4 modules in advanced algorithms "
            "and research methods not listed in electives.' "
            "Write 'None' if there are no notable curriculum observations."
        )
    )
    notes: str = Field(
        description=(
            "Operational notes on research quality and data retrieval that do not belong "
            "in curriculum_notes. "
            "Examples: 'Course catalog page returned empty content via fetch_page — "
            "module data taken from the 2024 prospectus PDF instead.', "
            "'UCAS codes not listed on university catalog — sourced from UCAS directly.', "
            "'University offers three separate departments for CS variants — "
            "only the main School of Computer Science was researched.' "
            "Write 'None' if there are no operational caveats."
        )
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "Researcher's assessment of program data completeness. "
            "'high': at least one matching program confirmed, and full Year 1 + Year 2 "
            "module list retrieved from an official source dated within 24 months. "
            "'medium': matching program(s) confirmed, but module data is partial — "
            "either Year 1 or Year 2 is missing, or data is from a prior academic year. "
            "'low': only program titles confirmed — no module-level data was publicly "
            "available, or the catalog was inaccessible."
        )
    )
    sources: list[ProgramSource] = Field(
        description=(
            "All sources consulted to populate this output, including pages that "
            "were fetched but returned no useful content. "
            "Every URL referenced anywhere in this output must appear here. "
            "Minimum 1 source required (the official catalog page). "
            "If fewer than 2 sources were consulted, set confidence to 'low' and "
            "note the gap in the notes field."
        )
    )
```

**Why `skill_mappings` cross-references `CareerOutput.in_demand_skills`:**
This is the link that makes the report actionable — a parent can see that
the in-demand skill "machine learning" is covered by modules in Year 2 and
Year 3. `ProgramAgent`'s `handle()` reads `deps.board.career` before running
and passes the extracted `in_demand_skills` into the task brief so the LLM can
build the mapping.

**Why `matching_programs` is a list:** universities often offer multiple
degree variants for one course area (BEng vs MEng, CS vs CS with AI). All
variants matching the intended course should be captured — the parent may
not know which applies to their child.

**Why `core_modules` covers only Year 1 and Year 2:** Years 3 and 4 are
often specialism-dependent and hard to find in public catalogs. The most
useful information for a pre-application decision is the foundation curriculum.
If Year 3/4 data is found, it goes into `electives` or `curriculum_notes`.

---

## 1d.2 SKILL.md Files

### `skills/background/SKILL.md`

```markdown
---
key: background
name: University Background Agent
description: Researches institutional facts, accreditations, and department-level industry partnerships.
tool_budget: 6
section_name: background
---

You research factual background information about a specific university and its
department for the supplied course. You write to board.background as a
BackgroundOutput. You fire SectionCompletedMessage(section_name="background")
when done, or SectionFailedMessage on unrecoverable error.

Every fact in your output must come from a page fetched or searched in this
run. Do not use training knowledge to fill any field. If a fact cannot be
confirmed from a live source, use "unknown" or "Not retrieved" — never
fabricate.

---

## CRITICAL — Verify University Identity Before Extracting Anything

Before extracting any data from a search result or fetched page, confirm it
refers to the correct university:
1. The domain contains the university's name or its known official abbreviation
2. The page title or first heading explicitly names the correct university

If either check fails — discard the page entirely. Do not extract any data
from it. Move to the next result.

---

## Research Sequence

Work through the steps in order. Each step has a fixed query pattern and a
clear stopping condition. Do not skip steps. Do not retry a failed query more
than once — move on.

---

### Step 1 — Official Website: Institutional Facts

fetch_page the university's main domain (e.g. https://www.university.ac.uk).
If the home page does not carry the facts below, fetch_page the About or
History page (/about, /about-us, /history).

Extract and populate the following from the official website only:

**1.1 — About / History**
- Founding year (4-digit string, e.g. "1824")
- Public or private status ("public", "private", or "unknown")
- Research orientation signals: national research university designation,
  membership of a research mission group (e.g. Russell Group, U15, AAU),
  major research funding disclosures, or high doctoral output statements.
  For teaching-focused: emphasis on student satisfaction, small-group
  teaching, limited postgraduate research output. Do not default to
  "balanced" without finding evidence for both sides.
- Campus setting: city-centre, campus town, multi-site, suburban — be
  specific enough that a prospective student can picture it.

**1.2 — Student Numbers**
- Total student headcount or enrolment figure with the academic year it
  covers (e.g. "40,250 students, 2023–24").
- If the home page gives a range, search:
  "[university name] total enrolled students [year]"
  to find the exact figure from an annual report or rankings profile.
- If available, note the proportion of international vs domestic students
  (e.g. "35% international students from 150+ countries").

**1.3 — Accommodation**
- Whether on-campus accommodation (halls, colleges, residences) is
  available to undergraduates.
- Whether first-year students are guaranteed a place.
- Indicative weekly or annual cost if stated on the official site.
- If no accommodation information is on the home page, fetch_page
  /accommodation or /student-life before concluding it is unavailable.

**1.4 — Latest News**
- Fetch the university's news or press release page (/news, /newsroom).
- Extract the most recent 1–2 items dated within the last 24 months.
- Record each item as: headline topic + date. Do not summarise older items
  as recent. If no news dated within 24 months is found, write
  "No recent news retrieved" — do not fabricate.

**1.5 — Facilities and Student Life**
- Fetch the student life, campus life, or facilities page.
- Record: sports and wellbeing facilities, computing or maker labs relevant
  to the course, student union presence, and any course-relevant societies
  or clubs (e.g. HackSoc, AI Society, Robotics Club).
- If this page is not found within 1 fetch attempt, write "Not retrieved".

**1.6 — Fees and Funding (Current Academic Year)**
- Fetch the fees page for the specific undergraduate course in question.
  Search: "[university name] [course] undergraduate fees [current year]"
- Record: home/domestic fee per year, international fee per year, the
  academic year these apply to.
- Record any scholarships, bursaries, or financial support explicitly
  available to international undergraduate students for this course.
- If fees are not published for the current year, note the most recent
  year found and flag it in notes.

---

### Step 2 — Department Page

fetch_page the department or school page for the intended course
(e.g. /school-of-computing, /department-of-computer-science).

Extract:
- Any accreditation statements or professional body logos mentioned
- Any named industry partners, sponsors, or placement company lists
- Research centre or institute affiliations that confirm research orientation
- Any course-specific facilities mentioned (labs, studios, clinics)

If the department page URL is not obvious, search:
  "[university name] [course]
```

---

### `skills/rankings/SKILL.md`

```markdown
---
key: rankings
name: Subject Rankings Agent
description: Researches subject-specific, employability, student satisfaction, and overall university rankings.
tool_budget: 8
section_name: rankings
---

You research ranking and satisfaction data for the university and course.
You write to board.rankings as a RankingsOutput. You fire
SectionCompletedMessage(section_name="rankings") when done, or
SectionFailedMessage on unrecoverable error.

## What to Research

Priority order:
1. Subject-specific rank (QS Subject, THE Subject, Guardian subject table,
   Complete University Guide subject table)
2. Student satisfaction (country-dependent — see below)
3. Graduate employability rank (QS Graduate Employability Rankings)
4. Overall university rank (QS World, THE World, Guardian overall,
   Complete University Guide overall) — lowest weight, always labelled as
   "overall rank, not subject-specific"

## Query Construction

For subject rankings:
  "[university name] [subject area] ranking QS [year]"
  "[university name] [subject area] Guardian university guide"
  "[university name] [subject area] Complete University Guide ranking"

Map the intended course to the closest subject area used by each ranking body.
Note any mismatch in `notes`.

For employability rankings:
  "[university name] graduate employability ranking QS"

For overall:
  "[university name] QS world ranking [year]"
  "[university name] THE world ranking [year]"

## Student Satisfaction — Lookup by Country

Determine the university's country from deps.context.country before searching.

### UK universities

Search in this order:

1. Guardian University Guide subject table (subject-level NSS score):
   "[university name] [subject] Guardian University Guide student satisfaction"
   fetch_page the subject table on theguardian.com/education — extract the
   "Satisfied with course" and "Satisfied with teaching" percentage columns
   for the target university row.

2. Complete University Guide subject table:
   "[university name] [subject] Complete University Guide student satisfaction"
   fetch_page thecompleteuniversityguide.co.uk subject table — extract the
   "Student Satisfaction" column (NSS Q1–24 average).

3. Whatuni Student Choice Awards rankings table:
   "[university name] Whatuni Student Choice Awards ranking"
   fetch_page whatuni.com/student-awards-winners/wusca-rankings/university-of-the-year/
   Look up the university's overall position. Also check the
   "Lecturers and Teaching Quality" and "Student Support" category tables
   if a tool call is still available.

CRITICAL: Never report a satisfaction figure sourced from the university's
own website. Always go to the source table. A subject-level NSS score is
always more useful than an institution-wide score.

### Australian universities

Search in this order:

1. ComparED subject-level data (primary):
   "[university name] [subject] student satisfaction compared.edu.au"
   fetch_page compared.edu.au and search for the institution + subject area.
   Extract: Teaching Quality %, Skills Development %, Overall Educational
   Experience %, and any subject-level ranking position.

2. QILT SES national institution-level (secondary, if subject-level not found):
   "[university name] QILT student experience survey [year]"
   Extract the Overall Educational Experience % from qilt.edu.au results.

Do not use the university's own press release quoting QILT figures —
fetch the QILT or ComparED page directly.

### Singapore universities

Singapore has no government student satisfaction survey. The MOE Graduate
Employment Survey (GES / JAUGES) measures employment outcomes only —
it is not a satisfaction survey and must not be used here.

Do NOT spend tool budget searching for a Singapore satisfaction survey.
Leave student_satisfaction_rankings as an empty list.
Write the following exact text in the notes field:
"No equivalent student satisfaction survey exists for Singapore universities.
MOE GES covers graduate employment outcomes only."

GES employment data is useful context — include a brief note in
ranking_summary and notes if retrieved elsewhere, but it belongs in
employability context, not satisfaction.

### Other countries

Leave student_satisfaction_rankings empty and note the absence in notes.
Do not fabricate satisfaction data or use unverified aggregator sites.

## Signal Quality Rules

- Only include rankings from the four named sources: QS, THE, Guardian,
  Complete University Guide. Do not include unverified lists from marketing
  sites or newspaper supplements that are not those four sources.
- Only use rankings and survey data dated within the last 2 years. Discard
  any entry older than 2 years. If the most recent data found is older than
  2 years, leave the list empty and note the gap.
- If a university is listed as "unranked" for a subject, record it as such —
  do not omit the finding.
- Distinguish subject rank from overall rank explicitly in every entry and
  in the summary.
- Satisfaction scores must come from primary source tables only.

**Banned source domains — apply to every entry in every list:**

- University's own domain — the university is reporting its own result.
  Go to the ranking body's page directly.
- Social media (instagram.com, twitter.com, x.com, linkedin.com,
  facebook.com, tiktok.com).
- Aggregator and mirror sites (uscholars.in, universitycompare.com,
  uniranking.org, and any site that republishes QS, THE, or QILT data
  without being that body itself).

When Tavily returns a snippet where the rank figure looks correct but the
URL is from a banned domain, treat the URL as unusable. The rank figure
may guide your next search but you must find the canonical source before
creating an entry.

## Tool Budget — 8 calls

Suggested allocation:
- 2 calls: subject rankings (QS + Guardian/CUG)
- 2 calls: satisfaction (Guardian subject table + ComparED or WUSCAs)
- 1 call: employability ranking
- 1 call: overall rank
- 2 calls: fetch_page on specific table pages to extract exact figures

Singapore universities: redirect the 2 satisfaction calls to subject
rankings or employability instead.

## Tool Usage Strategy

Tavily is the primary search tool. Use fetch_page when Tavily returns a
snippet confirming the table is on a specific permitted URL.

Do not retry a failed query more than once.

**Recovery procedure when Tavily returns a banned-domain URL:**

1. Note the rank figure and source name from the snippet text.
2. Construct a new search query targeting the ranking body's own domain:
     "[ranking body name] [university name] [subject or award category] [year]"
3. If the new query returns a result on a permitted domain, fetch_page that
   URL to confirm the entry.
4. If after 1 retry no permitted-domain page is found, omit the entry.
   Use an empty string for the url field and record the gap in notes.
   Do not create an entry with a banned-domain URL under any circumstances.

**Specific WUSCAs recovery note:**
If Tavily returns a university's social media post celebrating a WUSCAs win,
extract the award category and approximate year from the text, then fetch
whatuni.com/student-awards-winners/wusca-rankings/university-of-the-year/
directly to confirm rank position and year before creating the SatisfactionEntry.

## Edge Cases

**Subject area not separately ranked:**
Niche courses may fall under a broader subject in ranking tables. Use the
closest applicable subject and note the mapping in notes.

**University only appears in national rankings, not world rankings:**
UK national tables (Guardian, CUG) and Australian ComparED subject tables
are valid primary sources. List both where available.

**Ranking position given as a band, not a number:**
"51–100" is a valid rank string. Do not convert it to a single integer.

**NSS score only available at institution level, not subject level:**
Record it with scope="Institution-wide" and note the gap. Do not present
an institution-wide score as a subject-level one.
```

---

### `skills/program/SKILL.md`

```markdown
---
key: program
name: Undergraduate Program Agent
description: Researches the specific undergraduate program structure, modules, and curriculum-to-career mapping.
tool_budget: 7
section_name: program
---

You research the undergraduate program structure for the intended course at
the university. You write to board.program as a ProgramOutput. You fire
SectionCompletedMessage(section_name="program") when done, or
SectionFailedMessage on unrecoverable error.

You receive career context from board.career — specifically `in_demand_skills`.
Use these to build the `skill_mappings` field.

## Source Rule

**All data must come from the university's official domain only — no exceptions.**

If you cannot find the information on the official domain, leave the field
empty. Do not use UCAS, aggregators, student forums, or any third-party site
as a fallback. A low-confidence output with honest gaps is correct behaviour.
A populated output sourced from third-party sites is a failure.

## Research Steps

**Step 1 — Confirm the official domain**

Search: `"[university name] official website"`

Identify the university's official domain from the result. All subsequent
searches and fetches must target only this domain.

**Step 2 — Find the course page**

Run this search query exactly, substituting the values:
  [university name] [course] undergraduate

Example pattern (do not copy literally — substitute actual values):
  If university is "X" and course is "Y": search "X Y undergraduate"

The official course page is almost always the first or second result.
Check the URL of the top results — the course page will be on the
official domain and will contain the course name in the path.
fetch_page that URL immediately.

Do not fetch student profile pages, news pages, fee documents, PDF handbooks,
or department overview pages — these never contain module lists. If the
first result on the official domain is any of these, skip it and check
the next result on the official domain.

If no course page is found in the first search, try once more:
  [university name] [course] BSc modules

If still no course page found on the official domain after 2 searches,
set confidence='low' and record in curriculum_notes that the official
course page was not found.

**Step 3 — Extract program variants and structure**

From the official course page extract:
- All degree titles matching the intended course (BSc, BEng, MEng, BA variants)
- Degree type, duration in years, UCAS code (if listed on the page)
- Whether a sandwich/placement year or study abroad option is offered

**Step 4 — Extract modules**

From the same page, or a linked curriculum/modules page on the same domain,
extract:
- Year 1 and Year 2 compulsory modules by name exactly as listed
- Any optional/elective modules

If the course page links to a separate modules page, fetch_page that URL
only if it is on the official domain. Do not infer module names from
snippets — only include modules confirmed from a fetched page.

**Step 5 — Map skills**

For each skill in `in_demand_skills`, identify which confirmed modules
develop it. An empty mapping is acceptable — do not fabricate module names.

## Handling Failures

**404:** Do not guess alternative URL patterns. Run one new search on the
official domain with different terms. Move on if it also fails.

**robots.txt block:** Treat as a permanent failure for that path. Do not
retry. Note it in `curriculum_notes` and move on.

**No module list published:** Some universities publish only program
overviews. Return the program variants found, leave `core_modules` and
`electives` empty, set `confidence: "low"`, and note the gap.

**Cannot find official page at all:** Set `confidence: "low"` and note
the failed search attempts in `curriculum_notes`. Do not populate any
field from a non-official source.

## Output Requirements

- `matching_programs`: all degree variants found on the official domain — at least 1 required
- `core_modules`: Year 1 and Year 2 compulsory modules only; `compulsory: True`
- `electives`: optional modules; `compulsory: False`
- `skill_mappings`: one entry per in-demand skill; `modules` may be empty
- `curriculum_notes`: gaps, anomalies, blocked pages, failed searches
- `sources`: official domain URLs only — never UCAS or third-party
- `confidence`: `"high"` = full Year 1 + Year 2 module list confirmed from official source;
  `"medium"` = partial module data from official source;
  `"low"` = program titles only, or official page not found
```

---

## 1d.3 Agent Implementations

All three agents follow the same structure as `CareerAgent` from Stage 1c.
The key differences are highlighted.

### `agents/background_agent.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.section_completed import SectionCompletedMessage
from schemas.messages.section_failed import SectionFailedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.background_output import BackgroundOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search


class BackgroundAgent(BaseAgent):
    """Researches institutional background and department-level industry partnerships.

    Subscribes to: CareerResearchCompletedMessage
    Writes to:     board.background (BackgroundOutput)
    Fires:         SectionCompletedMessage(section_name="background") on success
                   SectionFailedMessage(section_name="background") on error
    """

    def __init__(self, instructions: str = "", tool_budget: int = 6) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=BackgroundOutput,
            system_prompt=self.get_instruction(),
            capabilities=[self._setup_telemetry_hooks()],
            tools=[tavily_search, fetch_page],
        )

        logger.info("BackgroundAgent | initialized")

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.career_completed import CareerResearchCompletedMessage

        async def handler(message: CareerResearchCompletedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(CareerResearchCompletedMessage, handler)
        logger.info("BackgroundAgent | subscribed to MessageHub")

    def get_instruction(self) -> str:
        base = "You are the University Background Agent in a university research pipeline."
        return base + "\n\n" + self.instructions if self.instructions else base

    def reset(self) -> None:
        self._calls_made = 0

    # ── Core handler ──────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        self._calls_made = 0

        logger.info(
            "BackgroundAgent | starting — university=%r",
            deps.context.university_name,
        )

        await deps.hub.publish(ProgressUpdateMessage(
            status="started",
            message=f"Researching background on {deps.context.university_name}…",
            triggered_by="background_agent",
            timestamp=datetime.now().isoformat(),
        ))

        task_brief = (
            f"University: {deps.context.university_name}\n"
            f"Course: {deps.context.intended_course}\n"
            f"Country: {deps.context.country}\n"
            f"Study level: {deps.context.study_level}"
        )


        import traceback
        from pydantic import ValidationError

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.background = result.output

            logger.info(
                "BackgroundAgent | completed — confidence=%s",
                result.output.confidence,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="University background research complete.",
                triggered_by="background_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionCompletedMessage(
                section_name="background",
                triggered_by="background_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except ValidationError as exc:
            # LLM returned output that failed schema validation — log each field error
            logger.error("BackgroundAgent | schema validation failed:")
            for err in exc.errors():
                logger.error("  field=%s  error=%s  input=%s", err["loc"], err["msg"], err.get("input"))

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Background research produced invalid output: {exc.error_count()} field errors",
                triggered_by="background_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="background",
                reason=f"Schema validation failed: {exc.error_count()} errors — check logs",
                triggered_by="background_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            # Log the full traceback unconditionally — not just for FallbackModel
            logger.error("BackgroundAgent | failed: %s", exc)
            traceback.print_exc()

            # Then also unpack FallbackModel sub-exceptions if present
            if hasattr(exc, 'exceptions'):
                for i, sub in enumerate(exc.exceptions):
                    logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
                    traceback.print_exception(type(sub), sub, sub.__traceback__)

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Background research failed: {exc}",
                triggered_by="background_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="background",
                reason=str(exc),
                triggered_by="background_agent",
                timestamp=datetime.now().isoformat(),
            ))
```

---

### `agents/rankings_agent.py`

```python
# agents/rankings_agent.py
from __future__ import annotations

from datetime import datetime

from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.section_completed import SectionCompletedMessage
from schemas.messages.section_failed import SectionFailedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.rankings_output import RankingsOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search


class RankingsAgent(BaseAgent):
    """Researches subject-specific, employability, student satisfaction,
    and overall university rankings.

    Satisfaction sources are country-dependent:
      UK:          NSS via Guardian/CUG subject tables; Whatuni Student Choice Awards
      Australia:   QILT Student Experience Survey via compared.edu.au (subject-level)
      Singapore:   No equivalent survey — student_satisfaction_rankings left empty

    Subscribes to: CareerResearchCompletedMessage
    Writes to:     board.rankings (RankingsOutput)
    Fires:         SectionCompletedMessage(section_name="rankings") on success
                   SectionFailedMessage(section_name="rankings") on error
    """

    def __init__(self, instructions: str = "", tool_budget: int = 8) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=RankingsOutput,
            system_prompt=self.get_instruction(),
            capabilities=[self._setup_telemetry_hooks()],
            tools=[tavily_search, fetch_page],
        )

        logger.info("RankingsAgent | initialized")

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.career_completed import CareerResearchCompletedMessage

        async def handler(message: CareerResearchCompletedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(CareerResearchCompletedMessage, handler)
        logger.info("RankingsAgent | subscribed to MessageHub")

    def get_instruction(self) -> str:
        base = "You are the Subject Rankings Agent in a university research pipeline."
        return base + "\n\n" + self.instructions if self.instructions else base

    def reset(self) -> None:
        self._calls_made = 0

    # ── Core handler ──────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        self._calls_made = 0

        logger.info(
            "RankingsAgent | starting — university=%r course=%r country=%r",
            deps.context.university_name,
            deps.context.intended_course,
            deps.context.country,
        )

        await deps.hub.publish(ProgressUpdateMessage(
            status="started",
            message=f"Researching rankings for {deps.context.university_name}…",
            triggered_by="rankings_agent",
            timestamp=datetime.now().isoformat(),
        ))

        task_brief = (
            f"University: {deps.context.university_name}\n"
            f"Course: {deps.context.intended_course}\n"
            f"Country: {deps.context.country}\n"
            f"Study level: {deps.context.study_level}\n\n"
            "Research subject-specific rankings, student satisfaction, "
            "employability rankings, and overall university rank. "
            "Use the country field to select the correct satisfaction source: "
            "UK → NSS via Guardian/CUG subject tables + Whatuni Student Choice Awards; "
            "Australia → QILT SES via compared.edu.au; "
            "Singapore → no satisfaction survey exists, leave "
            "student_satisfaction_rankings empty and note the absence."
        )

        import traceback
        from pydantic import ValidationError

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.rankings = result.output

            logger.info(
                "RankingsAgent | completed — subject_entries=%d "
                "satisfaction_entries=%d confidence=%s",
                len(result.output.subject_rankings),
                len(result.output.student_satisfaction_rankings),
                result.output.confidence,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="Rankings research complete.",
                triggered_by="rankings_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionCompletedMessage(
                section_name="rankings",
                triggered_by="rankings_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except ValidationError as exc:
            logger.error("RankingsAgent | schema validation failed:")
            for err in exc.errors():
                logger.error("  field=%s  error=%s  input=%s", err["loc"], err["msg"], err.get("input"))

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Rankings research produced invalid output: {exc.error_count()} field errors",
                triggered_by="rankings_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="rankings",
                reason=f"Schema validation failed: {exc.error_count()} errors — check logs",
                triggered_by="rankings_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            logger.error("RankingsAgent | failed: %s", exc)
            traceback.print_exc()

            if hasattr(exc, 'exceptions'):
                for i, sub in enumerate(exc.exceptions):
                    logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
                    traceback.print_exception(type(sub), sub, sub.__traceback__)

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Rankings research failed: {exc}",
                triggered_by="rankings_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="rankings",
                reason=str(exc),
                triggered_by="rankings_agent",
                timestamp=datetime.now().isoformat(),
            ))
```

---

### `agents/program_agent.py`

`ProgramAgent` is the only Stage 1d agent that reads `board.career` before
constructing its task brief. The `in_demand_skills` extracted by `CareerAgent`
are passed directly into the task brief so the LLM can build the
`skill_mappings` field without needing to re-derive them.

```python
# agents/program_agent.py
from __future__ import annotations

from datetime import datetime

import traceback
from pydantic import ValidationError

from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.section_completed import SectionCompletedMessage
from schemas.messages.section_failed import SectionFailedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.program_output import ProgramOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search


class ProgramAgent(BaseAgent):
    """Researches the undergraduate program structure and curriculum-to-career mapping.

    Subscribes to: CareerResearchCompletedMessage
    Writes to:     board.program (ProgramOutput)
    Fires:         SectionCompletedMessage(section_name="program") on success
                   SectionFailedMessage(section_name="program") on error

    Reads board.career.in_demand_skills before running — passes them into the
    task brief so the LLM can map curriculum modules to career skills.
    If board.career is None (CareerAgent failed), the skill_mappings field
    will be empty — that is expected and handled gracefully.
    """

    def __init__(self, instructions: str = "", tool_budget: int = 7) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=ProgramOutput,
            system_prompt=self.get_instruction(),
            capabilities=[self._setup_telemetry_hooks()],
            tools=[tavily_search, fetch_page],
        )

        logger.info("ProgramAgent | initialized")

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.career_completed import CareerResearchCompletedMessage

        async def handler(message: CareerResearchCompletedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(CareerResearchCompletedMessage, handler)
        logger.info("ProgramAgent | subscribed to MessageHub")

    def get_instruction(self) -> str:
        base = "You are the Undergraduate Program Agent in a university research pipeline."
        return base + "\n\n" + self.instructions if self.instructions else base

    def reset(self) -> None:
        self._calls_made = 0

    # ── Core handler ──────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        self._calls_made = 0

        logger.info(
            "ProgramAgent | starting — university=%r course=%r",
            deps.context.university_name,
            deps.context.intended_course,
        )

        await deps.hub.publish(ProgressUpdateMessage(
            status="started",
            message=f"Researching program structure for {deps.context.intended_course}…",
            triggered_by="program_agent",
            timestamp=datetime.now().isoformat(),
        ))

        # Read in_demand_skills from CareerAgent output if available
        in_demand_skills: list[str] = []
        if deps.board.career:
            in_demand_skills = deps.board.career.in_demand_skills

        skills_str = (
            "\n".join(f"  - {s}" for s in in_demand_skills)
            if in_demand_skills
            else "  (not available — CareerAgent did not complete)"
        )

        task_brief = (
            f"University: {deps.context.university_name}\n"
            f"Course: {deps.context.intended_course}\n"
            f"Country: {deps.context.country}\n"
            f"Study level: {deps.context.study_level}\n"
            f"In-demand skills to map (from career research):\n{skills_str}"
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)

            if result.output is None:
                raise ValueError(
                    "Agent returned None output — LLM produced an empty or "
                    "unparseable structured response"
                )

            deps.board.program = result.output

            logger.info(
                "ProgramAgent | completed — programs=%d confidence=%s",
                len(result.output.matching_programs),
                result.output.confidence,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="Program structure research complete.",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionCompletedMessage(
                section_name="program",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except ValidationError as exc:
            logger.error("ProgramAgent | schema validation failed:")
            for err in exc.errors():
                logger.error("  field=%s  error=%s  input=%s", err["loc"], err["msg"], err.get("input"))

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Program research produced invalid output: {exc.error_count()} field errors",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="program",
                reason=f"Schema validation failed: {exc.error_count()} errors — check logs",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            logger.error("ProgramAgent | failed: %s", exc)
            traceback.print_exc()

            if hasattr(exc, 'exceptions'):
                for i, sub in enumerate(exc.exceptions):
                    logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
                    traceback.print_exception(type(sub), sub, sub.__traceback__)

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Program research failed: {exc}",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="program",
                reason=str(exc),
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))
```

**Why `ProgramAgent` reads `board.career` directly in `handle()`, not in `subscribe()`:**
`subscribe()` is called before the pipeline fires. At subscription time, `board.career`
is always `None`. `handle()` is called after `CareerResearchCompletedMessage` fires —
at that point, `board.career` has been written (or remains `None` if CareerAgent failed).
Reading it in `handle()` is the only time the data is available.

**Why the `SectionFailedMessage` fires even on exception:** the quorum gate in
`ScoringAgent` waits for `expected_sections` results — pass or fail. If an exception
is swallowed without publishing `SectionFailedMessage`, the gate never opens and the
pipeline stalls permanently. Always fire one of the two section messages, regardless
of outcome.

---

---

## 1d.4 Exception Handling

Every agent in Stage 1d uses the same two-layer exception handling pattern
in its `handle()` method. This section defines the pattern once — it applies
identically to `BackgroundAgent`, `RankingsAgent`, and `ProgramAgent`.

---

### Why Two Separate Except Blocks

A single `except Exception` would catch pydantic `ValidationError` but hide
which field failed. The most common runtime failure at this stage is the LLM
returning a field value that does not match the schema — wrong type, wrong
Literal value, or a missing required field. Without a dedicated `ValidationError`
block, the error log shows only the exception message with no field detail,
making it very difficult to know whether to fix the SKILL.md output rules,
the schema, or the prompt.

`ValidationError` is caught first (more specific), then `Exception` catches
everything else (FallbackModel exhaustion, tool errors, timeouts, unexpected
model behaviour).

---

### Layer 1 — `ValidationError` (Schema Mismatch)

**When it fires:** pydantic raises `ValidationError` when the LLM's output
cannot be coerced into the agent's output schema. Common causes at this stage:

| Field | Likely mismatch |
|---|---|
| `ProgramVariant.duration_years` | LLM returns `"3"` (string) instead of `3` (int) |
| `BackgroundOutput.public_or_private` | LLM returns `"Public"` instead of `"public"` |
| `RankingEntry.rank` | LLM returns `None` instead of `"unranked"` |
| Any `Literal` field | LLM returns a value outside the allowed set |
| Any `list[...]` field | LLM returns `null` instead of `[]` |

**What to do when it fires:**
1. Read the field log — it shows `field`, `error`, and `input` for each
   violation. The `input` value tells you exactly what the LLM returned.
2. If the input is a type mismatch (e.g. `"3"` for an `int` field): tighten
   the SKILL.md output requirement for that field. Add an explicit type
   instruction.
3. If the input is a Literal violation (e.g. `"Public"` for `"public"`):
   add the exact allowed values to the Field description with a note that
   casing is significant.
4. If the field is `null` / `None` for a list field: add a SKILL.md rule
   stating the field must always be a list, even if empty (`[]`).

**Pattern:**

```python
except ValidationError as exc:
    logger.error("BackgroundAgent | schema validation failed:")
    for err in exc.errors():
        logger.error(
            "  field=%s  error=%s  input=%s",
            err["loc"], err["msg"], err.get("input"),
        )

    await deps.hub.publish(ProgressUpdateMessage(
        status="failed",
        message=f"Background research produced invalid output: {exc.error_count()} field errors",
        triggered_by="background_agent",
        timestamp=datetime.now().isoformat(),
    ))

    await deps.hub.publish(SectionFailedMessage(
        section_name="background",
        reason=f"Schema validation failed: {exc.error_count()} errors — check logs",
        triggered_by="background_agent",
        timestamp=datetime.now().isoformat(),
    ))
```

Change `BackgroundAgent` / `"background"` to the relevant agent and section
name in `RankingsAgent` and `ProgramAgent`.

---

### Layer 2 — `Exception` (Everything Else)

**When it fires:** any error that is not a schema mismatch. The most common
causes at this stage:

| Exception | Cause |
|---|---|
| `FallbackModel` exhaustion | Both primary and secondary models failed — check sub-exceptions |
| `ModelHTTPError` (429) | Rate limit hit on primary or secondary model |
| `ModelHTTPError` (404) | Model name is wrong or has been deprecated |
| `UnexpectedModelBehavior` | Model exceeded retry limit for structured output — usually a thinking-token model (e.g. deepseek-r1) producing malformed JSON |
| Tool error | `tavily_search` or `fetch_page` raised — check tool logs |
| `asyncio.TimeoutError` | Agent exceeded wall-clock time — not currently enforced but possible in future |

**What to do when it fires:**
1. `traceback.print_exc()` runs unconditionally — read the full stack trace
   first before looking at the summary log line.
2. If `hasattr(exc, 'exceptions')` is True, it is a `FallbackModel` error.
   Read each sub-exception in order — the first is the primary model failure,
   the second is the secondary. Fix whichever is broken.
3. If the error is `UnexpectedModelBehavior: Exceeded maximum output retries`,
   the model is a reasoning/thinking model that wraps output in `<think>`
   blocks. Switch to a non-thinking variant or a standard chat model.
4. If the error is a tool error, check whether the tool client was initialised
   before the agent ran — see Section 14 of the Master Reference.

**Pattern:**

```python
except Exception as exc:
    logger.error("BackgroundAgent | failed: %s", exc)
    traceback.print_exc()

    if hasattr(exc, 'exceptions'):
        for i, sub in enumerate(exc.exceptions):
            logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
            traceback.print_exception(type(sub), sub, sub.__traceback__)

    await deps.hub.publish(ProgressUpdateMessage(
        status="failed",
        message=f"Background research failed: {exc}",
        triggered_by="background_agent",
        timestamp=datetime.now().isoformat(),
    ))

    await deps.hub.publish(SectionFailedMessage(
        section_name="background",
        reason=str(exc),
        triggered_by="background_agent",
        timestamp=datetime.now().isoformat(),
    ))
```

---

### Full Handle Method Structure

The complete `try/except` block sits inside `handle()` after the task brief
is constructed. The structure is identical across all three agents:

```python
async def handle(self, deps: Deps) -> None:
    self._calls_made = 0  # reset budget counter per-run

    task_brief = self._build_task_brief(deps)  # agent-specific

    import traceback
    from pydantic import ValidationError

    try:
        result = await self._agent.run(task_brief, deps=deps)
        deps.board.<field> = result.output  # agent-specific field name

        logger.info(
            "<AgentName> | completed — confidence=%s",
            result.output.confidence,
        )

        await deps.hub.publish(ProgressUpdateMessage(
            status="completed",
            message="<Section> research complete.",
            triggered_by="<agent_name>",
            timestamp=datetime.now().isoformat(),
        ))

        await deps.hub.publish(SectionCompletedMessage(
            section_name="<section_name>",
            triggered_by="<agent_name>",
            timestamp=datetime.now().isoformat(),
        ))

    except ValidationError as exc:
        logger.error("<AgentName> | schema validation failed:")
        for err in exc.errors():
            logger.error(
                "  field=%s  error=%s  input=%s",
                err["loc"], err["msg"], err.get("input"),
            )

        await deps.hub.publish(ProgressUpdateMessage(
            status="failed",
            message=f"<Section> research produced invalid output: {exc.error_count()} field errors",
            triggered_by="<agent_name>",
            timestamp=datetime.now().isoformat(),
        ))

        await deps.hub.publish(SectionFailedMessage(
            section_name="<section_name>",
            reason=f"Schema validation failed: {exc.error_count()} errors — check logs",
            triggered_by="<agent_name>",
            timestamp=datetime.now().isoformat(),
        ))

    except Exception as exc:
        logger.error("<AgentName> | failed: %s", exc)
        traceback.print_exc()

        if hasattr(exc, 'exceptions'):
            for i, sub in enumerate(exc.exceptions):
                logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
                traceback.print_exception(type(sub), sub, sub.__traceback__)

        await deps.hub.publish(ProgressUpdateMessage(
            status="failed",
            message=f"<Section> research failed: {exc}",
            triggered_by="<agent_name>",
            timestamp=datetime.now().isoformat(),
        ))

        await deps.hub.publish(SectionFailedMessage(
            section_name="<section_name>",
            reason=str(exc),
            triggered_by="<agent_name>",
            timestamp=datetime.now().isoformat(),
        ))
```

Substitutions per agent:

| Placeholder | BackgroundAgent | RankingsAgent | ProgramAgent |
|---|---|---|---|
| `<field>` | `background` | `rankings` | `program` |
| `<AgentName>` | `BackgroundAgent` | `RankingsAgent` | `ProgramAgent` |
| `<agent_name>` | `background_agent` | `rankings_agent` | `program_agent` |
| `<section_name>` | `background` | `rankings` | `program` |
| `<Section>` | `Background` | `Rankings` | `Program` |

---

### What the Quorum Gate Sees

Both exception paths publish `SectionFailedMessage`. The `ScoringAgent`
quorum gate increments its counter on both `SectionCompletedMessage` and
`SectionFailedMessage` — so a failed agent does not stall the pipeline.
The failed blackboard field remains `None`. `ScoringAgent` handles `None`
fields by recording them as unscored with a note, rather than raising.

This means a single agent failure produces a degraded report, not a crash.


---

## 1d.5 Updated `services/research_handler.py`

Add the three new agents to the handler. The handler constructs all agents at startup
and wires them in `handle_request()`.

```python
# services/research_handler.py — Stage 1d additions (show only changes)

# New imports
from agents.background_agent import BackgroundAgent
from agents.rankings_agent import RankingsAgent
from agents.program_agent import ProgramAgent

# In __init__, after CareerAgent construction:
background_skill = _get("background")
self._background_agent = BackgroundAgent(
    instructions=background_skill.instructions if background_skill else "",
    tool_budget=background_skill.tool_budget if background_skill else 6,
)

rankings_skill = _get("rankings")
self._rankings_agent = RankingsAgent(
    instructions=rankings_skill.instructions if rankings_skill else "",
    tool_budget=rankings_skill.tool_budget if rankings_skill else 6,
)

program_skill = _get("program")
self._program_agent = ProgramAgent(
    instructions=program_skill.instructions if program_skill else "",
    tool_budget=program_skill.tool_budget if program_skill else 7,
)

logger.info("research_handler | BackgroundAgent, RankingsAgent, ProgramAgent constructed")


# In handle_request(), after self._career_agent.reset() + subscribe:
for agent in (self._background_agent, self._rankings_agent, self._program_agent):
    agent.reset()
    agent.subscribe(hub, deps)
```

---

## 1d.6 Updated `main.py`

```python
# main.py — Stage 1d additions
# After existing board.career print block, add:

for field_name, label in [
    ("background", "board.background"),
    ("rankings",   "board.rankings"),
    ("program",    "board.program"),
]:
    value = getattr(board, field_name)
    if value is None:
        logger.error("main | %s is None", label)
    else:
        logger.info("main | %s populated successfully", label)
        print(f"\n── {label} ──────────────────────────────────────────")
        print(value.model_dump_json(indent=2))
        print("──────────────────────────────────────────────────────────\n")
```

Note that Stage 1d runs three concurrent agents for the first time. The three agents
all subscribe to `CareerResearchCompletedMessage`, so when CareerAgent fires that
message, all three start concurrently via `asyncio.gather()` in the hub. This is the
pipeline's concurrent fan-out working as designed — the three board fields will
populate in whatever order the LLM calls complete.

---

## 1d.7 Tests — `tests/test_stage_1d.py`

```python
# tests/test_stage_1d.py
"""
Stage 1d tests — BackgroundAgent, RankingsAgent, ProgramAgent.

Structural tests run without API calls.
Integration tests (marked) make real LLM calls — skip with:
  pytest -k "not populates_board and not fires_completed"
"""
from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime

from core.message_hub import MessageHub
from core.blackboard import Blackboard
from core.deps import Deps, ResearchContext
from core.skill_loader import scan_skills_dir

from agents.background_agent import BackgroundAgent
from agents.rankings_agent import RankingsAgent
from agents.program_agent import ProgramAgent

from schemas.outputs.background_output import BackgroundOutput
from schemas.outputs.rankings_output import RankingsOutput
from schemas.outputs.program_output import ProgramOutput

from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.section_completed import SectionCompletedMessage
from schemas.messages.section_failed import SectionFailedMessage

TIMESTAMP = datetime.now().isoformat()


# ── Output schema imports ─────────────────────────────────────────────────────

def test_background_output_imports_cleanly() -> None:
    from schemas.outputs.background_output import (  # noqa: F401
        BackgroundOutput, AccreditationItem, IndustryPartnership, BackgroundSource
    )

def test_rankings_output_imports_cleanly() -> None:
    from schemas.outputs.rankings_output import (  # noqa: F401
        RankingsOutput, RankingEntry
    )

def test_program_output_imports_cleanly() -> None:
    from schemas.outputs.program_output import (  # noqa: F401
        ProgramOutput, ProgramVariant, ModuleItem, SkillMapping, ProgramSource
    )


# ── SKILL.md loading ──────────────────────────────────────────────────────────

def test_background_skill_loads() -> None:
    skills = scan_skills_dir(Path("skills"))
    assert "background" in skills
    assert skills["background"].tool_budget == 6
    assert skills["background"].section_name == "background"

def test_rankings_skill_loads() -> None:
    skills = scan_skills_dir(Path("skills"))
    assert "rankings" in skills
    assert skills["rankings"].tool_budget == 6
    assert skills["rankings"].section_name == "rankings"

def test_program_skill_loads() -> None:
    skills = scan_skills_dir(Path("skills"))
    assert "program" in skills
    assert skills["program"].tool_budget == 7
    assert skills["program"].section_name == "program"


# ── Agent construction ────────────────────────────────────────────────────────

def test_background_agent_constructs() -> None:
    agent = BackgroundAgent()
    assert agent._agent is not None
    assert agent._tool_budget == 6
    assert agent._calls_made == 0

def test_rankings_agent_constructs() -> None:
    agent = RankingsAgent()
    assert agent._agent is not None
    assert agent._tool_budget == 6

def test_program_agent_constructs() -> None:
    agent = ProgramAgent()
    assert agent._agent is not None
    assert agent._tool_budget == 7


# ── reset() ───────────────────────────────────────────────────────────────────

def test_all_agents_reset_clears_calls_made() -> None:
    for AgentClass in (BackgroundAgent, RankingsAgent, ProgramAgent):
        agent = AgentClass()
        agent._calls_made = 5
        agent.reset()
        assert agent._calls_made == 0, f"{AgentClass.__name__}.reset() did not clear _calls_made"


# ── get_instruction() ─────────────────────────────────────────────────────────

def test_get_instruction_includes_skill_body() -> None:
    for AgentClass in (BackgroundAgent, RankingsAgent, ProgramAgent):
        agent = AgentClass(instructions="UNIQUE_MARKER_XYZ")
        assert "UNIQUE_MARKER_XYZ" in agent.get_instruction(), (
            f"{AgentClass.__name__}.get_instruction() did not include injected instructions"
        )

def test_get_instruction_base_carries_no_domain_rules() -> None:
    """Base prompt must be a single identity line — domain rules belong in SKILL.md."""
    for AgentClass in (BackgroundAgent, RankingsAgent, ProgramAgent):
        agent = AgentClass(instructions="")
        base = agent.get_instruction()
        assert len(base.strip().splitlines()) == 1, (
            f"{AgentClass.__name__}.get_instruction() base has more than 1 line when no instructions provided"
        )


# ── subscribe() ───────────────────────────────────────────────────────────────

def test_all_agents_subscribe_to_career_completed() -> None:
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
    for AgentClass in (BackgroundAgent, RankingsAgent, ProgramAgent):
        agent = AgentClass()
        agent.subscribe(hub, deps)

    assert hub.subscriber_count(CareerResearchCompletedMessage) == 3


# ── Integration tests (real LLM calls) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_background_agent_populates_board() -> None:
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
    agent = BackgroundAgent()
    agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test", timestamp=TIMESTAMP,
    ))

    assert board.background is not None
    assert isinstance(board.background, BackgroundOutput)
    assert board.background.confidence in ("high", "medium", "low")


@pytest.mark.asyncio
async def test_rankings_agent_populates_board() -> None:
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
    agent = RankingsAgent()
    agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test", timestamp=TIMESTAMP,
    ))

    assert board.rankings is not None
    assert isinstance(board.rankings, RankingsOutput)
    assert len(board.rankings.subject_rankings) >= 1


@pytest.mark.asyncio
async def test_program_agent_populates_board() -> None:
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
    agent = ProgramAgent()
    agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test", timestamp=TIMESTAMP,
    ))

    assert board.program is not None
    assert isinstance(board.program, ProgramOutput)
    assert len(board.program.matching_programs) >= 1


@pytest.mark.asyncio
async def test_all_three_fire_section_completed() -> None:
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
    fired: list[SectionCompletedMessage] = []

    async def capture(msg):
        fired.append(msg)

    hub.subscribe(SectionCompletedMessage, capture)

    for AgentClass in (BackgroundAgent, RankingsAgent, ProgramAgent):
        agent = AgentClass()
        agent.subscribe(hub, deps)

    await hub.publish(CareerResearchCompletedMessage(
        triggered_by="test", timestamp=TIMESTAMP,
    ))

    section_names = {m.section_name for m in fired}
    assert section_names == {"background", "rankings", "program"}, (
        f"Expected all three section names, got: {section_names}"
    )
```

---

## 1d.8 Run the Tests

```bash
# Structural tests only (no LLM calls)
pytest tests/test_stage_1d.py -v -k "not populates_board and not fires_completed"

# Full suite (requires OPENROUTER_API_KEY and RESEARCH_MODEL in .env)
pytest tests/test_stage_1d.py -v -s
```

Expected structural test output:

```
tests/test_stage_1d.py::test_background_output_imports_cleanly PASSED
tests/test_stage_1d.py::test_rankings_output_imports_cleanly PASSED
tests/test_stage_1d.py::test_program_output_imports_cleanly PASSED
tests/test_stage_1d.py::test_background_skill_loads PASSED
tests/test_stage_1d.py::test_rankings_skill_loads PASSED
tests/test_stage_1d.py::test_program_skill_loads PASSED
tests/test_stage_1d.py::test_background_agent_constructs PASSED
tests/test_stage_1d.py::test_rankings_agent_constructs PASSED
tests/test_stage_1d.py::test_program_agent_constructs PASSED
tests/test_stage_1d.py::test_all_agents_reset_clears_calls_made PASSED
tests/test_stage_1d.py::test_get_instruction_includes_skill_body PASSED
tests/test_stage_1d.py::test_get_instruction_base_carries_no_domain_rules PASSED
tests/test_stage_1d.py::test_all_agents_subscribe_to_career_completed PASSED
```

---

## 1d.9 Manual Verification

After tests pass, run the full CLI:

```bash
python main.py
```

Expected log sequence — all three agents run concurrently after CareerAgent fires:

```
INFO | career_agent | starting — university='University of Manchester' ...
WARNING | career_agent | completed — paths=5 confidence=high
INFO | background_agent | starting — university='University of Manchester'
INFO | rankings_agent | starting — university='University of Manchester' course='Computer Science'
INFO | program_agent | starting — university='University of Manchester' course='Computer Science'
INFO | background_agent | completed — confidence=high
INFO | rankings_agent | completed — subject_entries=3 confidence=high
INFO | program_agent | completed — programs=2 confidence=medium
```

The order of the three section agent log pairs is non-deterministic — they run
concurrently. All three completing before the process exits confirms the fan-out
is working correctly.

Confirm in the printed output:
- `board.background.founded` is a year string, not "unknown"
- `board.background.accreditations` is a list (may be empty — that is valid)
- `board.rankings.subject_rankings` contains at least 1 entry with a named source
- `board.rankings.ranking_summary` is a non-empty string
- `board.program.matching_programs` contains at least 1 entry
- `board.program.core_modules` is populated (if the university publishes modules)

---

## 1d.10 Common Failure Modes at This Stage

**`board.background` / `board.rankings` / `board.program` all remain `None`**
The three agents subscribe to `CareerResearchCompletedMessage`. If `CareerAgent`
fails to fire that message (possible if it throws before the `finally` publish),
none of the three handlers trigger. Check the `career_agent | failed` log.
Confirm `CareerResearchCompletedMessage` is fired unconditionally in
`CareerAgent.handle()`, outside the try/except.

**Only one or two of the three fields populate**
One agent threw an exception and published `SectionFailedMessage` instead.
Check the `*_agent | failed` log for the specific error. Common cause at this
stage: pydantic validation error because the LLM returned a field type mismatch
(e.g. `duration_years` as a string instead of int). Check the output schema
and tighten the SKILL.md output requirement if needed.

**`test_get_instruction_base_carries_no_domain_rules` fails**
The `get_instruction()` base string has more than one line. Trim it to a single
identity sentence. All domain rules belong in SKILL.md.

**`test_all_agents_subscribe_to_career_completed` fails with count 0 or < 3**
`hub.subscriber_count()` requires `MessageHub` to have `subscriber_count()` from
Stage 1a. If it's missing, add it. Also confirm all three `.subscribe()` calls
are made in the test before checking the count.

**`ProgramAgent` populates `skill_mappings` with empty lists for all skills**
This is correct if `deps.board.career` is `None` (CareerAgent was not run in
the test). In the full CLI run, `board.career` will be populated. If
`skill_mappings` is empty even in a full run, the LLM did not find curriculum
coverage for the skills — check the `curriculum_notes` field for an explanation.

---

## Stage 1d Completion Checklist

- [ ] `schemas/outputs/background_output.py` — `BackgroundOutput`,
      `AccreditationItem`, `IndustryPartnership`, `BackgroundSource` implemented
- [ ] `schemas/outputs/rankings_output.py` — `RankingsOutput`, `RankingEntry`
      implemented; `rank` field is `str` not `int`
- [ ] `schemas/outputs/program_output.py` — `ProgramOutput`, `ProgramVariant`,
      `ModuleItem`, `SkillMapping`, `ProgramSource` implemented
- [ ] `skills/background/SKILL.md` — frontmatter valid, `tool_budget: 6`,
      `section_name: background`, non-empty body
- [ ] `skills/rankings/SKILL.md` — frontmatter valid, `tool_budget: 6`,
      `section_name: rankings`, non-empty body
- [ ] `skills/program/SKILL.md` — frontmatter valid, `tool_budget: 7`,
      `section_name: program`, non-empty body
- [ ] `agents/background_agent.py` — subscribes to `CareerResearchCompletedMessage`,
      fires `SectionCompletedMessage` and `SectionFailedMessage`,
      `capabilities=[self._setup_telemetry_hooks()]` in Agent constructor
- [ ] `agents/rankings_agent.py` — same pattern as above
- [ ] `agents/program_agent.py` — reads `deps.board.career.in_demand_skills`
      in `handle()`, passes them into task brief, same pattern otherwise
- [ ] `services/research_handler.py` — constructs all three agents, resets and
      subscribes them in `handle_request()`
- [ ] `main.py` — prints `board.background`, `board.rankings`, `board.program`
- [ ] `pytest tests/test_stage_1d.py -v -k "not populates_board and not fires_completed"`
      — 13 structural tests pass
- [ ] `python main.py` — all three board fields populated from real data,
      log shows concurrent completion
- [ ] Stage 1c tests still pass: `pytest tests/test_stage_1c.py -v`

---

*End of Stage 1d Specification*