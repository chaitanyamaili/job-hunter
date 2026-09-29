from __future__ import annotations

from datetime import date, datetime

from .base import ConnectorError, Job, get_with_retry

LEVER_URL = "https://api.lever.co/v0/postings/{token}?mode=json"

_WORKPLACE_TYPE_MAP = {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite", "onsite": "onsite"}


def fetch_lever(board_token: str, company_name: str) -> list[Job]:
    url = LEVER_URL.format(token=board_token)
    response = get_with_retry(url)

    if response.status_code == 404:
        raise ConnectorError(f"lever board '{board_token}' not found")
    if response.status_code >= 400:
        raise ConnectorError(
            f"lever request for '{board_token}' failed with status {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ConnectorError(f"lever response for '{board_token}' was not valid JSON") from exc

    if not isinstance(payload, list):
        raise ConnectorError(f"lever response for '{board_token}' had unexpected shape")

    jobs = []
    for entry in payload:
        categories = entry.get("categories") or {}
        jobs.append(
            Job(
                title=entry.get("text", ""),
                company=company_name,
                location=categories.get("location", ""),
                url=entry.get("hostedUrl", ""),
                source="lever",
                remote_type=_WORKPLACE_TYPE_MAP.get((entry.get("workplaceType") or "").lower()),
                posted_date=_parse_created_at(entry.get("createdAt")),
                description_snippet=(entry.get("descriptionPlain") or "")[:280],
            )
        )
    return jobs


def _parse_created_at(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000).date()
    except (ValueError, OSError, OverflowError):
        return None
