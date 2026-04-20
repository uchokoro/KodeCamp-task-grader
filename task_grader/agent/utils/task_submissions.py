import os
import json
from dataclasses import asdict
from enum import StrEnum

from dotenv import find_dotenv, load_dotenv

from ...docs import (
    GoogleColabDownloader,
    GoogleDocsDownloader,
    SubmissionDownloader,
    SubmissionDownloaderFactory,
)
from ...lms import LMSClient, SubmissionCategory


_ = load_dotenv(find_dotenv())
_workspace_slug = os.getenv("KC_COHORT_WORKSPACE_SLUG", "")
_task_id = os.getenv("TASK_ID")
_doc_download_dir = os.getenv("DOCUMENTS_DOWNLOAD_FOLDER", "")


class SubmissionFormat(StrEnum):
    COLAB = "google_colab"
    DOC = "google_doc"


submission_format_mapping: dict[SubmissionFormat, type[SubmissionDownloader]] = {
    SubmissionFormat.COLAB: GoogleColabDownloader,
    SubmissionFormat.DOC: GoogleDocsDownloader,
}


def get_downloader_factory(
    submission_formats: set[SubmissionFormat],
) -> SubmissionDownloaderFactory:
    # Instantiate download factory with valid registered submission downloaders
    downloader_factory = SubmissionDownloaderFactory()

    for submission_format in submission_formats:
        downloader = submission_format_mapping.get(submission_format, None)  # type: ignore[arge-type]
        if not downloader or not issubclass(downloader, SubmissionDownloader):
            raise ValueError(
                f"No valid submission downloader maps to {submission_format}"
            )

        downloader_factory.register_downloader(
            key=submission_format, downloader=downloader
        )

    return downloader_factory


def download_submissions(
    submission_format: SubmissionFormat,
    downloader_factory: SubmissionDownloaderFactory,
    download_dir: str = _doc_download_dir,
    task_id: str = str(_task_id),
    workspace_slug: str = _workspace_slug,
    submission_category: SubmissionCategory = SubmissionCategory.SUBMITTED,
    max_submissions_to_download: int = 2000,
) -> None:
    # Instantiate the LMS client and confirm that access token is `None` by default
    lms_client = LMSClient.from_env()

    # Login and check if token is valid after login
    lms_client.login()
    print(f"Token validity after login: {lms_client.is_token_valid()}")

    # Retrieve metadata for solutions submitted for task with id: `task_id`
    solutions = lms_client.get_task_submissions(
        task_id=task_id,
        workspace_slug=workspace_slug,
        category=submission_category,
        limit=max_submissions_to_download,
    )

    # Download the submissions
    downloader = downloader_factory.get_downloader(str(submission_format))
    download_count = 0
    problem_submissions = {}
    name_to_submission_id_mapping = {}

    for solution in solutions:
        submission_url = solution.solution_urls[0]
        name = solution.trainee_name
        split_name = name.strip().split()
        filename = "_".join(split_name).strip().lower()
        name_to_submission_id_mapping[filename] = {
            "submission_id": solution.submission_id,
            "submission_date": solution.submission_date,
        }

        try:
            _ = downloader.download_as(
                doc_url=submission_url, dest_dir=download_dir, filename=filename
            )
            download_count += 1
        except Exception as e:
            print(f"Failed to download {filename}: {e}")
            problem_submissions[solution.trainee_name] = asdict(solution)

    print(f"Download completed: {download_count} submission files downloaded.")
    print("\n\n----------------------\nProblem submissions:")
    print(json.dumps(problem_submissions, indent=4))
    print("\n\n----------------------\nName to submission id mapping:")
    print(json.dumps(name_to_submission_id_mapping, indent=4))
