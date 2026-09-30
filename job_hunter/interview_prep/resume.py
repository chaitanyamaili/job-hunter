from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..connectors.base import ConnectorError, get_with_retry
from .extractor import InterviewPrepError
from .html_text import extract_visible_text

DEFAULT_RESUME_PATH = "resume.md"


def load_resume(source: str | None) -> str | None:
    if source is None:
        path = Path(DEFAULT_RESUME_PATH)
        if not path.exists():
            return None
        return path.read_text()

    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        try:
            response = get_with_retry(source)
        except ConnectorError as exc:
            raise InterviewPrepError(str(exc)) from exc
        if response.status_code >= 400:
            raise InterviewPrepError(
                f"request for resume '{source}' failed with status {response.status_code}"
            )
        soup = BeautifulSoup(response.text, "html.parser")
        return extract_visible_text(soup)

    path = Path(source)
    if not path.exists():
        raise InterviewPrepError(f"resume file not found: {source}")
    return path.read_text()
