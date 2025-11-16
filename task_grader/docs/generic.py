from abc import ABC, abstractmethod
import requests


class SubmissionDownloader(ABC):
    """
    Task submission downloader interface.
    Download a task submission from its URL.
    """

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    @classmethod
    @abstractmethod
    def get_description(cls) -> str | None:
        """
        Provide description of the downloader.
        """
        pass

    @abstractmethod
    def download_as(
        self,
        doc_url: str,
        dest_dir: str,
        filename: str | None = None,
        as_format: str = "txt",
    ) -> str:
        pass
