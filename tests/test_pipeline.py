from datetime import date
from unittest.mock import patch

from job_hunter.config import CompanyConfig, Config, FilterConfig, ScheduleConfig
from job_hunter.connectors.autodetect import CompanyResult
from job_hunter.connectors.base import Job
from job_hunter.pipeline import run_pipeline


def _config(tmp_path):
    connections_csv = tmp_path / "connections.csv"
    connections_csv.write_text("name,company,title\nJane Doe,Acme,Engineer\n")
    return Config(
        companies=[CompanyConfig(name="Acme")],
        filters=FilterConfig(
            designations=["Backend"],
            locations=["Austin"],
            workplace_types=["remote"],
            posted_within_days=14,
            exclude_keywords=[],
        ),
        connections_csv=str(connections_csv),
        output_dir=str(tmp_path / "reports"),
        schedule=ScheduleConfig(interval="6h"),
    )


@patch("job_hunter.pipeline.fetch_for_company")
def test_run_pipeline_writes_filtered_matches_with_referrals(mock_fetch, tmp_path):
    mock_fetch.return_value = CompanyResult(
        company="Acme",
        source="greenhouse",
        jobs=[
            Job(
                title="Backend Engineer",
                company="Acme",
                location="Austin, TX",
                url="https://boards.greenhouse.io/acme/1",
                source="greenhouse",
                remote_type="remote",
                posted_date=date.today(),
            ),
            Job(
                title="Sales Manager",
                company="Acme",
                location="Austin, TX",
                url="https://boards.greenhouse.io/acme/2",
                source="greenhouse",
                remote_type="remote",
                posted_date=date.today(),
            ),
        ],
    )

    report_path = run_pipeline(_config(tmp_path))

    content = report_path.read_text()
    assert "Backend Engineer" in content
    assert "Sales Manager" not in content
    assert "Possible referrals: Jane Doe (Engineer)" in content
