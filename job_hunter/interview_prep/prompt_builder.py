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
