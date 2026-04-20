from abc import ABC, abstractmethod
import requests


class SubmissionDownloader(ABC):
    """Base interface for all Google-based resource downloaders."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    @classmethod
    def get_description(cls) -> str | None:
        """Provide description of the downloader."""
        return cls.__doc__ or None

    @abstractmethod
    def download(self, url: str, dest_dir: str, filename: str | None = None) -> str:
        """The generic download action shared by all types."""
        pass


class FileDownloader(SubmissionDownloader, ABC):
    """
    Interface for single-file document downloads (Docs, Colab).
    Adds support for format conversion.
    """

    @abstractmethod
    def download_as(
        self,
        doc_url: str,
        dest_dir: str,
        filename: str | None = None,
        as_format: str = "txt",
    ) -> str:
        """Specific method for files that require format-shifting."""
        pass

    def download(self, url: str, dest_dir: str, filename: str | None = None) -> str:
        # Calls the specific method with default format
        return self.download_as(url, dest_dir, filename)


class FolderDownloader(SubmissionDownloader, ABC):
    """Interface for Google Drive folders or directory-like structures."""

    @abstractmethod
    def download(
        self,
        url: str,
        dest_dir: str,
        filename: str | None = None,
        recursive: bool = True,
        overwrite: bool = False,
    ) -> str:
        """Implementation for pulling entire folders."""
        pass
