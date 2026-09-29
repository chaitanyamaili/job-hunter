from __future__ import annotations

import logging
import time

import schedule as schedule_lib

from .pipeline import run_once

logger = logging.getLogger(__name__)

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _interval_to_seconds(interval: str) -> int:
    amount = int(interval[:-1])
    unit = interval[-1]
    return amount * _UNIT_SECONDS[unit]


def run_daemon(config_path: str, interval: str) -> None:
    def _job() -> None:
        try:
            path = run_once(config_path)
            logger.info("Report written to %s", path)
        except Exception:
            logger.exception("Scheduled run failed; will retry next interval")

    schedule_lib.every(_interval_to_seconds(interval)).seconds.do(_job)
    _job()
    while True:
        schedule_lib.run_pending()
        time.sleep(1)
