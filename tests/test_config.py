import pytest

from job_hunter.config import ConfigError, load_config, validate_interval

VALID_YAML = """
companies:
  - name: Stripe
  - name: SomeStartup
    ats: greenhouse
    board_token: some-startup
  - name: NicheCo
    careers_url: https://niche.co/careers
filters:
  designations:
    - "Software Engineer"
  locations:
    - "Austin"
  workplace_types:
    - remote
  posted_within_days: 14
  exclude_keywords:
    - "Clearance required"
connections_csv: ./connections.csv
output_dir: ./reports
schedule:
  interval: 6h
"""


def test_load_valid_config(tmp_path):
    (tmp_path / "connections.csv").write_text("name,company,title\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace(
        "connections_csv: ./connections.csv",
        f"connections_csv: {tmp_path / 'connections.csv'}",
    ))

    config = load_config(config_path)

    assert [c.name for c in config.companies] == ["Stripe", "SomeStartup", "NicheCo"]
    assert config.companies[1].ats == "greenhouse"
    assert config.companies[1].board_token == "some-startup"
    assert config.companies[2].careers_url == "https://niche.co/careers"
    assert config.filters.designations == ["Software Engineer"]
    assert config.filters.posted_within_days == 14
    assert config.schedule.interval == "6h"


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_malformed_yaml_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("companies: [unclosed")

    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(config_path)


def test_empty_companies_list_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace(
        "companies:\n  - name: Stripe\n  - name: SomeStartup\n    ats: greenhouse\n    board_token: some-startup\n  - name: NicheCo\n    careers_url: https://niche.co/careers\n",
        "companies: []\n",
    ))

    with pytest.raises(ConfigError, match="companies"):
        load_config(config_path)


def test_empty_designations_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace('    - "Software Engineer"\n', ""))

    with pytest.raises(ConfigError, match="designations"):
        load_config(config_path)


def test_invalid_workplace_type_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace("- remote", "- teleport"))

    with pytest.raises(ConfigError, match="workplace_types"):
        load_config(config_path)


def test_bad_interval_raises(tmp_path):
    (tmp_path / "connections.csv").write_text("name,company,title\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        VALID_YAML.replace("interval: 6h", "interval: soon").replace(
            "connections_csv: ./connections.csv",
            f"connections_csv: {tmp_path / 'connections.csv'}",
        )
    )

    with pytest.raises(ConfigError, match="interval"):
        load_config(config_path)


def test_validate_interval_rejects_zero():
    with pytest.raises(ConfigError):
        validate_interval("0h")


def test_missing_connections_csv_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace(
        "connections_csv: ./connections.csv",
        f"connections_csv: {tmp_path / 'missing_connections.csv'}",
    ))

    with pytest.raises(ConfigError, match="connections_csv"):
        load_config(config_path)


def test_company_entry_not_a_mapping_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace("  - name: Stripe\n", "  - Stripe\n"))

    with pytest.raises(ConfigError, match="companies"):
        load_config(config_path)


def test_non_numeric_posted_within_days_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace("posted_within_days: 14", "posted_within_days: two weeks"))

    with pytest.raises(ConfigError, match="posted_within_days"):
        load_config(config_path)
