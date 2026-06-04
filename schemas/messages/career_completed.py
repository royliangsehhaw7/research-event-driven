from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class CareerResearchCompletedMessage(BaseMessage):
    """Fired by CareerAgent when board.career is populated.

    Carries no payload — all 7 section agents read board.career directly.
    This message is the signal that Phase 2 can begin.
    """
    pass