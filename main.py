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
