# core/message_hub.py
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


@dataclass
class AgentParam:
    """Single parameter received by every agent handler.

    message: the event that triggered this handler — typed to the subscribed message type.
    deps:    the per-request bundle (hub, board, context) — same instance across all handlers.
    """
    message: BaseModel
    deps: Any


class MessageHub:
    """Pure fan-out message dispatcher.

    One instance per research request — created fresh in
    ResearchHandler.handle_request(). Never reused across requests.
    Reusing accumulates handlers from prior requests.

    Usage:
        hub = MessageHub()
        hub.subscribe(SomeMessage, agent.handle)
        await hub.publish(SomeMessage(triggered_by="x", timestamp="..."), deps)
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, message_type: type, handler: Callable) -> None:
        """Register an async handler for a message type.

        Multiple handlers per type are allowed — all fire concurrently
        on publish. Same handler registered twice will fire twice.
        """
        self._subscribers[message_type].append(handler)

    async def publish(self, message: BaseModel, deps: Any) -> None:
        """Package message + deps into AgentParam, dispatch to all handlers concurrently.

        Uses asyncio.gather() — all handlers start simultaneously.
        If no handlers are registered for the message type, does nothing.
        Handler exceptions are not caught here — they propagate to the caller.
        """
        handlers = self._subscribers.get(type(message), [])
        if not handlers:
            return
        param = AgentParam(message=message, deps=deps)
        await asyncio.gather(*[h(param) for h in handlers])

    def subscriber_count(self, message_type: type) -> int:
        """Return number of registered handlers for a message type.
        Used in tests to verify subscription state."""
        return len(self._subscribers.get(message_type, []))