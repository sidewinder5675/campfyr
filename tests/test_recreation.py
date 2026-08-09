from datetime import date

import pytest

from campfyr.recreation import RecreationClient


def campsite(site, availabilities):
    return {
        "site": site,
        "loop": "Pine Loop",
        "campsite_type": "STANDARD NONELECTRIC",
        "availabilities": availabilities,
    }


@pytest.mark.parametrize(
    "value, expected",
    [
        ("234539", "234539"),
        ("https://www.recreation.gov/camping/campgrounds/234539", "234539"),
        ("https://www.recreation.gov/camping/campgrounds/234539/availability", "234539"),
        ("https://mobile.recreation.gov/camping/campgrounds/234539?tab=seasons", "234539"),
    ],
)
def test_extract_campground_id(value, expected):
    assert RecreationClient.extract_campground_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://example.com/camping/campgrounds/234539",
        "https://www.recreation.gov/search?q=234539",
        "not a campground",
    ],
)
def test_rejects_non_campground_inputs(value):
    with pytest.raises(ValueError):
        RecreationClient.extract_campground_id(value)


def test_find_available_sites_requires_every_night_across_months(monkeypatch):
    client = RecreationClient()
    january = {
        "1": campsite("001", {"2027-01-31T00:00:00Z": "Available"}),
        "2": campsite("002", {"2027-01-31T00:00:00Z": "Reserved"}),
    }
    february = {
        "1": campsite("001", {"2027-02-01T00:00:00Z": "Available"}),
        "2": campsite("002", {"2027-02-01T00:00:00Z": "Available"}),
        "3": campsite("003", {"2027-02-01T00:00:00Z": "Available"}),
    }

    def fake_month(campground_id, month):
        return january if month.month == 1 else february

    monkeypatch.setattr(client, "get_month", fake_month)
    result = client.find_available_sites("234539", date(2027, 1, 31), date(2027, 2, 2))

    assert [site["id"] for site in result] == ["1"]


def test_checkout_date_is_not_required(monkeypatch):
    client = RecreationClient()
    monkeypatch.setattr(
        client,
        "get_month",
        lambda campground_id, month: {
            "1": campsite(
                "001",
                {
                    "2027-06-10T00:00:00Z": "Available",
                    "2027-06-11T00:00:00Z": "Reserved",
                },
            )
        },
    )

    result = client.find_available_sites("234539", date(2027, 6, 10), date(2027, 6, 11))
    assert [site["id"] for site in result] == ["1"]


def test_any_night_mode_keeps_available_dates(monkeypatch):
    client = RecreationClient()
    monkeypatch.setattr(
        client,
        "get_month",
        lambda campground_id, month: {
            "1": campsite(
                "001",
                {
                    "2027-06-10T00:00:00Z": "Reserved",
                    "2027-06-11T00:00:00Z": "Available",
                },
            )
        },
    )

    result = client.find_any_night_sites("234539", date(2027, 6, 10), date(2027, 6, 12))
    assert result[0]["available_nights"] == ["2027-06-11"]
