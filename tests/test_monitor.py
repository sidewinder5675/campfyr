from datetime import date, timedelta

from campfyr import db
from campfyr.monitor import MonitorService


class FakeRecreation:
    def __init__(self, sites):
        self.sites = sites

    def find_matches(self, campground_id, start_date, end_date, match_mode):
        return self.sites


class FakeNotifier:
    configured = True

    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return {
            "channel": "pushover",
            "recipient": "Pushover user",
            "status": "sent",
            "message": message,
            "provider_id": "request-123",
        }


def create_watch(database_path):
    start = date.today() + timedelta(days=10)
    end = start + timedelta(days=2)
    return db.insert_watch(
        database_path,
        {
            "id": "watch-1",
            "campground_id": "234539",
            "campground_name": "SARDINE LAKE",
            "campground_url": "https://www.recreation.gov/camping/campgrounds/234539",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )


def test_alerts_once_then_only_for_new_availability(tmp_path):
    database_path = str(tmp_path / "campfyr.db")
    db.init_database(database_path)
    create_watch(database_path)
    recreation = FakeRecreation([{"id": "1", "site": "001", "loop": "A", "type": "Tent"}])
    notifier = FakeNotifier()
    service = MonitorService(database_path, recreation=recreation, notifier=notifier)

    first = service.check_watch("watch-1")
    second = service.check_watch("watch-1")

    assert first["status"] == "available"
    assert second["status"] == "available"
    assert len(notifier.messages) == 1
    assert len(db.list_notifications(database_path)) == 1

    recreation.sites.append({"id": "2", "site": "002", "loop": "A", "type": "Tent"})
    service.check_watch("watch-1")
    assert len(notifier.messages) == 2

    recreation.sites = [recreation.sites[0]]
    service.check_watch("watch-1")
    assert len(notifier.messages) == 2

    recreation.sites = []
    service.check_watch("watch-1")
    recreation.sites = [{"id": "1", "site": "001", "loop": "A", "type": "Tent"}]
    service.check_watch("watch-1")
    assert len(notifier.messages) == 3


def test_expired_watch_is_automatically_disabled(tmp_path):
    database_path = str(tmp_path / "campfyr.db")
    db.init_database(database_path)
    yesterday = date.today() - timedelta(days=1)
    db.insert_watch(
        database_path,
        {
            "id": "expired",
            "campground_id": "234539",
            "campground_name": "Old trip",
            "campground_url": "https://www.recreation.gov/camping/campgrounds/234539",
            "start_date": (yesterday - timedelta(days=2)).isoformat(),
            "end_date": yesterday.isoformat(),
        },
    )
    service = MonitorService(database_path, recreation=FakeRecreation([]), notifier=FakeNotifier())
    result = service.check_watch("expired")

    assert result["status"] == "expired"
    assert result["is_active"] is False
