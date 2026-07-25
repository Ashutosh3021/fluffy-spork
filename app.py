import os
import uuid
import time
import logging
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional, Dict

import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

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
app.config['JSON_SORT_KEYS'] = False

CORS(app, resources={
    r"/*": {
        "origins": [
            "https://keep-awake1.vercel.app",
            re.compile(r"http://localhost:.*")
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
    }
})

ALLOWED_METHODS = {"GET", "HEAD", "POST", "PUT"}

# ---------------------------------------------------------------------------
# Data Models (In-Memory)
# ---------------------------------------------------------------------------
@dataclass
class User:
    id: str
    email: str
    password: str

@dataclass
class Service:
    id: str
    user_id: str
    base_url: str
    endpoints: List[str]
    interval_seconds: int
    method: str = "GET"
    last_pinged_at: float = 0.0

@dataclass
class PingRecord:
    id: str
    service_id: str
    timestamp: str
    endpoint: str
    status_code: Optional[int]
    success: bool
    response_time_ms: int
    error: Optional[str]

# ---------------------------------------------------------------------------
# In-Memory Storage
# ---------------------------------------------------------------------------
db_users: Dict[str, User] = {}
db_users_by_email: Dict[str, User] = {}
db_tokens: Dict[str, str] = {}
db_services: Dict[str, Service] = {}
db_ping_records: List[PingRecord] = []

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.environ.get("PORT", "8080"))
SELF_URL = os.environ.get("SELF_URL", "")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "15"))
start_time = time.time()

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}), 200

@app.route("/api/status")
def status():
    uptime_seconds = time.time() - start_time
    return jsonify({
        "status": "ok",
        "version": "1.1.0",
        "uptime_seconds": int(uptime_seconds),
        "users_count": len(db_users),
        "services_count": len(db_services),
    }), 200


# ---------------------------------------------------------------------------
# Auth Helpers
# ---------------------------------------------------------------------------
def get_current_user():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    user_id = db_tokens.get(token)
    if user_id:
        return db_users.get(user_id)
    return None

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
    if email in db_users_by_email:
        return jsonify({"error": "Email already exists"}), 409

    user_id = str(uuid.uuid4())
    user = User(id=user_id, email=email, password=password)
    db_users[user_id] = user
    db_users_by_email[email] = user

    return jsonify({"message": "User created", "user_id": user_id}), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password") or data.get("pin")

    if not email or not password:
        return jsonify({"error": "Email and password/pin are required"}), 400

    user = db_users_by_email.get(email)
    if not user or user.password != password:
        return jsonify({"error": "Invalid credentials"}), 401

    token = str(uuid.uuid4())
    db_tokens[token] = user.id

    return jsonify({"token": token}), 200

@app.route("/api/auth/profile", methods=["PUT"])
@require_auth
def update_profile():
    user = get_current_user()
    data = request.json or {}

    new_email = data.get("email")
    new_password = data.get("password") or data.get("pin")

    if new_email:
        if new_email != user.email and new_email in db_users_by_email:
            return jsonify({"error": "Email already exists"}), 409
        del db_users_by_email[user.email]
        user.email = new_email
        db_users_by_email[new_email] = user

    if new_password:
        user.password = new_password

    return jsonify({"message": "Profile updated"}), 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_method(method: Optional[str]) -> str:
    m = (method or "GET").upper().strip()
    if m not in ALLOWED_METHODS:
        return "GET"
    return m

def _do_ping(url: str, method: str = "GET") -> dict:
    """Ping a single URL with the given HTTP method."""
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
            "error": None
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "url": url,
            "method": method,
            "success": False,
            "status_code": None,
            "response_time_ms": elapsed_ms,
            "error": str(e)
        }


# ---------------------------------------------------------------------------
# Test-before-create (no service ID required)
# ---------------------------------------------------------------------------
@app.route("/api/test", methods=["POST"])
@require_auth
def test_url():
    """Test one or more URLs without saving a service."""
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
# Service Management Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/services", methods=["GET"])
@require_auth
def list_services():
    user = get_current_user()
    user_services = [s for s in db_services.values() if s.user_id == user.id]
    return jsonify([s.__dict__ for s in user_services]), 200

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

    interval_seconds = data.get("interval_seconds")
    interval_minutes = data.get("interval_minutes")
    pings_per_day = data.get("pings_per_day")

    if interval_seconds:
        interval = int(interval_seconds)
    elif interval_minutes:
        interval = int(interval_minutes) * 60
    elif pings_per_day:
        interval = int(86400 / max(1, int(pings_per_day)))
    else:
        interval = 840

    if interval < 60:
        return jsonify({"error": "Interval must be at least 60 seconds"}), 400

    service_id = str(uuid.uuid4())
    service = Service(
        id=service_id,
        user_id=user.id,
        base_url=base_url,
        endpoints=endpoints if isinstance(endpoints, list) else ["/health"],
        interval_seconds=interval,
        method=method
    )
    db_services[service_id] = service
    return jsonify(service.__dict__), 201

@app.route("/api/services/<service_id>", methods=["GET"])
@require_auth
def get_service(service_id):
    user = get_current_user()
    service = db_services.get(service_id)
    if not service or service.user_id != user.id:
        return jsonify({"error": "Service not found"}), 404
    return jsonify(service.__dict__), 200

@app.route("/api/services/<service_id>", methods=["PUT"])
@require_auth
def update_service(service_id):
    user = get_current_user()
    service = db_services.get(service_id)
    if not service or service.user_id != user.id:
        return jsonify({"error": "Service not found"}), 404

    data = request.json or {}
    if "base_url" in data or "url" in data:
        service.base_url = data.get("base_url") or data.get("url")
    if "endpoints" in data:
        service.endpoints = data["endpoints"]
    if "method" in data:
        service.method = _normalize_method(data["method"])
    if "interval_seconds" in data:
        service.interval_seconds = int(data["interval_seconds"])
    elif "interval_minutes" in data:
        service.interval_seconds = int(data["interval_minutes"]) * 60
    elif "pings_per_day" in data:
        service.interval_seconds = int(86400 / max(1, int(data["pings_per_day"])))

    return jsonify(service.__dict__), 200

@app.route("/api/services/<service_id>", methods=["DELETE"])
@require_auth
def delete_service(service_id):
    user = get_current_user()
    service = db_services.get(service_id)
    if not service or service.user_id != user.id:
        return jsonify({"error": "Service not found"}), 404

    del db_services[service_id]
    return jsonify({"message": "Service deleted"}), 200

@app.route("/api/services/<service_id>/test", methods=["POST"])
@require_auth
def test_service(service_id):
    user = get_current_user()
    service = db_services.get(service_id)
    if not service or service.user_id != user.id:
        return jsonify({"error": "Service not found"}), 404

    results = []
    for endpoint in service.endpoints:
        url = service.base_url.rstrip("/") + "/" + endpoint.lstrip("/")
        result = _do_ping(url, service.method)
        result["endpoint"] = endpoint
        results.append(result)

    return jsonify({"results": results}), 200


# ---------------------------------------------------------------------------
# History & Records Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/history", methods=["GET"])
@require_auth
def get_history():
    user = get_current_user()
    service_id = request.args.get("service_id")

    user_service_ids = {s.id for s in db_services.values() if s.user_id == user.id}

    if service_id and service_id not in user_service_ids:
        return jsonify({"error": "Service not found or unauthorized"}), 404

    records = []
    for r in reversed(db_ping_records):
        if r.service_id in user_service_ids:
            if not service_id or r.service_id == service_id:
                records.append(r.__dict__)
        if len(records) >= 100:
            break

    return jsonify(records), 200

@app.route("/api/services/<service_id>/analytics", methods=["GET"])
@require_auth
def get_analytics(service_id):
    user = get_current_user()
    service = db_services.get(service_id)
    if not service or service.user_id != user.id:
        return jsonify({"error": "Service not found"}), 404

    service_records = [r for r in db_ping_records if r.service_id == service_id]

    if not service_records:
        return jsonify({
            "total_pings": 0,
            "success_rate": 0,
            "avg_response_time_ms": 0
        }), 200

    successful_pings = [r for r in service_records if r.success and r.status_code and r.status_code < 400]

    total = len(service_records)
    successes = len(successful_pings)
    success_rate = (successes / total) * 100 if total > 0 else 0

    total_time = sum(r.response_time_ms for r in successful_pings)
    avg_time = (total_time / successes) if successes > 0 else 0

    return jsonify({
        "total_pings": total,
        "success_rate": round(success_rate, 2),
        "avg_response_time_ms": round(avg_time, 2)
    }), 200

# ---------------------------------------------------------------------------
# Background Execution Engine
# ---------------------------------------------------------------------------
def ping_url(url: str, service_id: str, endpoint: str, method: str = "GET"):
    result = _do_ping(url, method)
    record = PingRecord(
        id=str(uuid.uuid4()),
        service_id=service_id,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        endpoint=endpoint,
        status_code=result["status_code"],
        success=result["success"],
        response_time_ms=result["response_time_ms"],
        error=result["error"]
    )
    if result["success"]:
        logger.info(f"✅  PING OK   | {method} {url} | HTTP {result['status_code']} | {result['response_time_ms']}ms")
    else:
        logger.error(f"❌  ERROR     | {method} {url} | {result['error']}")

    db_ping_records.append(record)
    if len(db_ping_records) > 10000:
        db_ping_records.pop(0)

def pinger_loop():
    logger.info("🚀  Background execution engine started.")
    last_self_ping = 0.0
    self_ping_interval = 840

    while True:
        now = time.time()

        if SELF_URL and (now - last_self_ping) >= self_ping_interval:
            logger.info(f"🔄  Self keep-alive ping to {SELF_URL}")
            try:
                requests.get(SELF_URL, timeout=REQUEST_TIMEOUT)
                logger.info(f"✅  SELF PING OK")
            except Exception as e:
                logger.error(f"❌  SELF PING ERROR | {e}")
            last_self_ping = time.time()

        for service_id, service in list(db_services.items()):
            if (now - service.last_pinged_at) >= service.interval_seconds:
                logger.info(f"🔄  Pinging service {service_id} ({service.method} {service.base_url})")
                for endpoint in service.endpoints:
                    url = service.base_url.rstrip("/") + "/" + endpoint.lstrip("/")
                    ping_url(url, service_id, endpoint, service.method)
                    time.sleep(9)
                service.last_pinged_at = time.time()

        time.sleep(1)

pinger_thread = threading.Thread(target=pinger_loop, daemon=True, name="pinger")
pinger_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
