from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ScoringCompletedMessage(BaseMessage):
    """Fired by ScoringAgent when board.score is populated.
    AlternativesAgent subscribes to this.
    """
    pass