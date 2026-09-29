import responses

from job_hunter.connectors.base import ConnectorError
from job_hunter.connectors.generic_crawler import fetch_generic

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@type": "JobPosting",
  "title": "Platform Engineer",
  "url": "https://niche.co/careers/platform-engineer",
  "datePosted": "2026-09-22",
  "jobLocationType": "TELECOMMUTE",
  "description": "Own our platform.",
  "jobLocation": {"address": {"addressLocality": "Remote"}}
}
</script>
</head><body></body></html>
"""

HEURISTIC_HTML = """
<html><body>
<a href="/careers/data-engineer">Data Engineer</a>
<a href="/about">About us</a>
</body></html>
"""

EMPTY_HTML = "<html><body><p>No structured content here.</p></body></html>"


@responses.activate
def test_fetch_generic_prefers_json_ld():
    responses.add(responses.GET, "https://niche.co/careers", body=JSON_LD_HTML, status=200)

    jobs = fetch_generic("https://niche.co/careers", "NicheCo")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Platform Engineer"
    assert job.remote_type == "remote"
    assert job.posted_date.isoformat() == "2026-09-22"
    assert job.location == "Remote"
    assert job.source == "generic"


@responses.activate
def test_fetch_generic_falls_back_to_heuristic():
    responses.add(responses.GET, "https://niche.co/careers", body=HEURISTIC_HTML, status=200)

    jobs = fetch_generic("https://niche.co/careers", "NicheCo")

    assert len(jobs) == 1
    assert jobs[0].title == "Data Engineer"
    assert jobs[0].url == "https://niche.co/careers/data-engineer"


@responses.activate
def test_fetch_generic_returns_empty_when_no_matches():
    responses.add(responses.GET, "https://niche.co/careers", body=EMPTY_HTML, status=200)

    jobs = fetch_generic("https://niche.co/careers", "NicheCo")

    assert jobs == []


@responses.activate
def test_fetch_generic_raises_on_error_status():
    responses.add(responses.GET, "https://niche.co/careers", status=500)
    responses.add(responses.GET, "https://niche.co/careers", status=500)

    try:
        fetch_generic("https://niche.co/careers", "NicheCo")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass
