# Interview Prep Tool — Design Spec

**Status:** Approved for planning
**Date:** 2026-09-30

## Purpose

Given any job posting URL — not limited to companies or ATS providers the
main job-hunter pipeline already knows about — produce an interview-prep
brief: likely interview questions (behavioral + technical), tech/topics to
brush up on based on the posting's requirements, and STAR-method answer
drafts grounded in the user's own resume. Optionally hand the assembled
prompt to a local AI CLI (Claude, Gemini, etc.) and capture its response.

This is a new, standalone component alongside the existing job-hunter
pipeline. It shares two things with that pipeline: the referral-matching
logic in `job_hunter/referrals.py` (reused unmodified) and the general
coding conventions of the codebase (dataclasses, custom exception types,
`pathlib.Path`, BeautifulSoup-only HTML parsing, no new dependencies).

## Non-Goals

- No direct API integration with any AI provider (no API keys, no billing).
  Only shelling out to CLI tools the user already has installed.
- No PDF resume parsing. Resume input is either a local text/markdown file
  or an HTML page reachable by URL.
- No attempt to solve bot-blocked job postings (e.g. sites behind
  aggressive bot management). Such failures surface as a clear error, same
  as the existing `generic_crawler` does for career pages.
- No caching or deduplication of interview-prep runs across invocations —
  each run is independent.

## Global Constraints

- No new third-party dependencies beyond what `requirements.txt` already
  has (`requests`, `beautifulsoup4`, `PyYAML`, `schedule`, plus `pytest`/
  `responses` for tests).
- Follows existing codebase conventions: `from __future__ import
  annotations`, dataclasses for structured data, a dedicated `*Error`
  exception class per failure domain, `pathlib.Path` for all filesystem
  work, timestamped output filenames matching the existing
  `YYYY-MM-DD_HHMM` pattern used by `job_hunter/report.py`.
- Entry point is a separate script (`interview_prep.py`) at the repo root,
  parallel to `main.py` — not a new flag on `main.py`.
- Only `claude` and `gemini` CLIs are implemented as agent targets (both
  confirmed installed in this environment). The agent registry is a plain
  dict so a future CLI (e.g. `codex`, once installed) is a one-line
  addition — do not build a plugin-discovery system for this.

## Architecture

```
interview_prep.py                     # CLI entry point (argparse), mirrors main.py's style
job_hunter/interview_prep/
    __init__.py
    extractor.py      # fetch + extract a single job posting's structured info
    html_text.py       # shared heuristic "extract visible text from HTML" helper
    resume.py          # load resume content from a local path or URL
    prompt_builder.py  # assemble the engineered prompt string
    agents.py          # run a local AI CLI as a subprocess
```

`job_hunter/referrals.py` (existing) is imported and used unmodified.

### Why a shared `html_text.py`

Both the job-posting fallback extraction and the resume-as-webpage path
need the same thing: given a `BeautifulSoup` document, strip
`<script>`/`<style>`/`<nav>`/`<header>`/`<footer>` and return the visible
body text, truncated to a sane length. One function, two callers —
`extractor.py`'s heuristic fallback and `resume.py`'s URL path.

## Components

### `job_hunter/interview_prep/html_text.py`

```python
def extract_visible_text(soup: BeautifulSoup, max_chars: int = 6000) -> str:
    """Strip script/style/nav/header/footer, return truncated visible text."""
```

### `job_hunter/interview_prep/extractor.py`

```python
class InterviewPrepError(Exception):
    """Raised when a job posting cannot be fetched or parsed."""

@dataclass
class JobPosting:
    title: str
    company: str          # "" if it could not be determined
    description_text: str
    url: str

def fetch_job_posting(url: str) -> JobPosting:
    """
    Fetch `url`. Raise InterviewPrepError on 4xx/5xx or transport failure
    (reuses job_hunter.connectors.base.get_with_retry).

    Try JSON-LD JobPosting first: look for a <script type="application/
    ld+json"> tag whose @type is "JobPosting"; pull `title`,
    `description` (HTML-stripped to text), and
    `hiringOrganization.name` for company.

    If no JSON-LD JobPosting is found, fall back to heuristic extraction:
    title from <title> or first <h1>; company left as "" (heuristic
    extraction cannot reliably determine it — referral matching is
    skipped in this case, not guessed at); description_text via
    html_text.extract_visible_text(soup).

    Never raises for "extraction produced little text" — that is a
    degraded-but-successful result, not a failure. Only unreachable/error
    HTTP responses raise InterviewPrepError.
    """
```

### `job_hunter/interview_prep/resume.py`

```python
def load_resume(source: str | None) -> str | None:
    """
    - source is None: try the default './resume.md'. If it doesn't exist,
      return None (proceed without resume content — this is the lenient
      default-file case).
    - source is an http:// or https:// URL: fetch it, run
      html_text.extract_visible_text on the parsed page. Raise
      InterviewPrepError if the fetch fails (explicit input, so this is a
      hard failure, not a silent skip).
    - source is anything else: treat as a local file path. Raise
      InterviewPrepError if it does not exist (explicit input → hard
      failure). Read and return its text as-is (no HTML stripping needed
      for a plain resume.md).
    """
```

### `job_hunter/interview_prep/prompt_builder.py`

```python
def build_prompt(
    posting: JobPosting,
    resume_text: str | None,
    referral: Connection | None,
) -> str:
    """
    Assemble the interview-prep prompt. Always asks for, in this order:
      1. Likely interview questions (behavioral + technical), grounded in
         the posting's description_text.
      2. Tech/topics to brush up on, derived from the posting's stated
         requirements.
      3. STAR-method draft answers — grounded in resume_text if present;
         if resume_text is None, ask for STAR-method *frameworks* the user
         can fill in themselves, and say so explicitly in the prompt so
         the AI doesn't fabricate a candidate history.
    Includes the referral's name/title verbatim if referral is not None,
    framed as context the candidate can mention or use to ask for a warm
    introduction.
    Includes posting.title/company/url as a header block for context.
    """
```

### `job_hunter/interview_prep/agents.py`

```python
class AgentError(Exception):
    """Raised when a requested agent CLI is unavailable or fails."""

_AGENTS: dict[str, list[str]] = {
    "claude": ["claude", "-p"],
    "gemini": ["gemini", "-p"],
}

def run_agent(name: str, prompt: str) -> str:
    """
    Look up name in _AGENTS (KeyError path → AgentError listing valid
    names). Run the mapped argv + [prompt] via subprocess.run, capturing
    stdout as text. FileNotFoundError (binary not on PATH) and non-zero
    exit both raise AgentError with a clear message — never a raw
    traceback. Returns stdout stripped of trailing whitespace.
    """
```

## Data Flow (CLI)

```
interview_prep.py <url>
    [--resume PATH_OR_URL]         # default: ./resume.md (lenient if absent)
    [--agent claude|gemini]        # default: None (prompt-only)
    [--connections-csv PATH]       # default: ./connections.csv (lenient if absent)
    [--output-dir DIR]             # default: ./reports/interview_prep

1. posting = extractor.fetch_job_posting(url)
2. resume_text = resume.load_resume(args.resume)
3. referral = None
   if posting.company and connections_csv exists:
       connections = referrals.load_connections(args.connections_csv)
       matches = referrals.find_referrals(Job(title="", company=posting.company,
                                              location="", url=url, source="single"),
                                          connections)
       referral = matches[0] if matches else None
4. prompt = prompt_builder.build_prompt(posting, resume_text, referral)
5. response = agents.run_agent(args.agent, prompt) if args.agent else None
6. print prompt to stdout; print response to stdout if present
7. write markdown file to <output-dir>/<slug>_<timestamp>.md containing:
   - posting title/company/url
   - the prompt
   - the response (if an agent ran), or a note that none was requested
```

Filename slug: derived from `posting.company` (slugified, same `slugify()`
already in `job_hunter/connectors/autodetect.py`) if non-empty, else from
the URL's domain. Timestamp format matches `report.py`'s
`YYYY-MM-DD_HHMM`.

## Error Handling

| Condition | Behavior |
|---|---|
| Job URL unreachable / 4xx / 5xx | `InterviewPrepError`, CLI prints message, exits 1 — no traceback |
| Job URL reachable but no JSON-LD and heuristic text is sparse | Proceed; prompt notes the description may be incomplete |
| `--resume` explicit path/URL unreachable or missing | `InterviewPrepError` (explicit input, hard failure) |
| Default `resume.md` missing (no `--resume` given) | Proceed with `resume_text=None`; prompt asks for frameworks instead of grounded answers |
| `--connections-csv` missing (default, not explicit) | Proceed with `referral=None`, no error |
| `posting.company` empty (heuristic extraction couldn't determine it) | Referral lookup skipped, no error |
| `--agent` value not in `_AGENTS` | `AgentError` listing valid names |
| Agent binary not on PATH, or non-zero exit | `AgentError` with a clear message, no raw traceback |

## Testing

- `tests/interview_prep/test_html_text.py` — visible-text extraction:
  strips script/style/nav/header/footer; truncates at `max_chars`.
- `tests/interview_prep/test_extractor.py` — `responses`-mocked HTML:
  JSON-LD JobPosting present; JSON-LD absent (heuristic fallback); 403
  response raises `InterviewPrepError`.
- `tests/interview_prep/test_resume.py` — local file present; local file
  explicitly requested but missing (raises); default file missing (returns
  `None`); URL fetch success (`responses`-mocked); URL fetch failure
  (raises).
- `tests/interview_prep/test_prompt_builder.py` — pure string-assembly
  assertions: all three ask-for sections always present; STAR section
  wording differs when `resume_text` is `None` vs a real value; referral
  line present only when a `Connection` is passed.
- `tests/interview_prep/test_agents.py` — `subprocess.run` mocked: success
  case returns stripped stdout; unknown agent name raises `AgentError`;
  `FileNotFoundError` from `subprocess.run` raises `AgentError`; non-zero
  exit raises `AgentError`.
- `tests/test_interview_prep_cli.py` — one end-to-end test mirroring
  `tests/test_main.py`'s style: HTTP fetch and `subprocess.run` both
  mocked, asserts the output file is written and contains expected
  sections.

## Review Focus

(For the implementation plan's Review Focus section — input classes the
spec implies but whose tests are not automatically obvious from the
component list above.)

1. A job URL whose JSON-LD `JobPosting.description` field contains raw
   HTML (common — many sites embed an HTML string, not plain text) —
   expected: it gets stripped to plain text, not dumped into the prompt
   with markup in it.
2. A resume URL that redirects (e.g. `http://` to `https://`, or a
   personal site that 301s to `www.`) — expected: the redirect is
   followed and the final page's content is used, not a failure.
3. `--agent` passed but the value has different case or whitespace than
   the registry key (e.g. `"Claude"`) — expected: a clear `AgentError`
   naming valid options, not a silent `KeyError` traceback.
4. A connections.csv with a company name that matches the posting's
   extracted company only after normalization (e.g. "GitLab Inc." vs
   "GitLab") — expected: `find_referrals`'s existing normalization
   handles this already (reused unmodified), so this is a regression
   check, not new logic.
5. Running with no `--agent` and no `--resume` and no `connections.csv`
   present at all — expected: the tool still produces a usable prompt-only
   output, since every enrichment is optional by design.
