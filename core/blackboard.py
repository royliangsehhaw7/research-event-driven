from __future__ import annotations

from dataclasses import dataclass

from schemas.outputs.career_output import CareerOutput
from schemas.outputs.background_output import BackgroundOutput
from schemas.outputs.rankings_output import RankingsOutput
from schemas.outputs.program_output import ProgramOutput
from schemas.outputs.employability_output import EmployabilityOutput
from schemas.outputs.accomodation_output import AccommodationOutput
from schemas.outputs.news_output import NewsOutput
from schemas.outputs.forum_output import ForumOutput
from schemas.outputs.scoring_output import ScoringOutput
from schemas.outputs.alternatives_output import AlternativesOutput


@dataclass
class Blackboard:
    """Per-request result accumulator. One fresh instance per research run.

    Fields are None until the corresponding agent completes.
    None means either: agent hasn't run yet, or agent failed.
    ScoringAgent treats both cases identically — redistribute weight.

    Never share a Blackboard instance across requests.
    """

    career:        CareerOutput        | None = None
    background:    BackgroundOutput    | None = None
    rankings:      RankingsOutput      | None = None
    program:       ProgramOutput       | None = None
    employability: EmployabilityOutput | None = None
    accommodation: AccommodationOutput | None = None
    news:          NewsOutput          | None = None
    forum:         ForumOutput         | None = None
    score:         ScoringOutput       | None = None
    alternatives:  AlternativesOutput  | None = None

    def is_complete(self) -> bool:
        """True when all 8 research sections are populated.

        score and alternatives may still be None — they run after sections.
        Used by tests to verify a full research run completed.
        """
        return all([
            self.career       is not None,
            self.background   is not None,
            self.rankings     is not None,
            self.program      is not None,
            self.employability is not None,
            self.accommodation is not None,
            self.news         is not None,
            self.forum        is not None,
        ])

    def section_count(self) -> int:
        """Count of non-None research sections (excludes score and alternatives).
        Used by ScoringAgent to understand what it has to work with."""
        fields = [
            self.career, self.background, self.rankings, self.program,
            self.employability, self.accommodation, self.news, self.forum,
        ]
        return sum(1 for f in fields if f is not None)
    