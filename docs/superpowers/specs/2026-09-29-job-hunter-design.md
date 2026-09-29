# Job Hunter — Design Spec

Date: 2026-09-29

## Purpose

A personal Python tool that periodically checks a configured list of
companies for new job openings matching the user's criteria (designation,
location, workplace type, recency), cross-references matches against the
user's own LinkedIn connections (self-maintained, since LinkedIn does not
expose this via API/export), and writes a Markdown report per run. It can
run once, or as a long-lived process on a self-managed interval.

## Constraints

- No LinkedIn scraping or use of LinkedIn's private APIs — LinkedIn's ToS
  prohibits this and it does not offer a public API for job search or for
  reading other users' profile/employer data. Only the user's own,
  manually-maintained data is used for referral matching.
- Job sourcing is limited to ATS platforms with public, unauthenticated
  JSON APIs (Greenhouse, Lever), plus a fallback generic crawler against a
  company's own public careers page (URL supplied by the user, no
  auto-discovery/guessing of that URL).
- Scheduling must be OS-agnostic: implemented inside the Python process
  (via the `schedule` library), not via cron/launchd/Task Scheduler.

## Architecture & Data Flow

```
config.yaml ─┐
             ▼
      ConfigLoader (validates companies, filters, paths; fails fast on
                     malformed YAML / missing required fields)
             │
             ▼
   For each company:
     1. Try Greenhouse connector (guess board_token = slugified name)
     2. Try Lever connector (same guess)
     3. If both fail and an explicit ats/board_token override is given
        in config → use it directly
     4. Else if a careers_url is given in config → generic crawler
        (JSON-LD schema.org/JobPosting first, heuristic HTML fallback)
     5. Else → flagged "unmatched" in the report, with a hint URL
        (boards.greenhouse.io/<slug>, jobs.lever.co/<slug>) to check
        manually
             │  (raw postings normalized into a shared Job shape)
             ▼
        Filters: title (substring, OR), location (substring, OR),
                 workplace_type (remote/hybrid/onsite; unknown → include),
                 posted_within_days (unknown date → include),
                 exclude_keywords (substring on title+description → drop)
             │
             ▼
        Referral Matcher: normalize company names (lowercase, trim,
                 strip Inc/LLC/Corp suffixes), exact-match against
                 connections.csv (name, company, title)
             │
             ▼
        Markdown Report Writer: one timestamped file per run in
                 output_dir
             │
             ▼
        Scheduler: --once (single run) or --daemon --interval <duration>
                 (loop via `schedule` library; per-run exceptions are
                 caught/logged, loop continues)
```

`Job` shared shape: `title, company, location, remote_type, url,
posted_date, description_snippet, source`.

## Module Layout

```
job_hunter/
  config.py          # load/validate YAML config
  connectors/
    base.py           # connector interface, shared Job dataclass
    greenhouse.py
    lever.py
    generic_crawler.py  # JSON-LD + heuristic HTML fallback
    autodetect.py       # tries greenhouse/lever against a company name
  filters.py           # title/location/workplace_type/date/keyword filtering
  referrals.py         # connections.csv normalization + matching
  report.py            # Markdown rendering
  scheduler.py          # --once / --daemon modes
main.py
config.example.yaml
connections.example.csv
tests/
  ...                  # mirrors module layout, pytest + responses/requests-mock
```

## Config Schema (`config.yaml`)

```yaml
companies:
  - name: Stripe                    # auto-detect tries Greenhouse then Lever
  - name: Airbnb
  - name: SomeStartup
    ats: greenhouse                 # explicit override, skips auto-detect
    board_token: some-startup
  - name: NicheCo
    careers_url: https://niche.co/careers   # generic crawler fallback

filters:
  designations:                     # substring match, case-insensitive, OR'd
    - "Software Engineer"
    - "Backend"
  locations:                        # substring match, case-insensitive, OR'd
    - "Austin"
    - "Remote"
  workplace_types:                  # subset of: remote, hybrid, onsite
    - remote
    - hybrid
  posted_within_days: 14
  exclude_keywords:                 # substring match against title+description
    - "Clearance required"
    - "Staff"

connections_csv: ./connections.csv   # columns: name, company, title

output_dir: ./reports

schedule:
  interval: 6h                      # used only in --daemon mode
```

## Filtering & Referral Matching Rules

- Title / location: case-insensitive substring, job passes if it matches
  *any* entry in the respective list.
- Workplace type: sourced from Lever's `workplaceType` field directly;
  Greenhouse/generic-crawler jobs use JSON-LD `jobLocationType` or
  Greenhouse custom metadata when present. Unknown → included, labeled
  "workplace type unknown."
- Posted-within-N-days: compares each connector's date field (Greenhouse
  `updated_at`, Lever `createdAt`, JSON-LD `datePosted`). Unknown →
  included, labeled "date unknown."
- Exclude keywords: hard filter, case-insensitive substring on title +
  description snippet; any match drops the job entirely.
- Referral matching: company names normalized (lowercase, trim, strip
  Inc/LLC/Corp suffixes) then exact-matched (not substring) against
  `connections.csv` to avoid false positives. Matches are attached to the
  job entry as a "Possible referrals" list (name + title).

## Error Handling

- Per-company fetch failures are isolated (logged as a warning in the
  report) and never abort the rest of the run.
- Transient errors (timeouts, 5xx) get one retry with ~2s backoff; 4xx
  errors are not retried (indicates a wrong token/URL, not a transient
  issue).
- Generic crawler pages with no JSON-LD and no heuristic match are
  reported as "no jobs found (page may need manual review)," distinct
  from a genuine zero-match result.
- Config is validated at startup; malformed YAML, missing required
  fields, or bad interval strings fail fast before any network calls.
- Malformed rows in `connections.csv` (missing required columns) are
  skipped with a warning; well-formed rows are unaffected.
- In `--daemon` mode, an unhandled exception during one scheduled run is
  caught and logged; the loop continues to the next scheduled run.

## Testing Approach

- `pytest`, with all HTTP calls mocked (`responses` or `requests-mock`) —
  no test hits a live API.
- Connector tests use trimmed real-world fixture JSON/HTML to verify
  normalization into the shared `Job` shape and correct auto-detect slug
  guessing / JSON-LD parsing.
- Filter tests are pure unit tests covering substring matching, the
  unknown-workplace-type and unknown-date inclusion rules, and keyword
  exclusion.
- Referral matcher tests cover company-name normalization edge cases
  (suffixes, casing, whitespace) and exact-match behavior.
- Report writer tests assert expected Markdown structure for a given set
  of jobs + referral matches.
- Config validation tests assert fail-fast behavior for malformed
  input.
- Not automated: live calls to Greenhouse/Lever/a real careers page —
  a manual smoke test after setup, not part of the test suite.

## Out of Scope (v1)

- ATS platforms beyond Greenhouse/Lever/generic-crawler (e.g. Workday,
  SmartRecruiters, iCIMS).
- Auto-discovery of a company's careers page URL.
- Any LinkedIn scraping or automated LinkedIn data import.
- Email/Slack delivery of reports (Markdown file only).
- Salary filtering (not reliably available across sources).
