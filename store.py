"""Pyronites-backed persistence for fluffy-spork.

Tables (create once in the Pyronites dashboard or via bootstrap_schema):

  fs_users          id, email, password
  fs_tokens         id (token), user_id
  fs_services       id, user_id, base_url, endpoints, interval_seconds, method, last_pinged_at
  fs_ping_records   id, user_id, service_id, timestamp, endpoint, status_code, success, response_time_ms, error

``endpoints`` is a JSON array string. Numeric/bool fields are stored as strings
compatible with the backend TEXT columns when needed.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from pyronites import ApiError, NotFoundError, create_client

logger = logging.getLogger(__name__)

T_USERS = "fs_users"
T_TOKENS = "fs_tokens"
T_SERVICES = "fs_services"
T_PINGS = "fs_ping_records"


def _client():
    return create_client(
        url=os.environ.get("PYRONITES_URL"),
        key=os.environ.get("PYRONITES_KEY"),
    )


def bootstrap_schema() -> None:
    """Best-effort CREATE TABLE via admin SQL. Safe to call on every startup."""
    ddl = [
        f"""CREATE TABLE IF NOT EXISTS {T_USERS} (
            id TEXT PRIMARY KEY,
            email TEXT,
            password TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS {T_TOKENS} (
            id TEXT PRIMARY KEY,
            user_id TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS {T_SERVICES} (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            base_url TEXT,
            endpoints TEXT,
            interval_seconds TEXT,
            method TEXT,
            last_pinged_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS {T_PINGS} (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            service_id TEXT,
            timestamp TEXT,
            endpoint TEXT,
            status_code TEXT,
            success TEXT,
            response_time_ms TEXT,
            error TEXT
        )""",
    ]
    c = _client()
    try:
        for sql in ddl:
            try:
                c.sql(sql)
            except ApiError as e:
                logger.warning("bootstrap_schema: %s", e)
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def user_by_email(email: str) -> Optional[Dict[str, Any]]:
    c = _client()
    try:
        rows = list(c.table(T_USERS).select().eq("email", email).limit(5))
        return rows[0] if rows else None
    finally:
        c.close()


def user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    c = _client()
    try:
        return c.table(T_USERS).get(user_id)
    except NotFoundError:
        return None
    except ApiError:
        return None
    finally:
        c.close()


def user_create(user_id: str, email: str, password: str) -> Dict[str, Any]:
    c = _client()
    try:
        return c.table(T_USERS).insert(
            {"id": user_id, "email": email, "password": password}
        )
    finally:
        c.close()


def user_update(user_id: str, **fields: Any) -> Dict[str, Any]:
    c = _client()
    try:
        return c.table(T_USERS).update(fields).eq("id", user_id)
    finally:
        c.close()


def users_count() -> int:
    c = _client()
    try:
        return len(list(c.table(T_USERS).select().limit(200)))
    except ApiError:
        return 0
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def token_save(token: str, user_id: str) -> None:
    c = _client()
    try:
        c.table(T_TOKENS).insert({"id": token, "user_id": user_id})
    finally:
        c.close()


def token_user_id(token: str) -> Optional[str]:
    c = _client()
    try:
        row = c.table(T_TOKENS).get(token)
        return row.get("user_id") if row else None
    except NotFoundError:
        return None
    except ApiError:
        return None
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def _service_to_row(svc: Dict[str, Any]) -> Dict[str, Any]:
    endpoints = svc.get("endpoints", ["/health"])
    if not isinstance(endpoints, str):
        endpoints = json.dumps(endpoints)
    return {
        "id": svc["id"],
        "user_id": svc["user_id"],
        "base_url": svc["base_url"],
        "endpoints": endpoints,
        "interval_seconds": str(int(svc.get("interval_seconds", 840))),
        "method": svc.get("method") or "GET",
        "last_pinged_at": str(float(svc.get("last_pinged_at") or 0.0)),
    }


def _row_to_service(row: Dict[str, Any]) -> Dict[str, Any]:
    endpoints = row.get("endpoints") or "[]"
    if isinstance(endpoints, str):
        try:
            endpoints = json.loads(endpoints)
        except json.JSONDecodeError:
            endpoints = ["/health"]
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "base_url": row["base_url"],
        "endpoints": endpoints if isinstance(endpoints, list) else ["/health"],
        "interval_seconds": int(float(row.get("interval_seconds") or 840)),
        "method": row.get("method") or "GET",
        "last_pinged_at": float(row.get("last_pinged_at") or 0.0),
    }


def services_for_user(user_id: str) -> List[Dict[str, Any]]:
    c = _client()
    try:
        rows = list(c.table(T_SERVICES).select().eq("user_id", user_id).limit(200))
        return [_row_to_service(r) for r in rows]
    finally:
        c.close()


def services_all() -> List[Dict[str, Any]]:
    c = _client()
    try:
        rows = list(c.table(T_SERVICES).select().limit(200))
        return [_row_to_service(r) for r in rows]
    except ApiError:
        return []
    finally:
        c.close()


def service_get(service_id: str) -> Optional[Dict[str, Any]]:
    c = _client()
    try:
        row = c.table(T_SERVICES).get(service_id)
        return _row_to_service(row) if row else None
    except NotFoundError:
        return None
    except ApiError:
        return None
    finally:
        c.close()


def service_create(svc: Dict[str, Any]) -> Dict[str, Any]:
    c = _client()
    try:
        row = c.table(T_SERVICES).insert(_service_to_row(svc))
        return _row_to_service(row)
    finally:
        c.close()


def service_update(service_id: str, **fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if "base_url" in fields:
        payload["base_url"] = fields["base_url"]
    if "endpoints" in fields:
        ep = fields["endpoints"]
        payload["endpoints"] = ep if isinstance(ep, str) else json.dumps(ep)
    if "method" in fields:
        payload["method"] = fields["method"]
    if "interval_seconds" in fields:
        payload["interval_seconds"] = str(int(fields["interval_seconds"]))
    if "last_pinged_at" in fields:
        payload["last_pinged_at"] = str(float(fields["last_pinged_at"]))
    c = _client()
    try:
        row = c.table(T_SERVICES).update(payload).eq("id", service_id)
        return _row_to_service(row)
    finally:
        c.close()


def service_delete(service_id: str) -> None:
    c = _client()
    try:
        c.table(T_SERVICES).delete().eq("id", service_id)
    finally:
        c.close()


def services_count() -> int:
    c = _client()
    try:
        return len(list(c.table(T_SERVICES).select().limit(200)))
    except ApiError:
        return 0
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Ping history (Recent History: Time / Service / Status / Duration)
# ---------------------------------------------------------------------------

def ping_append(record: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "id": record["id"],
        "user_id": record.get("user_id") or "",
        "service_id": record["service_id"],
        "timestamp": record["timestamp"],
        "endpoint": record.get("endpoint") or "/",
        "status_code": "" if record.get("status_code") is None else str(record["status_code"]),
        "success": "1" if record.get("success") else "0",
        "response_time_ms": str(int(record.get("response_time_ms") or 0)),
        "error": record.get("error") or "",
    }
    c = _client()
    try:
        return c.table(T_PINGS).insert(row)
    finally:
        c.close()


def _row_to_ping(row: Dict[str, Any]) -> Dict[str, Any]:
    sc = row.get("status_code")
    status_code = None
    if sc not in (None, ""):
        try:
            status_code = int(sc)
        except (TypeError, ValueError):
            status_code = None
    return {
        "id": row["id"],
        "user_id": row.get("user_id") or "",
        "service_id": row["service_id"],
        "timestamp": row.get("timestamp") or "",
        "endpoint": row.get("endpoint") or "/",
        "status_code": status_code,
        "success": str(row.get("success")) in ("1", "true", "True"),
        "response_time_ms": int(float(row.get("response_time_ms") or 0)),
        "error": row.get("error") or None,
    }


def pings_for_user(user_id: str, service_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    c = _client()
    try:
        if service_id:
            rows = list(
                c.table(T_PINGS).select().eq("service_id", service_id).limit(200)
            )
        else:
            rows = list(c.table(T_PINGS).select().eq("user_id", user_id).limit(200))
        out = [_row_to_ping(r) for r in rows]
        # Newest first by timestamp string (ISO)
        out.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
        return out[:limit]
    except ApiError:
        return []
    finally:
        c.close()


def pings_for_service(service_id: str) -> List[Dict[str, Any]]:
    c = _client()
    try:
        rows = list(c.table(T_PINGS).select().eq("service_id", service_id).limit(200))
        return [_row_to_ping(r) for r in rows]
    except ApiError:
        return []
    finally:
        c.close()
