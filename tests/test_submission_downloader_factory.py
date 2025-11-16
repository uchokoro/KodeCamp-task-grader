import pytest

from task_grader.docs.factory import SubmissionDownloaderFactory
from task_grader.docs.google_docs import GoogleDocsDownloader


def test_register_and_get_downloader_returns_instance():
    factory = SubmissionDownloaderFactory()

    # Register the class (not an instance) so factory can call it like a constructor
    factory.register_downloader("gdocs", GoogleDocsDownloader)  # type: ignore[arg-type]

    assert factory.is_registered("gdocs") is True

    downloader = factory.get_downloader("gdocs")
    assert isinstance(downloader, GoogleDocsDownloader)


def test_get_downloader_raises_for_unknown_key():
    factory = SubmissionDownloaderFactory()

    with pytest.raises(KeyError) as exc:
        factory.get_downloader("nonexistent")

    assert "No valid downloader registered for nonexistent" in str(exc.value)


def test_register_downloader_uses_description_from_downloader_docstring():
    factory = SubmissionDownloaderFactory()

    factory.register_downloader("gdocs", GoogleDocsDownloader)  # type: ignore[arg-type]
    desc = factory.get_downloader_description("gdocs")

    # By default, GoogleDocsDownloader.get_description returns its docstring
    assert desc == (GoogleDocsDownloader.__doc__ or None)


def test_get_downloader_description_raises_for_unknown_key():
    factory = SubmissionDownloaderFactory()

    with pytest.raises(KeyError) as exc:
        factory.get_downloader_description("unknown")

    assert "No downloader registered for unknown" in str(exc.value)


def test_confirm_registered_downloaders_returns_key_description_pairs():
    factory = SubmissionDownloaderFactory()

    factory.register_downloader("gdocs", GoogleDocsDownloader)  # type: ignore[arg-type]
    entries = factory.confirm_registered_downloaders()

    # Should be a list of dicts like [{"gdocs": "<description>"}]
    assert isinstance(entries, list)
    assert any(
        entry.get("gdocs") == (GoogleDocsDownloader.__doc__ or None)
        for entry in entries
    )
