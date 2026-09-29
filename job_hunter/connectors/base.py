from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import requests


class ConnectorError(Exception):
    """Raised when a connector cannot fetch or parse job postings."""


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    remote_type: str | None = None
    posted_date: date | None = None
    description_snippet: str = ""


def get_with_retry(
    url: str,
    timeout: int = 10,
    retries: int = 1,
    backoff_seconds: float = 2,
) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff_seconds)
                continue
            raise ConnectorError(f"request to {url} failed: {exc}") from exc

        if response.status_code >= 500 and attempt < retries:
            time.sleep(backoff_seconds)
            continue
        return response

    raise ConnectorError(f"request to {url} failed: {last_exc}")
