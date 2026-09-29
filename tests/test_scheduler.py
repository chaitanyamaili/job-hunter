from unittest.mock import patch

from job_hunter.scheduler import _interval_to_seconds


def test_interval_to_seconds_parses_units():
    assert _interval_to_seconds("30s") == 30
    assert _interval_to_seconds("5m") == 300
    assert _interval_to_seconds("6h") == 21600
    assert _interval_to_seconds("1d") == 86400


@patch("job_hunter.scheduler.run_once")
@patch("job_hunter.scheduler.schedule_lib")
@patch("job_hunter.scheduler.time")
def test_run_daemon_continues_after_a_failed_run(mock_time, mock_schedule_lib, mock_run_once):
    from job_hunter.scheduler import run_daemon

    mock_run_once.side_effect = [RuntimeError("boom"), "reports/ok.md"]
    mock_time.sleep.side_effect = KeyboardInterrupt

    captured = {}

    def fake_do(fn):
        captured["job"] = fn

    mock_schedule_lib.every.return_value.seconds.do.side_effect = fake_do

    try:
        run_daemon("config.yaml", "1h")
    except KeyboardInterrupt:
        pass

    assert mock_run_once.call_count == 1
