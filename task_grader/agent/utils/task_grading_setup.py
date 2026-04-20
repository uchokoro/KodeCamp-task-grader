from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin

from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ...grading import Criterion, Rubric, ScoreScale


SchemaValue = str | dict[str, Any]
Schema = dict[str, SchemaValue]


def extract_dataclass_schema(obj) -> SchemaValue:
    """
    Recursively extracts the schema of a dataclass.
    Works with both dataclass classes and instances.
    """
    # If `obj` is an instance, get its class
    cls = obj if isinstance(obj, type) else type(obj)

    if not is_dataclass(cls):
        return getattr(cls, "__name__", str(cls))

    schema: dict[str, SchemaValue] = {}

    for field in fields(cls):  # noqa
        field_name = field.name
        field_type = field.type
        origin = get_origin(field_type)
        args = get_args(field_type)

        if origin in (list, tuple, set):  # Covers standard and typing collections
            inner_type = args[0] if args else Any
            schema[field_name] = {
                "type": getattr(origin, "__name__", str(origin)),
                "items": extract_dataclass_schema(inner_type),  # Returns SchemaValue
            }
        elif origin is dict:
            key_type = args[0] if args else Any
            value_type = args[1] if len(args) > 1 else Any
            schema[field_name] = {
                "type": "dict",
                "keys": str(key_type),
                "values": extract_dataclass_schema(value_type),  # Returns SchemaValue
            }
        elif is_dataclass(field_type):
            schema[field_name] = extract_dataclass_schema(field_type)
        else:
            # Fallback for primitive types (int, str, etc.)
            schema[field_name] = getattr(field_type, "__name__", str(field_type))

    return schema


def extract_txt_file_contents(txt_filepath: str | Path) -> str:
    """Extracts the contents of a TXT file."""
    if not isinstance(txt_filepath, Path):
        txt_filepath = Path(txt_filepath)

    if not txt_filepath.is_file():
        raise FileNotFoundError(f"Description file not found: {txt_filepath}")

    with open(txt_filepath, "r", encoding="utf-8") as txt_file:
        contents = txt_file.read()

    return contents


def generate_score_scale_values(score_scale_literal) -> str:
    literal_values = get_args(score_scale_literal)
    # Extract the literal values into a string like '"0-1", "0-5", "0-10", "percentage"'
    values_str = ", ".join(f'"{v}"' for v in literal_values)

    return values_str


def build_rubric(
    assignment: str,
    template: str,
    model: BaseChatModel,
    additional_requirements: str = "",
    max_score: int = 100,
    passing_threshold: int = 75,
) -> Rubric:
    prompt_template = ChatPromptTemplate.from_template(template)
    output_parser = JsonOutputParser()
    rubric_chain = prompt_template | model | output_parser
    rubric_chain_input = {
        "overall_max_score": max_score,
        "min_passing_score": passing_threshold,
        "score_scale_values": generate_score_scale_values(ScoreScale),
        "task_description": assignment,
        "output_schema": extract_dataclass_schema(Rubric),
        "additional_requirements": additional_requirements,
    }
    rubric_data = rubric_chain.invoke(rubric_chain_input)
    criteria = []

    for criterion in rubric_data["criteria"]:
        if not isinstance(criterion["id"], str):
            criterion["id"] = str(criterion["id"])
        criteria.append(Criterion(**criterion))

    rubric = Rubric(
        task_id=rubric_data["task_id"],
        title=rubric_data["title"],
        description=rubric_data["description"],
        overall_max_score=rubric_data["overall_max_score"],
        min_passing_score=rubric_data["min_passing_score"],
        criteria=criteria,
    )

    return rubric
