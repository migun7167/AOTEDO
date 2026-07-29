"""Authentication and role-based access control.

Roles follow design document §4:

  ADMINISTRATOR  import, reprocess, manual match, resolve, settings, users, audit
  OPERATOR       import, view, mark reviewed, add notes, export
  VIEWER         view and export only
"""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

SESSION_COOKIE = "paot_session"
SESSION_HOURS = 12
PBKDF2_ITERATIONS = 120_000

# Sign-in throttling: this many failures for one username inside the window
# locks it until the window rolls past the oldest failure.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

MIN_PASSWORD_LENGTH = 8
# Rejected outright — these are the ones an attacker tries first, and the
# seeded demo passwords must not survive into production.
WEAK_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "1234567890",
    "qwerty123", "admin123", "operator123", "viewer123", "paperless",
    "aot12345", "changeme", "letmein1", "welcome1",
}

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


class PasswordError(ValueError):
    pass


def validate_password(password: str, username: str = "") -> str:
    """Reject the passwords that make an audit finding, not every weak one."""
    password = (password or "").strip()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordError(
            f"รหัสผ่านต้องยาวอย่างน้อย {MIN_PASSWORD_LENGTH} ตัวอักษร")
    if password.lower() in WEAK_PASSWORDS:
        raise PasswordError("รหัสผ่านนี้เดาง่ายเกินไป กรุณาตั้งใหม่")
    if username and password.lower() == username.strip().lower():
        raise PasswordError("รหัสผ่านต้องไม่ซ้ำกับชื่อผู้ใช้")
    if password.isdigit() or password.isalpha():
        raise PasswordError("รหัสผ่านต้องมีทั้งตัวอักษรและตัวเลข")
    return password


def ensure_default_users(conn: sqlite3.Connection) -> None:
    """Create the three demo accounts on an empty user table.

    They are flagged must_change_password, so the published demo credentials
    cannot survive into real use — the first sign-in has to replace them.
    """
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    ts = _now().isoformat(timespec="seconds")
    for username, password, role, display in DEFAULT_USERS:
        conn.execute(
            """INSERT INTO users
               (id, username, display_name, password_hash, role, active,
                must_change_password, created_at)
               VALUES (?,?,?,?,?,1,1,?)""",
            (str(uuid.uuid4()), username, display,
             hash_password(password), role, ts))


def _record_attempt(conn: sqlite3.Connection, username: str, ip: str | None,
                    success: bool) -> None:
    """Commit immediately: a failed sign-in raises, and the request's own
    transaction is rolled back — without this the attempt would vanish and
    throttling would never trigger."""
    conn.execute(
        """INSERT INTO login_attempts (id, username, ip_address, success, created_at)
           VALUES (?,?,?,?,?)""",
        (str(uuid.uuid4()), username, ip, 1 if success else 0,
         _now().isoformat(timespec="seconds")))
    conn.commit()


def failed_attempts(conn: sqlite3.Connection, username: str) -> int:
    """Failures since the last success, inside the lockout window."""
    since = (_now() - timedelta(minutes=LOCKOUT_MINUTES)).isoformat(
        timespec="seconds")
    rows = conn.execute(
        """SELECT success FROM login_attempts
           WHERE username = ? AND created_at >= ?
           ORDER BY created_at DESC""", (username, since)).fetchall()
    count = 0
    for row in rows:
        if row["success"]:
            break
        count += 1
    return count


def login(conn: sqlite3.Connection, username: str, password: str,
          ip: str | None = None) -> tuple[dict, str]:
    username = username.strip().lower()

    if failed_attempts(conn, username) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(status_code=429, detail={
            "code": "TOO_MANY_ATTEMPTS",
            "message": f"ลองผิดเกิน {MAX_FAILED_ATTEMPTS} ครั้ง "
                       f"กรุณารออีก {LOCKOUT_MINUTES} นาทีแล้วลองใหม่"})

    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND active = 1",
        (username,)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        _record_attempt(conn, username, ip, success=False)
        remaining = MAX_FAILED_ATTEMPTS - failed_attempts(conn, username)
        message = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
        if 0 < remaining <= 2:
            message += f" (เหลืออีก {remaining} ครั้งก่อนถูกล็อก)"
        raise HTTPException(status_code=401, detail={
            "code": "INVALID_CREDENTIALS", "message": message})

    _record_attempt(conn, username, ip, success=True)
    token = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, row["id"], now.isoformat(timespec="seconds"),
         (now + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")))
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?",
                 (now.isoformat(timespec="seconds"), row["id"]))
    return _public(row), token


def change_password(conn: sqlite3.Connection, user_id: str, current: str,
                    new_password: str) -> None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise PasswordError("ไม่พบผู้ใช้")
    if not verify_password(current, row["password_hash"]):
        raise HTTPException(status_code=401, detail={
            "code": "INVALID_CREDENTIALS", "message": "รหัสผ่านเดิมไม่ถูกต้อง"})
    if verify_password(new_password, row["password_hash"]):
        raise PasswordError("รหัสผ่านใหม่ต้องไม่ซ้ำกับรหัสผ่านเดิม")
    validate_password(new_password, row["username"])
    conn.execute(
        """UPDATE users SET password_hash = ?, must_change_password = 0
           WHERE id = ?""", (hash_password(new_password), user_id))
    # every other session of this account is invalidated
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def create_user(conn: sqlite3.Connection, username: str, password: str,
                role: str, display_name: str = "") -> dict:
    username = (username or "").strip().lower()
    if not re.match(r"^[a-z0-9._-]{3,32}$", username):
        raise PasswordError(
            "ชื่อผู้ใช้ต้องยาว 3-32 ตัว ใช้ได้เฉพาะ a-z 0-9 . _ -")
    if role not in ROLES:
        raise PasswordError(f"บทบาทต้องเป็นหนึ่งใน {', '.join(ROLES)}")
    if conn.execute("SELECT 1 FROM users WHERE username = ?",
                    (username,)).fetchone():
        raise PasswordError(f"มีผู้ใช้ชื่อ {username} อยู่แล้ว")
    validate_password(password, username)
    user_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO users
           (id, username, display_name, password_hash, role, active,
            must_change_password, created_at)
           VALUES (?,?,?,?,?,1,1,?)""",
        (user_id, username, display_name or username, hash_password(password),
         role, _now().isoformat(timespec="seconds")))
    return {"id": user_id, "username": username, "role": role,
            "displayName": display_name or username}


def update_user(conn: sqlite3.Connection, user_id: str, actor: dict,
                role: str | None = None, active: bool | None = None,
                display_name: str | None = None) -> dict:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise PasswordError("ไม่พบผู้ใช้")

    if role is not None and role not in ROLES:
        raise PasswordError(f"บทบาทต้องเป็นหนึ่งใน {', '.join(ROLES)}")

    # An administrator must not lock themselves out, nor leave the system
    # without anyone who can administer it.
    losing_admin = (row["role"] == ADMIN
                    and ((role is not None and role != ADMIN)
                         or active is False))
    if losing_admin:
        others = conn.execute(
            """SELECT COUNT(*) c FROM users
               WHERE role = ? AND active = 1 AND id != ?""",
            (ADMIN, user_id)).fetchone()["c"]
        if others == 0:
            raise PasswordError(
                "ต้องมี Administrator ที่ใช้งานได้อย่างน้อย 1 บัญชีเสมอ")
    if active is False and row["id"] == actor["id"]:
        raise PasswordError("ปิดการใช้งานบัญชีของตัวเองไม่ได้")

    conn.execute(
        """UPDATE users SET role = COALESCE(?, role),
           active = COALESCE(?, active),
           display_name = COALESCE(?, display_name) WHERE id = ?""",
        (role, None if active is None else int(active), display_name, user_id))
    if active is False:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"id": user_id}


def reset_password(conn: sqlite3.Connection, user_id: str,
                   new_password: str) -> None:
    row = conn.execute("SELECT username FROM users WHERE id = ?",
                       (user_id,)).fetchone()
    if not row:
        raise PasswordError("ไม่พบผู้ใช้")
    validate_password(new_password, row["username"])
    conn.execute(
        """UPDATE users SET password_hash = ?, must_change_password = 1
           WHERE id = ?""", (hash_password(new_password), user_id))
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


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
            "displayName": row["display_name"], "role": row["role"],
            "mustChangePassword": bool(row["must_change_password"])}


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
