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
