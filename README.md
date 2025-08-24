# debilarr

Pause SABnzbd automatically when someone is watching Jellyfin.
Resume downloads when playback stops.

This container polls Jellyfin sessions on an interval and toggles SABnzbd’s **global** pause/resume accordingly. No Jellyfin plugins required.

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
    # If Jellyfin/SAB are on the host, you can also use:
    # network_mode: host
    # Or add host-gateway for Linux:
    # extra_hosts:
    #   - "host.docker.internal:host-gateway"
```

Bring it up:

```bash
docker compose up -d
docker logs -f debilarr
```

## Configuration

| Variable           | Default | Description                                                                                              |
| ------------------ | ------- | -------------------------------------------------------------------------------------------------------- |
| `JELLYFIN_URL`     | —       | Base URL to Jellyfin (e.g. `http://jellyfin:8096`). Prefer internal/LAN URL, not a public reverse proxy. |
| `JELLYFIN_API_KEY` | —       | Jellyfin API key (sent as `X-Emby-Token` header).                                                        |
| `SAB_URL`          | —       | Base URL to SABnzbd (e.g. `http://sabnzbd:8080`). Prefer internal/LAN URL.                               |
| `SAB_API_KEY`      | —       | SABnzbd API key.                                                                                         |
| `INTERVAL`         | `30`    | Poll interval in seconds.                                                                                |
| `RESUME_COOLDOWN`  | `60`    | Idle seconds required before resuming SAB.                                                               |
| `INCLUDE_PAUSED`   | `false` | If `true`, treat paused/buffering as “watching” (keeps SAB paused).                                      |
| `VERIFY_TLS`       | `true`  | Set `false` to skip TLS verification (for self-signed internal HTTPS).                                   |
| `REQUEST_TIMEOUT`  | `8`     | Per-request timeout (seconds).                                                                           |
| `LOG_LEVEL`        | `INFO`  | `DEBUG`, `INFO`, `WARN`, or `ERROR`.                                                                     |

## How it decides “playing”

A session counts as playing when:

* `NowPlayingItem` exists, and
* `PlayState.IsPaused` is false, and
* `PlayState.IsBuffering` is false.

If `INCLUDE_PAUSED=true`, paused/buffering sessions also count.

SABnzbd is controlled globally:

* Pause: `mode=pause`
* Resume: `mode=resume`
* State check: `mode=queue&output=json` (reads `queue.paused`)

## Networking notes

Use **internal** URLs for reliability. Avoid going through public reverse proxies/CDNs.

* Same compose network: `JELLYFIN_URL=http://jellyfin:8096`, `SAB_URL=http://sabnzbd:8080`
* Services on the host:

  * `network_mode: host` and `http://127.0.0.1:<port>`
  * or Linux host-gateway: `http://host.docker.internal:<port>` with `extra_hosts: ["host.docker.internal:host-gateway"]`

## Troubleshooting

* **521 / 502 from public URL**
  You’re likely hitting a CDN/reverse proxy. Point the container to **direct** LAN/internal URLs. The poller does not need the public endpoint.

* **How to test Jellyfin in Postman**
  `GET https://<your-jellyfin>/Sessions` with header `X-Emby-Token: <API_KEY>`.
  For local quick tests you can also use `?api_key=<API_KEY>` query param.

* **Logs show no resume**
  Check `INTERVAL` and `RESUME_COOLDOWN`. With defaults, you need \~60 seconds of continuous idle. If you set `INCLUDE_PAUSED=true`, a paused stream keeps SAB paused.

* **Force update container**

  ```bash
  docker compose pull debilarr
  docker compose up -d --force-recreate debilarr
  ```

  Or if building locally:

  ```bash
  docker compose up -d --build --force-recreate debilarr
  ```

## Example log lines

```
2025-08-24 21:18:07 INFO Starting polling | interval=30 resume_cooldown=60 include_paused=False
2025-08-24 21:18:37 DEBUG No active playback | idle_seconds=30
2025-08-24 21:19:05 INFO Paused SAB due to active playback
2025-08-24 21:20:15 INFO Idle threshold reached; resuming SAB | idle_seconds=60
```

## Advanced (contributors)

If you need to build locally or publish your own tag:

```bash
# Multi-arch build (amd64 + arm64)
docker buildx create --use --name debilarr-builder
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t mateuszkukiela/debilarr:latest \
  --push .
```

---

That’s it. Users can pull `mateuszkukiela/debilarr:latest` and run with the env vars above. If you want badges or a minimal “Kubernetes” example, say the word.
