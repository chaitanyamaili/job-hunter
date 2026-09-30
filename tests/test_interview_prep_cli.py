from unittest.mock import patch

from interview_prep import main
from job_hunter.interview_prep.extractor import JobPosting
from job_hunter.referrals import Connection


def _posting(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme Corp",
        description_text="Build scalable systems.",
        url="https://example.com/job/1",
    )
    defaults.update(overrides)
    return JobPosting(**defaults)


@patch("interview_prep.run_agent")
@patch("interview_prep.load_connections")
@patch("interview_prep.load_resume")
@patch("interview_prep.fetch_job_posting")
def test_cli_writes_report_with_full_enrichment(
    mock_fetch, mock_load_resume, mock_load_connections, mock_run_agent, tmp_path
):
    mock_fetch.return_value = _posting()
    mock_load_resume.return_value = "5 years of backend experience."
    mock_load_connections.return_value = [
        Connection(name="Jane Smith", company="Acme, Inc.", title="Staff Engineer")
    ]
    mock_run_agent.return_value = "Great prep content."

    connections_path = tmp_path / "connections.csv"
    connections_path.write_text("name,company,title\n")
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "https://example.com/job/1",
            "--agent",
            "claude",
            "--connections-csv",
            str(connections_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    files = list(output_dir.glob("*_interview_prep.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Backend Engineer" in content
    assert "Jane Smith" in content
    assert "Great prep content." in content


@patch("interview_prep.fetch_job_posting")
def test_cli_writes_prompt_only_report_with_no_enrichment(mock_fetch, tmp_path, monkeypatch):
    mock_fetch.return_value = _posting(company="")
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "https://example.com/job/1",
            "--connections-csv",
            str(tmp_path / "missing_connections.csv"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    files = list(output_dir.glob("*_interview_prep.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Backend Engineer" in content
    assert "no agent requested" in content
