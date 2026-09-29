from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import ConnectorError, Job, get_with_retry

_JOB_LINK_RE = re.compile(r"(job|career|position|opening)", re.IGNORECASE)


def fetch_generic(careers_url: str, company_name: str) -> list[Job]:
    response = get_with_retry(careers_url)

    if response.status_code >= 400:
        raise ConnectorError(
            f"generic crawler request for '{careers_url}' failed with status {response.status_code}"
        )

    soup = BeautifulSoup(response.text, "html.parser")

    jobs = _extract_json_ld_jobs(soup, company_name, careers_url)
    if jobs:
        return jobs

    return _extract_heuristic_jobs(soup, company_name, careers_url)


def _extract_json_ld_jobs(soup: BeautifulSoup, company_name: str, base_url: str) -> list[Job]:
    jobs = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("@type") != "JobPosting":
                continue
            location = ""
            job_location = entry.get("jobLocation")
            if isinstance(job_location, dict):
                address = job_location.get("address")
                if isinstance(address, dict):
                    location = address.get("addressLocality", "")
            jobs.append(
                Job(
                    title=entry.get("title", ""),
                    company=company_name,
                    location=location,
                    url=entry.get("url", base_url),
                    source="generic",
                    remote_type="remote" if entry.get("jobLocationType") == "TELECOMMUTE" else None,
                    posted_date=_parse_date(entry.get("datePosted")),
                    description_snippet=(entry.get("description") or "")[:280],
                )
            )
    return jobs


def _extract_heuristic_jobs(soup: BeautifulSoup, company_name: str, base_url: str) -> list[Job]:
    jobs = []
    seen_urls = set()
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        if not text or not _JOB_LINK_RE.search(anchor["href"]):
            continue
        url = urljoin(base_url, anchor["href"])
        if url in seen_urls:
            continue
        seen_urls.add(url)
        jobs.append(
            Job(
                title=text,
                company=company_name,
                location="",
                url=url,
                source="generic",
                remote_type=None,
                posted_date=None,
                description_snippet="",
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
