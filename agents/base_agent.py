from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from pydantic_ai import Agent

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
        self._logger = logging.getLogger(self.__class__.__name__)

    def reset(self) -> None:
        """Called before each request's subscribe loop. No-op by default.
        Subclasses that carry per-request state (e.g. a _fired flag) override this."""
        ...


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
