import pytest
import responses

from job_hunter.interview_prep.extractor import InterviewPrepError
from job_hunter.interview_prep.resume import load_resume


def test_load_resume_from_local_file(tmp_path):
    resume_path = tmp_path / "my_resume.md"
    resume_path.write_text("# Jane Doe\nSenior Engineer")

    text = load_resume(str(resume_path))

    assert "Jane Doe" in text


def test_load_resume_missing_explicit_path_raises(tmp_path):
    missing = tmp_path / "missing.md"

    with pytest.raises(InterviewPrepError, match="not found"):
        load_resume(str(missing))


def test_load_resume_default_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert load_resume(None) is None


@responses.activate
def test_load_resume_from_url():
    responses.add(
        responses.GET,
        "https://example.com/resume",
        body="<html><body><nav>Menu</nav><main><h1>Jane Doe</h1><p>Senior Engineer</p></main></body></html>",
        status=200,
    )

    text = load_resume("https://example.com/resume")

    assert "Jane Doe" in text
    assert "Menu" not in text


@responses.activate
def test_load_resume_from_url_follows_redirect():
    responses.add(
        responses.GET,
        "http://example.com/resume",
        status=301,
        headers={"Location": "https://example.com/resume"},
    )
    responses.add(
        responses.GET,
        "https://example.com/resume",
        body="<html><body><main><h1>Jane Doe</h1></main></body></html>",
        status=200,
    )

    text = load_resume("http://example.com/resume")

    assert "Jane Doe" in text


@responses.activate
def test_load_resume_url_failure_raises():
    responses.add(responses.GET, "https://example.com/resume", status=404)

    with pytest.raises(InterviewPrepError, match="404"):
        load_resume("https://example.com/resume")
