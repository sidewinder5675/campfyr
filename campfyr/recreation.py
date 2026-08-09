"""Small, defensive client for Recreation.gov campground availability."""

import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class RecreationError(RuntimeError):
    pass


class RecreationClient:
    BASE_URL = "https://www.recreation.gov"
    CAMPGROUND_URL = BASE_URL + "/api/camps/campgrounds/{campground_id}"
    AVAILABILITY_URL = (
        BASE_URL + "/api/camps/availability/campground/{campground_id}/month"
    )
    ALLOWED_HOSTS = {"recreation.gov", "www.recreation.gov", "mobile.recreation.gov"}

    def __init__(self, timeout=20, cache_seconds=60, session=None):
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self.session = session or self._build_session()
        self._month_cache = {}

    @staticmethod
    def _build_session():
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            respect_retry_after_header=True,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "Campfyr/2.0 campsite availability monitor",
            }
        )
        return session

    @classmethod
    def extract_campground_id(cls, value):
        raw = str(value or "").strip()
        if re.fullmatch(r"\d{5,10}", raw):
            return raw

        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in cls.ALLOWED_HOSTS:
            raise ValueError("Enter a Recreation.gov campground URL or campground ID.")

        match = re.search(r"/camping/campgrounds/(\d+)(?:/|$)", parsed.path)
        if not match:
            raise ValueError("That URL does not look like a Recreation.gov campground page.")
        return match.group(1)

    @staticmethod
    def canonical_url(campground_id):
        return "https://www.recreation.gov/camping/campgrounds/{}".format(campground_id)

    def _get_json(self, url, params=None):
        try:
            response = self.session.get(url, params=params or {}, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RecreationError("Recreation.gov request failed: {}".format(exc)) from exc
        if not isinstance(payload, dict):
            raise RecreationError("Recreation.gov returned an unexpected response.")
        return payload

    def get_campground(self, campground_id):
        payload = self._get_json(self.CAMPGROUND_URL.format(campground_id=campground_id))
        campground = payload.get("campground")
        if not isinstance(campground, dict) or not campground.get("facility_name"):
            raise RecreationError("Recreation.gov did not return campground details.")
        return {
            "id": str(campground.get("facility_id", campground_id)),
            "name": campground["facility_name"].strip(),
        }

    def get_month(self, campground_id, month):
        month_start = month.replace(day=1)
        key = (str(campground_id), month_start.isoformat())
        cached = self._month_cache.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_seconds:
            return cached[1]

        payload = self._get_json(
            self.AVAILABILITY_URL.format(campground_id=campground_id),
            {"start_date": month_start.strftime("%Y-%m-%dT00:00:00.000Z")},
        )
        campsites = payload.get("campsites")
        if not isinstance(campsites, dict):
            raise RecreationError("Recreation.gov returned no campsite availability data.")
        self._month_cache[key] = (time.monotonic(), campsites)
        return campsites

    def find_available_sites(self, campground_id, start_date, end_date):
        """Return sites available for every night in [start_date, end_date)."""
        nights, merged = self._availability_for_window(campground_id, start_date, end_date)

        available = []
        for campsite in merged.values():
            statuses = campsite["availabilities"]
            if all(statuses.get(_api_date(night)) == "Available" for night in nights):
                available.append(_public_site(campsite))

        return sorted(available, key=lambda site: _natural_key(site["site"]))

    def find_any_night_sites(self, campground_id, start_date, end_date):
        """Return sites with at least one available night in [start_date, end_date)."""
        nights, merged = self._availability_for_window(campground_id, start_date, end_date)
        available = []
        for campsite in merged.values():
            open_nights = [
                night.isoformat()
                for night in nights
                if campsite["availabilities"].get(_api_date(night)) == "Available"
            ]
            if open_nights:
                site = _public_site(campsite)
                site["available_nights"] = open_nights
                available.append(site)
        return sorted(available, key=lambda site: _natural_key(site["site"]))

    def find_matches(self, campground_id, start_date, end_date, match_mode="entire_stay"):
        if match_mode == "entire_stay":
            return self.find_available_sites(campground_id, start_date, end_date)
        if match_mode == "any_night":
            return self.find_any_night_sites(campground_id, start_date, end_date)
        raise ValueError("Unknown match mode: {}".format(match_mode))

    def _availability_for_window(self, campground_id, start_date, end_date):
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            raise TypeError("start_date and end_date must be date objects")
        if start_date >= end_date:
            raise ValueError("Checkout must be after arrival.")

        nights = []
        current = start_date
        while current < end_date:
            nights.append(current)
            current += timedelta(days=1)

        months = sorted({night.replace(day=1) for night in nights})
        merged = {}
        for month in months:
            for campsite_id, campsite in self.get_month(campground_id, month).items():
                target = merged.setdefault(
                    str(campsite_id),
                    {
                        "id": str(campsite_id),
                        "site": str(campsite.get("site") or campsite_id),
                        "loop": str(campsite.get("loop") or ""),
                        "type": str(campsite.get("campsite_type") or ""),
                        "availabilities": {},
                    },
                )
                target["availabilities"].update(campsite.get("availabilities") or {})

        return nights, merged


def _api_date(value):
    return value.strftime("%Y-%m-%dT00:00:00Z")


def _natural_key(value):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _public_site(campsite):
    return {
        "id": campsite["id"],
        "site": campsite["site"],
        "loop": campsite["loop"],
        "type": campsite["type"],
    }
