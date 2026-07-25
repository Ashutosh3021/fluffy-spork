import os
import uuid
import time
import logging
import threading
from datetime import datetime, timezone
from typing import List, Optional

import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

import store

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
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

CORS(app, resources={
    r"/*": {
        "origins": [
            "https://keep-awake1.vercel.app",
            re.compile(r"http://localhost:.*"),
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
    }
})

ALLOWED_METHODS = {"GET", "HEAD", "POST", "PUT"}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.environ.get("PORT", "8080"))
SELF_URL = os.environ.get("SELF_URL", "")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "15"))
start_time = time.time()

# Ensure Pyronites tables exist (admin SQL when key allows; otherwise create in dashboard)
try:
    store.bootstrap_schema()
    logger.info("Pyronites schema bootstrap attempted.")
except Exception as e:
    logger.warning("Pyronites schema bootstrap skipped/failed: %s", e)


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }), 200


@app.route("/api/status")
def status():
    uptime_seconds = time.time() - start_time
    return jsonify({
        "status": "ok",
        "version": "1.3.0",
        "uptime_seconds": int(uptime_seconds),
        "users_count": store.users_count(),
        "services_count": store.services_count(),
        "storage": "pyronites",
    }), 200


# ---------------------------------------------------------------------------
# Auth Helpers
# ---------------------------------------------------------------------------
def get_current_user():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    user_id = store.token_user_id(token)
    if not user_id:
        return None
    return store.user_by_id(user_id)


def require_auth(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password") or data.get("pin")

    if not email or not password:
        return jsonify({"error": "Email and password/pin are required"}), 400
    if store.user_by_email(email):
        return jsonify({"error": "Email already exists"}), 409

    user_id = str(uuid.uuid4())
    store.user_create(user_id, email, password)
    return jsonify({"message": "User created", "user_id": user_id}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password") or data.get("pin")

    if not email or not password:
        return jsonify({"error": "Email and password/pin are required"}), 400

    user = store.user_by_email(email)
    if not user or user.get("password") != password:
        return jsonify({"error": "Invalid credentials"}), 401

    token = str(uuid.uuid4())
    store.token_save(token, user["id"])
    return jsonify({"token": token}), 200


@app.route("/api/auth/profile", methods=["PUT"])
@require_auth
def update_profile():
    user = get_current_user()
    data = request.json or {}

    new_email = data.get("email")
    new_password = data.get("password") or data.get("pin")
    fields = {}

    if new_email:
        if new_email != user["email"]:
            existing = store.user_by_email(new_email)
            if existing:
                return jsonify({"error": "Email already exists"}), 409
        fields["email"] = new_email

    if new_password:
        fields["password"] = new_password

    if fields:
        store.user_update(user["id"], **fields)

    return jsonify({"message": "Profile updated"}), 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_method(method: Optional[str]) -> str:
    m = (method or "GET").upper().strip()
    if m not in ALLOWED_METHODS:
        return "GET"
    return m


def _parse_interval(data: dict):
    interval_seconds = data.get("interval_seconds")
    interval_minutes = data.get("interval_minutes")
    pings_per_day = data.get("pings_per_day")

    if interval_seconds is not None:
        try:
            interval = int(interval_seconds)
        except (TypeError, ValueError):
            return None, "interval_seconds must be an integer"
    elif interval_minutes is not None:
        try:
            interval = int(interval_minutes) * 60
        except (TypeError, ValueError):
            return None, "interval_minutes must be an integer"
    elif pings_per_day is not None:
        try:
            ppd = int(pings_per_day)
        except (TypeError, ValueError):
            return None, "pings_per_day must be an integer"
        if ppd < 1 or ppd > 1440:
            return None, "pings_per_day must be between 1 and 1440"
        interval = int(86400 / ppd)
    else:
        interval = 840

    if interval < 60:
        return None, "Interval must be at least 60 seconds (1 minute)"

    return interval, None


def _do_ping(url: str, method: str = "GET") -> dict:
    method = _normalize_method(method)
    start = time.time()
    try:
        resp = requests.request(method, url, timeout=REQUEST_TIMEOUT)
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "url": url,
            "method": method,
            "success": True,
            "status_code": resp.status_code,
            "response_time_ms": elapsed_ms,
            "error": None,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "url": url,
            "method": method,
            "success": False,
            "status_code": None,
            "response_time_ms": elapsed_ms,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Test-before-create
# ---------------------------------------------------------------------------
@app.route("/api/test", methods=["POST"])
@require_auth
def test_url():
    data = request.json or {}

    base_url = data.get("base_url") or data.get("url")
    endpoints = data.get("endpoints")
    method = _normalize_method(data.get("method"))

    if not base_url:
        return jsonify({"error": "base_url (or url) is required"}), 400

    results = []
    if endpoints and isinstance(endpoints, list) and len(endpoints) > 0:
        for endpoint in endpoints:
            full = base_url.rstrip("/") + "/" + str(endpoint).lstrip("/")
            result = _do_ping(full, method)
            result["endpoint"] = endpoint
            results.append(result)
    else:
        result = _do_ping(base_url, method)
        result["endpoint"] = "/"
        results.append(result)

    return jsonify({"results": results}), 200


# ---------------------------------------------------------------------------
# Service Management
# ---------------------------------------------------------------------------
@app.route("/api/services", methods=["GET"])
@require_auth
def list_services():
    user = get_current_user()
    return jsonify(store.services_for_user(user["id"])), 200


@app.route("/api/services", methods=["POST"])
@require_auth
def create_service():
    user = get_current_user()
    data = request.json or {}

    base_url = data.get("base_url") or data.get("url")
    endpoints = data.get("endpoints", ["/health"])
    method = _normalize_method(data.get("method"))

    if not base_url:
        return jsonify({"error": "base_url is required"}), 400

    interval, err = _parse_interval(data)
    if err:
        return jsonify({"error": err}), 400

    service_id = str(uuid.uuid4())
    svc = store.service_create({
        "id": service_id,
        "user_id": user["id"],
        "base_url": base_url,
        "endpoints": endpoints if isinstance(endpoints, list) else ["/health"],
        "interval_seconds": interval,
        "method": method,
        "last_pinged_at": 0.0,
    })
    return jsonify(svc), 201


@app.route("/api/services/<service_id>", methods=["GET"])
@require_auth
def get_service(service_id):
    user = get_current_user()
    service = store.service_get(service_id)
    if not service or service["user_id"] != user["id"]:
        return jsonify({"error": "Service not found"}), 404
    return jsonify(service), 200


@app.route("/api/services/<service_id>", methods=["PUT"])
@require_auth
def update_service(service_id):
    user = get_current_user()
    service = store.service_get(service_id)
    if not service or service["user_id"] != user["id"]:
        return jsonify({"error": "Service not found"}), 404

    data = request.json or {}
    fields = {}
    if "base_url" in data or "url" in data:
        fields["base_url"] = data.get("base_url") or data.get("url")
    if "endpoints" in data:
        fields["endpoints"] = data["endpoints"]
    if "method" in data:
        fields["method"] = _normalize_method(data["method"])

    if any(k in data for k in ("interval_seconds", "interval_minutes", "pings_per_day")):
        interval, err = _parse_interval(data)
        if err:
            return jsonify({"error": err}), 400
        fields["interval_seconds"] = interval

    if fields:
        service = store.service_update(service_id, **fields)
    return jsonify(service), 200


@app.route("/api/services/<service_id>", methods=["DELETE"])
@require_auth
def delete_service(service_id):
    user = get_current_user()
    service = store.service_get(service_id)
    if not service or service["user_id"] != user["id"]:
        return jsonify({"error": "Service not found"}), 404

    store.service_delete(service_id)
    return jsonify({"message": "Service deleted"}), 200


@app.route("/api/services/<service_id>/test", methods=["POST"])
@require_auth
def test_service(service_id):
    user = get_current_user()
    service = store.service_get(service_id)
    if not service or service["user_id"] != user["id"]:
        return jsonify({"error": "Service not found"}), 404

    results = []
    for endpoint in service["endpoints"]:
        url = service["base_url"].rstrip("/") + "/" + endpoint.lstrip("/")
        result = _do_ping(url, service["method"])
        result["endpoint"] = endpoint
        results.append(result)

    return jsonify({"results": results}), 200


# ---------------------------------------------------------------------------
# History & Analytics (Recent History: Time / Service / Status / Duration)
# ---------------------------------------------------------------------------
@app.route("/api/history", methods=["GET"])
@require_auth
def get_history():
    user = get_current_user()
    service_id = request.args.get("service_id")

    if service_id:
        service = store.service_get(service_id)
        if not service or service["user_id"] != user["id"]:
            return jsonify({"error": "Service not found or unauthorized"}), 404

    records = store.pings_for_user(user["id"], service_id=service_id, limit=100)
    return jsonify(records), 200


@app.route("/api/services/<service_id>/analytics", methods=["GET"])
@require_auth
def get_analytics(service_id):
    user = get_current_user()
    service = store.service_get(service_id)
    if not service or service["user_id"] != user["id"]:
        return jsonify({"error": "Service not found"}), 404

    service_records = store.pings_for_service(service_id)

    if not service_records:
        return jsonify({
            "total_pings": 0,
            "success_rate": 0,
            "avg_response_time_ms": 0,
        }), 200

    successful = [
        r for r in service_records
        if r["success"] and r["status_code"] is not None and r["status_code"] < 400
    ]
    total = len(service_records)
    successes = len(successful)
    success_rate = (successes / total) * 100 if total else 0
    avg_time = (
        sum(r["response_time_ms"] for r in successful) / successes if successes else 0
    )

    return jsonify({
        "total_pings": total,
        "success_rate": round(success_rate, 2),
        "avg_response_time_ms": round(avg_time, 2),
    }), 200


# ---------------------------------------------------------------------------
# Background Execution Engine
# ---------------------------------------------------------------------------
def ping_url(url: str, service_id: str, user_id: str, endpoint: str, method: str = "GET"):
    result = _do_ping(url, method)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "service_id": service_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "endpoint": endpoint,
        "status_code": result["status_code"],
        "success": result["success"],
        "response_time_ms": result["response_time_ms"],
        "error": result["error"],
    }
    if result["success"]:
        logger.info(
            "✅  PING OK   | %s %s | HTTP %s | %sms",
            method, url, result["status_code"], result["response_time_ms"],
        )
    else:
        logger.error("❌  ERROR     | %s %s | %s", method, url, result["error"])

    try:
        store.ping_append(record)
    except Exception as e:
        logger.error("Failed to persist ping record: %s", e)


def pinger_loop():
    logger.info("🚀  Background execution engine started.")
    last_self_ping = 0.0
    self_ping_interval = 840

    while True:
        now = time.time()

        if SELF_URL and (now - last_self_ping) >= self_ping_interval:
            logger.info("🔄  Self keep-alive ping to %s", SELF_URL)
            try:
                requests.get(SELF_URL, timeout=REQUEST_TIMEOUT)
                logger.info("✅  SELF PING OK")
            except Exception as e:
                logger.error("❌  SELF PING ERROR | %s", e)
            last_self_ping = time.time()

        try:
            services = store.services_all()
        except Exception as e:
            logger.error("Failed to load services: %s", e)
            services = []

        for service in services:
            if (now - service["last_pinged_at"]) >= service["interval_seconds"]:
                logger.info(
                    "🔄  Pinging service %s (%s %s)",
                    service["id"], service["method"], service["base_url"],
                )
                for endpoint in service["endpoints"]:
                    url = service["base_url"].rstrip("/") + "/" + str(endpoint).lstrip("/")
                    ping_url(
                        url,
                        service["id"],
                        service["user_id"],
                        endpoint,
                        service["method"],
                    )
                    time.sleep(9)
                try:
                    store.service_update(service["id"], last_pinged_at=time.time())
                except Exception as e:
                    logger.error("Failed to update last_pinged_at: %s", e)

        time.sleep(1)


pinger_thread = threading.Thread(target=pinger_loop, daemon=True, name="pinger")
pinger_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
