from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from ..connectors.base import ConnectorError, get_with_retry
from .html_text import extract_visible_text


class InterviewPrepError(Exception):
    """Raised when a job posting cannot be fetched or parsed."""


@dataclass
class JobPosting:
    title: str
    company: str
    description_text: str
    url: str


def fetch_job_posting(url: str) -> JobPosting:
    try:
        response = get_with_retry(url)
    except ConnectorError as exc:
        raise InterviewPrepError(str(exc)) from exc

    if response.status_code >= 400:
        raise InterviewPrepError(
            f"request for '{url}' failed with status {response.status_code}"
        )

    soup = BeautifulSoup(response.text, "html.parser")

    posting = _extract_json_ld_posting(soup, url)
    if posting:
        return posting

    return _extract_heuristic_posting(soup, url)


def _extract_json_ld_posting(soup: BeautifulSoup, url: str) -> JobPosting | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("@type") != "JobPosting":
                continue
            title = entry.get("title", "")
            description_html = entry.get("description", "")
            description_text = BeautifulSoup(
                description_html, "html.parser"
            ).get_text(separator=" ", strip=True)
            company = ""
            hiring_org = entry.get("hiringOrganization")
            if isinstance(hiring_org, dict):
                company = hiring_org.get("name", "")
            return JobPosting(
                title=title,
                company=company,
                description_text=description_text,
                url=url,
            )
    return None


_GREENHOUSE_TITLE_PATTERN = re.compile(r"^Job Application for (.+) at (.+)$")


def _extract_heuristic_posting(soup: BeautifulSoup, url: str) -> JobPosting:
    title = ""
    company = ""
    if soup.title and soup.title.string:
        raw_title = soup.title.string.strip()
        match = _GREENHOUSE_TITLE_PATTERN.match(raw_title)
        if match:
            title, company = match.group(1).strip(), match.group(2).strip()
        else:
            title = raw_title
    else:
        heading = soup.find("h1")
        if heading:
            title = heading.get_text(strip=True)

    return JobPosting(
        title=title,
        company=company,
        description_text=extract_visible_text(soup),
        url=url,
    )
