# Job Hunter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python tool that fetches open roles from configured companies (Greenhouse, Lever, or a generic careers-page crawler), filters them by designation/location/workplace-type/recency/keyword, cross-references matches against the user's own connections for possible referrals, and writes a Markdown report — runnable once or on a self-managed schedule.

**Architecture:** A layered pipeline — config loading/validation → per-company connector fetch (Greenhouse/Lever auto-detected by slug, generic crawler as an explicit fallback) → filtering → referral matching → Markdown report — orchestrated by `pipeline.py` and exposed via a CLI (`main.py`) that supports `--once`, `--daemon`, and `--validate-config`.

**Tech Stack:** Python 3.11+, `requests` (HTTP), `PyYAML` (config), `beautifulsoup4` (HTML/JSON-LD parsing), `schedule` (in-process scheduling), `pytest` + `responses` (testing).

**Spec:** `docs/superpowers/specs/2026-09-29-job-hunter-design.md`

## Global Constraints

- No LinkedIn scraping or automated LinkedIn data import — referral matching only ever reads the user-maintained `connections.csv`.
- Job sourcing is limited to Greenhouse, Lever, and the generic crawler against a user-supplied `careers_url` — no auto-discovery of career page URLs, no other ATS platforms in v1.
- Scheduling is implemented inside the Python process via the `schedule` library — never cron/launchd/Task Scheduler.
- Transient HTTP errors (timeouts, 5xx) get exactly one retry with a ~2s backoff; 4xx errors are never retried.
- Config is validated in full before any network call is made, on every run (including every scheduled run in `--daemon` mode), so an edited `config.yaml` is always re-checked before the next fetch happens.
- Workplace-type and posted-date filters default to **include** when the underlying data is unknown; keyword exclusion is a hard drop regardless of ambiguity.
- Report output is a single timestamped Markdown file per run (no email/Slack delivery in v1).

## Review Focus

- Company config gives an explicit but wrong `ats`/`board_token` override (e.g. typo) — expected: the fetch fails and is reported as unmatched with the underlying error, and auto-detect is never silently attempted as a fallback.
- `connections_csv` path points to a file that doesn't exist — expected: a clear error at startup, not an unhandled traceback mid-run.
- The same job posting is reachable through two paths (e.g. duplicate URL across two company entries or connector attempts) — expected: it appears once in the report, not twice.
- `output_dir` doesn't exist yet on first run — expected: it's created automatically rather than crashing on file write.
- Required config lists (`companies`, `filters.designations`, `filters.locations`) are present but empty — expected: fails validation with a clear message rather than silently matching nothing on every run.

---

### Task 1: Config loader and validation

**Files:**
- Create: `requirements.txt`
- Create: `job_hunter/__init__.py`
- Create: `job_hunter/config.py`
- Create: `config.example.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `ConfigError(Exception)`; `CompanyConfig(name: str, ats: str | None, board_token: str | None, careers_url: str | None)`; `FilterConfig(designations: list[str], locations: list[str], workplace_types: list[str], posted_within_days: int, exclude_keywords: list[str])`; `ScheduleConfig(interval: str)`; `Config(companies: list[CompanyConfig], filters: FilterConfig, connections_csv: str, output_dir: str, schedule: ScheduleConfig)`; `load_config(path: str | Path) -> Config`; `validate_interval(interval: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
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
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML)

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
    config_path = tmp_path / "config.yaml"
    config_path.write_text(VALID_YAML.replace("interval: 6h", "interval: soon"))

    with pytest.raises(ConfigError, match="interval"):
        load_config(config_path)


def test_validate_interval_rejects_zero():
    with pytest.raises(ConfigError):
        validate_interval("0h")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter'`

- [ ] **Step 3: Write `requirements.txt`**

```
PyYAML==6.0.2
requests==2.32.3
schedule==1.2.2
beautifulsoup4==4.12.3
pytest==8.3.3
responses==0.25.3
```

- [ ] **Step 4: Create the package init**

```python
# job_hunter/__init__.py
```

- [ ] **Step 5: Implement `job_hunter/config.py`**

```python
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
    exclude_keywords = list(filters_raw.get("exclude_keywords", []))

    filters = FilterConfig(
        designations=list(designations),
        locations=list(locations),
        workplace_types=workplace_types,
        posted_within_days=int(posted_within_days),
        exclude_keywords=exclude_keywords,
    )

    connections_csv = _require(data, "connections_csv", "config.yaml")
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
```

- [ ] **Step 6: Create `config.example.yaml`**

```yaml
companies:
  - name: Stripe
  - name: Airbnb
  - name: SomeStartup
    ats: greenhouse
    board_token: some-startup
  - name: NicheCo
    careers_url: https://niche.co/careers

filters:
  designations:
    - "Software Engineer"
    - "Backend"
  locations:
    - "Austin"
    - "Remote"
  workplace_types:
    - remote
    - hybrid
  posted_within_days: 14
  exclude_keywords:
    - "Clearance required"
    - "Staff"

connections_csv: ./connections.csv

output_dir: ./reports

schedule:
  interval: 6h
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pip install -r requirements.txt && pytest tests/test_config.py -v`
Expected: PASS (8 tests)

- [ ] **Step 8: Commit**

```bash
git add requirements.txt job_hunter/__init__.py job_hunter/config.py config.example.yaml tests/test_config.py
git commit -m "feat: add config loader with fail-fast validation"
```

---

### Task 2: Shared Job model, retry helper, and Greenhouse connector

**Files:**
- Create: `job_hunter/connectors/__init__.py`
- Create: `job_hunter/connectors/base.py`
- Create: `job_hunter/connectors/greenhouse.py`
- Test: `tests/connectors/test_base.py`
- Test: `tests/connectors/test_greenhouse.py`

**Interfaces:**
- Consumes: nothing (first connector task).
- Produces: `Job(title: str, company: str, location: str, url: str, source: str, remote_type: str | None, posted_date: date | None, description_snippet: str)`; `ConnectorError(Exception)`; `get_with_retry(url: str, timeout: int = 10, retries: int = 1, backoff_seconds: float = 2) -> requests.Response`; `fetch_greenhouse(board_token: str, company_name: str) -> list[Job]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/connectors/test_base.py
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
```

```python
# tests/connectors/test_greenhouse.py
import responses

from job_hunter.connectors.base import ConnectorError
from job_hunter.connectors.greenhouse import fetch_greenhouse

FIXTURE = {
    "jobs": [
        {
            "title": "Backend Engineer",
            "location": {"name": "Austin, TX"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "updated_at": "2026-09-20T10:00:00-00:00",
            "content": "<p>Join our backend team.</p>",
        }
    ]
}


@responses.activate
def test_fetch_greenhouse_returns_normalized_jobs():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        json=FIXTURE,
        status=200,
    )

    jobs = fetch_greenhouse("acme", "Acme")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"
    assert job.location == "Austin, TX"
    assert job.url == "https://boards.greenhouse.io/acme/jobs/1"
    assert job.source == "greenhouse"
    assert job.posted_date.isoformat() == "2026-09-20"
    assert "backend team" in job.description_snippet


@responses.activate
def test_fetch_greenhouse_raises_on_404():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/nope/jobs?content=true",
        status=404,
    )

    try:
        fetch_greenhouse("nope", "Nope Inc")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass


@responses.activate
def test_fetch_greenhouse_raises_on_invalid_json():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        body="not json",
        status=200,
    )

    try:
        fetch_greenhouse("acme", "Acme")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/connectors/ -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter.connectors'`

- [ ] **Step 3: Implement `job_hunter/connectors/__init__.py`**

```python
# job_hunter/connectors/__init__.py
```

- [ ] **Step 4: Implement `job_hunter/connectors/base.py`**

```python
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import requests


class ConnectorError(Exception):
    """Raised when a connector cannot fetch or parse job postings."""


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    remote_type: str | None = None
    posted_date: date | None = None
    description_snippet: str = ""


def get_with_retry(
    url: str,
    timeout: int = 10,
    retries: int = 1,
    backoff_seconds: float = 2,
) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff_seconds)
                continue
            raise ConnectorError(f"request to {url} failed: {exc}") from exc

        if response.status_code >= 500 and attempt < retries:
            time.sleep(backoff_seconds)
            continue
        return response

    raise ConnectorError(f"request to {url} failed: {last_exc}")
```

- [ ] **Step 5: Implement `job_hunter/connectors/greenhouse.py`**

```python
from __future__ import annotations

from datetime import date, datetime

from .base import ConnectorError, Job, get_with_retry

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def fetch_greenhouse(board_token: str, company_name: str) -> list[Job]:
    url = GREENHOUSE_URL.format(token=board_token)
    response = get_with_retry(url)

    if response.status_code == 404:
        raise ConnectorError(f"greenhouse board '{board_token}' not found")
    if response.status_code >= 400:
        raise ConnectorError(
            f"greenhouse request for '{board_token}' failed with status {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ConnectorError(f"greenhouse response for '{board_token}' was not valid JSON") from exc

    jobs = []
    for entry in payload.get("jobs", []):
        jobs.append(
            Job(
                title=entry.get("title", ""),
                company=company_name,
                location=(entry.get("location") or {}).get("name", ""),
                url=entry.get("absolute_url", ""),
                source="greenhouse",
                remote_type=None,
                posted_date=_parse_date(entry.get("updated_at")),
                description_snippet=(entry.get("content") or "")[:280],
            )
        )
    return jobs


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/connectors/ -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Commit**

```bash
git add job_hunter/connectors/__init__.py job_hunter/connectors/base.py job_hunter/connectors/greenhouse.py tests/connectors/test_base.py tests/connectors/test_greenhouse.py
git commit -m "feat: add shared Job model, retry helper, and Greenhouse connector"
```

---

### Task 3: Lever connector

**Files:**
- Create: `job_hunter/connectors/lever.py`
- Test: `tests/connectors/test_lever.py`

**Interfaces:**
- Consumes: `Job`, `ConnectorError`, `get_with_retry` from `job_hunter.connectors.base`.
- Produces: `fetch_lever(board_token: str, company_name: str) -> list[Job]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/connectors/test_lever.py
import responses

from job_hunter.connectors.base import ConnectorError
from job_hunter.connectors.lever import fetch_lever

FIXTURE = [
    {
        "text": "Frontend Engineer",
        "categories": {"location": "Remote - US"},
        "workplaceType": "remote",
        "hostedUrl": "https://jobs.lever.co/acme/1",
        "createdAt": 1758326400000,
        "descriptionPlain": "Build delightful UIs.",
    }
]


@responses.activate
def test_fetch_lever_returns_normalized_jobs():
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/acme?mode=json",
        json=FIXTURE,
        status=200,
    )

    jobs = fetch_lever("acme", "Acme")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Frontend Engineer"
    assert job.location == "Remote - US"
    assert job.remote_type == "remote"
    assert job.url == "https://jobs.lever.co/acme/1"
    assert job.source == "lever"
    assert "delightful UIs" in job.description_snippet


@responses.activate
def test_fetch_lever_raises_on_404():
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/nope?mode=json",
        status=404,
    )

    try:
        fetch_lever("nope", "Nope Inc")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass


@responses.activate
def test_fetch_lever_raises_on_unexpected_shape():
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/acme?mode=json",
        json={"unexpected": "shape"},
        status=200,
    )

    try:
        fetch_lever("acme", "Acme")
        assert False, "expected ConnectorError"
    except ConnectorError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/connectors/test_lever.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter.connectors.lever'`

- [ ] **Step 3: Implement `job_hunter/connectors/lever.py`**

```python
from __future__ import annotations

from datetime import date, datetime

from .base import ConnectorError, Job, get_with_retry

LEVER_URL = "https://api.lever.co/v0/postings/{token}?mode=json"

_WORKPLACE_TYPE_MAP = {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite", "onsite": "onsite"}


def fetch_lever(board_token: str, company_name: str) -> list[Job]:
    url = LEVER_URL.format(token=board_token)
    response = get_with_retry(url)

    if response.status_code == 404:
        raise ConnectorError(f"lever board '{board_token}' not found")
    if response.status_code >= 400:
        raise ConnectorError(
            f"lever request for '{board_token}' failed with status {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ConnectorError(f"lever response for '{board_token}' was not valid JSON") from exc

    if not isinstance(payload, list):
        raise ConnectorError(f"lever response for '{board_token}' had unexpected shape")

    jobs = []
    for entry in payload:
        categories = entry.get("categories") or {}
        jobs.append(
            Job(
                title=entry.get("text", ""),
                company=company_name,
                location=categories.get("location", ""),
                url=entry.get("hostedUrl", ""),
                source="lever",
                remote_type=_WORKPLACE_TYPE_MAP.get((entry.get("workplaceType") or "").lower()),
                posted_date=_parse_created_at(entry.get("createdAt")),
                description_snippet=(entry.get("descriptionPlain") or "")[:280],
            )
        )
    return jobs


def _parse_created_at(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000).date()
    except (ValueError, OSError, OverflowError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/connectors/test_lever.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/connectors/lever.py tests/connectors/test_lever.py
git commit -m "feat: add Lever connector"
```

---

### Task 4: Generic crawler (JSON-LD + heuristic fallback)

**Files:**
- Create: `job_hunter/connectors/generic_crawler.py`
- Test: `tests/connectors/test_generic_crawler.py`

**Interfaces:**
- Consumes: `Job`, `ConnectorError`, `get_with_retry` from `job_hunter.connectors.base`.
- Produces: `fetch_generic(careers_url: str, company_name: str) -> list[Job]` (returns `[]` when the page has neither JSON-LD nor heuristic matches — caller decides how to report that).

- [ ] **Step 1: Write the failing tests**

```python
# tests/connectors/test_generic_crawler.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/connectors/test_generic_crawler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter.connectors.generic_crawler'`

- [ ] **Step 3: Implement `job_hunter/connectors/generic_crawler.py`**

```python
from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import ConnectorError, Job, get_with_retry

_JOB_LINK_RE = re.compile(r"(job|career|position|opening)", re.IGNORECASE)


def fetch_generic(careers_url: str, company_name: str) -> list[Job]:
    response = get_with_retry(careers_url)

    if response.status_code >= 400:
        raise ConnectorError(
            f"generic crawler request for '{careers_url}' failed with status {response.status_code}"
        )

    soup = BeautifulSoup(response.text, "html.parser")

    jobs = _extract_json_ld_jobs(soup, company_name, careers_url)
    if jobs:
        return jobs

    return _extract_heuristic_jobs(soup, company_name, careers_url)


def _extract_json_ld_jobs(soup: BeautifulSoup, company_name: str, base_url: str) -> list[Job]:
    jobs = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("@type") != "JobPosting":
                continue
            location = ""
            job_location = entry.get("jobLocation")
            if isinstance(job_location, dict):
                address = job_location.get("address")
                if isinstance(address, dict):
                    location = address.get("addressLocality", "")
            jobs.append(
                Job(
                    title=entry.get("title", ""),
                    company=company_name,
                    location=location,
                    url=entry.get("url", base_url),
                    source="generic",
                    remote_type="remote" if entry.get("jobLocationType") == "TELECOMMUTE" else None,
                    posted_date=_parse_date(entry.get("datePosted")),
                    description_snippet=(entry.get("description") or "")[:280],
                )
            )
    return jobs


def _extract_heuristic_jobs(soup: BeautifulSoup, company_name: str, base_url: str) -> list[Job]:
    jobs = []
    seen_urls = set()
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        if not text or not _JOB_LINK_RE.search(anchor["href"]):
            continue
        url = urljoin(base_url, anchor["href"])
        if url in seen_urls:
            continue
        seen_urls.add(url)
        jobs.append(
            Job(
                title=text,
                company=company_name,
                location="",
                url=url,
                source="generic",
                remote_type=None,
                posted_date=None,
                description_snippet="",
            )
        )
    return jobs


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/connectors/test_generic_crawler.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/connectors/generic_crawler.py tests/connectors/test_generic_crawler.py
git commit -m "feat: add generic crawler with JSON-LD and heuristic fallback"
```

---

### Task 5: Autodetect dispatcher

**Files:**
- Create: `job_hunter/connectors/autodetect.py`
- Test: `tests/connectors/test_autodetect.py`

**Interfaces:**
- Consumes: `CompanyConfig` from `job_hunter.config`; `fetch_greenhouse` from `job_hunter.connectors.greenhouse`; `fetch_lever` from `job_hunter.connectors.lever`; `fetch_generic` from `job_hunter.connectors.generic_crawler`; `ConnectorError`, `Job` from `job_hunter.connectors.base`.
- Produces: `slugify(name: str) -> str`; `CompanyResult(company: str, jobs: list[Job], source: str | None, unmatched: bool, note: str | None, hint_slug: str | None)`; `fetch_for_company(company: CompanyConfig) -> CompanyResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/connectors/test_autodetect.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/connectors/test_autodetect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter.connectors.autodetect'`

- [ ] **Step 3: Implement `job_hunter/connectors/autodetect.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import CompanyConfig
from .base import ConnectorError, Job
from .generic_crawler import fetch_generic
from .greenhouse import fetch_greenhouse
from .lever import fetch_lever

_FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever}


def slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


@dataclass
class CompanyResult:
    company: str
    jobs: list[Job] = field(default_factory=list)
    source: str | None = None
    unmatched: bool = False
    note: str | None = None
    hint_slug: str | None = None


def fetch_for_company(company: CompanyConfig) -> CompanyResult:
    if company.ats and company.board_token:
        return _fetch_explicit(company)

    slug = slugify(company.name)

    try:
        jobs = fetch_greenhouse(slug, company.name)
        return CompanyResult(company=company.name, jobs=jobs, source="greenhouse")
    except ConnectorError:
        pass

    try:
        jobs = fetch_lever(slug, company.name)
        return CompanyResult(company=company.name, jobs=jobs, source="lever")
    except ConnectorError:
        pass

    if company.careers_url:
        try:
            jobs = fetch_generic(company.careers_url, company.name)
        except ConnectorError as exc:
            return CompanyResult(company=company.name, unmatched=True, note=str(exc))
        if not jobs:
            return CompanyResult(
                company=company.name,
                source="generic",
                note="no jobs found (page may need manual review)",
            )
        return CompanyResult(company=company.name, jobs=jobs, source="generic")

    return CompanyResult(
        company=company.name,
        unmatched=True,
        hint_slug=slug,
        note=(
            f"could not auto-detect ATS; check https://boards.greenhouse.io/{slug} "
            f"or https://jobs.lever.co/{slug}, or add board_token/careers_url to config.yaml"
        ),
    )


def _fetch_explicit(company: CompanyConfig) -> CompanyResult:
    fetcher = _FETCHERS.get(company.ats)
    if fetcher is None:
        return CompanyResult(
            company=company.name,
            unmatched=True,
            note=f"unknown ats '{company.ats}' in config; expected 'greenhouse' or 'lever'",
        )
    try:
        jobs = fetcher(company.board_token, company.name)
    except ConnectorError as exc:
        return CompanyResult(company=company.name, unmatched=True, note=str(exc))
    return CompanyResult(company=company.name, jobs=jobs, source=company.ats)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/connectors/test_autodetect.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/connectors/autodetect.py tests/connectors/test_autodetect.py
git commit -m "feat: add autodetect dispatcher across greenhouse/lever/generic crawler"
```

---

### Task 6: Filters module

**Files:**
- Create: `job_hunter/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: `Job` from `job_hunter.connectors.base`; `FilterConfig` from `job_hunter.config`.
- Produces: `apply_filters(jobs: list[Job], filters: FilterConfig, today: date | None = None) -> list[Job]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_filters.py
from datetime import date

from job_hunter.config import FilterConfig
from job_hunter.connectors.base import Job
from job_hunter.filters import apply_filters


def _job(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme",
        location="Austin, TX",
        url="u",
        source="greenhouse",
        remote_type="remote",
        posted_date=date(2026, 9, 20),
        description_snippet="Join our team.",
    )
    defaults.update(overrides)
    return Job(**defaults)


def _filters(**overrides):
    defaults = dict(
        designations=["Backend"],
        locations=["Austin"],
        workplace_types=["remote", "hybrid"],
        posted_within_days=14,
        exclude_keywords=["Clearance"],
    )
    defaults.update(overrides)
    return FilterConfig(**defaults)


def test_job_matching_all_filters_is_kept():
    result = apply_filters([_job()], _filters(), today=date(2026, 9, 29))
    assert len(result) == 1


def test_job_with_non_matching_designation_is_dropped():
    result = apply_filters([_job(title="Sales Manager")], _filters(), today=date(2026, 9, 29))
    assert result == []


def test_job_with_non_matching_location_is_dropped():
    result = apply_filters([_job(location="Seattle, WA")], _filters(), today=date(2026, 9, 29))
    assert result == []


def test_job_with_unknown_workplace_type_is_kept():
    result = apply_filters([_job(remote_type=None)], _filters(), today=date(2026, 9, 29))
    assert len(result) == 1


def test_job_with_non_matching_workplace_type_is_dropped():
    result = apply_filters([_job(remote_type="onsite")], _filters(), today=date(2026, 9, 29))
    assert result == []


def test_job_with_unknown_posted_date_is_kept():
    result = apply_filters([_job(posted_date=None)], _filters(), today=date(2026, 9, 29))
    assert len(result) == 1


def test_job_posted_too_long_ago_is_dropped():
    result = apply_filters(
        [_job(posted_date=date(2026, 9, 1))], _filters(), today=date(2026, 9, 29)
    )
    assert result == []


def test_job_with_excluded_keyword_in_title_is_dropped():
    result = apply_filters(
        [_job(title="Backend Engineer - Clearance required")], _filters(), today=date(2026, 9, 29)
    )
    assert result == []


def test_job_with_excluded_keyword_in_description_is_dropped():
    result = apply_filters(
        [_job(description_snippet="Requires active Clearance.")],
        _filters(),
        today=date(2026, 9, 29),
    )
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_filters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter.filters'`

- [ ] **Step 3: Implement `job_hunter/filters.py`**

```python
from __future__ import annotations

from datetime import date, timedelta

from .config import FilterConfig
from .connectors.base import Job


def matches_any_substring(value: str, candidates: list[str]) -> bool:
    value_lower = value.lower()
    return any(candidate.lower() in value_lower for candidate in candidates)


def matches_designation(job: Job, designations: list[str]) -> bool:
    return matches_any_substring(job.title, designations)


def matches_location(job: Job, locations: list[str]) -> bool:
    return matches_any_substring(job.location, locations)


def matches_workplace_type(job: Job, workplace_types: list[str]) -> bool:
    if job.remote_type is None:
        return True
    return job.remote_type in workplace_types


def matches_posted_within(job: Job, days: int, today: date) -> bool:
    if job.posted_date is None:
        return True
    return job.posted_date >= today - timedelta(days=days)


def has_excluded_keyword(job: Job, exclude_keywords: list[str]) -> bool:
    haystack = f"{job.title} {job.description_snippet}"
    return matches_any_substring(haystack, exclude_keywords)


def apply_filters(jobs: list[Job], filters: FilterConfig, today: date | None = None) -> list[Job]:
    today = today or date.today()
    kept = []
    for job in jobs:
        if not matches_designation(job, filters.designations):
            continue
        if not matches_location(job, filters.locations):
            continue
        if not matches_workplace_type(job, filters.workplace_types):
            continue
        if not matches_posted_within(job, filters.posted_within_days, today):
            continue
        if has_excluded_keyword(job, filters.exclude_keywords):
            continue
        kept.append(job)
    return kept
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_filters.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/filters.py tests/test_filters.py
git commit -m "feat: add job filtering with unknown-field inclusion rules"
```

---

### Task 7: Referral matcher

**Files:**
- Create: `job_hunter/referrals.py`
- Create: `connections.example.csv`
- Test: `tests/test_referrals.py`

**Interfaces:**
- Consumes: `Job` from `job_hunter.connectors.base`.
- Produces: `ReferralsError(Exception)`; `Connection(name: str, company: str, title: str)`; `normalize_company_name(name: str) -> str`; `load_connections(csv_path: str) -> list[Connection]`; `find_referrals(job: Job, connections: list[Connection]) -> list[Connection]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_referrals.py
import pytest

from job_hunter.connectors.base import Job
from job_hunter.referrals import (
    Connection,
    ReferralsError,
    find_referrals,
    load_connections,
    normalize_company_name,
)


def test_normalize_company_name_strips_suffix_and_case():
    assert normalize_company_name("Stripe, Inc.") == "stripe"
    assert normalize_company_name("STRIPE") == "stripe"
    assert normalize_company_name("Acme Corp") == "acme"


def test_load_connections_parses_valid_rows(tmp_path):
    csv_path = tmp_path / "connections.csv"
    csv_path.write_text("name,company,title\nJane Doe,Stripe,Engineer\n")

    connections = load_connections(csv_path)

    assert connections == [Connection(name="Jane Doe", company="Stripe", title="Engineer")]


def test_load_connections_skips_rows_missing_required_fields(tmp_path):
    csv_path = tmp_path / "connections.csv"
    csv_path.write_text("name,company,title\n,Stripe,Engineer\nJohn Smith,,Manager\nJane Doe,Stripe,Engineer\n")

    connections = load_connections(csv_path)

    assert len(connections) == 1
    assert connections[0].name == "Jane Doe"


def test_load_connections_missing_file_raises(tmp_path):
    with pytest.raises(ReferralsError, match="not found"):
        load_connections(tmp_path / "missing.csv")


def test_find_referrals_matches_normalized_company_name():
    job = Job(title="T", company="Stripe, Inc.", location="L", url="u", source="greenhouse")
    connections = [
        Connection(name="Jane Doe", company="Stripe", title="Engineer"),
        Connection(name="John Smith", company="Airbnb", title="PM"),
    ]

    result = find_referrals(job, connections)

    assert result == [connections[0]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_referrals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter.referrals'`

- [ ] **Step 3: Implement `job_hunter/referrals.py`**

```python
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .connectors.base import Job

_SUFFIX_RE = re.compile(r"\b(inc|llc|corp|co|ltd)\.?\s*$", re.IGNORECASE)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


class ReferralsError(Exception):
    """Raised when connections.csv cannot be read."""


@dataclass
class Connection:
    name: str
    company: str
    title: str


def normalize_company_name(name: str) -> str:
    normalized = name.strip().lower()
    normalized = _SUFFIX_RE.sub("", normalized).strip()
    normalized = _PUNCTUATION_RE.sub("", normalized)
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def load_connections(csv_path: str | Path) -> list[Connection]:
    path = Path(csv_path)
    if not path.exists():
        raise ReferralsError(f"connections_csv not found: {csv_path}")

    connections = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("name") or "").strip()
            company = (row.get("company") or "").strip()
            title = (row.get("title") or "").strip()
            if not name or not company:
                continue
            connections.append(Connection(name=name, company=company, title=title))
    return connections


def find_referrals(job: Job, connections: list[Connection]) -> list[Connection]:
    target = normalize_company_name(job.company)
    return [c for c in connections if normalize_company_name(c.company) == target]
```

- [ ] **Step 4: Create `connections.example.csv`**

```csv
name,company,title
Jane Doe,Stripe,Senior Engineer
John Smith,Airbnb,Engineering Manager
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_referrals.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add job_hunter/referrals.py connections.example.csv tests/test_referrals.py
git commit -m "feat: add referral matcher against user-maintained connections.csv"
```

---

### Task 8: Markdown report writer

**Files:**
- Create: `job_hunter/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `CompanyResult` from `job_hunter.connectors.autodetect`; `Job` from `job_hunter.connectors.base`; `Connection`, `find_referrals` from `job_hunter.referrals`.
- Produces: `dedupe_jobs(results: list[CompanyResult]) -> list[tuple[CompanyResult, list[Job]]]`; `render_report(results: list[CompanyResult], connections: list[Connection], generated_at: datetime) -> str`; `write_report(markdown: str, output_dir: str, generated_at: datetime) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report.py
from datetime import date, datetime

from job_hunter.connectors.autodetect import CompanyResult
from job_hunter.connectors.base import Job
from job_hunter.referrals import Connection
from job_hunter.report import render_report, write_report


def _job(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme",
        location="Austin, TX",
        url="https://boards.greenhouse.io/acme/1",
        source="greenhouse",
        remote_type="remote",
        posted_date=date(2026, 9, 20),
        description_snippet="",
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_render_report_lists_jobs_and_referrals():
    results = [CompanyResult(company="Acme", jobs=[_job()], source="greenhouse")]
    connections = [Connection(name="Jane Doe", company="Acme", title="Engineer")]

    markdown = render_report(results, connections, datetime(2026, 9, 29, 8, 0))

    assert "Acme" in markdown
    assert "Backend Engineer" in markdown
    assert "Possible referrals: Jane Doe (Engineer)" in markdown


def test_render_report_dedupes_same_url_across_companies():
    duplicate_job = _job()
    results = [
        CompanyResult(company="Acme", jobs=[duplicate_job], source="greenhouse"),
        CompanyResult(company="Acme Mirror", jobs=[duplicate_job], source="greenhouse"),
    ]

    markdown = render_report(results, [], datetime(2026, 9, 29, 8, 0))

    assert markdown.count("Backend Engineer") == 1


def test_render_report_shows_no_matches_message_when_empty():
    markdown = render_report([], [], datetime(2026, 9, 29, 8, 0))
    assert "No matching openings this run." in markdown


def test_render_report_lists_unmatched_notes():
    results = [CompanyResult(company="Mystery Co", unmatched=True, note="could not auto-detect ATS")]

    markdown = render_report(results, [], datetime(2026, 9, 29, 8, 0))

    assert "Mystery Co" in markdown
    assert "could not auto-detect ATS" in markdown


def test_write_report_creates_missing_output_dir(tmp_path):
    output_dir = tmp_path / "reports"

    path = write_report("# Report", str(output_dir), datetime(2026, 9, 29, 8, 0))

    assert path.exists()
    assert path.read_text() == "# Report"
    assert path.parent == output_dir
    assert path.name == "2026-09-29_0800_job_matches.md"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_hunter.report'`

- [ ] **Step 3: Implement `job_hunter/report.py`**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .connectors.autodetect import CompanyResult
from .connectors.base import Job
from .referrals import Connection, find_referrals


def dedupe_jobs(results: list[CompanyResult]) -> list[tuple[CompanyResult, list[Job]]]:
    seen_urls: set[str] = set()
    deduped = []
    for result in results:
        unique_jobs = []
        for job in result.jobs:
            if job.url in seen_urls:
                continue
            seen_urls.add(job.url)
            unique_jobs.append(job)
        deduped.append((result, unique_jobs))
    return deduped


def render_report(
    results: list[CompanyResult],
    connections: list[Connection],
    generated_at: datetime,
) -> str:
    lines = [f"# Job Matches — {generated_at.strftime('%Y-%m-%d %H:%M')}", ""]

    deduped = dedupe_jobs(results)
    any_jobs = False
    for result, jobs in deduped:
        if not jobs:
            continue
        any_jobs = True
        lines.append(f"## {result.company}")
        lines.append("")
        for job in jobs:
            lines.append(f"- **{job.title}** — {job.location or 'location unknown'}")
            workplace = job.remote_type or "workplace type unknown"
            posted = job.posted_date.isoformat() if job.posted_date else "date unknown"
            lines.append(f"  - {workplace} · posted {posted} · [link]({job.url})")
            referrals = find_referrals(job, connections)
            if referrals:
                names = ", ".join(f"{c.name} ({c.title})" for c in referrals)
                lines.append(f"  - Possible referrals: {names}")
        lines.append("")

    if not any_jobs:
        lines.append("No matching openings this run.")
        lines.append("")

    notes = [result for result, _ in deduped if result.note]
    if notes:
        lines.append("## Notes")
        lines.append("")
        for result in notes:
            marker = "⚠️" if result.unmatched else "ℹ️"
            lines.append(f"- {marker} {result.company}: {result.note}")
        lines.append("")

    return "\n".join(lines)


def write_report(markdown: str, output_dir: str, generated_at: datetime) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = generated_at.strftime("%Y-%m-%d_%H%M") + "_job_matches.md"
    path = directory / filename
    path.write_text(markdown)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/report.py tests/test_report.py
git commit -m "feat: add markdown report writer with dedup and unmatched notes"
```

---

### Task 9: Pipeline orchestration, scheduler, and CLI

**Files:**
- Create: `job_hunter/pipeline.py`
- Create: `job_hunter/scheduler.py`
- Create: `main.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_scheduler.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `load_config`, `Config` from `job_hunter.config`; `fetch_for_company` from `job_hunter.connectors.autodetect`; `apply_filters` from `job_hunter.filters`; `load_connections` from `job_hunter.referrals`; `render_report`, `write_report` from `job_hunter.report`.
- Produces: `run_pipeline(config: Config) -> Path`; `run_once(config_path: str) -> Path`; `run_daemon(config_path: str, interval: str) -> None` (loops forever; only exits via `KeyboardInterrupt` or fatal error surfaced to the caller); `validate_config_cli(config_path: str) -> bool` (prints outcome, returns True on success); CLI flags `--config`, `--once`, `--daemon`, `--interval`, `--validate-config`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline.py
from datetime import date
from unittest.mock import patch

from job_hunter.config import CompanyConfig, Config, FilterConfig, ScheduleConfig
from job_hunter.connectors.autodetect import CompanyResult
from job_hunter.connectors.base import Job
from job_hunter.pipeline import run_pipeline


def _config(tmp_path):
    connections_csv = tmp_path / "connections.csv"
    connections_csv.write_text("name,company,title\nJane Doe,Acme,Engineer\n")
    return Config(
        companies=[CompanyConfig(name="Acme")],
        filters=FilterConfig(
            designations=["Backend"],
            locations=["Austin"],
            workplace_types=["remote"],
            posted_within_days=14,
            exclude_keywords=[],
        ),
        connections_csv=str(connections_csv),
        output_dir=str(tmp_path / "reports"),
        schedule=ScheduleConfig(interval="6h"),
    )


@patch("job_hunter.pipeline.fetch_for_company")
def test_run_pipeline_writes_filtered_matches_with_referrals(mock_fetch, tmp_path):
    mock_fetch.return_value = CompanyResult(
        company="Acme",
        source="greenhouse",
        jobs=[
            Job(
                title="Backend Engineer",
                company="Acme",
                location="Austin, TX",
                url="https://boards.greenhouse.io/acme/1",
                source="greenhouse",
                remote_type="remote",
                posted_date=date.today(),
            ),
            Job(
                title="Sales Manager",
                company="Acme",
                location="Austin, TX",
                url="https://boards.greenhouse.io/acme/2",
                source="greenhouse",
                remote_type="remote",
                posted_date=date.today(),
            ),
        ],
    )

    report_path = run_pipeline(_config(tmp_path))

    content = report_path.read_text()
    assert "Backend Engineer" in content
    assert "Sales Manager" not in content
    assert "Possible referrals: Jane Doe (Engineer)" in content
```

```python
# tests/test_scheduler.py
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
```

```python
# tests/test_main.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py tests/test_scheduler.py tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError` for `job_hunter.pipeline`, `job_hunter.scheduler`, and `main`

- [ ] **Step 3: Implement `job_hunter/pipeline.py`**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import Config, load_config
from .connectors.autodetect import fetch_for_company
from .filters import apply_filters
from .referrals import load_connections
from .report import render_report, write_report


def run_pipeline(config: Config) -> Path:
    results = []
    for company in config.companies:
        result = fetch_for_company(company)
        result.jobs = apply_filters(result.jobs, config.filters)
        results.append(result)

    connections = load_connections(config.connections_csv)
    generated_at = datetime.now()
    markdown = render_report(results, connections, generated_at)
    return write_report(markdown, config.output_dir, generated_at)


def run_once(config_path: str) -> Path:
    config = load_config(config_path)
    return run_pipeline(config)
```

- [ ] **Step 4: Implement `job_hunter/scheduler.py`**

```python
from __future__ import annotations

import logging
import time

import schedule as schedule_lib

from .pipeline import run_once

logger = logging.getLogger(__name__)

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _interval_to_seconds(interval: str) -> int:
    amount = int(interval[:-1])
    unit = interval[-1]
    return amount * _UNIT_SECONDS[unit]


def run_daemon(config_path: str, interval: str) -> None:
    def _job() -> None:
        try:
            path = run_once(config_path)
            logger.info("Report written to %s", path)
        except Exception:
            logger.exception("Scheduled run failed; will retry next interval")

    schedule_lib.every(_interval_to_seconds(interval)).seconds.do(_job)
    _job()
    while True:
        schedule_lib.run_pending()
        time.sleep(1)
```

- [ ] **Step 5: Implement `main.py`**

```python
from __future__ import annotations

import argparse
import logging
import sys

from job_hunter.config import ConfigError, load_config
from job_hunter.pipeline import run_once
from job_hunter.scheduler import run_daemon


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Job Hunter")
    parser.add_argument("--config", default="config.yaml")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="run once and exit (default)")
    mode.add_argument("--daemon", action="store_true", help="run continuously on an interval")
    mode.add_argument(
        "--validate-config",
        action="store_true",
        help="validate config.yaml and exit without fetching anything",
    )
    parser.add_argument("--interval", default=None, help="override schedule.interval, e.g. 6h")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.validate_config:
        try:
            load_config(args.config)
        except ConfigError as exc:
            print(f"Config error: {exc}")
            return 1
        print("Config OK")
        return 0

    if args.daemon:
        config = load_config(args.config)
        interval = args.interval or config.schedule.interval
        run_daemon(args.config, interval)
        return 0

    path = run_once(args.config)
    print(f"Report written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py tests/test_scheduler.py tests/test_main.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Commit**

```bash
git add job_hunter/pipeline.py job_hunter/scheduler.py main.py tests/test_pipeline.py tests/test_scheduler.py tests/test_main.py
git commit -m "feat: add pipeline orchestration, in-process scheduler, and CLI"
```

---

### Task 10: README and manual smoke test

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing new — documents the CLI surface produced by Task 9.

- [ ] **Step 1: Write `README.md`**

```markdown
# Job Hunter

Finds new job openings at companies you care about, filters them by role/location/
recency/keywords, and flags people in your network who might refer you.

## Setup

1. `pip install -r requirements.txt`
2. Copy `config.example.yaml` to `config.yaml` and edit:
   - `companies`: list company names; the tool auto-detects Greenhouse/Lever.
     If it can't, either add `ats` + `board_token` (see below) or a `careers_url`.
   - `filters`: designations/locations are substring-matched; workplace_types,
     posted_within_days, exclude_keywords as documented in
     `docs/superpowers/specs/2026-09-29-job-hunter-design.md`.
3. Copy `connections.example.csv` to `connections.csv` and fill in
   `name,company,title` rows for people in your network (LinkedIn doesn't
   expose this via export, so this is maintained by hand).

### Finding a `board_token`

Try `https://boards.greenhouse.io/<slug>` or `https://jobs.lever.co/<slug>`
with the company's lowercased, hyphenated name. If either loads a jobs page,
the slug in that URL is the `board_token`. Otherwise check the company's own
careers page (it may embed one of these) or inspect the Network tab in
browser dev tools for a request to `boards-api.greenhouse.io` or
`api.lever.co`.

## Usage

```bash
python main.py --validate-config       # check config.yaml without fetching anything
python main.py --once                  # single run, writes reports/<timestamp>_job_matches.md
python main.py --daemon --interval 6h  # runs continuously; Ctrl+C to stop
```

`--validate-config` is worth running after every edit to `config.yaml` — it's
also run automatically, in full, before any fetch on every single run
(including every scheduled run in `--daemon` mode), so a bad edit never
reaches the network step silently.

## Manual smoke test (not part of the automated suite)

1. Add one real company you know is on Greenhouse or Lever to `config.yaml`.
2. Run `python main.py --once`.
3. Confirm `reports/<timestamp>_job_matches.md` was created and lists real,
   current openings for that company.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add setup, usage, and manual smoke test instructions"
```
