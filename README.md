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
