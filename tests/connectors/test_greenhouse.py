import responses

from job_hunter.connectors.base import ConnectorError
from job_hunter.connectors.greenhouse import fetch_greenhouse

FIXTURE = {
    "jobs": [
        {
            "title": "Backend Engineer",
            "location": {"name": "Austin, TX"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "updated_at": "2026-09-20T10:00:00-00:00",
            "content": "<p>Join our backend team.</p>",
        }
    ]
}


@responses.activate
def test_fetch_greenhouse_returns_normalized_jobs():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        json=FIXTURE,
        status=200,
    )

    jobs = fetch_greenhouse("acme", "Acme")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"
    assert job.location == "Austin, TX"
    assert job.url == "https://boards.greenhouse.io/acme/jobs/1"
    assert job.source == "greenhouse"
    assert job.posted_date.isoformat() == "2026-09-20"
    assert "backend team" in job.description_snippet


@responses.activate
def test_fetch_greenhouse_raises_on_404():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/nope/jobs?content=true",
        status=404,
    )

    try:
        fetch_greenhouse("nope", "Nope Inc")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass


@responses.activate
def test_fetch_greenhouse_raises_on_invalid_json():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        body="not json",
        status=200,
    )

    try:
        fetch_greenhouse("acme", "Acme")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass
