from .generic import SubmissionDownloader


class SubmissionDownloaderFactory:
    def __init__(self):
        self._downloaders = {}

    def register_downloader(
        self, key: str, downloader: SubmissionDownloader, description: str | None = None
    ) -> None:
        if not description:
            description = downloader.get_description()
        self._downloaders[key] = {
            "downloader": downloader,
            "description": description,
        }

    def get_downloader(self, key: str, **kwargs) -> SubmissionDownloader:
        if key not in self._downloaders or not self._downloaders[key].get("downloader"):
            raise KeyError(f"No valid downloader registered for {key}")

        downloader = self._downloaders[key]["downloader"]

        return downloader(**kwargs)

    def is_registered(self, key: str) -> bool:
        return key in self._downloaders

    def confirm_registered_downloaders(self) -> list[dict[str, str]]:
        downloaders = []

        for key, downloader in self._downloaders.items():
            downloaders.append({key: downloader["description"]})

        return downloaders

    def get_downloader_description(self, key: str) -> str:
        downloader = self._downloaders.get(key)

        if not downloader:
            raise KeyError(f"No downloader registered for {key}")

        return downloader["description"]
