#!/usr/bin/env python3
"""
Poll Jellyfin sessions and pause/resume SABnzbd accordingly.

Behavior:
- If any Jellyfin session is actively playing (optionally also paused/buffering),
  pause SABnzbd.
- When no sessions are active for a continuous cooldown window, resume SABnzbd.

Configuration (env vars, or CLI flags override):
    JELLYFIN_URL       Base URL to Jellyfin, e.g., http://jellyfin:8096
    JELLYFIN_API_KEY   Jellyfin API key (X-Emby-Token)
    SAB_URL            Base URL to SABnzbd, e.g., http://sabnzbd:8080
    SAB_API_KEY        SABnzbd API key
    INTERVAL           Poll interval seconds (default: 30)
    RESUME_COOLDOWN    Idle seconds before resuming SAB (default: 60)
    INCLUDE_PAUSED     "true"/"1" to consider paused/buffering as active (default: false)
    VERIFY_TLS         "false"/"0" to disable TLS verification (default: true)
    REQUEST_TIMEOUT    Per-request timeout seconds (default: 8)
    LOG_LEVEL          DEBUG|INFO|WARN|ERROR (default: INFO)

Run inside Docker (see Dockerfile and compose below).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the polling loop.

    Attributes:
        jellyfin_url: Jellyfin base URL.
        jellyfin_api_key: Jellyfin API key (X-Emby-Token).
        sab_url: SABnzbd base URL.
        sab_api_key: SABnzbd API key.
        interval: Polling interval in seconds.
        resume_cooldown: Idle seconds before resuming SABnzbd.
        include_paused: Treat paused/buffering as active playback.
        verify_tls: Verify TLS certificates on HTTPS endpoints.
        request_timeout: Per-HTTP-request timeout seconds.
        log_level: Log level name.
    """
    jellyfin_url: str
    jellyfin_api_key: str
    sab_url: str
    sab_api_key: str
    interval: int = 30
    resume_cooldown: int = 60
    include_paused: bool = False
    verify_tls: bool = True
    request_timeout: int = 8
    log_level: str = "INFO"


class Logger:
    """Minimal stdout logger with levels."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def __init__(self, level: str = "INFO") -> None:
        self._lvl = self.LEVELS.get(level.upper(), 20)

    def _log(self, level: str, msg: str, **kv: Any) -> None:
        if self.LEVELS[level] < self._lvl:
            return
        extra = " ".join(f"{k}={v}" for k, v in kv.items())
        print(f"{level} {msg}{(' | ' + extra) if extra else ''}", flush=True)

    def debug(self, msg: str, **kv: Any) -> None: self._log("DEBUG", msg, **kv)
    def info(self, msg: str, **kv: Any) -> None: self._log("INFO", msg, **kv)
    def warn(self, msg: str, **kv: Any) -> None: self._log("WARN", msg, **kv)
    def error(self, msg: str, **kv: Any) -> None: self._log("ERROR", msg, **kv)


# ---------- Jellyfin ----------

def jellyfin_active_playback(cfg: Config, log: Logger) -> Tuple[bool, List[Dict[str, Any]]]:
    """Check if any Jellyfin session indicates active playback.

    Args:
        cfg: Runtime configuration.
        log: Logger.

    Returns:
        Tuple (any_active, session_summaries).
    """
    url = f"{cfg.jellyfin_url.rstrip('/')}/Sessions"
    headers = {"X-Emby-Token": cfg.jellyfin_api_key, "Accept": "application/json"}
    try:
        r = requests.get(url, headers=headers, timeout=cfg.request_timeout, verify=cfg.verify_tls)
        r.raise_for_status()
        sessions: List[Dict[str, Any]] = r.json() or []
    except Exception as e:
        log.error("Jellyfin sessions fetch failed", err=repr(e), url=url)
        return False, []

    any_active = False
    summaries: List[Dict[str, Any]] = []

    for s in sessions:
        now = s.get("NowPlayingItem")
        if not now:
            continue
        ps = s.get("PlayState") or {}
        is_playing = bool(ps.get("IsPlaying") or ps.get("IsVideoPaused") is False)
        is_paused = bool(ps.get("IsPaused") or ps.get("IsVideoPaused"))
        is_buffering = bool(ps.get("IsBuffering"))
        watching = is_playing or (cfg.include_paused and (is_paused or is_buffering))

        summaries.append({
            "user": s.get("UserName") or s.get("UserId"),
            "client": s.get("Client"),
            "item": now.get("Name") if isinstance(now, dict) else None,
            "is_playing": is_playing,
            "is_paused": is_paused,
            "is_buffering": is_buffering,
            "watching": watching,
        })
        if watching:
            any_active = True

    return any_active, summaries


# ---------- SABnzbd ----------

def sab_global_state(cfg: Config, log: Logger) -> Dict[str, Any]:
    """Return SABnzbd global state; empty dict on failure."""
    url = f"{cfg.sab_url.rstrip('/')}/sabnzbd/api"
    params = {"mode": "globalstat", "output": "json", "apikey": cfg.sab_api_key}
    try:
        r = requests.get(url, params=params, timeout=cfg.request_timeout, verify=cfg.verify_tls)
        r.raise_for_status()
        return r.json() or {}
    except Exception as e:
        log.error("SABnzbd globalstat failed", err=repr(e), url=url)
        return {}


def sab_set_pause(cfg: Config, log: Logger, pause: bool) -> bool:
    """Pause or resume SABnzbd; returns True on HTTP OK."""
    url = f"{cfg.sab_url.rstrip('/')}/sabnzbd/api"
    mode = "pause" if pause else "resume"
    try:
        r = requests.get(url, params={"mode": mode, "apikey": cfg.sab_api_key}, timeout=cfg.request_timeout, verify=cfg.verify_tls)
        r.raise_for_status()
        log.info("SABnzbd state change requested", action=mode)
        return True
    except Exception as e:
        log.error("SABnzbd state change failed", action=mode, err=repr(e))
        return False


# ---------- Loop ----------

def run(cfg: Config) -> None:
    """Main polling loop; intended to run as PID 1 in the container."""
    log = Logger(cfg.log_level)
    log.info("Starting polling", interval=cfg.interval, resume_cooldown=cfg.resume_cooldown, include_paused=cfg.include_paused)

    # Graceful shutdown
    stop = {"flag": False}
    def _handler(signum, frame) -> None:
        stop["flag"] = True
        log.info("Signal received, exiting", signum=signum)
    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)

    idle_accum = 0
    last_state: Optional[bool] = None  # True=paused, False=running, None=unknown

    while not stop["flag"]:
        is_active, details = jellyfin_active_playback(cfg, log)
        if log._lvl <= Logger.LEVELS["DEBUG"]:
            for d in details:
                log.debug("Session", **d)

        sab_state = sab_global_state(cfg, log)
        sab_paused = bool(sab_state.get("paused")) if sab_state else None

        if is_active:
            idle_accum = 0
            if sab_paused is False or (sab_paused is None and last_state is not True):
                sab_set_pause(cfg, log, pause=True)
                last_state = True
            else:
                log.debug("Already paused; no action")
        else:
            idle_accum += cfg.interval
            log.debug("No active playback", idle_seconds=idle_accum)
            if idle_accum >= cfg.resume_cooldown:
                if sab_paused is True or (sab_paused is None and last_state is not False):
                    sab_set_pause(cfg, log, pause=False)
                    last_state = False
                else:
                    log.debug("Already running; no action")

        time.sleep(cfg.interval)


def parse_args() -> Config:
    """Parse CLI args and environment variables into a Config."""
    env = os.environ

    def env_bool(name: str, default: bool) -> bool:
        v = env.get(name)
        return default if v is None else v.strip().lower() in {"1", "true", "yes", "y", "on"}

    p = argparse.ArgumentParser(description="Pause SABnzbd when Jellyfin is playing (polling).")
    p.add_argument("--jellyfin-url", default=env.get("JELLYFIN_URL"))
    p.add_argument("--jellyfin-api-key", default=env.get("JELLYFIN_API_KEY"))
    p.add_argument("--sab-url", default=env.get("SAB_URL"))
    p.add_argument("--sab-api-key", default=env.get("SAB_API_KEY"))
    p.add_argument("--interval", type=int, default=int(env.get("INTERVAL", "30")))
    p.add_argument("--resume-cooldown", type=int, default=int(env.get("RESUME_COOLDOWN", "60")))
    p.add_argument("--include-paused", action="store_true", default=env_bool("INCLUDE_PAUSED", False))
    p.add_argument("--no-verify-tls", dest="verify_tls", action="store_false", default=env_bool("VERIFY_TLS", True))
    p.add_argument("--request-timeout", type=int, default=int(env.get("REQUEST_TIMEOUT", "8")))
    p.add_argument("--log-level", default=env.get("LOG_LEVEL", "INFO"))
    args = p.parse_args()

    missing = [k for k, v in {
        "JELLYFIN_URL": args.jellyfin_url,
        "JELLYFIN_API_KEY": args.jellyfin_api_key,
        "SAB_URL": args.sab_url,
        "SAB_API_KEY": args.sab_api_key,
    }.items() if not v]
    if missing:
        print(f"ERROR Missing configuration: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)

    return Config(
        jellyfin_url=args.jellyfin_url,
        jellyfin_api_key=args.jellyfin_api_key,
        sab_url=args.sab_url,
        sab_api_key=args.sab_api_key,
        interval=args.interval,
        resume_cooldown=args.resume_cooldown,
        include_paused=args.include_paused,
        verify_tls=args.verify_tls,
        request_timeout=args.request_timeout,
        log_level=args.log_level,
    )


def main() -> None:
    """Entrypoint."""
    cfg = parse_args()
    run(cfg)


if __name__ == "__main__":
    main()
