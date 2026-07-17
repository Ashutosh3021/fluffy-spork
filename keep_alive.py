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


def ping_all(urls: list[str]) -> None:
    """Ping every URL in the list sequentially."""
    if not urls:
        logger.warning("⚠️  No URLs configured. Set the SITES_URLS environment variable.")
        return

    logger.info("🔄  Starting ping cycle — %d URL(s)", len(urls))
    for url in urls:
        ping_url(url)
    logger.info("✔️  Ping cycle complete. Next cycle in %d seconds (%d min).",
                PING_INTERVAL, PING_INTERVAL // 60)


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

    while True:
        ping_all(urls)
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
