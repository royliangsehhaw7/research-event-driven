# agents/career_agent.py
from __future__ import annotations




from datetime import datetime
from pydantic_ai import (
    Agent,
    AgentStreamEvent,
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallPartDelta,
)   

from agents.base_agent import BaseAgent

from core.logger import logger
from core.deps import Deps
from core.llm_factory import get_model

from schemas.messages.career_completed import CareerResearchCompletedMessage
from schemas.messages.progress_update import ProgressUpdateMessage
from schemas.outputs.career_output import CareerOutput

from tools.fetch_tool import fetch_page
from tools.search_tool import tavily_search


class CareerAgent(BaseAgent):
    """Phase 1 agent. Runs first, in isolation.

    Subscribes to: ResearchRequestedMessage
    Writes to:     board.career (CareerOutput)
    Fires:         CareerResearchCompletedMessage

    Tools: tavily_search (budget-capped via _make_search_tool), fetch_page (uncapped)

    Note: site: queries must not be passed to tavily_search — Tavily does not
    honour time_range filtering on site: prefixed queries. Use tavily_search to
    find URLs, then fetch_page to retrieve content from those URLs.
    """

    def __init__(self, instructions: str = "", tool_budget: int = 6) -> None:
        super().__init__(instructions=instructions)
        self._tool_budget = tool_budget
        self._calls_made  = 0

        self._agent = Agent(
            model=get_model("RESEARCH_MODEL"),
            deps_type=Deps,
            output_type=CareerOutput,
            system_prompt=self.get_instruction(),
            tools=[
                tavily_search,
                fetch_page,
            ],
        )

        logger.info('CareerAgent | initialized')



    # ── BaseAgent interface ────────────────────────────────────────────────────────────────────────────
    def subscribe(self, hub, deps: Deps) -> None:
        from schemas.messages.research_requested import ResearchRequestedMessage

        async def handler(message: ResearchRequestedMessage) -> None:
            await self.handle_async(message, deps)

        hub.subscribe(ResearchRequestedMessage, handler)
        logger.info('CareerAgent | Subscribed to MessageHub')

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

            Tool usage rules:
            - Use tavily_search for general queries only. Never pass site: prefixed queries
              to tavily_search — time filtering is not honoured for site: searches and results
              will be stale.
            - To retrieve content from a specific URL (e.g. a job board page or salary survey),
              call fetch_page with that URL directly.

            You must not research careers for a different country than deps.context.country.
        """.strip()

        if self.instructions:
            return base + "\n\n" + self.instructions
        return base

    def reset(self) -> None:
        """Reset per-request state. Called by ResearchHandler before each request."""
        self._calls_made = 0


    # ── Core handler ──────────────────────────────────────────────────────────────────────────────────
    async def handle(self, message, deps: Deps) -> None:
        """Run career research and fire CareerResearchCompletedMessage."""
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

        task_brief = (f"""
            University: {deps.context.university_name}
            Course: {deps.context.intended_course}
            Country: {deps.context.country}
            Study level: {deps.context.study_level}
            """
        )

        try:
            result = await self._agent.run(task_brief, deps=deps)
            deps.board.career = result.output
            logger.warning(
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
        except Exception as exc:
            logger.error("career_agent | failed: %s", exc)
            await deps.hub.publish(ProgressUpdateMessage(
                status="failed",
                message=f"Career research failed: {exc}",
                triggered_by="career_agent",
                timestamp=datetime.now().isoformat(),
            ))

        await deps.hub.publish(CareerResearchCompletedMessage(
            triggered_by="career_agent",
            timestamp=datetime.now().isoformat(),
        ))


    # ── Core handler (async) ───────────────────────────────────────────────────────────────────────────
 
        
    async def handle_async(self, message, deps: Deps) -> None:
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

        task_brief = f"""
            University: {deps.context.university_name}
            Course: {deps.context.intended_course}
            Country: {deps.context.country}
            Study level: {deps.context.study_level}
        """

        try:
            async with self._agent.run_stream_events(task_brief, deps=deps) as stream:
                async for event in stream:
                    if isinstance(event, FinalResultEvent):
                        deps.board.career = event.result.output
                    else:
                        self._log_live_event(event)

            logger.warning(
                "CareerAgent | completed — paths=%d confidence=%s",
                len(deps.board.career.career_paths),
                deps.board.career.confidence,
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

        await deps.hub.publish(CareerResearchCompletedMessage(
            triggered_by="career_agent",
            timestamp=datetime.now().isoformat(),
        ))


    def _log_live_event(self, event) -> None:
        if isinstance(event, FunctionToolCallEvent):
            logger.info(
                "CareerAgent | [TOOL CALL] tool=%r args=%s",
                event.part.tool_name,
                event.part.args,
            )

        elif isinstance(event, FunctionToolResultEvent):
            preview = str(event.part.content)[:300]
            logger.info(
                "CareerAgent | [TOOL RESULT] tool=%r → %r…",
                event.part.tool_name,
                preview,
            )

        elif isinstance(event, PartStartEvent):
            part_type = type(event.part).__name__
            if part_type == 'TextPart':
                logger.info("CareerAgent | [COT] reasoning started")

        elif isinstance(event, PartDeltaEvent):
            if isinstance(event.delta, TextPartDelta):
                logger.debug("CareerAgent | [COT CHUNK] %r", event.delta.content_delta)
            # ThinkingPartDelta skipped — too noisy