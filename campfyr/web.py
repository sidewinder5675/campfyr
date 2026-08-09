"""Web UI and JSON API."""

import os
import uuid
from datetime import date, datetime, timezone

from flask import Blueprint, current_app, jsonify, render_template, request

from . import db
from .monitor import MonitorService
from .notifications import build_sender
from .recreation import RecreationClient, RecreationError


web = Blueprint("web", __name__)


def _database_path():
    return current_app.config["DATABASE_PATH"]


def _client():
    return RecreationClient(timeout=current_app.config["RECREATION_TIMEOUT_SECONDS"])


@web.get("/")
def index():
    return render_template("index.html")


@web.get("/healthz")
def health():
    with db.connect(_database_path()) as connection:
        connection.execute("SELECT 1").fetchone()
    return jsonify({"status": "ok"})


@web.get("/api/status")
def status():
    sender = build_sender()
    provider = os.getenv("NOTIFICATION_PROVIDER", "pushover").strip().lower()
    worker_state = db.get_worker_state(_database_path())
    interval = current_app.config["CHECK_INTERVAL_SECONDS"]
    worker_state["is_running"] = _worker_is_fresh(worker_state.get("last_seen_at"), interval)
    return jsonify(
        {
            "version": "2.0.0",
            "notification_provider": provider,
            "notifications_configured": sender.configured,
            "check_interval_seconds": interval,
            "worker": worker_state,
        }
    )


@web.get("/api/watches")
def watches():
    return jsonify(db.list_watches(_database_path()))


@web.post("/api/watches")
def add_watch():
    payload = request.get_json(silent=True) or {}
    campground_value = payload.get("campground_url", "")
    try:
        campground_id = RecreationClient.extract_campground_id(campground_value)
        start_date, end_date = _validate_dates(
            payload.get("start_date"), payload.get("end_date")
        )
        match_mode = payload.get("match_mode", "entire_stay")
        if match_mode not in ("entire_stay", "any_night"):
            raise ValueError("Choose whole-trip or any-night matching.")
    except (TypeError, ValueError) as exc:
        return _error(str(exc), 400)

    for existing in db.list_watches(_database_path()):
        if (
            existing["campground_id"] == campground_id
            and existing["start_date"] == start_date.isoformat()
            and existing["end_date"] == end_date.isoformat()
            and existing["match_mode"] == match_mode
        ):
            return _error("You are already watching that campground for those dates.", 409)

    try:
        campground = _client().get_campground(campground_id)
    except RecreationError as exc:
        return _error(str(exc), 502)

    watch = db.insert_watch(
        _database_path(),
        {
            "id": str(uuid.uuid4()),
            "campground_id": campground_id,
            "campground_name": campground["name"],
            "campground_url": RecreationClient.canonical_url(campground_id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "match_mode": match_mode,
        },
    )
    return jsonify(watch), 201


@web.delete("/api/watches/<watch_id>")
def remove_watch(watch_id):
    if not db.delete_watch(_database_path(), watch_id):
        return _error("Watch not found.", 404)
    return "", 204


@web.post("/api/watches/<watch_id>/active")
def set_watch_active(watch_id):
    watch = db.get_watch(_database_path(), watch_id)
    if watch is None:
        return _error("Watch not found.", 404)
    payload = request.get_json(silent=True) or {}
    active = payload.get("active")
    if not isinstance(active, bool):
        return _error("The active field must be true or false.", 400)
    if active and date.fromisoformat(watch["end_date"]) <= date.today():
        return _error("An expired watch cannot be resumed.", 400)
    updated = db.update_watch(
        _database_path(),
        watch_id,
        is_active=active,
        status="pending" if active else "paused",
        last_error=None,
    )
    return jsonify(updated)


@web.post("/api/watches/<watch_id>/check")
def check_watch(watch_id):
    if db.get_watch(_database_path(), watch_id) is None:
        return _error("Watch not found.", 404)
    try:
        checked = MonitorService(_database_path(), recreation=_client()).check_watch(watch_id)
    except Exception as exc:
        return _error(str(exc), 502)
    return jsonify(checked)


@web.post("/api/check-all")
def check_all():
    results = MonitorService(_database_path(), recreation=_client()).check_all()
    status_code = 207 if any(item["status"] == "error" for item in results) else 200
    return jsonify({"results": results}), status_code


@web.get("/api/notifications")
def notifications():
    return jsonify(db.list_notifications(_database_path(), limit=20))


@web.post("/api/notifications/test")
def test_notification():
    sender = build_sender()
    result = sender.send("Campfyr test: notifications are working. 🏕️")
    if result["status"] == "not_configured":
        return _error(result["error"], 400)
    if result["status"] != "sent":
        return _error("Test notification failed: {}".format(result.get("error", "unknown error")), 502)
    return jsonify({"message": "Test notification sent.", "provider": result["channel"]})


def _validate_dates(start_value, end_value):
    try:
        start_date = date.fromisoformat(str(start_value))
        end_date = date.fromisoformat(str(end_value))
    except (TypeError, ValueError):
        raise ValueError("Arrival and checkout must be valid dates.")
    if start_date < date.today():
        raise ValueError("Arrival cannot be in the past.")
    if end_date <= start_date:
        raise ValueError("Checkout must be after arrival.")
    if (end_date - start_date).days > 30:
        raise ValueError("A watch can cover at most 30 nights.")
    return start_date, end_date


def _worker_is_fresh(timestamp, interval):
    if not timestamp:
        return False
    try:
        seen = datetime.fromisoformat(timestamp)
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - seen).total_seconds()
        return age <= max(interval * 2.5, 90)
    except ValueError:
        return False


def _error(message, status_code):
    return jsonify({"error": message}), status_code
