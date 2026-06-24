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