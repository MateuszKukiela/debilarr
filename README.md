# debilarr

Pause SABnzbd automatically when someone is watching Jellyfin.
Resume downloads when playback stops.

This container polls Jellyfin sessions and toggles SABnzbd’s **global** pause/resume accordingly. No Jellyfin plugins required.

## Quick start (Docker Hub)

### Docker run

```bash
docker run -d --name debilarr \
  --restart unless-stopped \
  -e JELLYFIN_URL=http://jellyfin:8096 \
  -e JELLYFIN_API_KEY=REDACTED_JELLYFIN \
  -e SAB_URL=http://sabnzbd:8080 \
  -e SAB_API_KEY=REDACTED_SAB \
  -e INTERVAL=30 \
  -e RESUME_COOLDOWN=60 \
  -e INCLUDE_PAUSED=false \
  -e LOG_LEVEL=INFO \
  mateuszkukiela/debilarr:latest
```

### Docker Compose

```yaml
version: "3.8"

services:
  debilarr:
    image: mateuszkukiela/debilarr:latest
    container_name: debilarr
    restart: unless-stopped
    environment:
      JELLYFIN_URL: "http://jellyfin:8096"          # or http://host.docker.internal:8096
      JELLYFIN_API_KEY: "REDACTED_JELLYFIN"
      SAB_URL: "http://sabnzbd:8080"               # or http://host.docker.internal:8080
      SAB_API_KEY: "REDACTED_SAB"
      INTERVAL: "30"
      RESUME_COOLDOWN: "60"
      INCLUDE_PAUSED: "false"                       # set "true" to also pause when paused/buffering
      LOG_LEVEL: "INFO"
    # If Jellyfin/SAB are on the host:
    # network_mode: host
    # Or Linux host-gateway:
    # extra_hosts:
    #   - "host.docker.internal:host-gateway"
```

Bring it up:

```bash
docker compose up -d
docker logs -f debilarr
```

## On-the-fly override from SAB GUI (Option B)

You can **force downloads while someone is watching** without redeploys by using SABnzbd’s built-in **Speed Limit** control:

* In SAB’s web UI, set a **Speed Limit > 0** (e.g., 1500 KB/s).
* `debilarr` detects that a limit is active and **skips auto-pause**, even if Jellyfin reports active playback.
* When you’re done, set the speed back to **Unlimited (0)** and auto-pause resumes its normal behavior.

Notes:

* The script reads `mode=queue&output=json` and checks SAB’s current `speedlimit`. Any value > 0 is treated as a **user override**.
* This is a live toggle entirely in the SAB GUI; no environment variables or file flags needed.

## How it decides “playing”

A session counts as playing when:

* `NowPlayingItem` exists, and
* `PlayState.IsPaused` is false, and
* `PlayState.IsBuffering` is false.

If `INCLUDE_PAUSED=true`, paused/buffering sessions also count.

SABnzbd is controlled globally:

* Pause: `mode=pause`
* Resume: `mode=resume`
* State/override check: `mode=queue&output=json` (reads `queue.paused` and `speedlimit`)

## Configuration

| Variable           | Default | Description                                                                  |
| ------------------ | ------- | ---------------------------------------------------------------------------- |
| `JELLYFIN_URL`     | —       | Base URL to Jellyfin (e.g. `http://jellyfin:8096`). Prefer internal/LAN URL. |
| `JELLYFIN_API_KEY` | —       | Jellyfin API key (sent as `X-Emby-Token` header).                            |
| `SAB_URL`          | —       | Base URL to SABnzbd (e.g. `http://sabnzbd:8080`). Prefer internal/LAN URL.   |
| `SAB_API_KEY`      | —       | SABnzbd API key.                                                             |
| `INTERVAL`         | `30`    | Poll interval in seconds.                                                    |
| `RESUME_COOLDOWN`  | `60`    | Idle seconds required before resuming SAB.                                   |
| `INCLUDE_PAUSED`   | `false` | If `true`, treat paused/buffering as “watching.”                             |
| `VERIFY_TLS`       | `true`  | Set `false` to skip TLS verification (self-signed internal HTTPS).           |
| `REQUEST_TIMEOUT`  | `8`     | Per-request timeout (seconds).                                               |
| `LOG_LEVEL`        | `INFO`  | `DEBUG`, `INFO`, `WARN`, or `ERROR`.                                         |

## Networking notes

Use **internal** URLs for reliability. Avoid public reverse proxies/CDNs for the poller.

* Same compose network: `JELLYFIN_URL=http://jellyfin:8096`, `SAB_URL=http://sabnzbd:8080`
* Services on the host:

  * `network_mode: host` and `http://127.0.0.1:<port>`
  * or Linux host-gateway: `http://host.docker.internal:<port>` with `extra_hosts: ["host.docker.internal:host-gateway"]`

## Troubleshooting

* **521 / 502 via public URL**
  You’re hitting a CDN/reverse proxy. Point the container to **direct** LAN/internal URLs. The poller doesn’t need your public endpoint.

* **Test Jellyfin API in Postman**
  `GET https://<jellyfin>/Sessions` with header `X-Emby-Token: <API_KEY>`.
  For local tests you can also use `?api_key=<API_KEY>`.

* **Not resuming**
  Check `INTERVAL` + `RESUME_COOLDOWN`. With defaults, you need \~60s of continuous idle. If `INCLUDE_PAUSED=true`, a paused stream still counts as active.

* **Force update container**

  ```bash
  docker compose pull debilarr
  docker compose up -d --force-recreate debilarr
  ```

  Or when building locally:

  ```bash
  docker compose up -d --build --force-recreate debilarr
  ```

## Example log lines

```
2025-08-24 21:18:07 INFO Starting polling | interval=30 resume_cooldown=60 include_paused=False
2025-08-24 21:18:37 DEBUG No active playback | idle_seconds=30
2025-08-24 21:19:05 INFO Paused SAB due to active playback
2025-08-24 21:19:20 INFO User override: SAB speed limit set, skipping auto-pause
2025-08-24 21:20:15 INFO Idle threshold reached; resuming SAB | idle_seconds=60
```

## Build and push (contributors)

```bash
# Multi-arch build (amd64 + arm64)
docker buildx create --use --name debilarr-builder
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t mateuszkukiela/debilarr:latest \
  --push .
```

---
