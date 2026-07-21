"""
watcher.py - Watcher Service
Monitors the main pinger's /health endpoint every 14 minutes.
If the pinger goes down, this service logs a clear warning so you
can investigate. Deploy this as a second, independent web service
on Render.com so the two services mutually keep each other alive.
"""

import os
import time
import logging
import threading
from datetime import datetime

import requests
from flask import Flask, jsonify

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from environment variables)
# ---------------------------------------------------------------------------
# Full URL of the main pinger's /health endpoint.
# Example: "https://keep-alive-pinger.onrender.com/health"
MAIN_PINGER_URL: str = os.environ.get("MAIN_PINGER_URL", "")

# How often to ping the main pinger (seconds). 14 min = 840 s.
PING_INTERVAL: int = int(os.environ.get("PING_INTERVAL", "840"))

# Per-request timeout in seconds.
REQUEST_TIMEOUT: int = int(os.environ.get("REQUEST_TIMEOUT", "15"))

# Port that Flask listens on (Render injects PORT automatically).
PORT: int = int(os.environ.get("PORT", "8080"))

# Wake-up configuration: hit multiple endpoints over ~50s to wake cold services.
WAKE_UP_ENABLED: bool = os.environ.get("WAKE_UP_ENABLED", "true").lower() == "true"
WAKE_UP_INTERVAL: int = int(os.environ.get("WAKE_UP_INTERVAL", "9"))
WAKE_UP_ENDPOINTS: list[str] = ["/health", "/", "/bad", "/demo", "/health", "/api"]

# Per-URL custom endpoints (JSON). Falls back to WAKE_UP_ENDPOINTS for unlisted URLs.
# Example: {"https://foo.onrender.com": ["/health", "/api"]}
import json as _json
WAKE_UP_ENDPOINTS_MAP: dict[str, list[str]] = {}
try:
    _raw_map = os.environ.get("WAKE_UP_ENDPOINTS_MAP", "")
    if _raw_map:
        WAKE_UP_ENDPOINTS_MAP = _json.loads(_raw_map)
except (_json.JSONDecodeError, ValueError):
    logger.warning("⚠️  WAKE_UP_ENDPOINTS_MAP is not valid JSON. Using default endpoints.")

# ---------------------------------------------------------------------------
# Flask app — exposes /health so the main pinger can ping this service back
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/health")
def health():
    """Lightweight health-check endpoint."""
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}), 200


@app.route("/")
def index():
    """Root endpoint — confirms the watcher service is reachable."""
    return jsonify({"service": "keep_alive_watcher", "health": "/health"}), 200


# ---------------------------------------------------------------------------
# Watcher logic
# ---------------------------------------------------------------------------

def check_pinger() -> None:
    """
    Send a GET request to MAIN_PINGER_URL and log whether the main
    pinger is healthy. All exceptions are caught so a transient network
    blip doesn't crash the watcher loop.
    """
    if not MAIN_PINGER_URL:
        logger.warning(
            "⚠️  MAIN_PINGER_URL is not set. "
            "The watcher will keep running but won't check anything."
        )
        return

    logger.info("🔍  Checking main pinger: %s", MAIN_PINGER_URL)
    try:
        response = requests.get(MAIN_PINGER_URL, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            logger.info("✅  PINGER OK  | HTTP %s | %s", response.status_code, MAIN_PINGER_URL)
        else:
            logger.warning(
                "⚠️  PINGER WARN | HTTP %s | %s — unexpected status code",
                response.status_code,
                MAIN_PINGER_URL,
            )
    except requests.exceptions.MissingSchema:
        logger.error("❌  BAD URL    | %s | URL is not valid (missing schema)", MAIN_PINGER_URL)
    except requests.exceptions.ConnectionError:
        logger.error(
            "❌  CONN ERR   | %s | Could not reach the main pinger — is it down?",
            MAIN_PINGER_URL,
        )
    except requests.exceptions.Timeout:
        logger.error(
            "❌  TIMEOUT    | %s | Main pinger did not respond within %ss",
            MAIN_PINGER_URL,
            REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        logger.error("❌  ERROR      | %s | %s", MAIN_PINGER_URL, exc)


def parse_base_url(url: str) -> str:
    """Extract scheme + host from a full URL. 'https://foo.onrender.com/health' → 'https://foo.onrender.com'."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def wake_up_pinger() -> bool:
    """
    Cold-start wake-up: hit multiple pinger endpoints over ~50s so Render
    registers the pinger as active. Returns True if at least one endpoint responded.
    """
    if not MAIN_PINGER_URL:
        logger.warning(
            "⚠️  MAIN_PINGER_URL is not set. "
            "The watcher will keep running but won't wake up anything."
        )
        return False

    base = parse_base_url(MAIN_PINGER_URL)
    endpoints = WAKE_UP_ENDPOINTS_MAP.get(base, WAKE_UP_ENDPOINTS)
    logger.info("🔥  WAKE-UP  | %s | hitting %d endpoints over ~%ds",
                base, len(endpoints), WAKE_UP_INTERVAL * len(endpoints))

    any_success = False
    for i, path in enumerate(endpoints):
        full_url = base + path
        try:
            response = requests.get(full_url, timeout=REQUEST_TIMEOUT)
            logger.info("✅  WAKE HIT | %s | HTTP %s", full_url, response.status_code)
            any_success = True
        except requests.exceptions.MissingSchema:
            logger.error("❌  BAD URL   | %s | URL is not valid (missing schema)", full_url)
        except requests.exceptions.ConnectionError:
            logger.error("❌  CONN ERR  | %s | Could not establish a connection", full_url)
        except requests.exceptions.Timeout:
            logger.error("❌  TIMEOUT   | %s | Request timed out after %ss", full_url, REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            logger.error("❌  ERROR     | %s | %s", full_url, exc)

        if i < len(endpoints) - 1:
            time.sleep(WAKE_UP_INTERVAL)

    if any_success:
        logger.info("✔️  WAKE-UP  | %s | complete", base)
    else:
        logger.warning("⚠️  WAKE-UP  | %s | failed — no endpoint responded", base)
    return any_success


def watcher_loop() -> None:
    """
    Background thread: check the main pinger immediately on startup,
    then sleep for PING_INTERVAL seconds and repeat indefinitely.
    """
    logger.info(
        "🚀  Watcher started. Interval: %ds | Target: %s",
        PING_INTERVAL,
        MAIN_PINGER_URL or "(not set)",
    )

    first_cycle = True
    wake_up_failed = False
    while True:
        if (first_cycle or wake_up_failed) and WAKE_UP_ENABLED:
            wake_up_failed = not wake_up_pinger()
        else:
            check_pinger()
        first_cycle = False
        logger.info(
            "💤  Sleeping for %d seconds (%d min) until next check.",
            PING_INTERVAL,
            PING_INTERVAL // 60,
        )
        time.sleep(PING_INTERVAL)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Start the watcher loop in a daemon thread so it doesn't block Flask.
    watcher_thread = threading.Thread(target=watcher_loop, daemon=True, name="watcher")
    watcher_thread.start()

    logger.info("🌐  Flask server starting on port %d", PORT)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
