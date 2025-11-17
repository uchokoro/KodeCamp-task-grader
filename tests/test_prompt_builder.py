import pytest
from typing import Literal, get_args

from task_grader.grading.prompt_builder import PromptBuilder
from task_grader.grading.rubric import (
    Rubric,
    Criterion,
    ScoreScale,
    SCORE_SCALE_DESCRIPTIONS,
)


BASE_TEMPLATE = """
##Context##
You're an expert in {knowledge_area}.

Rubric:
{rubric}

YAML spec:
  score_scale: "<one of {score_scale_values}>"

Notes:
9. Base the "overall_verdict" on how well the submission satisfies the rubric criteria.
10. {score_scale_ranges}
{other_enumerated_notes}
"""


def make_sample_rubric() -> Rubric:
    return Rubric(
        task_id="task-1",
        title="Sample Rubric",
        description="Evaluate how well the trainee designs a prompt template.",
        overall_max_score=100,
        min_passing_score=60,
        criteria=[
            Criterion(
                id="clarity",
                name="Clarity of intent and scope",
                description="How clearly the evaluation intent and scope are stated.",
                weight=0.3,
                scale="0-10",
            ),
            Criterion(
                id="structure",
                name="Prompt structure",
                description="How well-structured and modular the prompt is.",
                weight=0.4,
                scale="0-10",
            ),
        ],
    )


def test_with_placeholder_replaces_text():
    builder = PromptBuilder("Hello {name}. {placeholder}")
    builder.with_placeholder("{placeholder}", "Extra text.")
    assert (
        builder.template == "Hello {name}. Extra text."
    )  # {name} should still be available for .format later

    final = builder.build(name="Firstname")
    assert final == "Hello Firstname. Extra text."


def test_with_additional_notes_uses_placeholder():
    template = "Line 1\nNotes:\n{other_enumerated_notes}\nEnd."
    builder = PromptBuilder(template)
    builder.with_additional_notes("1. First note\n2. Second note")
    assert "1. First note" in builder.template
    assert "{other_enumerated_notes}" not in builder.template


def test_with_score_scale_metadata_injects_values_and_ranges():
    builder = PromptBuilder(BASE_TEMPLATE)
    builder.with_score_scale_metadata(ScoreScale, SCORE_SCALE_DESCRIPTIONS)

    tmpl = builder.template
    score_scale_literals = get_args(ScoreScale)

    # Check that the literal values string was injected
    for scale in score_scale_literals:
        token = f'"{scale}"'
        assert token in tmpl

        # Confirm that the found literal value is not just from the range description text
        assert tmpl.count(token) >= 2

    # Check that the ranges note mentions each scale and its description
    for scale, desc in SCORE_SCALE_DESCRIPTIONS.items():
        assert f'"{scale}" \u2192 {desc}' in tmpl


def test_with_score_scale_metadata_raises_for_missing_descriptions():
    # Fake descriptions with a missing key
    bad_descriptions = {
        "0-1": "use integer 0 or 1",
        "0-5": "use integer 0–5",
        # "0-10" is missing
        "percentage": "use integer 0–100",
    }

    builder = PromptBuilder(BASE_TEMPLATE)
    with pytest.raises(ValueError) as excinfo:
        builder.with_score_scale_metadata(ScoreScale, bad_descriptions)

    msg = str(excinfo.value)
    assert "Missing descriptions for score scales" in msg
    assert "0-10" in msg


def test_extract_placeholders_and_validate_placeholders():
    template = "Hi {name}, welcome to {track}. Rubric:\n{rubric}"
    builder = PromptBuilder(template)

    # By default, no default_format_kwargs
    missing = builder.validate_placeholders(provided_keys={"name", "track"})
    # rubric is not provided in provided_keys, so should be missing
    assert missing == {"rubric"}

    # If we pre-fill rubric and provide other keys, nothing should be missing
    builder = PromptBuilder(template, default_format_kwargs={"rubric": "Rubric text"})
    missing = builder.validate_placeholders(provided_keys={"name", "track"})
    assert missing == set()


def test_build_merges_default_and_explicit_kwargs():
    template = "Hello {name}, rubric: {rubric}"
    builder = PromptBuilder(
        template, default_format_kwargs={"rubric": "Default rubric"}
    )
    final = builder.build(name="Firstname")
    assert final == "Hello Firstname, rubric: Default rubric"

    # Explicit rubric in build() should override default
    final_override = builder.build(name="Firstname", rubric="Overridden rubric")
    assert final_override == "Hello Firstname, rubric: Overridden rubric"


def test_render_rubric_structure_via_from_rubric():
    rubric = make_sample_rubric()

    builder = PromptBuilder.from_rubric(
        base_template=BASE_TEMPLATE,
        rubric=rubric,
        score_scale_literal=ScoreScale,
        scale_descriptions=SCORE_SCALE_DESCRIPTIONS,
        additional_notes="11. Extra constraint.",
    )

    # Rubric should be pre-filled in default_format_kwargs
    rubric_text = builder._default_format_kwargs["rubric"]
    assert rubric.title in rubric_text
    assert rubric.description in rubric_text
    assert "Overall max score:" in rubric_text
    assert "Criteria:" in rubric_text

    # Check that at least one criterion is rendered with id and name
    first_criterion = rubric.criteria[0]
    assert first_criterion.id in rubric_text
    assert first_criterion.name in rubric_text
    assert str(first_criterion.weight) in rubric_text
    assert f'"{first_criterion.scale}"' in rubric_text

    # Ensure additional_notes were injected into the template
    assert "11. Extra constraint." in builder.template


def test_full_prompt_build_flow_with_from_rubric():
    rubric = make_sample_rubric()

    builder = PromptBuilder.from_rubric(
        base_template=BASE_TEMPLATE,
        rubric=rubric,
        score_scale_literal=ScoreScale,
        scale_descriptions=SCORE_SCALE_DESCRIPTIONS,
        additional_notes="11. Extra constraint.",
    )

    # Validate placeholders before build
    planned_keys = {
        "knowledge_area",
        "assignment",
        "trainee_name",
        "submission",
        "cohort_specifics",
        "track_name",
        "other_enumerated_notes",
    }
    missing = builder.validate_placeholders(planned_keys)
    # We expect no missing keys except ones not used in BASE_TEMPLATE
    # (this test template only uses knowledge_area and rubric, but we keep it simple).
    # For safety, just assert that knowledge_area and rubric are not missing.
    assert "knowledge_area" in builder._extract_placeholders()
    assert "rubric" in builder._extract_placeholders()
    assert "rubric" not in missing

    # Now build a final prompt
    final_prompt = builder.build(
        knowledge_area="prompt engineering",
        cohort_specifics="Agentic AI Track, Nov 2025",
        track_name="Agentic AI",
        assignment="Assignment text here",
        trainee_name="Firstname Lastname",
        submission="Submission text here",
        other_enumerated_notes="",
    )

    # Spot-check the final prompt includes key pieces
    assert "prompt engineering" in final_prompt
    assert "Sample Rubric" in final_prompt
    assert "Criteria:" in final_prompt
    assert '"0-1"' in final_prompt  # from score_scale_values
    assert "11. Extra constraint." in final_prompt


def test_with_score_scale_metadata_supports_different_literal_type():
    """with_score_scale_metadata should work with any Literal, not just ScoreScale."""
    AltScoreScale = Literal["low", "medium", "high"]
    ALT_DESCRIPTIONS = {
        "low": "use an integer score from 0 to 3",
        "medium": "use an integer score from 4 to 7",
        "high": "use an integer score from 8 to 10",
    }

    builder = PromptBuilder(BASE_TEMPLATE)
    builder.with_score_scale_metadata(AltScoreScale, ALT_DESCRIPTIONS)

    tmpl = builder.template
    alt_literals = get_args(AltScoreScale)

    # Check that literal values were injected
    for scale in alt_literals:
        token = f'"{scale}"'
        assert token in tmpl
        assert tmpl.count(token) >= 2

    # Check guardrail text
    for scale, desc in ALT_DESCRIPTIONS.items():
        assert f'"{scale}" \u2192 {desc}' in tmpl


def test_with_score_scale_metadata_uses_custom_descriptions_mapping():
    """Custom descriptions mapping should control guardrail text."""
    CUSTOM_DESCRIPTIONS = {
        "0-1": "binary scoring only",
        "0-5": "0–5 low-resolution scale",
        "0-10": "0–10 high-resolution scale",
        "percentage": "0–100 percentage scale",
    }

    builder = PromptBuilder(BASE_TEMPLATE)
    builder.with_score_scale_metadata(ScoreScale, CUSTOM_DESCRIPTIONS)

    tmpl = builder.template

    # Check all scales appear
    for scale in get_args(ScoreScale):
        assert f'"{scale}"' in tmpl

    # Check custom descriptions appear
    for scale, desc in CUSTOM_DESCRIPTIONS.items():
        assert f'"{scale}" \u2192 {desc}' in tmpl

    # Check that none of the original descriptions are present
    for original_desc in SCORE_SCALE_DESCRIPTIONS.values():
        if original_desc not in CUSTOM_DESCRIPTIONS.values():
            assert original_desc not in tmpl
