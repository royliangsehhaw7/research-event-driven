from __future__ import annotations
from schemas.messages.base_message import BaseMessage


class ReportReadyMessage(BaseMessage):
    """Fired by ReportGenerator when both output files are written.

    file_paths contains paths to the 2 output files:
      [0] report.md  — full report with executive summary
      [1] score.json — machine-readable score breakdown
    Chainlit UI subscribes to this to trigger download links.
    """
    file_paths: list[str]