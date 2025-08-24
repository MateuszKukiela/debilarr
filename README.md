# debilarr

Pause SABnzbd automatically when someone is watching Jellyfin.
Resume downloads when playback stops.

This avoids buffering or stuttering during streaming sessions by throttling SABnzbd at the right times.

## How it works

* A lightweight Python script runs inside a container.
* It **polls Jellyfin sessions** every few seconds (default 30s).
* If any session is playing (optionally paused/buffering), SABnzbd is paused.
* When no one is watching for a configured cooldown period, SABnzbd resumes.

No plugins, no invasive setup — just a sidecar service.

## Configuration

Everything is configured through environment variables (or CLI flags if you run manually).

| Variable           | Default | Description                                        |
| ------------------ | ------- | -------------------------------------------------- |
| `JELLYFIN_URL`     | *none*  | Base URL to Jellyfin (e.g. `http://jellyfin:8096`) |
| `JELLYFIN_API_KEY` | *none*  | Jellyfin API key (`X-Emby-Token`)                  |
| `SAB_URL`          | *none*  | Base URL to SABnzbd (e.g. `http://sabnzbd:8080`)   |
| `SAB_API_KEY`      | *none*  | SABnzbd API key                                    |
| `INTERVAL`         | `30`    | Polling interval in seconds                        |
| `RESUME_COOLDOWN`  | `60`    | Idle seconds before resuming SAB                   |
| `INCLUDE_PAUSED`   | `false` | `"true"` to treat paused/buffering as active       |
| `VERIFY_TLS`       | `true`  | `"false"` to skip TLS certificate checks           |
| `REQUEST_TIMEOUT`  | `8`     | Per-request timeout (seconds)                      |
| `LOG_LEVEL`        | `INFO`  | `DEBUG`, `INFO`, `WARN`, `ERROR`                   |

## Docker

### Build and run directly

```bash
git clone https://github.com/yourname/debilarr.git
cd debilarr

docker build -t debilarr .
docker run -d --name debilarr \
  -e JELLYFIN_URL=http://jellyfin:8096 \
  -e JELLYFIN_API_KEY=your_jellyfin_token \
  -e SAB_URL=http://sabnzbd:8080 \
  -e SAB_API_KEY=your_sab_token \
  debilarr
```

### Docker Compose

```yaml
version: "3.8"

services:
  debilarr:
    build: .
    container_name: debilarr
    restart: unless-stopped
    environment:
      JELLYFIN_URL: "http://jellyfin:8096"
      JELLYFIN_API_KEY: "REDACTED_JELLYFIN"
      SAB_URL: "http://sabnzbd:8080"
      SAB_API_KEY: "REDACTED_SAB"
      INTERVAL: "30"
      RESUME_COOLDOWN: "60"
      INCLUDE_PAUSED: "false"
      LOG_LEVEL: "INFO"
    # Uncomment if you need host networking:
    # network_mode: host
```

Bring it up:

```bash
docker compose up -d --build
```

Check logs:

```bash
docker logs -f debilarr
```

## Example logs

```
INFO Starting polling | interval=30 resume_cooldown=60 include_paused=False
INFO SABnzbd state change requested | action=pause
INFO SABnzbd state change requested | action=resume
```

## Build and Push Multi-arch Images (Docker Hub)

To support both `amd64` and `arm64`:

```bash
# 1. Create a buildx builder (once per machine)
docker buildx create --use --name debilarr-builder

# 2. Authenticate to Docker Hub
echo "$DOCKERHUB_TOKEN" | docker login -u YOUR_USER --password-stdin

# 3. Build and push multi-arch image
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t YOUR_USER/debilarr:0.1.0 \
  -t YOUR_USER/debilarr:latest \
  --push .
```


## Why the name?

Because it’s a dumb little helper that glues **Jellyfin** and **SABnzbd** together. Nothing more, nothing less.
