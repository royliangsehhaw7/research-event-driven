# schemas/job_posting.py
from __future__ import annotations

from pydantic import BaseModel, Field


class JobPosting(BaseModel):
    """A single job posting. Normalised from either Adzuna or MyCareersFuture."""

    title: str = Field(
        description=(
            "Job title as listed in the posting. "
            "Examples: 'Graduate Software Engineer', 'Data Analyst', "
            "'Junior Backend Developer'. "
            "Use this to assess role relevance and extract career path signals."
        )
    )
    company: str = Field(
        description=(
            "Name of the hiring company as listed in the posting. "
            "This is a real employer name — use it to populate "
            "CareerPath.typical_companies. "
            "Empty string if the company name was not provided by the API."
        )
    )
    location: str = Field(
        description=(
            "City or region of the role as returned by the API. "
            "Examples: 'London', 'Sydney CBD', 'Singapore'. "
            "May include broader regions (e.g. 'South East England'). "
            "Empty string if location was not provided."
        )
    )
    description: str = Field(
        description=(
            "Full job description text as returned by the API. "
            "This is the primary source for in_demand_skills extraction — "
            "read it for technology stacks, tools, frameworks, and soft skills "
            "mentioned across multiple postings. "
            "May be truncated by the API for very long postings."
        )
    )
    salary_min: float | None = Field(
        description=(
            "Minimum salary in local currency (annual), as a float. "
            "None if the posting did not include salary data. "
            "Use with salary_max and currency to populate SalaryRange entries. "
            "Do not infer a salary range from None — omit or write 'Not available'."
        )
    )
    salary_max: float | None = Field(
        description=(
            "Maximum salary in local currency (annual), as a float. "
            "None if the posting did not include salary data. "
            "salary_min and salary_max together define the full range for this posting."
        )
    )
    currency: str = Field(
        description=(
            "ISO 4217 currency code for the salary figures. "
            "Set by the tool based on the country: 'GBP' for UK, "
            "'AUD' for Australia, 'SGD' for Singapore. "
            "This is set by the tool — not derived from the posting text."
        )
    )
    date_posted: str = Field(
        description=(
            "Date the posting was published, as returned by the API. "
            "Format varies by source: Adzuna returns ISO datetime strings "
            "(e.g. '2024-03-15T10:22:00Z'); MCF returns date strings. "
            "All postings returned by these tools have passed a recency filter "
            "at the API level — do not treat very old dates as valid."
        )
    )
    skills: list[str] = Field(
        description=(
            "Structured skill tags returned directly by the API. "
            "MCF returns a skills array — names are extracted from it. "
            "Adzuna returns no structured skill tags — this is always [] for "
            "Adzuna postings. Do not scan description text to populate this field. "
            "The LLM reads the description field directly to extract skill signals "
            "for in_demand_skills — this field provides only structured API data."
        )
    )
    source_url: str = Field(
        description=(
            "Direct URL to the job posting on the originating job board. "
            "For Adzuna: the redirect URL from the API response. "
            "For MCF: constructed as "
            "'https://www.mycareersfuture.gov.sg/job/{uuid}'. "
            "Use this to verify posting details if needed."
        )
    )
    source: str = Field(
        description=(
            "Which tool returned this posting. Either 'adzuna' or 'mycareersfuture'. "
            "Use to audit which tool was called and confirm the correct "
            "country-tool routing was applied."
        )
    )


class JobPostingsResponse(BaseModel):
    """The full response from a job posting tool call."""

    query: str = Field(
        description=(
            "The search query passed to the job posting tool. "
            "Matches the query argument — use to confirm the correct role "
            "was searched for."
        )
    )
    country: str = Field(
        description=(
            "The country context used for this search. "
            "Matches deps.context.country at call time. "
            "Used to confirm the correct tool was routed to for the country."
        )
    )
    total_found: int = Field(
        description=(
            "Total number of matching postings in the API for this query, "
            "not just the number returned. "
            "Example: total_found=1200 with 15 postings returned means the API "
            "has many more results than were fetched. "
            "0 when error is set, or when the query genuinely matched nothing."
        )
    )
    postings: list[JobPosting] = Field(
        default_factory=list,
        description=(
            "Normalised job postings returned by the tool, up to max_results. "
            "May be an empty list when error is set or when the query matched "
            "nothing. Pass these directly into CareerOutput.job_postings — "
            "do not re-filter or summarise them before writing to the output."
        )
    )
    error: str | None = Field(
        default=None,
        description=(
            "Error message if the tool call failed or was routed to the wrong "
            "country. None on success. "
            "Common values: unsupported country message (e.g. calling adzuna_jobs "
            "for Singapore), HTTP error from the API, connection timeout. "
            "When error is set, postings is [] and total_found is 0. "
            "Do not retry on error — note it in CareerOutput.notes and continue."
        )
    )