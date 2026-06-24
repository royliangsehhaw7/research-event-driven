# agents/career_agent.py
from __future__ import annotations

import traceback
from datetime import datetime
from pydantic import ValidationError
from pydantic_ai import Agent

from agents.base_agent import BaseAgent
from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.career_output import CareerOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search
from tools.adzuna_tool import adzuna_jobs
from tools.mcf_tool import mcf_jobs


class CareerAgent(BaseAgent):
    """Phase 1 agent. Runs first, in isolation.

    Subscribes to: ResearchRequestedMessage
    Writes to:     board.career (CareerOutput)
    Fires:         CareerResearchCompletedMessage (unconditionally — even on failure)

    Tools: tavily_search (budget-capped), fetch_page (uncapped),
           adzuna_jobs (UK/AU), mcf_jobs (Singapore)

    Note: site: queries must not be passed to tavily_search — Tavily does not
    honour time_range filtering on site: prefixed queries. Use tavily_search to
    find URLs, then fetch_page to retrieve content from those URLs.
    """

    def __init__(self, instructions: str = "", tool_budget: int = 8) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=CareerOutput,
            system_prompt=self.get_instruction(),
            capabilities=[self._setup_telemetry_hooks()],
            tools=[
                tavily_search,
                fetch_page,
                adzuna_jobs,
                mcf_jobs,
            ],
        )

        logger.info("CareerAgent | initialized")


    # ── BaseAgent interface ───────────────────────────────────────────────────

    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.research_requested import ResearchRequestedMessage

        async def handler(message: ResearchRequestedMessage) -> None:
            await self.handle(message, deps)

        hub.subscribe(ResearchRequestedMessage, handler)
        logger.info("CareerAgent | subscribed to MessageHub")

    def get_instruction(self) -> str:
        base = "You are the Career Research Agent in a university research pipeline."
        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def reset(self) -> None:
        """Reset per-request state. Called by ResearchHandler before each request."""
        self._calls_made = 0


    # ── Core handler ──────────────────────────────────────────────────────────

    async def handle(self, message, deps: Deps) -> None:
        """Run career research and fire CareerResearchCompletedMessage.

        CareerResearchCompletedMessage is fired unconditionally in the finally
        block — even if the LLM call fails. If it is not fired, the entire
        downstream pipeline stalls because no section agent will receive its
        trigger message.
        """
        self._calls_made = 0

        logger.info(
            "CareerAgent | starting — university=%r course=%r country=%r",
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
            f"Study level: {deps.context.study_level}"
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.career = result.output

            logger.info(
                "CareerAgent | completed — paths=%d confidence=%s",
                len(result.output.career_paths),
                result.output.confidence,
            )

            await deps.hub.publish(ProgressUpdateMessage(
                status="completed",
                message="Career landscape research complete.",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except ValidationError as exc:
            # LLM returned output that failed schema validation.
            # Log each field violation so the failing field is identifiable
            # without inspecting the raw LLM response.
            logger.error("CareerAgent | schema validation failed:")
            for err in exc.errors():
                logger.error(
                    "  field=%s  error=%s  input=%s",
                    err["loc"], err["msg"], err.get("input"),
                )

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career research produced invalid output: {exc.error_count()} field errors",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))

        except Exception as exc:
            # Catches: FallbackModel exhaustion, ModelHTTPError (429/404),
            # UnexpectedModelBehavior (thinking-model output retries exceeded),
            # tool errors, and any other unexpected failures.
            logger.error("CareerAgent | failed: %s", exc)
            traceback.print_exc()

            # FallbackModel wraps both sub-exceptions — unpack for visibility
            if hasattr(exc, "exceptions"):
                for i, sub in enumerate(exc.exceptions):
                    logger.error("Sub-exception %d: %s: %s", i, type(sub).__name__, sub)
                    traceback.print_exception(type(sub), sub, sub.__traceback__)

            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career research failed: {exc}",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))

        finally:
            # Fire unconditionally. board.career will be None if an exception
            # was raised above. Section agents handle None career gracefully.
            await deps.hub.publish(CareerResearchCompletedMessage(
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))