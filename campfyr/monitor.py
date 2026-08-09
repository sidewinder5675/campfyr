"""Availability checks and alert de-duplication."""

import hashlib
import json
import logging
from datetime import date, timedelta

from . import db
from .notifications import build_sender
from .recreation import RecreationClient


LOG = logging.getLogger(__name__)


class MonitorService:
    def __init__(self, database_path, recreation=None, notifier=None):
        self.database_path = database_path
        self.recreation = recreation or RecreationClient()
        self.notifier = notifier or build_sender()

    def check_watch(self, watch_id, notify=True):
        watch = db.get_watch(self.database_path, watch_id)
        if watch is None:
            raise KeyError("Watch not found")

        start_date = date.fromisoformat(watch["start_date"])
        end_date = date.fromisoformat(watch["end_date"])
        if end_date <= date.today():
            return db.update_watch(
                self.database_path,
                watch_id,
                is_active=False,
                status="expired",
                available_site_count=0,
                available_sites_json="[]",
                last_checked_at=db.utc_now(),
                last_error=None,
                notification_key="",
            )

        try:
            sites = self.recreation.find_matches(
                watch["campground_id"], start_date, end_date, watch["match_mode"]
            )
            status = "available" if sites else "unavailable"
            key = _site_key(sites)
            previous_tokens = _availability_tokens(watch["available_sites"])
            current_tokens = _availability_tokens(sites)
            newly_available = current_tokens - previous_tokens
            should_notify = bool(sites) and (
                not watch["notification_key"] or bool(newly_available)
            )

            changes = {
                "status": status,
                "available_site_count": len(sites),
                "available_sites_json": json.dumps(sites, separators=(",", ":")),
                "last_checked_at": db.utc_now(),
                "last_error": None,
            }

            if not sites:
                changes["notification_key"] = ""
            elif notify and should_notify:
                result = self.notifier.send(_availability_message(watch, sites))
                if result["status"] != "not_configured":
                    db.add_notification(self.database_path, watch_id, result)
                if result["status"] == "sent":
                    changes["notification_key"] = key
                    changes["last_notified_at"] = db.utc_now()

            return db.update_watch(self.database_path, watch_id, **changes)
        except Exception as exc:
            LOG.exception("Availability check failed for watch %s", watch_id)
            db.update_watch(
                self.database_path,
                watch_id,
                status="error",
                last_checked_at=db.utc_now(),
                last_error=str(exc)[:500],
            )
            raise

    def check_all(self, notify=True):
        results = []
        for watch in db.list_watches(self.database_path, active_only=True):
            try:
                checked = self.check_watch(watch["id"], notify=notify)
                results.append({"id": watch["id"], "status": checked["status"]})
            except Exception as exc:
                results.append({"id": watch["id"], "status": "error", "error": str(exc)})
        return results


def _site_key(sites):
    if not sites:
        return ""
    value = ",".join(sorted(_availability_tokens(sites)))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _availability_tokens(sites):
    tokens = set()
    for site in sites:
        nights = site.get("available_nights")
        if nights:
            tokens.update("{}:{}".format(site["id"], night) for night in nights)
        else:
            tokens.add(site["id"])
    return tokens


def _availability_message(watch, sites):
    checkout = date.fromisoformat(watch["end_date"])
    last_night = checkout - timedelta(days=1)
    if watch["match_mode"] == "any_night":
        site_names = "; ".join(
            "{}: {}".format(site["site"], ", ".join(site["available_nights"]))
            for site in sites[:6]
        )
        window_text = "between {start} and {last_night}".format(
            start=watch["start_date"], last_night=last_night.isoformat()
        )
    else:
        site_names = ", ".join(site["site"] for site in sites[:8])
        window_text = "for {start}–{last_night}".format(
            start=watch["start_date"], last_night=last_night.isoformat()
        )
    if len(sites) > (6 if watch["match_mode"] == "any_night" else 8):
        site_names += " +{} more".format(
            len(sites) - (6 if watch["match_mode"] == "any_night" else 8)
        )
    return (
        "Campfyr found {count} site{plural} at {name} {window}. "
        "Sites: {sites}. Book now: {url}"
    ).format(
        count=len(sites),
        plural="" if len(sites) == 1 else "s",
        name=watch["campground_name"],
        window=window_text,
        sites=site_names,
        url=watch["campground_url"],
    )
