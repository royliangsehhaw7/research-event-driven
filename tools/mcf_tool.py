# tools/mcf_tool.py
from __future__ import annotations

import httpx
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger
from schemas.job_posting import JobPosting, JobPostingsResponse

_BASE = "https://api.mycareersfuture.gov.sg/v2"


def _extract_skills(posting: dict) -> list[str]:
    """Extract skill names from the MCF skills array in the API response.

    MCF returns a structured skills array — extract names from it directly.
    No description scanning.
    """
    return [
        s.get("skill", "")
        for s in posting.get("skills", [])
        if s.get("skill")
    ]


def _parse_salary(posting: dict) -> tuple[float | None, float | None]:
    """Extract min/max salary from MCF salary object."""
    salary = posting.get("salary", {})
    minimum = salary.get("minimum")
    maximum = salary.get("maximum")
    return (
        float(minimum) if minimum else None,
        float(maximum) if maximum else None,
    )


async def mcf_jobs(
    ctx: RunContext[Deps],
    query: str,
    max_results: int = 15,
) -> JobPostingsResponse:
    """Search live job postings via MyCareersFuture API. Singapore only.

    Call this tool when deps.context.country is "Singapore".
    Do not call this tool for UK or Australia — use adzuna_jobs instead.

    No authentication required — this is a public government API.

    Args:
        query:       job search query (e.g. "software engineer computer science")
        max_results: number of postings to return (default 15, max 100)

    Returns:
        JobPostingsResponse with normalised postings. Never raises —
        returns error field on failure so the agent can continue.
    """
    country = ctx.deps.context.country

    if country != "Singapore":
        return JobPostingsResponse(
            query=query,
            country=country,
            total_found=0,
            error=(
                f"mcf_jobs only supports Singapore. "
                f"country={country!r} is not supported. Use adzuna_jobs for UK and Australia."
            ),
        )

    params = {
        "search":  query,
        "limit":   min(max_results, 100),
        "offset":  0,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_BASE}/jobs", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("mcf_tool | request failed: %s", exc)
        return JobPostingsResponse(
            query=query, country=country, total_found=0,
            error=str(exc),
        )

    total = data.get("total", 0)
    postings = []

    for job in data.get("results", []):
        salary_min, salary_max = _parse_salary(job)

        postings.append(JobPosting(
            title=       job.get("title", ""),
            company=     job.get("postedCompany", {}).get("name", ""),
            location=    job.get("location", {}).get("oneLineAddress", "Singapore"),
            description= job.get("description", ""),
            salary_min=  salary_min,
            salary_max=  salary_max,
            currency=    "SGD",
            date_posted= job.get("originalPostingDate", ""),
            skills=      _extract_skills(job),
            source_url=  f"https://www.mycareersfuture.gov.sg/job/{job.get('uuid', '')}",
            source=      "mycareersfuture",
        ))

    logger.info(
        "mcf_tool | query=%r total=%d returned=%d",
        query, total, len(postings),
    )

    return JobPostingsResponse(
        query=query,
        country=country,
        total_found=total,
        postings=postings,
    )