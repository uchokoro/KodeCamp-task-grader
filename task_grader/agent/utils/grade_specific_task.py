import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any
from dotenv import find_dotenv, load_dotenv
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq

from .convert_colab_to_txt import extract_ipynb_to_txt
from .task_grading_setup import build_rubric, extract_txt_file_contents
from ...grading import EvaluationResult, LLMTaskEvaluator, Rubric


_ = load_dotenv(find_dotenv())

groq_model_name = "meta-llama/llama-4-scout-17b-16e-instruct"  # "llama-3.3-70b-versatile" # "openai/gpt-oss-120b" # "meta-llama/llama-4-maverick-17b-128e-instruct"
ollama_model_name = "llama3.2:3b"
temperature = 0.0
groq_api_key = os.getenv("GROQ_API_KEY")
task_desc_path = os.getenv("TASK_DESCRIPTION_PATH", "")
rubric_gen_prompt_path = os.getenv("RUBRIC_TEMPLATE_PATH", "")
submissions_folder = os.getenv("DOCUMENTS_DOWNLOAD_FOLDER", "")
grading_template_filepath = os.getenv("GRADING_TEMPLATE_PATH", "")
grading_results_folder = os.getenv("GRADING_RESULTS_DIR_PATH", "")
rubric_directory = os.getenv("RUBRIC_DIR", "")


def grade_task(
    task_stage: int,
    grading_iteration: int,
    name_to_submission_id_mapping: dict[str, dict[str, str]],
    submissions_dir: str | Path = submissions_folder,
    is_colab_submissions: bool = True,
    submissions_subdir_name: str = "as_text",
    task_desc_filepath: str | Path = task_desc_path,
    rubric_gen_prompt_filepath: str | Path = rubric_gen_prompt_path,
    rubric_dir: str | Path = rubric_directory,
    evaluation_results_dir: str | Path = grading_results_folder,
    grading_template_path: str | Path = grading_template_filepath,
    use_groq: bool = False,
    build_task_rubric: bool = False,
    save_rubric: bool = False,
    max_submissions_to_grade: int = 100,
    submission_filenames_to_omit: list[str] | None = None,
) -> int:
    # Ensure that all paths are Path objects, and cast them as Path if necessary
    if not isinstance(submissions_dir, Path):
        submissions_dir = Path(submissions_dir)

    if not isinstance(task_desc_filepath, Path):
        task_desc_filepath = Path(task_desc_filepath)

    if not isinstance(rubric_gen_prompt_filepath, Path):
        rubric_gen_prompt_filepath = Path(rubric_gen_prompt_filepath)

    if not isinstance(rubric_dir, Path):
        rubric_dir = Path(rubric_dir)

    if not isinstance(grading_template_path, Path):
        grading_template_path = Path(grading_template_path)

    assignment_text = extract_txt_file_contents(task_desc_filepath)
    rubric_filename = f"task_{task_stage}_rubric"

    if use_groq:
        llm = ChatGroq(
            model=groq_model_name,
            temperature=temperature,
            api_key=groq_api_key,
        )
    else:
        llm = ChatOllama(
            model=ollama_model_name,
            temperature=temperature,
        )

    rubric_dir = Path(rubric_dir)

    if not rubric_dir.is_dir():
        raise NotADirectoryError(f"{rubric_dir} is not a valid directory")

    if build_task_rubric:
        if not rubric_gen_prompt_filepath.is_file():
            raise FileNotFoundError(f"File {rubric_gen_prompt_filepath} not found")

        rubric_gen_template = extract_txt_file_contents(rubric_gen_prompt_filepath)
        rubric = build_rubric(
            assignment=assignment_text, template=rubric_gen_template, model=llm
        )

        if save_rubric:
            rubric.save_to_json(rubric_dir, rubric_filename)

        print(json.dumps(asdict(rubric), indent=4))
    else:
        rubric = Rubric.load_from_json(rubric_dir, rubric_filename)

    base_template = grading_template_path.read_text(encoding="utf-8")
    evaluator = LLMTaskEvaluator(
        llm=llm,
        base_prompt_template=base_template,
    )

    knowledge_area = os.getenv("KNOWLEDGE_AREA", "")
    cohort_name = os.getenv("COHORT", "")
    track_name = os.getenv("TRACK", "")

    if not submissions_dir.is_dir():
        raise NotADirectoryError(
            f"Source directory '{submissions_dir}' is not a valid  directory"
        )

    if is_colab_submissions:
        # Extract the `ipynb` filenames from submissions_dir without the extension
        filenames = (
            p.stem
            for p in submissions_dir.iterdir()
            if p.is_file() and p.suffix == ".ipynb"
        )

        for file_name in filenames:
            extract_ipynb_to_txt(
                ipynb_dir=submissions_dir,
                filename=file_name,
                text_subdir_name=submissions_subdir_name,
            )

        submissions_dir = submissions_dir / submissions_subdir_name

    task_submission_evaluations = grade_extracted_submissions(
        submissions_directory=submissions_dir,
        name_to_submission_id=name_to_submission_id_mapping,
        evaluator=evaluator,
        rubric=rubric,
        assignment_text=assignment_text,
        knowledge_area=knowledge_area,
        cohort_specifics=cohort_name,
        track_name=track_name,
        how_many_submissions_max=max_submissions_to_grade,
        filenames_to_omit=submission_filenames_to_omit,
    )

    write_evaluations_dict_to_file(
        evaluations_dict=task_submission_evaluations,
        directory=evaluation_results_dir,
        task_stage=task_stage,
        grading_iteration=grading_iteration,
    )

    return len(task_submission_evaluations.keys())


def grade_extracted_submissions(
    submissions_directory: Path,
    name_to_submission_id: dict[str, dict[str, str]],
    evaluator: LLMTaskEvaluator,
    rubric: Rubric,
    assignment_text: str,
    knowledge_area: str,
    cohort_specifics: str,
    track_name: str,
    how_many_submissions_max: int,
    filenames_to_omit: list[str] | None = None,
) -> dict[str, Any]:
    if not submissions_directory.is_dir():
        raise NotADirectoryError(f"{submissions_directory} must be a valid directory")

    filepaths = [path for path in submissions_directory.iterdir() if path.is_file()]

    evaluations_dict = {}
    submissions_to_omit = set(filenames_to_omit) if filenames_to_omit else set()

    for filepath in filepaths[:how_many_submissions_max]:
        trainee_name = filepath.stem

        if trainee_name in submissions_to_omit:
            continue

        submission_text = extract_txt_file_contents(filepath)
        print(
            f"\nExtract from {trainee_name}'s submission text:\n{submission_text[:100]}"
        )  # remove
        try:
            trainee_evaluation: EvaluationResult = evaluator.evaluate(
                rubric=rubric,
                assignment=assignment_text,
                submission=submission_text,
                trainee_name=trainee_name,
                knowledge_area=knowledge_area,
                cohort_specifics=cohort_specifics,
                track_name=track_name,
                other_notes="",
            )

            evaluations_dict[trainee_name] = {
                "submission_id": name_to_submission_id[trainee_name]["submission_id"],
                "submission_date": name_to_submission_id[trainee_name][
                    "submission_date"
                ],
                "evaluation": trainee_evaluation,  # was initially wrapped with `asdict`
            }
        except Exception as e:
            evaluations_dict[trainee_name] = {
                "submission_id": name_to_submission_id[trainee_name]["submission_id"],
                "submission_date": name_to_submission_id[trainee_name][
                    "submission_date"
                ],
                "evaluation": f"Error: {e}",
            }

    return evaluations_dict


def write_evaluations_dict_to_file(
    evaluations_dict: dict[str, Any],
    directory: str | Path,
    task_stage: int,
    grading_iteration: int = 1,
) -> None:
    if not isinstance(directory, Path):
        directory = Path(directory)

    if not directory.is_dir():
        raise NotADirectoryError(f"{directory} must be a valid directory")

    filepath = (
        directory
        / f"task_{task_stage}_evaluation_results_iteration_{grading_iteration}.json"
    )

    for key, value in evaluations_dict.items():
        if isinstance(value, dict) and "evaluation" in value:
            if isinstance(value["evaluation"], str):
                evaluations_dict[key]["evaluation"] = value["evaluation"]
            else:
                evaluations_dict[key]["evaluation"] = asdict(value["evaluation"])

    try:
        with open(filepath, "w") as f:
            json.dump(evaluations_dict, f, indent=4)

        print(f"Wrote evaluation results to {filepath}")
    except IOError as e:
        print(f"Failed to write to {filepath}: {e}")


def print_result(result: EvaluationResult) -> None:
    print("\n=== Intro ===")
    print(result.intro)

    print("\n=== Overall Evaluation ===")
    print(result.overall_evaluation)

    print("\n=== Overall Verdict ===")
    print(result.overall_verdict)

    print("\n=== Criteria Evaluations ===")
    for ce in result.criteria:
        print(f"- [{ce.id}] {ce.name}")
        print(f"  scale: {ce.score_scale}, score: {ce.score}")
        print(f"  justification: {ce.justification}")
        print()

    print("\n=== Total Score ===")
    print(result.total_score)

    print("\n=== Raw YAML (for debugging) ===")
    print(result.raw_yaml)
