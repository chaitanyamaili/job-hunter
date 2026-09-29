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
