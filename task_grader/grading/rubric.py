import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Mapping, get_args

ScoreScale = Literal["0-1", "0-5", "0-10", "percentage"]

# Numeric ranges for each score scale.
# Used only for validation + computing an overall numeric score.
SCORE_SCALE_NUMERIC_RANGES: dict[ScoreScale, tuple[int, int]] = {
    "0-1": (0, 1),
    "0-5": (0, 5),
    "0-10": (0, 10),
    "percentage": (0, 100),
}


def _build_score_scale_descriptions(
    ranges: Mapping[ScoreScale, tuple[int, int]],
) -> dict[ScoreScale, str]:
    """
    Generate human-readable descriptions for each score scale from its numeric range.
    """
    descriptions: dict[ScoreScale, str] = {}

    for scale, (lo, hi) in ranges.items():
        # Optional: special-case 0–1 to keep the slightly nicer "0 or 1" phrasing
        if lo == 0 and hi == 1:
            desc = "use an integer score of 0 or 1"
        else:
            desc = f"use an integer score from {lo} to {hi}"
        descriptions[scale] = desc

    return descriptions


# Map each score scale to its description (used as semantic guardrail in the grading prompt template)
SCORE_SCALE_DESCRIPTIONS: dict[ScoreScale, str] = _build_score_scale_descriptions(
    SCORE_SCALE_NUMERIC_RANGES
)


@dataclass
class Criterion:
    id: str
    name: str
    description: str
    weight: float
    scale: ScoreScale
    skill_domain: str = "General"  # e.g., 'Code Quality', 'Logic', 'Security'
    bloom_level: str = "Apply"  # e.g., 'Analyze', 'Evaluate', 'Create'
    performance_levels: dict[int, str] = field(
        default_factory=dict
    )  # e.g., {5: "Exemplary...", 3: "Proficient..."}

    def __post_init__(self):
        if self.scale not in SCORE_SCALE_DESCRIPTIONS:
            raise ValueError(
                f"Invalid scale: {self.scale}. Must be one of {get_args(ScoreScale)}"
            )

        if self.weight <= 0:
            raise ValueError(f"Invalid weight: {self.weight}. Must be positive")

        if self.performance_levels:
            lo, hi = SCORE_SCALE_NUMERIC_RANGES[self.scale]
            scores = sorted(self.performance_levels.keys())

            for score in scores:
                if not (lo <= score <= hi):
                    raise ValueError(
                        f"Score {score} in performance_levels out of range for {self.scale}"
                    )

            if scores[0] != lo or scores[-1] != hi:
                raise ValueError(
                    f"Criterion '{self.name}' must define performance levels for "
                    f"the scale boundaries ({lo} and {hi})."
                )

            # Contiguity Check
            # Ensures no 'unexplained' scores exist between defined levels in small scales
            if self.scale in ["0-1", "0-5"] and len(scores) != (hi - lo + 1):
                raise ValueError(
                    f"Criterion '{self.name}' has missing levels for scale {self.scale}."
                )

    def save_to_json(
        self, dest_dir: str | Path, filename: str, indent: int = 4
    ) -> None:
        """Save a Criterion object to a JSON file"""
        if not isinstance(dest_dir, Path):
            dest_dir = Path(dest_dir)

        # Create the destination directory if it doesn't already exist
        dest_dir.mkdir(parents=True, exist_ok=True)

        filepath: Path = dest_dir / f"{filename}.json"

        with open(filepath, "w") as f:
            json.dump(asdict(self), f, indent=indent)

    @classmethod
    def load_from_json(cls, source_dir: str | Path, filename: str) -> "Criterion":
        """Load a Criterion object from a JSON file"""
        if not isinstance(source_dir, Path):
            source_dir = Path(source_dir)

        filepath: Path = source_dir / f"{filename}.json"

        with open(filepath, "r") as f:
            criterion_data = json.load(f)

        if criterion_data.get("performance_levels") is not None:
            criterion_data["performance_levels"] = {
                int(key): val
                for key, val in criterion_data["performance_levels"].items()
            }

        return cls(**criterion_data)


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
            raise ValueError(
                f"Invalid min_passing_score: {self.min_passing_score}. Must be positive"
            )

        if self.min_passing_score > self.overall_max_score:
            raise ValueError(
                f"Invalid min_passing_score: {self.min_passing_score}. Cannot exceed overall_max_score"
            )

    def save_to_json(
        self, dest_dir: str | Path, filename: str, indent: int = 4
    ) -> None:
        """Save a Rubric object to a JSON file"""
        if not isinstance(dest_dir, Path):
            dest_dir = Path(dest_dir)

        # Create the destination directory if it doesn't already exist
        dest_dir.mkdir(parents=True, exist_ok=True)

        filepath: Path = dest_dir / f"{filename}.json"

        with open(filepath, "w") as f:
            json.dump(asdict(self), f, indent=indent)

    @classmethod
    def load_from_json(cls, source_dir: str | Path, filename: str) -> "Rubric":
        """Load a Rubric object from a JSON file"""
        if not isinstance(source_dir, Path):
            source_dir = Path(source_dir)

        filepath: Path = source_dir / f"{filename}.json"

        with open(filepath, "r") as f:
            rubric_data = json.load(f)

        for criterion in rubric_data["criteria"]:
            perf_levels = criterion.get("performance_levels")
            if perf_levels is not None:
                criterion["performance_levels"] = {
                    int(key): val
                    for key, val in criterion["performance_levels"].items()
                }

        rubric_data["criteria"] = [
            Criterion(**criterion) for criterion in rubric_data["criteria"]
        ]

        return cls(**rubric_data)
