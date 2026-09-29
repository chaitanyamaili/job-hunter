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
