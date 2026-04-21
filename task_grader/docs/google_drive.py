import os
import re
import shutil
import gdown
from gdown.exceptions import DownloadError
from .generic import FolderDownloader

# Pattern for /folders/<ID>
_FOLDER_ID_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")


def extract_folder_id(folder_url: str) -> str | None:
    """Extract the Google Drive Folder ID from a typical sharing URL."""
    match = _FOLDER_ID_RE.search(folder_url)
    return match.group(1) if match else None


class GoogleDriveDownloader(FolderDownloader):
    """
    Downloads a public Google Drive Folder using the gdown library.
    """

    def download(
        self,
        url: str,
        dest_dir: str,
        filename: str | None = None,
        overwrite: bool = False,
    ) -> str:
        """
        Uses gdown to download an entire folder with optional overwrite logic.
        """
        folder_id = extract_folder_id(url)

        if not folder_id:
            raise ValueError(f"Could not extract folder ID from URL: {url}")

        # If a filename is provided, we use it as the name of the folder on disk
        # Otherwise, gdown will use the remote folder's name.
        output_path = os.path.join(dest_dir, filename) if filename else dest_dir

        # Overwrite logic: Remove existing directory if overwrite is True
        if overwrite and os.path.exists(output_path):
            shutil.rmtree(output_path)

        # Ensure the parent directory exists
        os.makedirs(dest_dir, exist_ok=True)

        try:
            result = gdown.download_folder(
                id=folder_id, output=output_path, quiet=False, resume=False
            )
            print(
                f"Successfully downloaded {len(result)} files from Google Drive at {url}"
            )
        except DownloadError as e:
            print(
                f"Encountered an error while trying to download he Google Drive folder from '{url}'\n{e}"
            )
            raise DownloadError(e)

        if result is None:
            raise RuntimeError(
                f"Could not download the Google Drive folder from '{url}'"
            )

        # result is a list of file paths downloaded; we return the base directory
        return output_path
