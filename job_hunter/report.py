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
