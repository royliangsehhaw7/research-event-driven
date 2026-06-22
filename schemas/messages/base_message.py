from __future__ import annotations
from pydantic import BaseModel
from typing import Optional

class BaseMessage(BaseModel):
    """All messages inherit from this.

    triggered_by: identifier of the component that fired the message.
                  Use class name: "career_agent", "research_handler".
    timestamp:    ISO 8601 string. datetime.now().isoformat() is acceptable.
    """
    triggered_by: Optional[str] = None
    timestamp: Optional[str] = None