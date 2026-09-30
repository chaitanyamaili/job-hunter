import pytest
import responses

from job_hunter.interview_prep.extractor import InterviewPrepError, fetch_job_posting

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Senior Backend Engineer",
  "description": "<p>Build <b>scalable</b> systems.</p>",
  "hiringOrganization": {"name": "Acme Corp"}
}
</script>
</head><body></body></html>
"""

HEURISTIC_HTML = """
<html><head><title>Backend Role at Acme</title></head>
<body>
<nav>Home</nav>
<main><h1>Backend Role</h1><p>We build scalable systems.</p></main>
</body></html>
"""


@responses.activate
def test_fetch_job_posting_prefers_json_ld():
    responses.add(responses.GET, "https://example.com/job/1", body=JSON_LD_HTML, status=200)

    posting = fetch_job_posting("https://example.com/job/1")

    assert posting.title == "Senior Backend Engineer"
    assert posting.company == "Acme Corp"
    assert "Build scalable systems." in posting.description_text
    assert "<b>" not in posting.description_text
    assert posting.url == "https://example.com/job/1"


@responses.activate
def test_fetch_job_posting_falls_back_to_heuristic():
    responses.add(responses.GET, "https://example.com/job/2", body=HEURISTIC_HTML, status=200)

    posting = fetch_job_posting("https://example.com/job/2")

    assert posting.title == "Backend Role at Acme"
    assert posting.company == ""
    assert "We build scalable systems." in posting.description_text
    assert "Home" not in posting.description_text


@responses.activate
def test_fetch_job_posting_raises_on_error_status():
    responses.add(responses.GET, "https://example.com/job/3", status=403)

    with pytest.raises(InterviewPrepError, match="403"):
        fetch_job_posting("https://example.com/job/3")
