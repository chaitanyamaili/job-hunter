from datetime import date

from job_hunter.config import FilterConfig
from job_hunter.connectors.base import Job
from job_hunter.filters import apply_filters


def _job(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme",
        location="Austin, TX",
        url="u",
        source="greenhouse",
        remote_type="remote",
        posted_date=date(2026, 9, 20),
        description_snippet="Join our team.",
    )
    defaults.update(overrides)
    return Job(**defaults)


def _filters(**overrides):
    defaults = dict(
        designations=["Backend"],
        locations=["Austin"],
        workplace_types=["remote", "hybrid"],
        posted_within_days=14,
        exclude_keywords=["Clearance"],
    )
    defaults.update(overrides)
    return FilterConfig(**defaults)


def test_job_matching_all_filters_is_kept():
    result = apply_filters([_job()], _filters(), today=date(2026, 9, 29))
    assert len(result) == 1


def test_job_with_non_matching_designation_is_dropped():
    result = apply_filters([_job(title="Sales Manager")], _filters(), today=date(2026, 9, 29))
    assert result == []


def test_job_with_non_matching_location_is_dropped():
    result = apply_filters([_job(location="Seattle, WA")], _filters(), today=date(2026, 9, 29))
    assert result == []


def test_job_with_unknown_workplace_type_is_kept():
    result = apply_filters([_job(remote_type=None)], _filters(), today=date(2026, 9, 29))
    assert len(result) == 1


def test_job_with_non_matching_workplace_type_is_dropped():
    result = apply_filters([_job(remote_type="onsite")], _filters(), today=date(2026, 9, 29))
    assert result == []


def test_job_with_unknown_posted_date_is_kept():
    result = apply_filters([_job(posted_date=None)], _filters(), today=date(2026, 9, 29))
    assert len(result) == 1


def test_job_posted_too_long_ago_is_dropped():
    result = apply_filters(
        [_job(posted_date=date(2026, 9, 1))], _filters(), today=date(2026, 9, 29)
    )
    assert result == []


def test_job_with_excluded_keyword_in_title_is_dropped():
    result = apply_filters(
        [_job(title="Backend Engineer - Clearance required")], _filters(), today=date(2026, 9, 29)
    )
    assert result == []


def test_job_with_excluded_keyword_in_description_is_dropped():
    result = apply_filters(
        [_job(description_snippet="Requires active Clearance.")],
        _filters(),
        today=date(2026, 9, 29),
    )
    assert result == []
