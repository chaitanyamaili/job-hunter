from unittest.mock import MagicMock, patch

import pytest

from job_hunter.interview_prep.agents import AgentError, run_agent


@patch("subprocess.run")
def test_run_agent_returns_stripped_stdout(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Here is your prep.\n", stderr="")

    result = run_agent("claude", "some prompt")

    assert result == "Here is your prep."
    mock_run.assert_called_once_with(
        ["claude", "-p", "some prompt"], capture_output=True, text=True
    )


def test_run_agent_unknown_name_raises():
    with pytest.raises(AgentError, match="unknown agent"):
        run_agent("codex", "some prompt")


def test_run_agent_case_sensitive_name_raises():
    with pytest.raises(AgentError, match="unknown agent"):
        run_agent("Claude", "some prompt")


@patch("subprocess.run", side_effect=FileNotFoundError())
def test_run_agent_binary_not_found_raises(mock_run):
    with pytest.raises(AgentError, match="not found on PATH"):
        run_agent("claude", "some prompt")


@patch("subprocess.run")
def test_run_agent_nonzero_exit_raises(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

    with pytest.raises(AgentError, match="boom"):
        run_agent("gemini", "some prompt")
