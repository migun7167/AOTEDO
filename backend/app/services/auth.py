"""Authentication and role-based access control.

Roles follow design document §4:

  ADMINISTRATOR  import, reprocess, manual match, resolve, settings, users, audit
  OPERATOR       import, view, mark reviewed, add notes, export
  VIEWER         view and export only
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

SESSION_COOKIE = "paot_session"
SESSION_HOURS = 12
PBKDF2_ITERATIONS = 120_000

ADMIN = "ADMINISTRATOR"
OPERATOR = "OPERATOR"
VIEWER = "VIEWER"
ROLES = (ADMIN, OPERATOR, VIEWER)

DEFAULT_USERS = [
    ("admin", "admin123", ADMIN, "System Administrator"),
    ("operator", "operator123", OPERATOR, "Cargo Operator"),
    ("viewer", "viewer123", VIEWER, "Read-only Viewer"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), int(iterations))
    return secrets.compare_digest(dk.hex(), digest)


def ensure_default_users(conn: sqlite3.Connection) -> None:
    """Create the three demo accounts on an empty user table."""
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    ts = _now().isoformat(timespec="seconds")
    for username, password, role, display in DEFAULT_USERS:
        conn.execute(
            """INSERT INTO users
               (id, username, display_name, password_hash, role, active, created_at)
               VALUES (?,?,?,?,?,1,?)""",
            (str(uuid.uuid4()), username, display,
             hash_password(password), role, ts))


def login(conn: sqlite3.Connection, username: str, password: str) -> tuple[dict, str]:
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND active = 1",
        (username.strip().lower(),)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail={
            "code": "INVALID_CREDENTIALS",
            "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"})
    token = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, row["id"], now.isoformat(timespec="seconds"),
         (now + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")))
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?",
                 (now.isoformat(timespec="seconds"), row["id"]))
    return _public(row), token


def logout(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def session_user(conn: sqlite3.Connection, token: str | None) -> dict | None:
    if not token:
        return None
    row = conn.execute(
        """SELECT u.* , s.expires_at FROM sessions s
           JOIN users u ON u.id = s.user_id
           WHERE s.token = ? AND u.active = 1""", (token,)).fetchone()
    if not row:
        return None
    if row["expires_at"] < _now().isoformat(timespec="seconds"):
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return None
    return _public(row)


def _public(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"],
            "displayName": row["display_name"], "role": row["role"]}


def require(*roles: str):
    """FastAPI dependency: authenticated, and in one of `roles` if given."""
    def dependency(request: Request) -> dict:
        # imported here to avoid a circular import at module load
        from ..database import db
        with db() as conn:
            user = session_user(conn, request.cookies.get(SESSION_COOKIE))
        if not user:
            raise HTTPException(status_code=401, detail={
                "code": "UNAUTHENTICATED", "message": "กรุณาเข้าสู่ระบบ"})
        if roles and user["role"] not in roles:
            raise HTTPException(status_code=403, detail={
                "code": "FORBIDDEN",
                "message": f"บทบาท {user['role']} ไม่มีสิทธิ์ดำเนินการนี้"})
        return user
    return dependency
