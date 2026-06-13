# schemas/job_posting.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class JobPosting:
    """A single job posting. Normalised from either Adzuna or MyCareersFuture."""
    title:          str
    company:        str
    location:       str
    description:    str
    salary_min:     float | None    # in local currency, annual
    salary_max:     float | None    # in local currency, annual
    currency:       str             # ISO code — GBP, AUD, SGD
    date_posted:    str             # ISO date string YYYY-MM-DD or as returned
    skills:         list[str]       # extracted from description or tags
    source_url:     str             # direct link to the posting
    source:         str             # "adzuna" or "mycareersfuture"


@dataclass
class JobPostingsResponse:
    """The full response from a job posting tool call."""
    query:          str
    country:        str             # matches deps.context.country
    total_found:    int             # total matching postings in the API, not just returned
    postings:       list[JobPosting] = field(default_factory=list)
    error:          str | None = None