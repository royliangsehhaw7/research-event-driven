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
    await fetch_client.startup()
    try:
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
    finally:
        await fetch_client.shutdown()



if __name__ == "__main__":
    asyncio.run(run(
        university_name="University of Manchester",
        intended_course="Computer Science",
        country="UK",
    ))