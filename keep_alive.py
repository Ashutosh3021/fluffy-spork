"""
keep_alive.py - Main Pinger Service
Pings a list of URLs every 14 minutes to prevent Render.com free-tier
services from spinning down. Exposes a /health endpoint so the watcher
can confirm this service itself is alive.
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
# Comma-separated list of URLs to keep alive.
# Example: "https://service-a.onrender.com,https://service-b.onrender.com"
SITES_URLS_RAW: str = os.environ.get("SITES_URLS", "")

# How often to ping each URL (seconds). 14 min = 840 s.
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
# Example: {"https://foo.onrender.com": ["/health", "/api"], "https://bar.onrender.com": ["/health", "/status"]}
import json as _json
WAKE_UP_ENDPOINTS_MAP: dict[str, list[str]] = {}
try:
    _raw_map = os.environ.get("WAKE_UP_ENDPOINTS_MAP", "")
    if _raw_map:
        WAKE_UP_ENDPOINTS_MAP = _json.loads(_raw_map)
except (_json.JSONDecodeError, ValueError):
    logger.warning("⚠️  WAKE_UP_ENDPOINTS_MAP is not valid JSON. Using default endpoints for all URLs.")

# ---------------------------------------------------------------------------
# Flask app — exposes /health so the watcher can verify we are running
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/health")
def health():
    """Lightweight health-check endpoint."""
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}), 200


@app.route("/")
def index():
    """Root endpoint — confirms the service is reachable."""
    return jsonify({"service": "keep_alive_pinger", "health": "/health"}), 200


# ---------------------------------------------------------------------------
# Pinger logic
# ---------------------------------------------------------------------------

def parse_urls(raw: str) -> list[str]:
    """
    Split the comma-separated URL string, strip whitespace, and discard
    any empty entries.
    """
    return [url.strip() for url in raw.split(",") if url.strip()]


def parse_base_url(url: str) -> str:
    """Extract scheme + host from a full URL. 'https://foo.onrender.com/health' → 'https://foo.onrender.com'."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def wake_up_url(url: str) -> bool:
    """
    Cold-start wake-up: hit multiple endpoints over ~50s so Render
    registers the service as active. One failed hit doesn't stop the cycle.
    Returns True if at least one endpoint responded successfully.
    """
    base = parse_base_url(url)
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


def ping_url(url: str) -> None:
    """
    Send a single GET request to *url* and log the outcome.
    Catches all common network / HTTP exceptions so one bad URL
    cannot break the entire ping cycle.
    """
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        logger.info("✅  PING OK   | %s | HTTP %s", url, response.status_code)
    except requests.exceptions.MissingSchema:
        logger.error("❌  BAD URL   | %s | URL is not valid (missing schema)", url)
    except requests.exceptions.ConnectionError:
        logger.error("❌  CONN ERR  | %s | Could not establish a connection", url)
    except requests.exceptions.Timeout:
        logger.error("❌  TIMEOUT   | %s | Request timed out after %ss", url, REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        logger.error("❌  ERROR     | %s | %s", url, exc)


def ping_all(urls: list[str], first_cycle: bool = False,
             retry_urls: set[str] | None = None) -> set[str]:
    """Ping every URL in the list sequentially. Returns set of URLs that failed wake-up."""
    if not urls:
        logger.warning("⚠️  No URLs configured. Set the SITES_URLS environment variable.")
        return set()

    failed: set[str] = set()
    logger.info("🔄  Starting ping cycle — %d URL(s) %s", len(urls),
                "(wake-up)" if first_cycle else "")
    for url in urls:
        if first_cycle and WAKE_UP_ENABLED:
            if not wake_up_url(url):
                failed.add(url)
        elif url in (retry_urls or set()):
            logger.info("🔁  RETRY    | %s | re-attempting wake-up", url)
            if not wake_up_url(url):
                failed.add(url)
        else:
            ping_url(url)
    logger.info("✔️  Ping cycle complete. Next cycle in %d seconds (%d min).",
                PING_INTERVAL, PING_INTERVAL // 60)
    return failed


def pinger_loop() -> None:
    """
    Background thread: ping all URLs immediately on startup, then
    sleep for PING_INTERVAL seconds and repeat indefinitely.
    """
    urls = parse_urls(SITES_URLS_RAW)

    if not urls:
        logger.warning(
            "⚠️  SITES_URLS is empty or not set. "
            "The pinger will keep running but won't ping anything."
        )

    logger.info("🚀  Pinger started. Interval: %ds | URLs: %d", PING_INTERVAL, len(urls))

    first_cycle = True
    failed_urls: set[str] = set()
    while True:
        failed_urls = ping_all(urls, first_cycle=first_cycle, retry_urls=failed_urls)
        first_cycle = False
        time.sleep(PING_INTERVAL)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Start the pinger in a daemon thread so it doesn't block Flask.
    pinger_thread = threading.Thread(target=pinger_loop, daemon=True, name="pinger")
    pinger_thread.start()

    logger.info("🌐  Flask server starting on port %d", PORT)
    # Use threaded=True so the health endpoint remains responsive while
    # the background thread is sleeping between ping cycles.
    app.run(host="0.0.0.0", port=PORT, threaded=True)
