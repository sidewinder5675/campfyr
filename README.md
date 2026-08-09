# Campfyr

Campfyr watches Recreation.gov campgrounds for a campsite that is available for an entire stay—or for any open night in a flexible window—then sends a Pushover notification with the open site numbers and booking link.

This version combines the original Flask/JSON front end and the separate Chronos/`camply` script into one durable service.

## What changed

- Two match modes: require one site for the whole trip, or preserve the original Chronos behavior and alert on any single open night in the window.
- Pushover notifications are de-duplicated. Campfyr alerts once when availability appears, then again only if another site opens or availability disappears and later returns.
- A dedicated background worker checks every 10 minutes by default. A `--once` mode remains available for Chronos or cron.
- SQLite replaces a shared JSON file, avoiding lost writes and corrupted data when the UI and checker run together.
- Dates, Recreation.gov URLs, network responses, and API errors are validated.
- Checks retry temporary Recreation.gov failures and use timeouts.
- The UI shows worker health, check results, available site numbers, errors, pause/resume controls, and a Pushover test.
- Docker runs as an unprivileged user and keeps its database in a named volume.
- Optional HTTP Basic authentication is available for installs exposed beyond a trusted LAN.

## Quick start on a NAS

Requirements: Docker Engine and Docker Compose.

1. Copy the environment template and add the two Pushover values:

   ```sh
   cp .env.example .env
   ```

   Edit `.env`:

   ```dotenv
   NOTIFICATION_PROVIDER=pushover
   PUSHOVER_USER_KEY=your_user_key
   PUSHOVER_API_TOKEN=your_application_token
   ```

   The user key comes from your Pushover dashboard. The application token is the same token used by the old `config.json` script. Keep both values private.

2. Build and start both services:

   ```sh
   docker compose up -d --build
   ```

3. Open `http://YOUR-NAS-IP:5001`, add a campground, and use **Send a test** to verify Pushover.

4. Inspect service health when needed:

   ```sh
   docker compose ps
   docker compose logs -f worker
   ```

The `campfyr-data` Docker volume contains the SQLite database. Back up that volume as part of the NAS backup routine.

## Pushover setup

Campfyr uses Pushover's HTTPS Message API. If the existing keys are stored in `config.json`, move the values without copying the file into the image:

| Old `config.json` key | New `.env` key |
| --- | --- |
| `pushover_user_key` | `PUSHOVER_USER_KEY` |
| `pushover_api_token` | `PUSHOVER_API_TOKEN` |

The UI works without notification keys, but no availability alert will be sent until both values are configured and the containers are restarted.

## Import the old watchlist

The old `campSiteRequests.json` format can be imported. Duplicate campground/date combinations are skipped, and past trips are retained as expired watches. Imported watches use **Any single open night** mode. Because the old date range was inclusive, the importer converts its final date to the new checkout-style date by adding one day.

With a local Docker checkout:

```sh
docker compose run --rm web python -m campfyr.migrate /app/campSiteRequests.json
```

To import a different file, temporarily copy it into the repository or mount it into the container, then pass its container path to the same command.

## Keep using Chronos (optional)

The included worker is the simplest setup and does not require Chronos. To let Chronos own the schedule instead:

1. Stop and disable the `worker` service.
2. Run this command from a container that mounts the same `/data` volume and uses the same `.env`:

   ```sh
   python -m campfyr.worker --once
   ```

Schedule it every 600 seconds. Never run the continuous worker and a Chronos one-shot job at the same time, or both may check and notify concurrently.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `NOTIFICATION_PROVIDER` | `pushover` | `pushover` or optional `twilio` |
| `PUSHOVER_USER_KEY` | empty | Pushover user or group key |
| `PUSHOVER_API_TOKEN` | empty | Pushover application API token |
| `CHECK_INTERVAL_SECONDS` | `600` | Background interval; minimum worker interval is 60 seconds |
| `RECREATION_TIMEOUT_SECONDS` | `20` | Per-request network timeout |
| `CAMPFYR_USERNAME` | empty | Enables HTTP Basic authentication when paired with a password |
| `CAMPFYR_PASSWORD` | empty | Enables HTTP Basic authentication when paired with a username |
| `CAMPFYR_DATABASE_PATH` | `/data/campfyr.db` in Docker | SQLite database location |
| `LOG_LEVEL` | `INFO` | Worker log level |

Twilio remains available as an optional SMS provider by setting `NOTIFICATION_PROVIDER=twilio` and the four `TWILIO_*` values in `.env`.

## Development and tests

Campfyr targets Python 3.12.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Run the web app locally:

```sh
flask --app 'campfyr:create_app()' run --port 5001 --debug
```

Use a local database path before running the worker outside Docker:

```sh
export CAMPFYR_DATABASE_PATH=instance/campfyr.db
python -m campfyr.worker
```

## Availability semantics

**One site for the whole trip** requires the same campsite to be available on every camping night. **Any single open night** matches the original Chronos script's `nights=1` behavior and reports isolated openings anywhere between arrival and the night before checkout. The UI always treats the final date as checkout, not as a camping night.

Campfyr reads the same Recreation.gov web endpoints used by the public campground interface. They are not a documented, guaranteed public API and may change. The client validates responses and surfaces failures in the UI, but an upstream change can still require a Campfyr update. Campfyr does not book sites or bypass Recreation.gov; it only sends availability alerts.
