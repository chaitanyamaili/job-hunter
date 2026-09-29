from __future__ import annotations

from datetime import date, datetime

from .base import ConnectorError, Job, get_with_retry

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def fetch_greenhouse(board_token: str, company_name: str) -> list[Job]:
    url = GREENHOUSE_URL.format(token=board_token)
    response = get_with_retry(url)

    if response.status_code == 404:
        raise ConnectorError(f"greenhouse board '{board_token}' not found")
    if response.status_code >= 400:
        raise ConnectorError(
            f"greenhouse request for '{board_token}' failed with status {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ConnectorError(f"greenhouse response for '{board_token}' was not valid JSON") from exc

    jobs = []
    for entry in payload.get("jobs", []):
        jobs.append(
            Job(
                title=entry.get("title", ""),
                company=company_name,
                location=(entry.get("location") or {}).get("name", ""),
                url=entry.get("absolute_url", ""),
                source="greenhouse",
                remote_type=None,
                posted_date=_parse_date(entry.get("updated_at")),
                description_snippet=(entry.get("content") or "")[:280],
            )
        )
    return jobs


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
