from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ResearchRequestedMessage(BaseMessage):
    """Fired by ResearchHandler to start the pipeline.

    Carries the three inputs that define a research run.
    CareerAgent subscribes to this — it is the pipeline trigger.
    """
    university_name: str
    intended_course: str
    country:         str   # already derived by ResearchHandler