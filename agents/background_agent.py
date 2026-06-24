# agents/background_agent.py
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