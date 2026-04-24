import io
import os
import re
import subprocess
import zipfile

from .generic import FolderDownloader

# Pattern to extract owner and repo: github.com/owner/repo
_REPO_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)")


class GitHubRepoDownloader(FolderDownloader):
    """
    Downloads a public GitHub repository as a ZIP and extracts it.
    """

    @staticmethod
    def _get_auth_url(url: str) -> str:
        """Injects the GITHUB_TOKEN into the URL for CLI authentication."""
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return url

        # Convert https://github.com/owner/repo to https://<token>@github.com/owner/repo
        return url.replace("https://", f"https://{token}@")

    @staticmethod
    def _prepare_output_path(
        url: str, dest_dir: str, filename: str | None = None, overwrite: bool = False
    ) -> tuple[str, str, str]:
        """
        Parses the GitHub URL and prepares the local destination directory.
        Returns the absolute path to the target directory.
        """
        match = _REPO_URL_RE.search(url)

        if not match:
            raise ValueError(f"Invalid GitHub URL: {url}")

        owner, repo = match.groups()
        # Normalize repo name: remove .git and trailing slashes
        repo = repo.replace(".git", "").strip("/")

        # Determine target output path
        target_name = filename if filename else repo
        output_path = os.path.abspath(os.path.join(dest_dir, target_name))

        if overwrite and os.path.exists(output_path):
            import shutil

            shutil.rmtree(output_path)

        return output_path, owner, repo

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

        output_path, owner, repo = self._prepare_output_path(
            url, dest_dir, filename, overwrite
        )

        # Add Token, if available in the environment, to Session Headers
        # This enables the downloader to handle private repos that the token is authorized for
        token = os.getenv("GITHUB_TOKEN")

        if token:
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                }
            )

        download_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"

        resp = self._session.get(download_url, stream=True)

        if not resp.ok:
            # Provide helpful feedback if auth might be the issue
            error_msg = (
                f"Failed to download GitHub repo, {url}, (Status: {resp.status_code})."
            )

            if resp.status_code == 401:
                error_msg += " Unauthenticated: Check your GITHUB_TOKEN."
            elif resp.status_code == 403:
                error_msg += " Unauthorized: Check your GITHUB_TOKEN."

            raise RuntimeError(error_msg)

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

    def clone(
        self,
        url: str,
        dest_dir: str,
        filename: str | None = None,
        depth: int | None = 1,
        overwrite: bool = False,
    ) -> str:
        """
        Clones the repository using the git CLI.

        - depth: 1 performs a 'shallow' clone (fastest, no history).
        - overwrite: Removes existing directory before cloning.
        """

        output_path, owner, repo = self._prepare_output_path(
            url, dest_dir, filename, overwrite
        )
        auth_url = self._get_auth_url(url)

        # Build the git command
        cmd = ["git", "clone"]
        if depth:
            cmd.extend(["--depth", str(depth)])
        cmd.extend([auth_url, output_path])

        # Execute clone
        try:
            # shell=True is usually avoided, but on Windows CMD it can help with path resolution
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            # Mask the token in the error message so it doesn't leak in logs
            error_log = e.stderr.replace(os.getenv("GITHUB_TOKEN", ""), "********")
            raise RuntimeError(f"Git clone failed: {error_log}")

        return output_path
