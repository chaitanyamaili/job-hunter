from unittest.mock import patch

from job_hunter.config import CompanyConfig
from job_hunter.connectors.autodetect import fetch_for_company, slugify
from job_hunter.connectors.base import ConnectorError, Job


def _job(source):
    return Job(title="T", company="C", location="L", url="u", source=source)


def test_slugify_basic():
    assert slugify("Some Startup") == "some-startup"
    assert slugify("Acme, Inc.") == "acme-inc"


@patch("job_hunter.connectors.autodetect.fetch_greenhouse")
def test_autodetect_uses_greenhouse_when_it_matches(mock_greenhouse):
    mock_greenhouse.return_value = [_job("greenhouse")]

    result = fetch_for_company(CompanyConfig(name="Acme"))

    assert result.source == "greenhouse"
    assert result.jobs == [_job("greenhouse")]
    assert not result.unmatched
    mock_greenhouse.assert_called_once_with("acme", "Acme")


@patch("job_hunter.connectors.autodetect.fetch_lever")
@patch("job_hunter.connectors.autodetect.fetch_greenhouse")
def test_autodetect_falls_back_to_lever(mock_greenhouse, mock_lever):
    mock_greenhouse.side_effect = ConnectorError("not found")
    mock_lever.return_value = [_job("lever")]

    result = fetch_for_company(CompanyConfig(name="Acme"))

    assert result.source == "lever"
    assert not result.unmatched


@patch("job_hunter.connectors.autodetect.fetch_generic")
@patch("job_hunter.connectors.autodetect.fetch_lever")
@patch("job_hunter.connectors.autodetect.fetch_greenhouse")
def test_autodetect_falls_back_to_generic_crawler(mock_greenhouse, mock_lever, mock_generic):
    mock_greenhouse.side_effect = ConnectorError("not found")
    mock_lever.side_effect = ConnectorError("not found")
    mock_generic.return_value = [_job("generic")]

    result = fetch_for_company(
        CompanyConfig(name="NicheCo", careers_url="https://niche.co/careers")
    )

    assert result.source == "generic"
    mock_generic.assert_called_once_with("https://niche.co/careers", "NicheCo")


@patch("job_hunter.connectors.autodetect.fetch_generic")
@patch("job_hunter.connectors.autodetect.fetch_lever")
@patch("job_hunter.connectors.autodetect.fetch_greenhouse")
def test_autodetect_reports_no_jobs_found_note(mock_greenhouse, mock_lever, mock_generic):
    mock_greenhouse.side_effect = ConnectorError("not found")
    mock_lever.side_effect = ConnectorError("not found")
    mock_generic.return_value = []

    result = fetch_for_company(
        CompanyConfig(name="NicheCo", careers_url="https://niche.co/careers")
    )

    assert result.jobs == []
    assert "no jobs found" in result.note


@patch("job_hunter.connectors.autodetect.fetch_lever")
@patch("job_hunter.connectors.autodetect.fetch_greenhouse")
def test_autodetect_flags_unmatched_with_hint(mock_greenhouse, mock_lever):
    mock_greenhouse.side_effect = ConnectorError("not found")
    mock_lever.side_effect = ConnectorError("not found")

    result = fetch_for_company(CompanyConfig(name="Acme"))

    assert result.unmatched
    assert result.hint_slug == "acme"
    assert "boards.greenhouse.io/acme" in result.note
    assert "jobs.lever.co/acme" in result.note


@patch("job_hunter.connectors.autodetect.fetch_greenhouse")
def test_explicit_override_does_not_fall_back_to_autodetect(mock_greenhouse):
    mock_greenhouse.side_effect = ConnectorError("greenhouse board 'wrong-token' not found")

    result = fetch_for_company(
        CompanyConfig(name="Acme", ats="greenhouse", board_token="wrong-token")
    )

    assert result.unmatched
    assert "wrong-token" in result.note
    mock_greenhouse.assert_called_once_with("wrong-token", "Acme")
