import requests
import responses

from job_hunter.connectors.base import ConnectorError, get_with_retry


@responses.activate
def test_get_with_retry_returns_response_on_success():
    responses.add(responses.GET, "https://example.com/ok", json={"a": 1}, status=200)

    response = get_with_retry("https://example.com/ok")

    assert response.status_code == 200


@responses.activate
def test_get_with_retry_retries_once_on_500_then_succeeds(monkeypatch):
    monkeypatch.setattr("job_hunter.connectors.base.time.sleep", lambda _: None)
    responses.add(responses.GET, "https://example.com/flaky", status=500)
    responses.add(responses.GET, "https://example.com/flaky", json={"a": 1}, status=200)

    response = get_with_retry("https://example.com/flaky")

    assert response.status_code == 200


@responses.activate
def test_get_with_retry_does_not_retry_on_404(monkeypatch):
    monkeypatch.setattr("job_hunter.connectors.base.time.sleep", lambda _: None)
    responses.add(responses.GET, "https://example.com/missing", status=404)

    response = get_with_retry("https://example.com/missing")

    assert response.status_code == 404
    assert len(responses.calls) == 1


@responses.activate
def test_get_with_retry_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("job_hunter.connectors.base.time.sleep", lambda _: None)
    responses.add(responses.GET, "https://example.com/down", body=requests.ConnectionError("boom"))
    responses.add(responses.GET, "https://example.com/down", body=requests.ConnectionError("boom"))

    try:
        get_with_retry("https://example.com/down")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass
