import base64
from datetime import date, timedelta

import pytest

from campfyr import create_app
import campfyr.web as web_module


class FakeClient:
    def get_campground(self, campground_id):
        return {"id": campground_id, "name": "SARDINE LAKE"}

    def find_matches(self, campground_id, start_date, end_date, match_mode):
        return []


@pytest.fixture
def app(tmp_path, monkeypatch):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test.db"),
            "CAMPFYR_USERNAME": "",
            "CAMPFYR_PASSWORD": "",
        }
    )
    monkeypatch.setattr(web_module, "_client", lambda: FakeClient())
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def future_trip():
    start = date.today() + timedelta(days=20)
    return start.isoformat(), (start + timedelta(days=3)).isoformat()


def test_watch_lifecycle(client):
    start, end = future_trip()
    response = client.post(
        "/api/watches",
        json={
            "campground_url": "https://www.recreation.gov/camping/campgrounds/234539",
            "start_date": start,
            "end_date": end,
        },
    )
    assert response.status_code == 201
    watch = response.get_json()
    assert watch["campground_name"] == "SARDINE LAKE"

    duplicate = client.post(
        "/api/watches",
        json={"campground_url": "234539", "start_date": start, "end_date": end},
    )
    assert duplicate.status_code == 409

    paused = client.post("/api/watches/{}/active".format(watch["id"]), json={"active": False})
    assert paused.status_code == 200
    assert paused.get_json()["status"] == "paused"

    deleted = client.delete("/api/watches/{}".format(watch["id"]))
    assert deleted.status_code == 204
    assert client.get("/api/watches").get_json() == []


def test_date_validation(client):
    start, end = future_trip()
    response = client.post(
        "/api/watches",
        json={"campground_url": "234539", "start_date": end, "end_date": start},
    )
    assert response.status_code == 400
    assert "Checkout" in response.get_json()["error"]


def test_optional_auth_does_not_block_health_check(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "auth.db"),
            "CAMPFYR_USERNAME": "camper",
            "CAMPFYR_PASSWORD": "secret",
        }
    )
    client = app.test_client()
    assert client.get("/").status_code == 401
    assert client.get("/healthz").status_code == 200

    credentials = base64.b64encode(b"camper:secret").decode("ascii")
    response = client.get("/", headers={"Authorization": "Basic {}".format(credentials)})
    assert response.status_code == 200


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
