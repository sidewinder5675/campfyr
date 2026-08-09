"""Import watches from the original campSiteRequests.json format."""

import argparse
import json
import os
import uuid
from datetime import date, timedelta

from . import db
from .recreation import RecreationClient


def import_json(database_path, json_path):
    with open(json_path, "r", encoding="utf-8") as source:
        entries = json.load(source)
    if not isinstance(entries, list):
        raise ValueError("Legacy JSON must contain a list of watches.")

    db.init_database(database_path)
    existing = {
        (watch["campground_id"], watch["start_date"], watch["end_date"])
        for watch in db.list_watches(database_path)
    }
    imported = 0
    skipped = 0
    for entry in entries:
        campground_id = str(
            entry.get("campground_id")
            or RecreationClient.extract_campground_id(entry.get("campground_url"))
        )
        legacy_end = date.fromisoformat(entry["end_date"])
        checkout = legacy_end + timedelta(days=1)
        key = (campground_id, entry["start_date"], checkout.isoformat())
        if key in existing:
            skipped += 1
            continue
        expired = checkout <= date.today()
        db.insert_watch(
            database_path,
            {
                "id": str(uuid.uuid4()),
                "campground_id": campground_id,
                "campground_name": entry.get("campground_name") or "Campground {}".format(campground_id),
                "campground_url": RecreationClient.canonical_url(campground_id),
                "start_date": entry["start_date"],
                "end_date": checkout.isoformat(),
                "match_mode": "any_night",
                "is_active": not expired,
                "status": "expired" if expired else "pending",
            },
        )
        existing.add(key)
        imported += 1
    return imported, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", help="Path to campSiteRequests.json")
    parser.add_argument(
        "--database",
        default=os.getenv("CAMPFYR_DATABASE_PATH", "/data/campfyr.db"),
        help="SQLite destination (defaults to CAMPFYR_DATABASE_PATH)",
    )
    args = parser.parse_args(argv)
    imported, skipped = import_json(args.database, args.json_path)
    print("Imported {} watch(es); skipped {} duplicate(s).".format(imported, skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
