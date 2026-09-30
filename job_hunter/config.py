from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_INTERVAL_RE = re.compile(r"^(\d+)(s|m|h|d)$")
_VALID_WORKPLACE_TYPES = {"remote", "hybrid", "onsite"}


class ConfigError(Exception):
    """Raised when config.yaml is missing required fields or malformed."""


@dataclass
class CompanyConfig:
    name: str
    ats: str | None = None
    board_token: str | None = None
    careers_url: str | None = None


@dataclass
class FilterConfig:
    designations: list[str]
    locations: list[str]
    workplace_types: list[str]
    posted_within_days: int
    exclude_keywords: list[str] = field(default_factory=list)


@dataclass
class ScheduleConfig:
    interval: str = "6h"


@dataclass
class Config:
    companies: list[CompanyConfig]
    filters: FilterConfig
    connections_csv: str
    output_dir: str
    schedule: ScheduleConfig


def _require(data: dict, key: str, context: str):
    value = data.get(key)
    if value in (None, "", []):
        raise ConfigError(f"config.yaml: missing required field '{key}' in {context}")
    return value


def validate_interval(interval: str) -> None:
    match = _INTERVAL_RE.match(interval.strip())
    if not match or int(match.group(1)) <= 0:
        raise ConfigError(
            f"config.yaml: schedule.interval '{interval}' is invalid; "
            "expected a positive number followed by s/m/h/d, e.g. '6h'"
        )


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        raw_text = path.read_text()
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("config.yaml must be a mapping at the top level")

    companies_raw = _require(data, "companies", "config.yaml")
    companies = []
    for entry in companies_raw:
        if not isinstance(entry, dict):
            raise ConfigError(
                f"config.yaml: each companies entry must be a mapping with a 'name' "
                f"field, got {entry!r}"
            )
        name = _require(entry, "name", "a companies entry")
        companies.append(
            CompanyConfig(
                name=name,
                ats=entry.get("ats"),
                board_token=entry.get("board_token"),
                careers_url=entry.get("careers_url"),
            )
        )

    filters_raw = _require(data, "filters", "config.yaml")
    designations = _require(filters_raw, "designations", "filters")
    locations = _require(filters_raw, "locations", "filters")
    workplace_types = list(filters_raw.get("workplace_types", ["remote", "hybrid", "onsite"]))
    for workplace_type in workplace_types:
        if workplace_type not in _VALID_WORKPLACE_TYPES:
            raise ConfigError(
                f"config.yaml: filters.workplace_types contains invalid value "
                f"'{workplace_type}'; expected one of {sorted(_VALID_WORKPLACE_TYPES)}"
            )
    posted_within_days = _require(filters_raw, "posted_within_days", "filters")
    try:
        posted_within_days = int(posted_within_days)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"config.yaml: filters.posted_within_days must be a whole number, "
            f"got {posted_within_days!r}"
        ) from exc
    exclude_keywords = list(filters_raw.get("exclude_keywords", []))

    filters = FilterConfig(
        designations=list(designations),
        locations=list(locations),
        workplace_types=workplace_types,
        posted_within_days=posted_within_days,
        exclude_keywords=exclude_keywords,
    )

    connections_csv = _require(data, "connections_csv", "config.yaml")
    if not Path(connections_csv).exists():
        raise ConfigError(f"config.yaml: connections_csv not found: {connections_csv}")
    output_dir = _require(data, "output_dir", "config.yaml")

    schedule_raw = data.get("schedule", {})
    interval = schedule_raw.get("interval", "6h")
    validate_interval(interval)

    return Config(
        companies=companies,
        filters=filters,
        connections_csv=connections_csv,
        output_dir=output_dir,
        schedule=ScheduleConfig(interval=interval),
    )
