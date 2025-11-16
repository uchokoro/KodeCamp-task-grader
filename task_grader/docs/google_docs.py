import os
import re
from .generic import SubmissionDownloader

# Pattern for document/d/<ID>
_DOC_ID_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")


def extract_doc_id(doc_url: str) -> str | None:
    """
    Extract the Google Doc ID from a typical docs URL.

    Examples:
        https://docs.google.com/document/d/<DOC_ID>/edit
        https://docs.google.com/document/d/<DOC_ID>/
    """
    match = _DOC_ID_RE.search(doc_url)
    if match:
        return match.group(1)

    return None


class GoogleDocsDownloader(SubmissionDownloader):
    """
    Download Google Docs document from its URL.
    Expects the doc to be publicly accessible
    (e.g. 'Anyone with the link can view').
    """

    @classmethod
    def get_description(cls) -> str | None:
        return cls.__doc__ or None

    def download_as(
        self,
        doc_url: str,
        dest_dir: str,
        filename: str | None = None,
        as_format: str = "txt",
    ) -> str:
        """
        Download a Google Doc given its URL and save it to dest_dir.

        - Converts the share link into an export URL, e.g.:
            https://docs.google.com/document/d/<ID>/export?format=docx

        - filename is the desired name for the file on disk without the extension.
            If none is provided, then the document id, as extracted from the URL is used

        - as_format can be 'docx', 'pdf', 'odt', etc., depending on your preference.

        - Returns the filepath of the downloaded file.
        """
        doc_id = extract_doc_id(doc_url)
        if not doc_id:
            raise ValueError(f"Could not extract document ID from URL: {doc_url}")

        export_url = (
            f"https://docs.google.com/document/d/{doc_id}/export?format={as_format}"
        )
        resp = self._session.get(export_url)

        if not resp.ok:
            raise RuntimeError(
                f"Failed to download Google Doc (status {resp.status_code}). "
                f"URL: {doc_url}\nResponse text:\n{resp.text}"
            )

        if not filename:
            filename = doc_id

        filepath = os.path.join(dest_dir, f"{filename}.{as_format}")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(resp.content)

        return filepath
