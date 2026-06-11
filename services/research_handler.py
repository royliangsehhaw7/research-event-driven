# services/research_handler.py — Stage 1c (CareerAgent only)
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from core.blackboard import Blackboard
from core.deps import Deps, ResearchContext
from core.message_hub import MessageHub
from core.skill_loader import scan_skills_dir, SkillMeta
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
            tool_budget=career_skill.tool_budget if career_skill else 6,
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