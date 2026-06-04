from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ProgressUpdateMessage(BaseMessage):
    """Fired by any agent to report live status to the Chainlit UI.

    status values:
      "started"   — agent has begun working
      "completed" — agent finished successfully
      "failed"    — agent encountered an unrecoverable error

    message is a human-readable string shown in the Chainlit step display.
    Example: "Forum Agent: found 12 relevant threads across 3 platforms"
    """
    status:  str   # "started" | "completed" | "failed"
    message: str