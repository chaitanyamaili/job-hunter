from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import CompanyConfig
from .base import ConnectorError, Job
from .generic_crawler import fetch_generic
from .greenhouse import fetch_greenhouse
from .lever import fetch_lever

def slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


@dataclass
class CompanyResult:
    company: str
    jobs: list[Job] = field(default_factory=list)
    source: str | None = None
    unmatched: bool = False
    note: str | None = None
    hint_slug: str | None = None


def fetch_for_company(company: CompanyConfig) -> CompanyResult:
    if company.ats and company.board_token:
        return _fetch_explicit(company)

    slug = slugify(company.name)

    try:
        jobs = fetch_greenhouse(slug, company.name)
        return CompanyResult(company=company.name, jobs=jobs, source="greenhouse")
    except ConnectorError:
        pass

    try:
        jobs = fetch_lever(slug, company.name)
        return CompanyResult(company=company.name, jobs=jobs, source="lever")
    except ConnectorError:
        pass

    if company.careers_url:
        try:
            jobs = fetch_generic(company.careers_url, company.name)
        except ConnectorError as exc:
            return CompanyResult(company=company.name, unmatched=True, note=str(exc))
        if not jobs:
            return CompanyResult(
                company=company.name,
                source="generic",
                note="no jobs found (page may need manual review)",
            )
        return CompanyResult(company=company.name, jobs=jobs, source="generic")

    return CompanyResult(
        company=company.name,
        unmatched=True,
        hint_slug=slug,
        note=(
            f"could not auto-detect ATS; check https://boards.greenhouse.io/{slug} "
            f"or https://jobs.lever.co/{slug}, or add board_token/careers_url to config.yaml"
        ),
    )


def _fetch_explicit(company: CompanyConfig) -> CompanyResult:
    if company.ats == "greenhouse":
        fetcher = fetch_greenhouse
    elif company.ats == "lever":
        fetcher = fetch_lever
    else:
        return CompanyResult(
            company=company.name,
            unmatched=True,
            note=f"unknown ats '{company.ats}' in config; expected 'greenhouse' or 'lever'",
        )
    try:
        jobs = fetcher(company.board_token, company.name)
    except ConnectorError as exc:
        return CompanyResult(company=company.name, unmatched=True, note=str(exc))
    return CompanyResult(company=company.name, jobs=jobs, source=company.ats)
