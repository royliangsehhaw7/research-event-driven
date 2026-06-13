# main.py — Stage 1c
from __future__ import annotations

import asyncio
from dotenv import load_dotenv
from core.logger import logger

from mcps.fetch_client import fetch_client
from services.research_handler import ResearchHandler


load_dotenv()  # must happen before any tool module is imported


async def run(university_name: str, intended_course: str, country: str) -> None:
    try:
        await fetch_client.startup()
    
        handler = ResearchHandler()
        board = await handler.handle_request(
            university_name=university_name,
            intended_course=intended_course,
            country=country,
        )
        logger.info('Main | research started')

        if board.career is None:
            print(f"main | board.career is None — CareerAgent failed or did not run")
        else:
            print("\n── board.career ───────────────────────────────────────────────")
            print(board.career.model_dump_json(indent=2))
            print("─────────────────────────────────────────────────────────────────\n")
    finally:
        await fetch_client.shutdown()



if __name__ == "__main__":
    asyncio.run(run(
        university_name="Imperial College of London",
        intended_course="Computer Science",
        country="UK",
    ))