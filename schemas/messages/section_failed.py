from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class SectionFailedMessage(BaseMessage):
    """Fired by any of the 7 section agents on failure.

    ScoringAgent handles this identically to SectionCompletedMessage
    for quorum counting — it increments received_count regardless.
    The difference: ScoringAgent calls setattr(board, section_name, None)
    to ensure the field is None before scoring.

    section_name must match blackboard field name exactly.
    reason is a human-readable string for logging and report notes.
    """
    section_name: str
    reason:       str