"""SQLite persistence for Campfyr."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id TEXT PRIMARY KEY,
    campground_id TEXT NOT NULL,
    campground_name TEXT NOT NULL,
    campground_url TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    match_mode TEXT NOT NULL DEFAULT 'entire_stay',
    is_active INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    available_site_count INTEGER NOT NULL DEFAULT 0,
    available_sites_json TEXT NOT NULL DEFAULT '[]',
    notification_key TEXT NOT NULL DEFAULT '',
    last_checked_at TEXT,
    last_notified_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_watches_active_dates
ON watches(is_active, start_date, end_date);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    provider_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (watch_id) REFERENCES watches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worker_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_seen_at TEXT,
    last_cycle_completed_at TEXT,
    last_error TEXT
);

INSERT OR IGNORE INTO worker_state(id) VALUES (1);
"""


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(database_path):
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_database(database_path):
    with connect(database_path) as connection:
        connection.executescript(SCHEMA)
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(watches)").fetchall()
        }
        if "match_mode" not in columns:
            connection.execute(
                "ALTER TABLE watches ADD COLUMN match_mode TEXT NOT NULL DEFAULT 'entire_stay'"
            )


def _watch_from_row(row):
    if row is None:
        return None
    watch = dict(row)
    watch["is_active"] = bool(watch["is_active"])
    watch["available_sites"] = json.loads(watch.pop("available_sites_json") or "[]")
    return watch


def list_watches(database_path, active_only=False):
    sql = "SELECT * FROM watches"
    params = []
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY start_date ASC, campground_name COLLATE NOCASE ASC, created_at ASC"
    with connect(database_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [_watch_from_row(row) for row in rows]


def get_watch(database_path, watch_id):
    with connect(database_path) as connection:
        row = connection.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone()
    return _watch_from_row(row)


def insert_watch(database_path, watch):
    now = utc_now()
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO watches (
                id, campground_id, campground_name, campground_url,
                start_date, end_date, match_mode, is_active, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watch["id"],
                watch["campground_id"],
                watch["campground_name"],
                watch["campground_url"],
                watch["start_date"],
                watch["end_date"],
                watch.get("match_mode", "entire_stay"),
                int(watch.get("is_active", True)),
                watch.get("status", "pending"),
                now,
                now,
            ),
        )
    return get_watch(database_path, watch["id"])


def update_watch(database_path, watch_id, **changes):
    allowed = {
        "is_active",
        "status",
        "available_site_count",
        "available_sites_json",
        "notification_key",
        "last_checked_at",
        "last_notified_at",
        "last_error",
    }
    invalid = set(changes) - allowed
    if invalid:
        raise ValueError("Unsupported watch fields: {}".format(", ".join(sorted(invalid))))
    if not changes:
        return get_watch(database_path, watch_id)

    changes["updated_at"] = utc_now()
    fields = ", ".join("{} = ?".format(name) for name in changes)
    values = [int(value) if name == "is_active" else value for name, value in changes.items()]
    values.append(watch_id)
    with connect(database_path) as connection:
        connection.execute("UPDATE watches SET {} WHERE id = ?".format(fields), values)
    return get_watch(database_path, watch_id)


def delete_watch(database_path, watch_id):
    with connect(database_path) as connection:
        cursor = connection.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
        return cursor.rowcount > 0


def add_notification(database_path, watch_id, result):
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO notifications (
                watch_id, channel, recipient, status, message,
                provider_id, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watch_id,
                result.get("channel", "sms"),
                result.get("recipient", ""),
                result["status"],
                result["message"],
                result.get("provider_id"),
                result.get("error"),
                utc_now(),
            ),
        )


def list_notifications(database_path, limit=20):
    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT notifications.*, watches.campground_name
            FROM notifications
            JOIN watches ON watches.id = notifications.watch_id
            ORDER BY notifications.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_worker_state(database_path, completed=False, error=None):
    now = utc_now()
    with connect(database_path) as connection:
        if completed:
            connection.execute(
                """
                UPDATE worker_state
                SET last_seen_at = ?, last_cycle_completed_at = ?, last_error = ?
                WHERE id = 1
                """,
                (now, now, error),
            )
        else:
            connection.execute(
                "UPDATE worker_state SET last_seen_at = ?, last_error = ? WHERE id = 1",
                (now, error),
            )


def get_worker_state(database_path):
    with connect(database_path) as connection:
        row = connection.execute("SELECT * FROM worker_state WHERE id = 1").fetchone()
    return dict(row) if row else {}
