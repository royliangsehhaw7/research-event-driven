# agents/career_agent.py
from __future__ import annotations

import logging
from datetime import datetime

from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.deps import Deps
from core.llm_factory import get_model
from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.career_output import CareerOutput
from tools.fetch_tool import fetch_page
from tools.search_tool_factory import make_search_tool

logger = logging.getLogger("career_agent")


class CareerAgent(BaseAgent):
    """Phase 1 agent. Runs first, in isolation.

    Subscribes to: ResearchRequestedMessage
    Writes to:     board.career (CareerOutput)
    Fires:         CareerResearchCompletedMessage

    Tools: tavily_search (budget-capped via make_search_tool), fetch_page (uncapped)
    """

    def __init__(self, instructions: str = "", tool_budget: int = 6) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget  = tool_budget
        self._calls_made   = [0]   # mutable ref passed to closure

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=CareerOutput,
            system_prompt=self.get_instruction(),
            tools=[
                make_search_tool("career_agent", self._calls_made, self._tool_budget),
                fetch_page,
            ],
        )

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.research_requested import ResearchRequestedMessage

        async def handler(message: ResearchRequestedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(ResearchRequestedMessage, handler)

    def get_instruction(self) -> str:
        base = """
            You are the Career Research Agent in a university research pipeline.

            Your job: research graduate career paths, salary ranges, and live job market
            demand for the course at the university named in your context.

            Pipeline role:
            - You run first, before any other section agent.
            - You write your findings to deps.board.career as a CareerOutput.
            - You fire CareerResearchCompletedMessage when done. This triggers all
            seven section agents to run concurrently.
            - If you fail to fire CareerResearchCompletedMessage, the entire pipeline
            stalls. Always fire it — even if your output is low confidence.

            Context you receive (from deps.context):
            - university_name: the university being researched
            - intended_course: the undergraduate course
            - country: the university's country — scope ALL salary and employer data to this
            - study_level: always "undergraduate"

            You must not research careers for a different country than deps.context.country.
        """.strip()

        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def reset(self) -> None:
        """Reset per-request state. Called by ResearchHandler before each request."""
        self._calls_made[0] = 0

    # ── Core handler ─────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        """Run career research and fire CareerResearchCompletedMessage."""
        self._calls_made[0] = 0   # reset counter on each run

        logger.info(
            "career_agent | starting — university=%r course=%r country=%r",
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
            f"Study level: {deps.context.study_level}\n\n"
            "Research graduate career paths, salary ranges in local currency, "
            "and live job market demand. Scope all findings to the country above."
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.career = result.output
            logger.info(
                "career_agent | completed — paths=%d confidence=%s",
                len(result.output.career_paths),
                result.output.confidence,
            )
            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="Career landscape research complete.",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))
        except Exception as exc:
            logger.error("career_agent | failed: %s", exc)
            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career research failed: {exc}",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))
            # Still fire the completed message so the pipeline does not stall.
            # board.career remains None — downstream agents handle this.

        await deps.hub.publish(CareerResearchCompletedMessage(
            triggered_by="career_agent",
            timestamp=datetime.now().isoformat(),
        ))