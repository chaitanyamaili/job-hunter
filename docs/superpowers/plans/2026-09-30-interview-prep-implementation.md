# Interview Prep Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given any job posting URL, build an interview-prep prompt
(likely questions, topics to review, STAR-method answers grounded in the
user's resume) and optionally run it through a local AI CLI (Claude or
Gemini), saving the result to a markdown report.

**Architecture:** A new standalone script `interview_prep.py` at the repo
root, backed by a new `job_hunter/interview_prep/` subpackage with five
small modules (`html_text.py`, `extractor.py`, `resume.py`,
`prompt_builder.py`, `agents.py`). Reuses `job_hunter/referrals.py`
unmodified for referral matching.

**Tech Stack:** Python 3, `requests` + `beautifulsoup4` (already a
dependency), `subprocess` for shelling out to local CLIs, `pytest` +
`responses` + `unittest.mock` for testing. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-interview-prep-design.md`

## Global Constraints

- No new third-party dependencies beyond what `requirements.txt` already
  has.
- Follows existing codebase conventions: `from __future__ import
  annotations`, dataclasses for structured data, a dedicated `*Error`
  exception class per failure domain, `pathlib.Path` for filesystem work,
  timestamped output filenames matching the `YYYY-MM-DD_HHMM` pattern
  already used by `job_hunter/report.py`.
- Entry point is a separate script (`interview_prep.py`), not a new flag
  on `main.py`.
- Only `claude` and `gemini` are implemented as agent targets (both
  confirmed installed in this environment). The agent registry is a plain
  dict — a future CLI is a one-line addition, not a plugin system.
- Always run `python -m pytest` (not bare `pytest`) — `tests/` has no
  `__init__.py` files.

## Review Focus

1. A job URL whose JSON-LD `JobPosting.description` field contains raw
   HTML — expected: stripped to plain text, not dumped into the prompt
   with markup in it. (Task 2)
2. A resume URL that redirects — expected: the redirect is followed and
   the final page's content is used, not a failure. (Task 3)
3. `--agent` value with different case than the registry key (e.g.
   `"Claude"`) — expected: a clear `AgentError` naming valid options, not
   a silent `KeyError`/crash. (Task 5)
4. A connections.csv company name that matches the posting's extracted
   company only after normalization (e.g. "Acme Corp, Inc." vs "Acme
   Corp") — expected: `find_referrals`'s existing normalization handles
   this already (reused unmodified); this is a regression check exercised
   through the full CLI flow. (Task 6)
5. Running with no `--agent`, no resume file, and no `connections.csv`
   present at all — expected: the tool still produces a usable
   prompt-only output, since every enrichment is optional by design.
   (Task 6)

---

### Task 1: Shared HTML visible-text extraction helper

**Files:**
- Create: `job_hunter/interview_prep/__init__.py` (empty)
- Create: `job_hunter/interview_prep/html_text.py`
- Test: `tests/interview_prep/test_html_text.py`

**Interfaces:**
- Consumes: `bs4.BeautifulSoup` (third-party, already a dependency)
- Produces: `extract_visible_text(soup: BeautifulSoup, max_chars: int = 6000) -> str` — used by Task 2 (`extractor.py`'s heuristic fallback) and Task 3 (`resume.py`'s URL path)

- [ ] **Step 1: Write the failing tests**

```python
# tests/interview_prep/test_html_text.py
from bs4 import BeautifulSoup

from job_hunter.interview_prep.html_text import extract_visible_text


def test_extract_visible_text_strips_boilerplate_tags():
    html = """
    <html><body>
    <nav>Home About</nav>
    <header>Site Header</header>
    <main><h1>Job Title</h1><p>We need a great engineer.</p></main>
    <footer>Copyright 2026</footer>
    <script>var x = 1;</script>
    <style>.a{color:red}</style>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")

    text = extract_visible_text(soup)

    assert "Job Title" in text
    assert "We need a great engineer." in text
    assert "Home About" not in text
    assert "Site Header" not in text
    assert "Copyright 2026" not in text
    assert "var x = 1" not in text
    assert "color:red" not in text


def test_extract_visible_text_truncates_to_max_chars():
    html = "<html><body><p>" + ("word " * 2000) + "</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")

    text = extract_visible_text(soup, max_chars=50)

    assert len(text) == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mkdir -p job_hunter/interview_prep tests/interview_prep && touch job_hunter/interview_prep/__init__.py && python -m pytest tests/interview_prep/test_html_text.py -v`
Expected: FAIL/ERROR with "No module named 'job_hunter.interview_prep.html_text'"

- [ ] **Step 3: Write minimal implementation**

```python
# job_hunter/interview_prep/html_text.py
from __future__ import annotations

from bs4 import BeautifulSoup

_STRIP_TAGS = ("script", "style", "nav", "header", "footer")


def extract_visible_text(soup: BeautifulSoup, max_chars: int = 6000) -> str:
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = " ".join(text.split())
    return text[:max_chars]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/interview_prep/test_html_text.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/interview_prep/__init__.py job_hunter/interview_prep/html_text.py tests/interview_prep/test_html_text.py
git commit -m "feat: add shared HTML visible-text extraction helper"
```

---

### Task 2: Job posting extractor

**Files:**
- Create: `job_hunter/interview_prep/extractor.py`
- Test: `tests/interview_prep/test_extractor.py`

**Interfaces:**
- Consumes: `extract_visible_text` from Task 1; `get_with_retry`,
  `ConnectorError` from `job_hunter.connectors.base` (existing, unmodified)
- Produces: `class InterviewPrepError(Exception)`; `@dataclass class
  JobPosting(title: str, company: str, description_text: str, url: str)`;
  `fetch_job_posting(url: str) -> JobPosting` — `InterviewPrepError` used
  by Task 3 and Task 6; `JobPosting` used by Task 4 and Task 6;
  `fetch_job_posting` used by Task 6

- [ ] **Step 1: Write the failing tests**

```python
# tests/interview_prep/test_extractor.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/interview_prep/test_extractor.py -v`
Expected: FAIL/ERROR with "No module named 'job_hunter.interview_prep.extractor'"

- [ ] **Step 3: Write minimal implementation**

```python
# job_hunter/interview_prep/extractor.py
from __future__ import annotations

import json
from dataclasses import dataclass

from bs4 import BeautifulSoup

from ..connectors.base import ConnectorError, get_with_retry
from .html_text import extract_visible_text


class InterviewPrepError(Exception):
    """Raised when a job posting cannot be fetched or parsed."""


@dataclass
class JobPosting:
    title: str
    company: str
    description_text: str
    url: str


def fetch_job_posting(url: str) -> JobPosting:
    try:
        response = get_with_retry(url)
    except ConnectorError as exc:
        raise InterviewPrepError(str(exc)) from exc

    if response.status_code >= 400:
        raise InterviewPrepError(
            f"request for '{url}' failed with status {response.status_code}"
        )

    soup = BeautifulSoup(response.text, "html.parser")

    posting = _extract_json_ld_posting(soup, url)
    if posting:
        return posting

    return _extract_heuristic_posting(soup, url)


def _extract_json_ld_posting(soup: BeautifulSoup, url: str) -> JobPosting | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("@type") != "JobPosting":
                continue
            title = entry.get("title", "")
            description_html = entry.get("description", "")
            description_text = BeautifulSoup(
                description_html, "html.parser"
            ).get_text(separator=" ", strip=True)
            company = ""
            hiring_org = entry.get("hiringOrganization")
            if isinstance(hiring_org, dict):
                company = hiring_org.get("name", "")
            return JobPosting(
                title=title,
                company=company,
                description_text=description_text,
                url=url,
            )
    return None


def _extract_heuristic_posting(soup: BeautifulSoup, url: str) -> JobPosting:
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    else:
        heading = soup.find("h1")
        if heading:
            title = heading.get_text(strip=True)

    return JobPosting(
        title=title,
        company="",
        description_text=extract_visible_text(soup),
        url=url,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/interview_prep/test_extractor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/interview_prep/extractor.py tests/interview_prep/test_extractor.py
git commit -m "feat: add job posting extractor (JSON-LD + heuristic fallback)"
```

---

### Task 3: Resume loader (local file or URL)

**Files:**
- Create: `job_hunter/interview_prep/resume.py`
- Test: `tests/interview_prep/test_resume.py`

**Interfaces:**
- Consumes: `InterviewPrepError` from Task 2; `extract_visible_text` from
  Task 1; `get_with_retry`, `ConnectorError` from
  `job_hunter.connectors.base` (existing, unmodified)
- Produces: `load_resume(source: str | None) -> str | None` — used by
  Task 6

- [ ] **Step 1: Write the failing tests**

```python
# tests/interview_prep/test_resume.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/interview_prep/test_resume.py -v`
Expected: FAIL/ERROR with "No module named 'job_hunter.interview_prep.resume'"

- [ ] **Step 3: Write minimal implementation**

```python
# job_hunter/interview_prep/resume.py
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..connectors.base import ConnectorError, get_with_retry
from .extractor import InterviewPrepError
from .html_text import extract_visible_text

DEFAULT_RESUME_PATH = "resume.md"


def load_resume(source: str | None) -> str | None:
    if source is None:
        path = Path(DEFAULT_RESUME_PATH)
        if not path.exists():
            return None
        return path.read_text()

    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        try:
            response = get_with_retry(source)
        except ConnectorError as exc:
            raise InterviewPrepError(str(exc)) from exc
        if response.status_code >= 400:
            raise InterviewPrepError(
                f"request for resume '{source}' failed with status {response.status_code}"
            )
        soup = BeautifulSoup(response.text, "html.parser")
        return extract_visible_text(soup)

    path = Path(source)
    if not path.exists():
        raise InterviewPrepError(f"resume file not found: {source}")
    return path.read_text()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/interview_prep/test_resume.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/interview_prep/resume.py tests/interview_prep/test_resume.py
git commit -m "feat: add resume loader supporting local files and URLs"
```

---

### Task 4: Prompt builder

**Files:**
- Create: `job_hunter/interview_prep/prompt_builder.py`
- Test: `tests/interview_prep/test_prompt_builder.py`

**Interfaces:**
- Consumes: `JobPosting` from Task 2; `Connection` from
  `job_hunter.referrals` (existing, unmodified)
- Produces: `build_prompt(posting: JobPosting, resume_text: str | None,
  referral: Connection | None) -> str` — used by Task 6

- [ ] **Step 1: Write the failing tests**

```python
# tests/interview_prep/test_prompt_builder.py
from job_hunter.interview_prep.extractor import JobPosting
from job_hunter.interview_prep.prompt_builder import build_prompt
from job_hunter.referrals import Connection


def _posting(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme Corp",
        description_text="Build scalable systems with Python.",
        url="https://example.com/job/1",
    )
    defaults.update(overrides)
    return JobPosting(**defaults)


def test_build_prompt_includes_core_sections():
    prompt = build_prompt(_posting(), resume_text=None, referral=None)

    assert "interview questions" in prompt
    assert "brush up" in prompt
    assert "STAR-method" in prompt
    assert "Backend Engineer" in prompt
    assert "Build scalable systems with Python." in prompt


def test_build_prompt_grounds_star_answers_in_resume_when_present():
    prompt = build_prompt(_posting(), resume_text="5 years leading backend teams.", referral=None)

    assert "Draft STAR-method" in prompt
    assert "5 years leading backend teams." in prompt
    assert "do not invent a candidate history" not in prompt


def test_build_prompt_uses_frameworks_when_no_resume():
    prompt = build_prompt(_posting(), resume_text=None, referral=None)

    assert "frameworks" in prompt
    assert "do not invent a candidate history" in prompt


def test_build_prompt_includes_referral_when_present():
    referral = Connection(name="Jane Smith", company="Acme Corp", title="Staff Engineer")

    prompt = build_prompt(_posting(), resume_text=None, referral=referral)

    assert "Jane Smith" in prompt
    assert "Staff Engineer" in prompt


def test_build_prompt_omits_referral_section_when_absent():
    prompt = build_prompt(_posting(), resume_text=None, referral=None)

    assert "Referral Contact" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/interview_prep/test_prompt_builder.py -v`
Expected: FAIL/ERROR with "No module named 'job_hunter.interview_prep.prompt_builder'"

- [ ] **Step 3: Write minimal implementation**

```python
# job_hunter/interview_prep/prompt_builder.py
from __future__ import annotations

from ..referrals import Connection
from .extractor import JobPosting


def build_prompt(
    posting: JobPosting,
    resume_text: str | None,
    referral: Connection | None,
) -> str:
    lines = [
        "You are an experienced technical interview coach.",
        "",
        f"## Job Posting: {posting.title or 'Unknown title'}",
        f"Company: {posting.company or 'Unknown'}",
        f"URL: {posting.url}",
        "",
        "### Job Description",
        posting.description_text or "(description could not be reliably extracted)",
        "",
    ]

    if referral:
        lines.append("### Referral Contact")
        lines.append(
            f"The candidate knows {referral.name} ({referral.title}) at this company. "
            "Suggest how they might mention this connection or ask for a warm introduction."
        )
        lines.append("")

    if resume_text:
        lines.append("### Candidate Resume")
        lines.append(resume_text)
        lines.append("")

    lines.append("### What I need from you")
    lines.append(
        "1. Likely interview questions (a mix of behavioral and technical) for this "
        "role, grounded in the job description above."
    )
    lines.append(
        "2. A list of technologies, concepts, or topics the candidate should brush up "
        "on, derived from the requirements in the job description."
    )
    if resume_text:
        lines.append(
            "3. Draft STAR-method (Situation, Task, Action, Result) answers to the "
            "likely behavioral questions, grounded in the candidate's resume above — "
            "use only experience that appears in the resume."
        )
    else:
        lines.append(
            "3. STAR-method (Situation, Task, Action, Result) frameworks for the "
            "likely behavioral questions, for the candidate to fill in themselves — "
            "no resume was provided, so do not invent a candidate history."
        )

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/interview_prep/test_prompt_builder.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/interview_prep/prompt_builder.py tests/interview_prep/test_prompt_builder.py
git commit -m "feat: add interview-prep prompt builder"
```

---

### Task 5: Local AI agent runner

**Files:**
- Create: `job_hunter/interview_prep/agents.py`
- Test: `tests/interview_prep/test_agents.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `class AgentError(Exception)`; `_AGENTS: dict[str, list[str]]`
  (keys: `"claude"`, `"gemini"`); `run_agent(name: str, prompt: str) ->
  str` — all three used by Task 6

- [ ] **Step 1: Write the failing tests**

```python
# tests/interview_prep/test_agents.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/interview_prep/test_agents.py -v`
Expected: FAIL/ERROR with "No module named 'job_hunter.interview_prep.agents'"

- [ ] **Step 3: Write minimal implementation**

```python
# job_hunter/interview_prep/agents.py
from __future__ import annotations

import subprocess

_AGENTS: dict[str, list[str]] = {
    "claude": ["claude", "-p"],
    "gemini": ["gemini", "-p"],
}


class AgentError(Exception):
    """Raised when a requested agent CLI is unavailable or fails."""


def run_agent(name: str, prompt: str) -> str:
    if name not in _AGENTS:
        valid = ", ".join(sorted(_AGENTS))
        raise AgentError(f"unknown agent '{name}'; expected one of: {valid}")

    argv = _AGENTS[name] + [prompt]
    try:
        result = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AgentError(
            f"agent '{name}' not found on PATH; install it or omit --agent to get the prompt only"
        ) from exc

    if result.returncode != 0:
        raise AgentError(
            f"agent '{name}' exited with status {result.returncode}: {result.stderr.strip()}"
        )

    return result.stdout.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/interview_prep/test_agents.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add job_hunter/interview_prep/agents.py tests/interview_prep/test_agents.py
git commit -m "feat: add local AI agent CLI runner"
```

---

### Task 6: CLI entry point

**Files:**
- Create: `interview_prep.py`
- Test: `tests/test_interview_prep_cli.py`

**Interfaces:**
- Consumes: `fetch_job_posting`, `InterviewPrepError`, `JobPosting` (Task
  2); `load_resume` (Task 3); `build_prompt` (Task 4); `run_agent`,
  `AgentError`, `_AGENTS` (Task 5); `load_connections`, `find_referrals`,
  `ReferralsError` from `job_hunter.referrals` (existing); `Job` from
  `job_hunter.connectors.base` (existing); `slugify` from
  `job_hunter.connectors.autodetect` (existing)
- Produces: `main(argv: list[str] | None = None) -> int` — the CLI entry
  point; nothing consumed by later tasks

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_interview_prep_cli.py
from unittest.mock import patch

from interview_prep import main
from job_hunter.interview_prep.extractor import JobPosting
from job_hunter.referrals import Connection


def _posting(**overrides):
    defaults = dict(
        title="Backend Engineer",
        company="Acme Corp",
        description_text="Build scalable systems.",
        url="https://example.com/job/1",
    )
    defaults.update(overrides)
    return JobPosting(**defaults)


@patch("interview_prep.run_agent")
@patch("interview_prep.load_connections")
@patch("interview_prep.load_resume")
@patch("interview_prep.fetch_job_posting")
def test_cli_writes_report_with_full_enrichment(
    mock_fetch, mock_load_resume, mock_load_connections, mock_run_agent, tmp_path
):
    mock_fetch.return_value = _posting()
    mock_load_resume.return_value = "5 years of backend experience."
    mock_load_connections.return_value = [
        Connection(name="Jane Smith", company="Acme Corp, Inc.", title="Staff Engineer")
    ]
    mock_run_agent.return_value = "Great prep content."

    connections_path = tmp_path / "connections.csv"
    connections_path.write_text("name,company,title\n")
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "https://example.com/job/1",
            "--agent",
            "claude",
            "--connections-csv",
            str(connections_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    files = list(output_dir.glob("*_interview_prep.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Backend Engineer" in content
    assert "Jane Smith" in content
    assert "Great prep content." in content


@patch("interview_prep.fetch_job_posting")
def test_cli_writes_prompt_only_report_with_no_enrichment(mock_fetch, tmp_path, monkeypatch):
    mock_fetch.return_value = _posting(company="")
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "https://example.com/job/1",
            "--connections-csv",
            str(tmp_path / "missing_connections.csv"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    files = list(output_dir.glob("*_interview_prep.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Backend Engineer" in content
    assert "no agent requested" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_interview_prep_cli.py -v`
Expected: FAIL/ERROR with "No module named 'interview_prep'"

- [ ] **Step 3: Write minimal implementation**

```python
# interview_prep.py
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from job_hunter.connectors.autodetect import slugify
from job_hunter.connectors.base import Job
from job_hunter.interview_prep.agents import AgentError, _AGENTS, run_agent
from job_hunter.interview_prep.extractor import InterviewPrepError, fetch_job_posting
from job_hunter.interview_prep.prompt_builder import build_prompt
from job_hunter.interview_prep.resume import load_resume
from job_hunter.referrals import ReferralsError, find_referrals, load_connections


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interview Prep")
    parser.add_argument("url", help="job posting URL")
    parser.add_argument(
        "--resume", default=None, help="path or URL to resume (default: ./resume.md)"
    )
    parser.add_argument("--agent", default=None, choices=sorted(_AGENTS))
    parser.add_argument("--connections-csv", default="./connections.csv")
    parser.add_argument("--output-dir", default="./reports/interview_prep")
    args = parser.parse_args(argv)

    try:
        posting = fetch_job_posting(args.url)
    except InterviewPrepError as exc:
        print(f"Error: {exc}")
        return 1

    try:
        resume_text = load_resume(args.resume)
    except InterviewPrepError as exc:
        print(f"Error: {exc}")
        return 1

    referral = None
    if posting.company and Path(args.connections_csv).exists():
        try:
            connections = load_connections(args.connections_csv)
        except ReferralsError:
            connections = []
        job_stub = Job(
            title=posting.title,
            company=posting.company,
            location="",
            url=posting.url,
            source="single",
        )
        matches = find_referrals(job_stub, connections)
        referral = matches[0] if matches else None

    prompt = build_prompt(posting, resume_text, referral)

    response = None
    if args.agent:
        try:
            response = run_agent(args.agent, prompt)
        except AgentError as exc:
            print(f"Error: {exc}")
            return 1

    print(prompt)
    if response:
        print()
        print(response)

    generated_at = datetime.now()
    slug = slugify(posting.company) if posting.company else slugify(urlparse(args.url).netloc or "job")
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = generated_at.strftime("%Y-%m-%d_%H%M") + f"_{slug}_interview_prep.md"
    path = directory / filename

    content_lines = [
        f"# Interview Prep — {posting.title or 'Unknown title'}",
        f"Company: {posting.company or 'Unknown'}",
        f"URL: {posting.url}",
        "",
        "## Prompt",
        "",
        prompt,
        "",
        "## Agent Response",
        "",
        response if response else "(no agent requested — prompt only)",
        "",
    ]
    path.write_text("\n".join(content_lines))
    print(f"\nSaved to {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_interview_prep_cli.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add interview_prep.py tests/test_interview_prep_cli.py
git commit -m "feat: add interview_prep.py CLI entry point"
```

---

### Task 7: Documentation and resume example

**Files:**
- Create: `resume.example.md`
- Modify: `README.md` (append a new section)
- Modify: `.gitignore` (add `resume.md`, matching the existing
  `connections.csv`/`config.yaml` personal-file pattern)

**Interfaces:**
- Consumes: nothing (documentation only)
- Produces: nothing (documentation only)

- [ ] **Step 1: Write `resume.example.md`**

```markdown
# Jane Doe

Senior Backend Engineer with 6 years of experience building distributed
systems in Python and Go.

## Experience

**Acme Corp** — Senior Backend Engineer (2022–present)
- Led the migration of a monolithic billing service to an event-driven
  architecture, cutting p99 latency by 40%.
- Mentored two junior engineers through their first on-call rotations.

**Startup Inc** — Backend Engineer (2019–2022)
- Built the initial version of the company's public API, used by 50+
  integration partners.

## Skills

Python, Go, PostgreSQL, Kafka, AWS, Kubernetes
```

- [ ] **Step 2: Add `resume.md` to `.gitignore`**

Add a line `resume.md` to `.gitignore`, alongside the existing
`connections.csv` and `config.yaml` entries.

- [ ] **Step 3: Append a new section to `README.md`**

```markdown

## Interview Prep Tool

Given any job posting URL, `interview_prep.py` builds an interview-prep
prompt (likely questions, topics to review, STAR-method answers) and,
optionally, runs it through a local AI CLI you already have installed.

```bash
python interview_prep.py <job-posting-url>                # prompt only, printed + saved
python interview_prep.py <job-posting-url> --agent claude  # also runs it through `claude -p`
python interview_prep.py <job-posting-url> --agent gemini  # or `gemini -p`
```

Optional flags:
- `--resume PATH_OR_URL` — local resume file or a URL to an HTML resume
  page (default: `./resume.md`, skipped if absent). Copy
  `resume.example.md` to `resume.md` and fill in your own experience so
  STAR-method answers are grounded in real examples instead of generic
  frameworks.
- `--connections-csv PATH` — reuses the same connections file as the main
  pipeline (default: `./connections.csv`) to flag a referral at the
  posting's company, if one exists.
- `--output-dir DIR` — where the markdown report is written (default:
  `./reports/interview_prep`).

Only `claude` and `gemini` are supported as `--agent` values right now —
whichever CLIs you have installed locally.
```

- [ ] **Step 4: Run the full test suite to confirm nothing broke**

Run: `python -m pytest -q`
Expected: PASS (all tests, no regressions)

- [ ] **Step 5: Commit**

```bash
git add resume.example.md .gitignore README.md
git commit -m "docs: document interview prep tool and add resume example"
```
