from __future__ import annotations

from datetime import date, timedelta

from .config import FilterConfig
from .connectors.base import Job


def matches_any_substring(value: str, candidates: list[str]) -> bool:
    value_lower = value.lower()
    return any(candidate.lower() in value_lower for candidate in candidates)


def matches_designation(job: Job, designations: list[str]) -> bool:
    return matches_any_substring(job.title, designations)


def matches_location(job: Job, locations: list[str]) -> bool:
    return matches_any_substring(job.location, locations)


def matches_workplace_type(job: Job, workplace_types: list[str]) -> bool:
    if job.remote_type is None:
        return True
    return job.remote_type in workplace_types


def matches_posted_within(job: Job, days: int, today: date) -> bool:
    if job.posted_date is None:
        return True
    return job.posted_date >= today - timedelta(days=days)


def has_excluded_keyword(job: Job, exclude_keywords: list[str]) -> bool:
    haystack = f"{job.title} {job.description_snippet}"
    return matches_any_substring(haystack, exclude_keywords)


def apply_filters(jobs: list[Job], filters: FilterConfig, today: date | None = None) -> list[Job]:
    today = today or date.today()
    kept = []
    for job in jobs:
        if not matches_designation(job, filters.designations):
            continue
        if not matches_location(job, filters.locations):
            continue
        if not matches_workplace_type(job, filters.workplace_types):
            continue
        if not matches_posted_within(job, filters.posted_within_days, today):
            continue
        if has_excluded_keyword(job, filters.exclude_keywords):
            continue
        kept.append(job)
    return kept
