# tools/adzuna_tool.py
from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv
from pydantic_ai import RunContext

from core.deps import Deps
from core.logger import logger
from schemas.job_posting import JobPosting, JobPostingsResponse

load_dotenv()

_APP_ID  = os.environ["ADZUNA_APP_ID"]
_APP_KEY = os.environ["ADZUNA_APP_KEY"]
_BASE    = os.environ["ADZUNA_URL"]

# Single source of truth for country routing.
# Key:   the exact string value of deps.context.country for supported countries.
# Value: (adzuna_country_code, iso_currency_code)
# To add a new country: add one entry here. Nothing else changes.
_COUNTRY_MAP: dict[str, tuple[str, str]] = {
    "UK":        ("gb", "GBP"),
    "Australia": ("au", "AUD"),
    "Singapore": ("sg", "SGD")
}


async def adzuna_jobs(
    ctx: RunContext[Deps],
    query: str,
    max_results: int = 15,
) -> JobPostingsResponse:
    """Search live job postings via Adzuna API. UK and Australia only.

    Call this tool when deps.context.country is "UK" or "Australia".
    Do not call this tool for Singapore — use mcf_jobs instead.

    Args:
        query:       job search query (e.g. "software engineer graduate")
        max_results: number of postings to return (default 15, max 50)

    Returns:
        JobPostingsResponse with normalised postings. Never raises —
        returns error field on failure so the agent can continue.
    """
    country = ctx.deps.context.country
    mapping = _COUNTRY_MAP.get(country)

    if not mapping:
        return JobPostingsResponse(
            query=query,
            country=country,
            total_found=0,
            error=(
                f"adzuna_jobs does not support country={country!r}. "
                f"Supported: {list(_COUNTRY_MAP)}. Use mcf_jobs for other countries."
            ),
        )

    adzuna_code, currency = mapping

    params = {
        "app_id":           _APP_ID,
        "app_key":          _APP_KEY,
        "results_per_page": min(max_results, 50),
        "what":             query,
        "content-type":     "application/json",
    }

    url = f"{_BASE}/{adzuna_code}/search/1"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("adzuna_tool | request failed: %s", exc)
        return JobPostingsResponse(
            query=query, country=country, total_found=0,
            error=str(exc),
        )

    total = data.get("count", 0)
    postings = []

    for job in data.get("results", []):
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")

        postings.append(JobPosting(
            title=       job.get("title", ""),
            company=     job.get("company", {}).get("display_name", ""),
            location=    job.get("location", {}).get("display_name", ""),
            description= job.get("description", ""),
            salary_min=  float(salary_min) if salary_min else None,
            salary_max=  float(salary_max) if salary_max else None,
            currency=    currency,
            date_posted= job.get("created", ""),
            skills=      [],   # Adzuna returns no structured skill tags; LLM reads description
            source_url=  job.get("redirect_url", ""),
            source=      "adzuna",
        ))

    logger.info(
        "adzuna_tool | country=%r query=%r total=%d returned=%d",
        country, query, total, len(postings),
    )

    return JobPostingsResponse(
        query=query,
        country=country,
        total_found=total,
        postings=postings,
    )