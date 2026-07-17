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

    while True:
        check_pinger()
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
