from dataclasses import dataclass
from typing import Literal

ScoreScale = Literal["0-1", "0-5", "0-10", "percentage"]

# Map each score scale to its description (used as semantic guardrail in the grading prompt template)
SCORE_SCALE_DESCRIPTIONS: dict[ScoreScale, str] = {
    "0-1": "use an integer score of 0 or 1",
    "0-5": "use an integer score from 0 to 5",
    "0-10": "use an integer score from 0 to 10",
    "percentage": "use an integer score from 0 to 100",
}


@dataclass
class Criterion:
    id: str
    name: str
    description: str
    weight: float
    scale: ScoreScale


@dataclass
class Rubric:
    task_id: str
    title: str
    description: str
    overall_max_score: float
    min_passing_score: float
    criteria: list[Criterion]

    def __post_init__(self):
        if not self.criteria:
            raise ValueError("criteria must be non-empty")

        if self.min_passing_score <= 0:
            raise ValueError("min_passing_score must be positive")

        if self.min_passing_score > self.overall_max_score:
            raise ValueError(
                "min_passing_score must be less than or equal to overall_max_score"
            )
