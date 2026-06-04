from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class SectionCompletedMessage(BaseMessage):
    """Fired by any of the 7 section agents on successful completion.

    section_name must match the blackboard field name exactly.
    ScoringAgent uses this name with setattr() to check board state.

    Valid values: "background", "rankings", "program", "employability",
                  "accommodation", "news", "forum"
    """
    section_name: str