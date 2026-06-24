# agents/program_agent.py
from __future__ import annotations

from datetime import datetime

import traceback
from pydantic import ValidationError

from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.section_completed import SectionCompletedMessage
from schemas.messages.section_failed import SectionFailedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.program_output import ProgramOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search


class ProgramAgent(BaseAgent):
    """Researches the undergraduate program structure and curriculum-to-career mapping.

    Subscribes to: CareerResearchCompletedMessage
    Writes to:     board.program (ProgramOutput)
    Fires:         SectionCompletedMessage(section_name="program") on success
                   SectionFailedMessage(section_name="program") on error

    Reads board.career.in_demand_skills before running — passes them into the
    task brief so the LLM can map curriculum modules to career skills.
    If board.career is None (CareerAgent failed), the skill_mappings field
    will be empty — that is expected and handled gracefully.
    """

    def __init__(self, instructions: str = "", tool_budget: int = 7) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=ProgramOutput,
            system_prompt=self.get_instruction(),
            capabilities=[self._setup_telemetry_hooks()],
            tools=[tavily_search, fetch_page],
        )

        logger.info("ProgramAgent | initialized")

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.career_completed import CareerResearchCompletedMessage

        async def handler(message: CareerResearchCompletedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(CareerResearchCompletedMessage, handler)
        logger.info("ProgramAgent | subscribed to MessageHub")

    def get_instruction(self) -> str:
        base = "You are the Undergraduate Program Agent in a university research pipeline."
        return base + "\n\n" + self.instructions if self.instructions else base

    def reset(self) -> None:
        self._calls_made = 0

    # ── Core handler ──────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        self._calls_made = 0

        logger.info(
            "ProgramAgent | starting — university=%r course=%r",
            deps.context.university_name,
            deps.context.intended_course,
        )

        await deps.hub.publish(ProgressUpdateMessage(
            status="started",
            message=f"Researching program structure for {deps.context.intended_course}…",
            triggered_by="program_agent",
            timestamp=datetime.now().isoformat(),
        ))

        # Read in_demand_skills from CareerAgent output if available
        in_demand_skills: list[str] = []
        if deps.board.career:
            in_demand_skills = deps.board.career.in_demand_skills

        skills_str = (
            "\n".join(f"  - {s}" for s in in_demand_skills)
            if in_demand_skills
            else "  (not available — CareerAgent did not complete)"
        )

        task_brief = (
            f"University: {deps.context.university_name}\n"
            f"Course: {deps.context.intended_course}\n"
            f"Country: {deps.context.country}\n"
            f"Study level: {deps.context.study_level}\n"
            f"In-demand skills to map (from career research):\n{skills_str}"
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)

            if result.output is None:
                raise ValueError(
                    "Agent returned None output — LLM produced an empty or "
                    "unparseable structured response"
                )

            deps.board.program = result.output

            logger.info(
                "ProgramAgent | completed — programs=%d confidence=%s",
                len(result.output.matching_programs),
                result.output.confidence,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="Program structure research complete.",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionCompletedMessage(
                section_name="program",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except ValidationError as exc:
            logger.error("ProgramAgent | schema validation failed:")
            for err in exc.errors():
                logger.error("  field=%s  error=%s  input=%s", err["loc"], err["msg"], err.get("input"))

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Program research produced invalid output: {exc.error_count()} field errors",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="program",
                reason=f"Schema validation failed: {exc.error_count()} errors — check logs",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            logger.error("ProgramAgent | failed: %s", exc)
            traceback.print_exc()

            if hasattr(exc, 'exceptions'):
                for i, sub in enumerate(exc.exceptions):
                    logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
                    traceback.print_exception(type(sub), sub, sub.__traceback__)

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Program research failed: {exc}",
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))

            await deps.hub.publish(SectionFailedMessage(
                section_name="program",
                reason=str(exc),
                triggered_by="program_agent",
                timestamp=datetime.now().isoformat(),
            ))