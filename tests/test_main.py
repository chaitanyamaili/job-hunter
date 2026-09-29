from unittest.mock import patch

from main import main


@patch("main.run_once")
def test_main_once_mode_prints_report_path(mock_run_once, capsys):
    mock_run_once.return_value = "reports/2026-09-29_0800_job_matches.md"

    main(["--config", "config.yaml", "--once"])

    captured = capsys.readouterr()
    assert "reports/2026-09-29_0800_job_matches.md" in captured.out


@patch("main.load_config")
def test_main_validate_config_reports_success(mock_load_config, capsys):
    main(["--config", "config.yaml", "--validate-config"])

    captured = capsys.readouterr()
    assert "Config OK" in captured.out


@patch("main.load_config")
def test_main_validate_config_reports_failure(mock_load_config, capsys):
    from job_hunter.config import ConfigError

    mock_load_config.side_effect = ConfigError("missing field 'companies'")

    exit_code = main(["--config", "config.yaml", "--validate-config"])

    captured = capsys.readouterr()
    assert "missing field 'companies'" in captured.out
    assert exit_code == 1
