import responses

from job_hunter.connectors.base import ConnectorError
from job_hunter.connectors.lever import fetch_lever

FIXTURE = [
    {
        "text": "Frontend Engineer",
        "categories": {"location": "Remote - US"},
        "workplaceType": "remote",
        "hostedUrl": "https://jobs.lever.co/acme/1",
        "createdAt": 1758326400000,
        "descriptionPlain": "Build delightful UIs.",
    }
]


@responses.activate
def test_fetch_lever_returns_normalized_jobs():
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/acme?mode=json",
        json=FIXTURE,
        status=200,
    )

    jobs = fetch_lever("acme", "Acme")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Frontend Engineer"
    assert job.location == "Remote - US"
    assert job.remote_type == "remote"
    assert job.url == "https://jobs.lever.co/acme/1"
    assert job.source == "lever"
    assert "delightful UIs" in job.description_snippet


@responses.activate
def test_fetch_lever_raises_on_404():
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/nope?mode=json",
        status=404,
    )

    try:
        fetch_lever("nope", "Nope Inc")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass


@responses.activate
def test_fetch_lever_raises_on_unexpected_shape():
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/acme?mode=json",
        json={"unexpected": "shape"},
        status=200,
    )

    try:
        fetch_lever("acme", "Acme")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass
