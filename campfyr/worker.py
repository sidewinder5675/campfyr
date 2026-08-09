"""Dedicated monitoring worker for Docker or one-shot schedulers such as Chronos."""

import argparse
import logging
import os
import signal
import threading

from .db import init_database, update_worker_state
from .monitor import MonitorService
from .recreation import RecreationClient


LOG = logging.getLogger(__name__)


def run_cycle(database_path, timeout=20):
    update_worker_state(database_path)
    service = MonitorService(
        database_path,
        recreation=RecreationClient(timeout=timeout, cache_seconds=90),
    )
    results = service.check_all(notify=True)
    errors = [result for result in results if result["status"] == "error"]
    error_text = "{} watch(es) failed".format(len(errors)) if errors else None
    update_worker_state(database_path, completed=True, error=error_text)
    LOG.info("Check complete: %s watch(es), %s error(s)", len(results), len(errors))
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check Campfyr watches")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle and exit (useful with Chronos or cron)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
    database_path = os.getenv("CAMPFYR_DATABASE_PATH", "/data/campfyr.db")
    interval = max(60, int(os.getenv("CHECK_INTERVAL_SECONDS", "600")))
    timeout = int(os.getenv("RECREATION_TIMEOUT_SECONDS", "20"))
    init_database(database_path)

    if args.once:
        return run_cycle(database_path, timeout=timeout)

    stop = threading.Event()

    def request_stop(signum, frame):
        LOG.info("Stopping worker after signal %s", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    LOG.info("Campfyr worker started; checking every %s seconds", interval)
    while not stop.is_set():
        try:
            run_cycle(database_path, timeout=timeout)
        except Exception as exc:
            LOG.exception("Worker cycle failed")
            update_worker_state(database_path, completed=True, error=str(exc)[:500])
        stop.wait(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
