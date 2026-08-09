# Campfyr on Unraid

Campfyr can run on Unraid without building images on a Mac or PC. GitHub Actions builds the image for both `linux/amd64` and `linux/arm64` and publishes it to `seydelserver/campfyr` on Docker Hub. Unraid only needs to pull the finished image.

## One-time Docker Hub publishing setup

The repository owner must complete these steps once. Do not paste the Docker Hub token into Campfyr, a terminal command, or a repository file.

1. In Docker Hub, open **Account settings → Personal access tokens** and create a token with **Read & Write** permission.
2. In the Campfyr GitHub repository, open **Settings → Secrets and variables → Actions**.
3. Add these repository secrets:
   - `DOCKERHUB_USERNAME` — the Docker Hub username, currently `seydelserver`
   - `DOCKERHUB_TOKEN` — the new Docker Hub access token
4. Open **Actions → Publish Docker image → Run workflow**.
5. Wait for **Build and publish image** to finish successfully.

After this setup, every relevant change merged into `main` automatically publishes a new `seydelserver/campfyr:latest` image. Version tags such as `v2.0.0` also create matching Docker image tags.

## Install with Docker Compose Manager

Install **Docker Compose Manager** from Unraid Apps if it is not already installed. Create a stack named `campfyr`, then place `compose.unraid.yaml` and a file named `.env` in that stack directory.

Start with the repository's `.env.example` file and fill in the notification settings:

```dotenv
NOTIFICATION_PROVIDER=pushover
PUSHOVER_USER_KEY=your_user_key
PUSHOVER_API_TOKEN=your_api_token
CHECK_INTERVAL_SECONDS=600
RECREATION_TIMEOUT_SECONDS=20
LOG_LEVEL=INFO
```

Create the persistent data directory once from the Unraid terminal:

```sh
mkdir -p /mnt/user/appdata/campfyr/data
chown -R 10001:10001 /mnt/user/appdata/campfyr/data
```

Bring the stack up from Docker Compose Manager, or from the stack directory:

```sh
docker compose -f compose.unraid.yaml up -d
```

Campfyr will be available at `http://YOUR-UNRAID-IP:5001`. The Docker page will show two containers:

- `Campfyr` serves the web interface.
- `Campfyr-Worker` checks Recreation.gov every 600 seconds.

Both containers use the same database in `/mnt/user/appdata/campfyr/data`. Do not run the old Chronos script at the same time.

## Update Campfyr

Once the GitHub publishing workflow finishes, update Unraid from Docker Compose Manager or run:

```sh
docker compose -f compose.unraid.yaml pull
docker compose -f compose.unraid.yaml up -d
```

This downloads the newest `seydelserver/campfyr:latest` image and safely recreates both containers while preserving the database.

## Moving from the old container

Do not delete `/mnt/user/appdata/chronos/scripts/camp` until the new installation is working. That folder is outside the container, so recreating the old container should not erase it.

If it contains `campSiteRequests.json`, the watches can be imported after the new stack is running. Run this from the Unraid terminal:

```sh
docker run --rm \
  --env-file /path/to/campfyr/.env \
  -e CAMPFYR_DATABASE_PATH=/data/campfyr.db \
  -v /mnt/user/appdata/campfyr/data:/data \
  -v /mnt/user/appdata/chronos/scripts/camp:/legacy:ro \
  seydelserver/campfyr:latest \
  python -m campfyr.migrate /legacy/campSiteRequests.json
```

Replace `/path/to/campfyr/.env` with the actual `.env` location used by Docker Compose Manager. Alternatively, recreate the watches through the Campfyr web interface.

## Troubleshooting

Check container status and recent logs:

```sh
docker compose -f compose.unraid.yaml ps
docker compose -f compose.unraid.yaml logs --tail=100 web worker
```

If the web page works but says **Watcher starting**, make sure `Campfyr-Worker` is running and both containers have the same `/data` mapping and `CAMPFYR_DATABASE_PATH` value.
