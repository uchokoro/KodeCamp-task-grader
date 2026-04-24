import os
import io
import zipfile
import re
from .generic import FolderDownloader

# Pattern to extract owner and repo: github.com/owner/repo
_REPO_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)")


class GitHubRepoDownloader(FolderDownloader):
    """
    Downloads a public GitHub repository as a ZIP and extracts it.
    """

    def download(
        self,
        url: str,
        dest_dir: str,
        filename: str | None = None,
        overwrite: bool = False,
    ) -> str:
        """
        Downloads the main/master branch of a public repo using the Zipball API.
        """
        match = _REPO_URL_RE.search(url)
        if not match:
            raise ValueError(f"Could not parse GitHub owner and repo from: {url}")

        owner, repo = match.groups()
        # Clean the repo name (it might end with .git or have trailing slashes)
        repo = repo.replace(".git", "").strip("/")

        # Determine target path
        target_name = filename if filename else repo
        output_path = os.path.join(dest_dir, target_name)

        if overwrite and os.path.exists(output_path):
            import shutil

            shutil.rmtree(output_path)

        download_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"

        resp = self._session.get(download_url, stream=True)

        if not resp.ok:
            raise RuntimeError(
                f"Error {resp.status_code}.\nFailed to download GitHub repo: {url}"
            )

        # Extract in memory to avoid temporary files
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            # GitHub's zipball puts everything inside a root folder named like 'owner-repo-hash'
            # We want to extract its contents directly into our output_path
            root_dir = z.namelist()[0].split("/")[0]

            os.makedirs(output_path, exist_ok=True)

            for member in z.infolist():
                # Strip the dynamic root folder name provided by GitHub
                if member.filename.startswith(root_dir + "/"):
                    member.filename = member.filename.replace(root_dir + "/", "", 1)
                    if member.filename:  # Avoid extracting the empty root dir
                        z.extract(member, output_path)

        return output_path
