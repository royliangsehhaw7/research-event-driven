# core/deps.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.message_hub import MessageHub
from core.blackboard import Blackboard


@dataclass
class ResearchContext:
    """Immutable context for a single research request.

    Set once by ResearchHandler. Never mutated by agents.

    Attributes:
        university_name: Exact name as supplied by the user.
                         e.g. "University of Manchester"
        intended_course: Exact course name as supplied by the user.
                         e.g. "Computer Science"
        country:         Derived by ResearchHandler from university_name.
                         Never None — derivation happens before pipeline starts.
                         e.g. "UK", "Australia", "USA"
        study_level:     Hardcoded to "undergraduate". Never changes.
    """
    university_name: str
    intended_course: str
    country:         str
    study_level:     str = "undergraduate"


@dataclass
class Deps:
    """Per-request dependency bundle. One fresh instance per research run.

    Passed to every agent handler via closure (see ResearchHandler).
    Agents read context, write to board, publish via hub.
    Never share a Deps instance across requests.

    Tool clients (tavily, fetch, reddit, ddg) are created once at
    ResearchHandler startup and reused across requests — they carry no
    per-request state. hub and board are fresh each request.

    tool_budget and calls_made are NOT on Deps — they live on each agent
    instance so concurrent agents manage their own counters independently.
    """
    hub:     MessageHub
    board:   Blackboard
    context: ResearchContext
    tavily:  Any              # TavilyClient — used by all research agents
    fetch:   Any              # MCPServerStdio from mcp/fetch_client.py — all research agents
    reddit:  Any | None       # praw.Reddit — ForumAgent only, None if not configured
    ddg:     Any              # DDGS — NewsAgent only
    