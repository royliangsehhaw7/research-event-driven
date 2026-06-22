from __future__ import annotations

from core.logger import logger
from abc import ABC, abstractmethod

from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelResponse, TextPart

from core.message_hub import MessageHub
from core.deps import Deps



class BaseAgent(ABC):
    """Base class for all research pipeline agents.

    Each subclass:
    - constructs its own pydantic-ai Agent with exactly the tools it needs
    - implements subscribe() to register its handler(s) on the hub via closure
    - implements get_instruction() to return its system prompt (base + SKILL.md body)

    instructions: the full markdown body from the agent's SKILL.md file.
    Injected by ResearchHandler at construction time. Empty string if SKILL.md
    is missing — agent is degraded but functional.
    """

    def __init__(self, instructions: str = "") -> None:
        self.instructions = instructions
        self._agent: Agent | None = None   # constructed by subclass __init__

        # Isolated request session metrics per-agent instance
        self._current_cot_buffer: list[str] = []

    def reset(self) -> None:
        """Called before each request's subscribe loop. No-op by default.
        Subclasses that carry per-request state (e.g. a _fired flag) override this."""
        ...

    def _setup_telemetry_hooks(self) -> Hooks:
        """Helper factory method called by subclasses during Agent construction.
        
        Injects uniform logging behavior across all subclass agents.
        """
        hooks = Hooks()

        @hooks.on.after_model_request
        async def capture_turn_metrics(ctx, response: ModelResponse, **kwargs) -> ModelResponse:
            # 1. Uniform fleet-wide token tracking (CORRECTED ATTRIBUTES)
            if response.usage:
                logger.warning(
                    "[TOKENS] Input=%d | Output=%d | Total=%d",
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.usage.total_tokens,
                )
            
            # 2. Uniform fleet-wide COT harvesting
            for part in response.parts:
                if isinstance(part, TextPart) and part.content:
                    self._current_cot_buffer.append(part.content)
                elif type(part).__name__ == 'ThinkingPart' and hasattr(part, 'content'):
                    thinking_content = getattr(part, 'content', '')
                    self._current_cot_buffer.append(thinking_content)
                    
                    # -> ADD THIS LINE: Log the thinking block immediately for this turn
                    if thinking_content:
                        logger.info("\n[THINKING BLOCK]\n%s\n", thinking_content)
                    
            return response

        return hooks

    def flush_cot_log(self) -> str:
        """Consolidates and returns the full COT buffer compiled across all LLM turns."""
        return "\n".join(self._current_cot_buffer).strip()


    
    @abstractmethod
    def subscribe(self, hub: MessageHub, deps: Deps) -> None:
        """Register this agent's handler(s) on the hub via closure.

        deps is captured at subscription time. The hub never receives deps.

        Example:
            def subscribe(self, hub, deps):
                async def handler(message):
                    await self.handle(message, deps)
                hub.subscribe(SomeMessage, handler)
        """
        ...

    @abstractmethod
    def get_instruction(self) -> str:
        """Return the full system prompt for this agent.

        Combine a short structural preamble (what blackboard field the agent
        writes, what message it fires, what output schema it returns) with
        self.instructions (the SKILL.md body — search strategy, query
        construction, quality filters, edge cases).

        Example:
            def get_instruction(self) -> str:
                base = \"\"\"
                    You are the CareerAgent in a university research pipeline.
                    Write your findings to deps.board.career as a CareerOutput.
                    Fire CareerResearchCompletedMessage when done.
                \"\"\"
                return base + "\\n\\n" + self.instructions if self.instructions else base
        """
        ...
