from pathlib import Path

import pytest

from task_grader.docs.google_docs import (
    extract_doc_id,
    GoogleDocsDownloader,
)


# --- Simple fakes -------------------------------------------------------------


class FakeResponse:
    def __init__(self, *, ok=True, status_code=200, content=b"", text=""):
        self.ok = ok
        self.status_code = status_code
        self.content = content
        self.text = text


class FakeSession:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.last_url: str | None = None

    def get(self, url: str) -> FakeResponse:
        self.last_url = url
        return self._response


# --- extract_doc_id tests -----------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://docs.google.com/document/d/ABC123DEF/edit",
            "ABC123DEF",
        ),
        (
            "https://docs.google.com/document/d/abc_123-XYZ/",
            "abc_123-XYZ",
        ),
        (
            "https://docs.google.com/document/d/ID_ONLY",
            "ID_ONLY",
        ),
        (
            "https://docs.google.com/document/d/ABC123DEF/edit?",  # extra path pieces
            "ABC123DEF",
        ),
    ],
)
def test_extract_doc_id_valid_urls(url, expected):
    assert extract_doc_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://docs.google.com/spreadsheets/d/ABC123/edit",  # wrong type
        "https://example.com/not/google/docs/url",
        "https://docs.google.com/document/edit",  # missing /d/<ID>
        "",
    ],
)
def test_extract_doc_id_invalid_urls(url):
    assert extract_doc_id(url) is None


# --- GoogleDocsDownloader tests ----------------------------------------------


def test_download_as_raises_for_invalid_url(tmp_path: Path):
    downloader = GoogleDocsDownloader(session=FakeSession(FakeResponse()))  # type: ignore[arg-type]

    with pytest.raises(ValueError) as exc:
        downloader.download_as(
            doc_url="https://example.com/not-a-doc-url",
            dest_dir=str(tmp_path),
        )

    assert "Could not extract document ID" in str(exc.value)


def test_download_as_builds_correct_export_url_and_writes_file(tmp_path: Path):
    # Arrange
    content = b"hello from google docs"
    response = FakeResponse(ok=True, status_code=200, content=content)
    session = FakeSession(response=response)
    downloader = GoogleDocsDownloader(session=session)  # type: ignore[arg-type]

    doc_url = "https://docs.google.com/document/d/ABC123DEF/edit"

    # Act
    out_path = downloader.download_as(
        doc_url=doc_url,
        dest_dir=str(tmp_path),
        as_format="txt",
    )

    # Assert: correct export URL used
    assert (
        session.last_url
        == "https://docs.google.com/document/d/ABC123DEF/export?format=txt"
    )

    # Assert: file created with expected content
    out_file = Path(out_path)
    assert out_file.exists()
    assert out_file.read_bytes() == content

    # By default, filename is doc_id
    assert out_file.name == "ABC123DEF.txt"


def test_download_as_uses_custom_filename(tmp_path: Path):
    content = b"custom filename content"
    response = FakeResponse(ok=True, status_code=200, content=content)
    session = FakeSession(response=response)
    downloader = GoogleDocsDownloader(session=session)  # type: ignore[arg-type]

    doc_url = "https://docs.google.com/document/d/ID_456/edit"

    out_path = downloader.download_as(
        doc_url=doc_url,
        dest_dir=str(tmp_path),
        filename="my_doc",
        as_format="pdf",
    )

    out_file = Path(out_path)
    assert out_file.exists()
    assert out_file.read_bytes() == content
    assert out_file.name == "my_doc.pdf"


def test_download_as_raises_runtimeerror_on_http_failure(tmp_path: Path):
    response = FakeResponse(
        ok=False,
        status_code=403,
        content=b"",
        text="Forbidden",
    )
    session = FakeSession(response=response)
    downloader = GoogleDocsDownloader(session=session)  # type: ignore[arg-type]

    doc_url = "https://docs.google.com/document/d/SECRET_DOC/edit"

    with pytest.raises(RuntimeError) as exc:
        downloader.download_as(
            doc_url=doc_url,
            dest_dir=str(tmp_path),
            as_format="txt",
        )

    msg = str(exc.value)
    assert "Failed to download Google Doc" in msg
    assert "status 403" in msg
    assert "SECRET_DOC" in msg
