from datetime import date, datetime

from job_hunter.connectors.autodetect import CompanyResult
from job_hunter.connectors.base import Job
from job_hunter.referrals import Connection
from job_hunter.report import render_report, write_report


def _job(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme",
        location="Austin, TX",
        url="https://boards.greenhouse.io/acme/1",
        source="greenhouse",
        remote_type="remote",
        posted_date=date(2026, 9, 20),
        description_snippet="",
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_render_report_lists_jobs_and_referrals():
    results = [CompanyResult(company="Acme", jobs=[_job()], source="greenhouse")]
    connections = [Connection(name="Jane Doe", company="Acme", title="Engineer")]

    markdown = render_report(results, connections, datetime(2026, 9, 29, 8, 0))

    assert "Acme" in markdown
    assert "Backend Engineer" in markdown
    assert "Possible referrals: Jane Doe (Engineer)" in markdown


def test_render_report_dedupes_same_url_across_companies():
    duplicate_job = _job()
    results = [
        CompanyResult(company="Acme", jobs=[duplicate_job], source="greenhouse"),
        CompanyResult(company="Acme Mirror", jobs=[duplicate_job], source="greenhouse"),
    ]

    markdown = render_report(results, [], datetime(2026, 9, 29, 8, 0))

    assert markdown.count("Backend Engineer") == 1


def test_render_report_shows_no_matches_message_when_empty():
    markdown = render_report([], [], datetime(2026, 9, 29, 8, 0))
    assert "No matching openings this run." in markdown


def test_render_report_lists_unmatched_notes():
    results = [CompanyResult(company="Mystery Co", unmatched=True, note="could not auto-detect ATS")]

    markdown = render_report(results, [], datetime(2026, 9, 29, 8, 0))

    assert "Mystery Co" in markdown
    assert "could not auto-detect ATS" in markdown


def test_write_report_creates_missing_output_dir(tmp_path):
    output_dir = tmp_path / "reports"

    path = write_report("# Report", str(output_dir), datetime(2026, 9, 29, 8, 0))

    assert path.exists()
    assert path.read_text() == "# Report"
    assert path.parent == output_dir
    assert path.name == "2026-09-29_0800_job_matches.md"
