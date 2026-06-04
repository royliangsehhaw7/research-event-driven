from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class AlternativesCompletedMessage(BaseMessage):
    """Fired by AlternativesAgent when board.alternatives is populated.
    ReportGenerator subscribes to this.
    """
    pass