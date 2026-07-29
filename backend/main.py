"""Paperless AOT — FWB/FHL Matching Portal API + frontend host."""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

from app.database import db, init_db  # noqa: E402
from app.services import do_service, export_service, settings_service  # noqa: E402
from app.services import import_service as svc  # noqa: E402
from app.services.auth import (  # noqa: E402
    ADMIN, OPERATOR, SESSION_COOKIE, VIEWER, ensure_default_users, require,
)
from app.services import auth as auth_service  # noqa: E402

app = FastAPI(title="Paperless AOT — FWB/FHL Matching Portal", version="1.1.0")

init_db()
with db() as _conn:
    ensure_default_users(_conn)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# Role shorthands (design doc §4)
any_user = require(ADMIN, OPERATOR, VIEWER)
can_import = require(ADMIN, OPERATOR)
can_review = require(ADMIN, OPERATOR)
admin_only = require(ADMIN)

# Effective status: an administrator's manual resolution wins over the
# computed one, so every status filter and display goes through this.
EFFECTIVE_STATUS = "COALESCE(mr.override_status, mr.match_status)"


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code,
                        content={"code": "ERROR", "message": str(detail)})


def client_info(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None,
            request.headers.get("user-agent"))


# ------------------------------------------------------------------- auth ---

class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/v1/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    ip, ua = client_info(request)
    with db() as conn:
        user, token = auth_service.login(conn, body.username, body.password, ip)
        svc.audit(conn, "LOGIN", user["username"], "users", user["id"],
                  after={"role": user["role"]}, ip=ip, user_agent=ua)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                        max_age=auth_service.SESSION_HOURS * 3600)
    return {"user": user}


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response):
    with db() as conn:
        auth_service.logout(conn, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "LOGGED_OUT"}


@app.get("/api/v1/auth/me")
def me(user: dict = Depends(any_user)):
    return {"user": user}


class PasswordBody(BaseModel):
    currentPassword: str
    newPassword: str


@app.post("/api/v1/auth/password")
def change_own_password(body: PasswordBody, request: Request,
                        response: Response, user: dict = Depends(any_user)):
    """Any signed-in user changes their own password; all sessions are dropped."""
    with db() as conn:
        try:
            auth_service.change_password(conn, user["id"], body.currentPassword,
                                         body.newPassword)
        except auth_service.PasswordError as e:
            raise HTTPException(400, {"code": "WEAK_PASSWORD",
                                      "message": str(e)})
        ip, ua = client_info(request)
        svc.audit(conn, "CHANGE_PASSWORD", user["username"], "users",
                  user["id"], ip=ip, user_agent=ua)
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "PASSWORD_CHANGED", "reloginRequired": True}


@app.get("/api/v1/users")
def list_users(user: dict = Depends(admin_only)):
    with db() as conn:
        rows = conn.execute(
            """SELECT id, username, display_name, role, active,
                      must_change_password, created_at, last_login_at
               FROM users ORDER BY username""").fetchall()
    return {"items": [dict(r) for r in rows]}


class NewUserBody(BaseModel):
    username: str
    password: str
    role: str
    displayName: str = ""


@app.post("/api/v1/users")
def add_user(body: NewUserBody, request: Request,
             user: dict = Depends(admin_only)):
    with db() as conn:
        try:
            created = auth_service.create_user(
                conn, body.username, body.password, body.role, body.displayName)
        except auth_service.PasswordError as e:
            raise HTTPException(400, {"code": "INVALID_USER",
                                      "message": str(e)})
        ip, ua = client_info(request)
        svc.audit(conn, "CREATE_USER", user["username"], "users",
                  created["id"], after={"username": created["username"],
                                        "role": created["role"]},
                  ip=ip, user_agent=ua)
    return created


class UpdateUserBody(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None
    displayName: Optional[str] = None


@app.patch("/api/v1/users/{user_id}")
def edit_user(user_id: str, body: UpdateUserBody, request: Request,
              user: dict = Depends(admin_only)):
    with db() as conn:
        before = conn.execute(
            "SELECT username, role, active FROM users WHERE id = ?",
            (user_id,)).fetchone()
        try:
            auth_service.update_user(conn, user_id, user, body.role,
                                     body.active, body.displayName)
        except auth_service.PasswordError as e:
            raise HTTPException(400, {"code": "INVALID_USER",
                                      "message": str(e)})
        ip, ua = client_info(request)
        svc.audit(conn, "UPDATE_USER", user["username"], "users", user_id,
                  before=dict(before) if before else None,
                  after=body.model_dump(exclude_none=True), ip=ip, user_agent=ua)
    return {"id": user_id}


class ResetPasswordBody(BaseModel):
    newPassword: str


@app.post("/api/v1/users/{user_id}/password")
def reset_user_password(user_id: str, body: ResetPasswordBody, request: Request,
                        user: dict = Depends(admin_only)):
    """Admin sets a password; the account must change it at next sign-in."""
    with db() as conn:
        try:
            auth_service.reset_password(conn, user_id, body.newPassword)
        except auth_service.PasswordError as e:
            raise HTTPException(400, {"code": "WEAK_PASSWORD",
                                      "message": str(e)})
        ip, ua = client_info(request)
        svc.audit(conn, "RESET_PASSWORD", user["username"], "users", user_id,
                  ip=ip, user_agent=ua)
    return {"id": user_id, "mustChangePassword": True}


# ---------------------------------------------------------------- imports ---

@app.post("/api/v1/imports/files")
async def import_files(request: Request, files: list[UploadFile] = File(...),
                       autoMatch: bool = True, user: dict = Depends(can_import)):
    with db() as conn:
        max_kb = settings_service.get_all(conn)["max_file_size_kb"]
        batch = svc.create_batch(conn, "WEB_UPLOAD", user["username"])
        results = []
        ok = fail = 0
        for f in files:
            content = await f.read()
            if len(content) > max_kb * 1024:
                results.append({
                    "filename": f.filename, "messageType": None, "version": None,
                    "status": "INVALID_FORMAT", "errorCode": "FILE_TOO_LARGE",
                    "errorMessage": f"ไฟล์ใหญ่เกิน {max_kb} KB",
                    "mawbNumbers": []})
                fail += 1
                continue
            raw = content.decode("utf-8", errors="replace")
            r = svc.import_message(conn, raw, f.filename, batch["id"],
                                   user=user["username"])
            results.append(r)
            if r["status"] in ("PARSED", "DUPLICATE"):
                ok += 1
            else:
                fail += 1
        conn.execute(
            """UPDATE import_batches SET total_files=?, success_files=?,
               failed_files=?, status='COMPLETED', updated_at=? WHERE id=?""",
            (len(files), ok, fail, svc.now(), batch["id"]))
    return {"batchId": batch["id"], "batchNo": batch["batch_no"],
            "totalFiles": len(files), "results": results}


class TextImport(BaseModel):
    rawMessage: str
    autoMatch: bool = True


@app.post("/api/v1/imports/text")
def import_text(body: TextImport, user: dict = Depends(can_import)):
    with db() as conn:
        batch = svc.create_batch(conn, "PASTE_TEXT", user["username"])
        r = svc.import_message(conn, body.rawMessage, None, batch["id"],
                               source_channel="PASTE_TEXT", user=user["username"])
        ok = 1 if r["status"] in ("PARSED", "DUPLICATE") else 0
        conn.execute(
            """UPDATE import_batches SET total_files=1, success_files=?,
               failed_files=?, status='COMPLETED', updated_at=? WHERE id=?""",
            (ok, 1 - ok, svc.now(), batch["id"]))
    return {"batchId": batch["id"], "batchNo": batch["batch_no"], "results": [r]}


@app.get("/api/v1/imports/{batch_id}")
def get_batch(batch_id: str, user: dict = Depends(any_user)):
    with db() as conn:
        batch = conn.execute(
            "SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
        if not batch:
            raise HTTPException(404, {"code": "NOT_FOUND",
                                      "message": "ไม่พบ import batch นี้"})
        messages = conn.execute(
            """SELECT id, message_type, message_version, original_filename,
                      file_size, parse_status, parse_error_code,
                      parse_error_message, duplicate_type, imported_at
               FROM cargo_messages WHERE batch_id = ? ORDER BY imported_at""",
            (batch_id,)).fetchall()
    return {"batch": dict(batch), "messages": [dict(m) for m in messages]}


# ---------------------------------------------------------------- matches ---

@app.get("/api/v1/matches")
def list_matches(page: int = 1, pageSize: int = 25, search: str = "",
                 status: str = "", origin: str = "", destination: str = "",
                 airlinePrefix: str = "", flight: str = "", version: str = "",
                 duplicate: str = "", dateFrom: str = "", dateTo: str = "",
                 reviewed: str = "", sortBy: str = "last_matched_at",
                 sortDirection: str = "desc", user: dict = Depends(any_user)):
    where, params = [], []
    if search:
        like = f"%{search.upper()}%"
        where.append(
            """(mr.mawb_number LIKE ? OR EXISTS (
                 SELECT 1 FROM fhl_house h WHERE h.mawb_number = mr.mawb_number
                 AND (h.hawb_number LIKE ? OR UPPER(h.shipper_name) LIKE ?
                      OR UPPER(h.consignee_name) LIKE ?))
                OR EXISTS (SELECT 1 FROM fwb_master w
                 WHERE w.id = mr.fwb_id AND (UPPER(w.flight_number) LIKE ?
                      OR UPPER(w.shipper_name) LIKE ? OR UPPER(w.consignee_name) LIKE ?
                      OR UPPER(w.reference_number) LIKE ?))
                OR EXISTS (SELECT 1 FROM cargo_messages c
                 JOIN fwb_master w2 ON w2.message_id = c.id
                 WHERE w2.mawb_number = mr.mawb_number
                   AND UPPER(COALESCE(c.original_filename,'')) LIKE ?)
                OR EXISTS (SELECT 1 FROM import_batches b
                 JOIN cargo_messages c2 ON c2.batch_id = b.id
                 JOIN fwb_master w3 ON w3.message_id = c2.id
                 WHERE w3.mawb_number = mr.mawb_number
                   AND UPPER(b.batch_no) LIKE ?))""")
        params += [like] * 10
    if status:
        wanted = [s for s in status.split(",") if s]
        where.append(f"{EFFECTIVE_STATUS} IN ({','.join('?' * len(wanted))})")
        params += wanted
    if origin:
        where.append("(SELECT origin FROM fwb_master WHERE id = mr.fwb_id) = ?")
        params.append(origin.upper())
    if destination:
        where.append(
            "(SELECT destination FROM fwb_master WHERE id = mr.fwb_id) = ?")
        params.append(destination.upper())
    if airlinePrefix:
        where.append(
            "(SELECT airline_prefix FROM fwb_master WHERE id = mr.fwb_id) = ?")
        params.append(airlinePrefix)
    if flight:
        where.append(
            """UPPER((SELECT flight_number FROM fwb_master
                      WHERE id = mr.fwb_id)) LIKE ?""")
        params.append(f"%{flight.upper()}%")
    if version:
        where.append(
            """EXISTS (SELECT 1 FROM cargo_messages c
                 JOIN fwb_master w ON w.message_id = c.id
                 WHERE w.id = mr.fwb_id AND c.message_version = ?)""")
        params.append(version)
    if duplicate in ("true", "false"):
        clause = """EXISTS (SELECT 1 FROM cargo_messages c
                      LEFT JOIN fwb_master w ON w.message_id = c.id
                      LEFT JOIN fhl_house h ON h.message_id = c.id
                      WHERE COALESCE(w.mawb_number, h.mawb_number) = mr.mawb_number
                        AND (c.parse_status = 'DUPLICATE'
                             OR c.duplicate_type IS NOT NULL))"""
        where.append(clause if duplicate == "true" else f"NOT {clause}")
    if dateFrom:
        where.append("substr(mr.last_matched_at,1,10) >= ?")
        params.append(dateFrom)
    if dateTo:
        where.append("substr(mr.last_matched_at,1,10) <= ?")
        params.append(dateTo)
    if reviewed in ("true", "false"):
        where.append("mr.reviewed = ?")
        params.append(1 if reviewed == "true" else 0)

    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    allowed_sort = {"mawb_number", "match_status", "match_score", "fhl_count",
                    "last_matched_at", "created_at", "weight_difference"}
    sort = sortBy if sortBy in allowed_sort else "last_matched_at"
    direction = "ASC" if sortDirection.lower() == "asc" else "DESC"
    pageSize = min(max(pageSize, 1), 200)

    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM matching_results mr {wsql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT mr.*, {EFFECTIVE_STATUS} AS effective_status,
                       w.origin, w.destination, w.flight_number, w.airline_prefix,
                  (SELECT GROUP_CONCAT(DISTINCT hawb_number) FROM fhl_house h
                   WHERE h.mawb_number = mr.mawb_number) hawb_numbers
                FROM matching_results mr
                LEFT JOIN fwb_master w ON w.id = mr.fwb_id
                {wsql} ORDER BY mr.{sort} {direction} LIMIT ? OFFSET ?""",
            params + [pageSize, (page - 1) * pageSize]).fetchall()
    return {"page": page, "pageSize": pageSize, "total": total,
            "items": [dict(r) for r in rows]}


@app.get("/api/v1/matches/{mawb}")
def match_detail(mawb: str, user: dict = Depends(any_user)):
    with db() as conn:
        mr = conn.execute(
            f"""SELECT mr.*, {EFFECTIVE_STATUS} AS effective_status
                FROM matching_results mr WHERE mawb_number = ?""",
            (mawb,)).fetchone()
        if not mr:
            raise HTTPException(404, {"code": "NOT_FOUND",
                                      "message": f"ไม่พบผลการจับคู่ของ {mawb}"})
        fwb = conn.execute(
            """SELECT w.*, c.message_version FROM fwb_master w
               JOIN cargo_messages c ON c.id = w.message_id WHERE w.id = ?""",
            (mr["fwb_id"],)).fetchone() if mr["fwb_id"] else None
        houses = conn.execute(
            """SELECT h.*, mh.linked_by FROM fhl_house h
               JOIN matching_result_houses mh ON mh.fhl_id = h.id
               WHERE mh.matching_result_id = ?
               ORDER BY h.hawb_number""", (mr["id"],)).fetchall()
        unlinked = conn.execute(
            """SELECT h.*, o.reason, o.performed_by, o.performed_at
               FROM house_link_overrides o JOIN fhl_house h ON h.id = o.fhl_id
               WHERE o.mawb_number = ? AND o.action = 'UNLINK'""",
            (mawb,)).fetchall()
        validations = conn.execute(
            "SELECT * FROM validation_results WHERE matching_result_id = ?",
            (mr["id"],)).fetchall()
        history = conn.execute(
            """SELECT * FROM match_history WHERE mawb_number = ?
               ORDER BY performed_at DESC LIMIT 50""", (mawb,)).fetchall()
        fsu = conn.execute(
            """SELECT * FROM fsu_status WHERE mawb_number = ?
               ORDER BY created_at, status_date""", (mawb,)).fetchall()
        raw_msgs = conn.execute(
            """SELECT id, message_type, message_version, original_filename,
                      parse_status, duplicate_type, imported_at, raw_message
               FROM cargo_messages WHERE id IN (
                 SELECT message_id FROM fwb_master WHERE mawb_number = ?
                 UNION SELECT message_id FROM fhl_house WHERE mawb_number = ?
                 UNION SELECT message_id FROM fsu_status WHERE mawb_number = ?
                 UNION SELECT message_id FROM ffm_flight WHERE mawb_number = ?)
               ORDER BY imported_at""", (mawb, mawb, mawb, mawb)).fetchall()
    return {
        "result": dict(mr),
        "fwb": dict(fwb) if fwb else None,
        "houses": [dict(h) for h in houses],
        "unlinkedHouses": [dict(h) for h in unlinked],
        "validations": [dict(v) for v in validations],
        "history": [dict(h) for h in history],
        "fsuEvents": [dict(e) for e in fsu],
        "rawMessages": [dict(m) for m in raw_msgs],
    }


@app.post("/api/v1/matches/{mawb}/rematch")
def rematch_endpoint(mawb: str, request: Request, user: dict = Depends(admin_only)):
    with db() as conn:
        result = svc.rematch(conn, mawb, user=user["username"],
                             event="MANUAL_REMATCH")
        ip, ua = client_info(request)
        svc.audit(conn, "REMATCH_MESSAGE", user["username"], "matching_results",
                  result["id"], ip=ip, user_agent=ua)
    return result


class ReviewBody(BaseModel):
    reviewed: bool = True
    note: str = ""


@app.post("/api/v1/matches/{mawb}/review")
def review(mawb: str, body: ReviewBody, request: Request,
           user: dict = Depends(can_review)):
    with db() as conn:
        prev = conn.execute(
            "SELECT reviewed, review_note FROM matching_results WHERE mawb_number=?",
            (mawb,)).fetchone()
        if not prev:
            raise HTTPException(404, {"code": "NOT_FOUND",
                                      "message": f"ไม่พบผลการจับคู่ของ {mawb}"})
        conn.execute(
            """UPDATE matching_results SET reviewed=?, reviewed_by=?,
               reviewed_at=?, review_note=?, updated_at=? WHERE mawb_number=?""",
            (1 if body.reviewed else 0, user["username"], svc.now(), body.note,
             svc.now(), mawb))
        ip, ua = client_info(request)
        svc.audit(conn, "MARK_REVIEWED", user["username"], "matching_results",
                  mawb, before=dict(prev),
                  after={"reviewed": body.reviewed, "note": body.note},
                  ip=ip, user_agent=ua)
    return {"mawbNumber": mawb, "reviewed": body.reviewed}


class OverrideBody(BaseModel):
    # Optional[...] rather than "str | None": Pydantic resolves model
    # annotations at runtime, and the newer syntax needs Python 3.10.
    status: Optional[str] = None   # RESOLVED, REJECTED or null to clear
    reason: str = ""


ALLOWED_OVERRIDES = {"RESOLVED", "REJECTED", "NEEDS_REVIEW"}


@app.post("/api/v1/matches/{mawb}/status")
def override_status(mawb: str, body: OverrideBody, request: Request,
                    user: dict = Depends(admin_only)):
    """FR-011: administrator resolves or rejects a match by hand."""
    if body.status is not None and body.status not in ALLOWED_OVERRIDES:
        raise HTTPException(400, {
            "code": "INVALID_STATUS",
            "message": f"สถานะต้องเป็นหนึ่งใน {', '.join(sorted(ALLOWED_OVERRIDES))}"})
    with db() as conn:
        prev = conn.execute(
            """SELECT match_status, override_status FROM matching_results
               WHERE mawb_number = ?""", (mawb,)).fetchone()
        if not prev:
            raise HTTPException(404, {"code": "NOT_FOUND",
                                      "message": f"ไม่พบผลการจับคู่ของ {mawb}"})
        conn.execute(
            """UPDATE matching_results SET override_status=?, override_reason=?,
               override_by=?, override_at=?, updated_at=? WHERE mawb_number=?""",
            (body.status, body.reason or None, user["username"], svc.now(),
             svc.now(), mawb))
        conn.execute(
            """INSERT INTO match_history
               (id, mawb_number, event_type, previous_status, new_status,
                details, performed_by, performed_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (svc.new_id(), mawb, "RESOLVE_ERROR",
             prev["override_status"] or prev["match_status"],
             body.status or prev["match_status"],
             json.dumps({"reason": body.reason}), user["username"], svc.now()))
        ip, ua = client_info(request)
        svc.audit(conn, "RESOLVE_ERROR", user["username"], "matching_results",
                  mawb, before=dict(prev),
                  after={"override_status": body.status}, reason=body.reason,
                  ip=ip, user_agent=ua)
    return {"mawbNumber": mawb, "overrideStatus": body.status}


class LinkBody(BaseModel):
    reason: str = ""


@app.post("/api/v1/matches/{mawb}/houses/{fhl_id}/link")
def link_house(mawb: str, fhl_id: str, body: LinkBody,
               user: dict = Depends(admin_only)):
    try:
        with db() as conn:
            return svc.set_house_link(conn, mawb, fhl_id, "LINK", body.reason,
                                      user["username"])
    except LookupError as e:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": str(e)})


@app.post("/api/v1/matches/{mawb}/houses/{fhl_id}/unlink")
def unlink_house(mawb: str, fhl_id: str, body: LinkBody,
                 user: dict = Depends(admin_only)):
    try:
        with db() as conn:
            return svc.set_house_link(conn, mawb, fhl_id, "UNLINK", body.reason,
                                      user["username"])
    except LookupError as e:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": str(e)})


@app.delete("/api/v1/matches/{mawb}/houses/{fhl_id}/link")
def clear_house_link(mawb: str, fhl_id: str, user: dict = Depends(admin_only)):
    with db() as conn:
        return svc.clear_house_link(conn, mawb, fhl_id, user["username"])


@app.get("/api/v1/houses/unassigned")
def unassigned_houses(search: str = "", limit: int = 50,
                      user: dict = Depends(any_user)):
    """Houses available to link manually — used by the manual-match picker."""
    like = f"%{search.upper()}%"
    with db() as conn:
        rows = conn.execute(
            """SELECT h.id, h.mawb_number, h.hawb_number, h.pieces,
                      h.gross_weight, h.weight_unit, h.commodity
               FROM fhl_house h
               WHERE (? = '' OR UPPER(h.hawb_number) LIKE ?
                      OR h.mawb_number LIKE ?)
               ORDER BY h.created_at DESC LIMIT ?""",
            (search, like, like, min(limit, 200))).fetchall()
    return {"items": [dict(r) for r in rows]}


# -------------------------------------------------------- delivery orders ---

class DOBody(BaseModel):
    """Fields the Cargo-IMP messages cannot supply are accepted here."""
    landedAt: str = ""              # ISO, overrides the FSU arrival event
    aircraftRegistration: str = ""
    customerCode: str = ""
    issuedBy: str = ""
    station: str = ""
    doDate: str = ""
    amend: bool = False            # rewrite an issued DO, keeping its number


@app.post("/api/v1/matches/{mawb}/houses/{fhl_id}/do")
def create_delivery_order(mawb: str, fhl_id: str, body: DOBody, request: Request,
                          user: dict = Depends(can_import)):
    """Issue (or reprint) the Delivery Order for one house waybill."""
    payload = body.model_dump()
    amend = bool(payload.pop("amend", False))
    overrides = {k: v for k, v in payload.items() if v}
    if amend and user["role"] != ADMIN:
        raise HTTPException(403, {
            "code": "FORBIDDEN",
            "message": "การแก้ไข DO ที่ออกไปแล้วทำได้เฉพาะ Administrator"})
    with db() as conn:
        settings = settings_service.get_all(conn)
        try:
            do = do_service.issue(
                conn, mawb, fhl_id, user["username"], overrides,
                number_start=settings["do_number_start"],
                default_issued_by=settings["do_issued_by"],
                shc_source=settings["do_shc_source"], amend=amend)
        except do_service.DOError as e:
            raise HTTPException(404, {"code": "DO_SOURCE_NOT_FOUND",
                                      "message": str(e)})
        ip, ua = client_info(request)
        svc.audit(conn,
                  "AMEND_DELIVERY_ORDER" if do.get("amended")
                  else "ISSUE_DELIVERY_ORDER",
                  user["username"], "delivery_orders", do["doNumber"],
                  after={"mawb": mawb, "hawb": do["hawbNumber"],
                         "reprint": do.get("reprint", False),
                         "amended": do.get("amended", False)},
                  ip=ip, user_agent=ua)
    return do


@app.get("/api/v1/do")
def list_delivery_orders(page: int = 1, pageSize: int = 50, search: str = "",
                         user: dict = Depends(any_user)):
    where, params = [], []
    if search:
        where.append("(mawb_number LIKE ? OR hawb_number LIKE ? OR do_number LIKE ?)")
        params += [f"%{search}%"] * 3
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    pageSize = min(max(pageSize, 1), 200)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM delivery_orders {wsql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, do_number, mawb_number, hawb_number, station, do_date,
                       consignee_name, flight_number, landed_at, expiry_at,
                       issued_by, pieces, weight, created_by, created_at,
                       reprint_count
                FROM delivery_orders {wsql}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            params + [pageSize, (page - 1) * pageSize]).fetchall()
    return {"page": page, "pageSize": pageSize, "total": total,
            "items": [dict(r) for r in rows]}


@app.get("/api/v1/do/{do_id}/preview")
def preview_delivery_order(do_id: str, user: dict = Depends(any_user)):
    with db() as conn:
        try:
            do = do_service.load(conn, do_id)
        except do_service.DOError as e:
            raise HTTPException(404, {"code": "NOT_FOUND", "message": str(e)})
    return Response(do_service.render_html(do), media_type="text/html")


@app.get("/api/v1/do/{do_id}/pdf")
def download_delivery_order(do_id: str, request: Request,
                            user: dict = Depends(any_user)):
    with db() as conn:
        try:
            do = do_service.load(conn, do_id)
        except do_service.DOError as e:
            raise HTTPException(404, {"code": "NOT_FOUND", "message": str(e)})
        ip, ua = client_info(request)
        svc.audit(conn, "EXPORT_DATA", user["username"], "delivery_orders",
                  do["doNumber"], after={"format": "PDF"}, ip=ip, user_agent=ua)
    filename = f"DO_{do['doNumber']}_{do.get('hawbNumber') or ''}.pdf"
    return Response(do_service.render_pdf(do), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="{filename}"'})


# -------------------------------------------------------------- dashboard ---

@app.get("/api/v1/dashboard/summary")
def dashboard_summary(user: dict = Depends(any_user)):
    with db() as conn:
        today = svc.now()[:10]
        imported_today = conn.execute(
            "SELECT COUNT(*) FROM cargo_messages WHERE substr(imported_at,1,10)=?",
            (today,)).fetchone()[0]
        status_counts = {r["s"]: r["c"] for r in conn.execute(
            f"""SELECT {EFFECTIVE_STATUS} s, COUNT(*) c
                FROM matching_results mr GROUP BY 1""")}
        type_counts = {r["message_type"] or "INVALID": r["c"] for r in conn.execute(
            "SELECT message_type, COUNT(*) c FROM cargo_messages GROUP BY 1")}
        parse_errors = conn.execute(
            """SELECT COUNT(*) FROM cargo_messages
               WHERE parse_status IN ('PARSE_ERROR','INVALID_FORMAT')""").fetchone()[0]
        duplicates = conn.execute(
            """SELECT COUNT(*) FROM cargo_messages
               WHERE parse_status='DUPLICATE' OR duplicate_type IS NOT NULL"""
        ).fetchone()[0]
        by_day = [dict(r) for r in conn.execute(
            """SELECT substr(imported_at,1,10) day, COUNT(*) c
               FROM cargo_messages GROUP BY 1 ORDER BY 1 DESC LIMIT 14""")]
        recent = [dict(r) for r in conn.execute(
            f"""SELECT mawb_number, {EFFECTIVE_STATUS} AS match_status,
                       match_score, fhl_count, last_matched_at
                FROM matching_results mr
                ORDER BY last_matched_at DESC LIMIT 8""")]
        top_routes = [dict(r) for r in conn.execute(
            """SELECT origin || '→' || destination route, COUNT(*) c,
                      SUM(gross_weight) weight
               FROM fwb_master WHERE origin IS NOT NULL
               GROUP BY 1 ORDER BY c DESC LIMIT 5""")]
    waiting = (status_counts.get("WAITING_FOR_FWB", 0)
               + status_counts.get("WAITING_FOR_FHL", 0))
    matched = (status_counts.get("MATCHED", 0)
               + status_counts.get("MATCHED_WITH_TOLERANCE", 0))
    return {
        "importedToday": imported_today,
        "matched": matched,
        "waiting": waiting,
        "partial": status_counts.get("PARTIAL_MATCH", 0)
                   + status_counts.get("NEEDS_REVIEW", 0),
        "errors": parse_errors + status_counts.get("REJECTED", 0),
        "duplicates": duplicates,
        "statusCounts": status_counts,
        "typeCounts": type_counts,
        "importsByDay": list(reversed(by_day)),
        "recent": recent,
        "topRoutes": top_routes,
    }


# ----------------------------------------------- errors, history, audit -----

@app.get("/api/v1/errors")
def list_errors(page: int = 1, pageSize: int = 50, kind: str = "",
                user: dict = Depends(any_user)):
    """Parse failures, rejected matches and failed validation rules."""
    with db() as conn:
        messages = [dict(r) for r in conn.execute(
            """SELECT id, original_filename, message_type, message_version,
                      parse_status, parse_error_code, parse_error_message,
                      duplicate_type, imported_by, imported_at
               FROM cargo_messages
               WHERE parse_status IN ('PARSE_ERROR','INVALID_FORMAT')
               ORDER BY imported_at DESC LIMIT 500""")]
        failed_rules = [dict(r) for r in conn.execute(
            """SELECT m.mawb_number, v.rule_code, v.severity, v.fwb_value,
                      v.fhl_value, v.difference_value, v.created_at
               FROM validation_results v
               JOIN matching_results m ON m.id = v.matching_result_id
               WHERE v.result = 'FAIL'
               ORDER BY v.severity, m.mawb_number LIMIT 500""")]
        duplicates = [dict(r) for r in conn.execute(
            """SELECT id, original_filename, message_type, duplicate_type,
                      parse_error_message, imported_at
               FROM cargo_messages
               WHERE parse_status = 'DUPLICATE' OR duplicate_type IS NOT NULL
               ORDER BY imported_at DESC LIMIT 500""")]
    return {"parseErrors": messages, "validationFailures": failed_rules,
            "duplicates": duplicates}


@app.get("/api/v1/history")
def list_history(page: int = 1, pageSize: int = 50, mawb: str = "",
                 user: dict = Depends(any_user)):
    where, params = [], []
    if mawb:
        where.append("mawb_number LIKE ?")
        params.append(f"%{mawb}%")
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    pageSize = min(max(pageSize, 1), 200)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM match_history {wsql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT * FROM match_history {wsql}
                ORDER BY performed_at DESC LIMIT ? OFFSET ?""",
            params + [pageSize, (page - 1) * pageSize]).fetchall()
    return {"page": page, "pageSize": pageSize, "total": total,
            "items": [dict(r) for r in rows]}


@app.get("/api/v1/audit")
def list_audit(page: int = 1, pageSize: int = 50, eventType: str = "",
               user: dict = Depends(admin_only)):
    where, params = [], []
    if eventType:
        where.append("event_type = ?")
        params.append(eventType)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    pageSize = min(max(pageSize, 1), 200)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM audit_logs {wsql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT * FROM audit_logs {wsql}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            params + [pageSize, (page - 1) * pageSize]).fetchall()
        types = [r["event_type"] for r in conn.execute(
            "SELECT DISTINCT event_type FROM audit_logs ORDER BY 1")]
    return {"page": page, "pageSize": pageSize, "total": total,
            "eventTypes": types, "items": [dict(r) for r in rows]}


# --------------------------------------------------------------- settings ---

@app.get("/api/v1/settings")
def get_settings(user: dict = Depends(any_user)):
    with db() as conn:
        return {"settings": settings_service.describe(conn)}


class SettingsBody(BaseModel):
    changes: dict
    rematch: bool = True


@app.put("/api/v1/settings")
def put_settings(body: SettingsBody, request: Request,
                 user: dict = Depends(admin_only)):
    with db() as conn:
        try:
            applied = settings_service.update(conn, body.changes, user["username"])
        except settings_service.SettingError as e:
            raise HTTPException(400, {"code": "INVALID_SETTING",
                                      "message": str(e)})
        ip, ua = client_info(request)
        svc.audit(conn, "UPDATE_RULE", user["username"], "app_settings", None,
                  before={k: v[0] for k, v in applied.items()},
                  after={k: v[1] for k, v in applied.items()}, ip=ip, user_agent=ua)
        rematched = (svc.rematch_all(conn, user["username"], "RULE_CHANGE_REMATCH")
                     if body.rematch and applied else 0)
        settings = settings_service.describe(conn)
    return {"applied": {k: {"before": v[0], "after": v[1]}
                        for k, v in applied.items()},
            "rematched": rematched, "settings": settings}


# ---------------------------------------------------- raw data explorer -----

EXPLORER_TABLES: dict[str, list[str]] = {
    "cargo_messages": ["id", "batch_id", "message_type", "message_version",
                       "original_filename", "file_size", "source_channel",
                       "message_hash", "parse_status", "parse_error_code",
                       "parse_error_message", "duplicate_type", "imported_by",
                       "imported_at"],
    "fwb_master": ["id", "mawb_number", "airline_prefix", "origin", "destination",
                   "pieces", "gross_weight", "weight_unit", "chargeable_weight",
                   "flight_number", "flight_date", "routing", "shipper_name",
                   "shipper_country", "consignee_name", "consignee_country",
                   "agent_code", "agent_name", "currency", "rate",
                   "freight_charge", "total_charge", "nature_of_goods",
                   "issue_date", "issue_place", "reference_number", "created_at"],
    "fhl_house": ["id", "mawb_number", "hawb_number", "origin", "destination",
                  "pieces", "gross_weight", "weight_unit", "commodity", "hs_code",
                  "consignee_tax_id", "shipper_name", "shipper_country",
                  "consignee_name", "consignee_country", "consignee_postal_code",
                  "consignee_phone", "created_at"],
    "ffm_flight": ["id", "flight_number", "flight_date", "origin", "destination",
                   "mawb_number", "pieces", "gross_weight", "weight_unit",
                   "nature_of_goods", "created_at"],
    "fsu_status": ["id", "mawb_number", "status_code", "airport", "flight_number",
                   "status_date", "status_time", "weight", "weight_unit",
                   "hawb_number", "raw_line", "created_at"],
    "delivery_orders": ["id", "do_number", "mawb_number", "hawb_number", "station",
                        "do_date", "customer_code", "consignee_name",
                        "flight_number", "aircraft_registration", "landed_at",
                        "expiry_at", "issued_by", "pieces", "weight",
                        "created_by", "created_at", "reprint_count"],
    "matching_results": ["id", "mawb_number", "match_status", "override_status",
                         "match_score", "fhl_count", "fwb_pieces",
                         "fhl_total_pieces", "pieces_difference", "fwb_weight",
                         "fhl_total_weight", "weight_difference",
                         "weight_difference_percentage", "origin_match",
                         "destination_match", "pieces_match", "weight_match",
                         "duplicate_hawb", "reviewed", "reviewed_by",
                         "review_note", "last_matched_at"],
    "validation_results": ["id", "matching_result_id", "rule_code", "severity",
                           "result", "fwb_value", "fhl_value",
                           "difference_value", "created_at"],
    "match_history": ["id", "mawb_number", "event_type", "previous_status",
                      "new_status", "previous_score", "new_score",
                      "performed_by", "performed_at"],
    "house_link_overrides": ["id", "mawb_number", "fhl_id", "action", "reason",
                             "performed_by", "performed_at"],
    "import_batches": ["id", "batch_no", "imported_by", "imported_at",
                       "source_channel", "total_files", "success_files",
                       "failed_files", "status"],
    "audit_logs": ["id", "event_type", "user_id", "entity_type", "entity_id",
                   "reason", "ip_address", "created_at"],
    "login_attempts": ["id", "username", "ip_address", "success", "created_at"],
}

FILTER_OPS = {
    "eq": "= ?", "ne": "!= ?", "gt": "> ?", "gte": ">= ?", "lt": "< ?",
    "lte": "<= ?", "contains": "LIKE ?", "startswith": "LIKE ?",
    "isnull": "IS NULL", "notnull": "IS NOT NULL",
}

NUMERIC_AGGS = {"count", "sum", "avg", "min", "max"}


@app.get("/api/v1/data/tables")
def data_tables(user: dict = Depends(any_user)):
    with db() as conn:
        out = []
        for t, cols in EXPLORER_TABLES.items():
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            out.append({"table": t, "columns": cols, "rowCount": count})
    return {"tables": out}


def _build_filters(table: str, filters: list[str], match: str = "and"):
    """Turn "column:op:value" strings into a safe WHERE clause.

    Column names are validated against the table's allow-list and operators
    against FILTER_OPS, so nothing user-supplied is ever interpolated into
    SQL — values always travel as bound parameters.
    """
    cols = EXPLORER_TABLES[table]
    where, params = [], []
    for f in filters:
        parts = f.split(":", 2)
        if len(parts) < 2:
            continue
        col, op = parts[0], parts[1]
        value = parts[2] if len(parts) > 2 else ""
        if col not in cols or op not in FILTER_OPS:
            continue
        clause = FILTER_OPS[op]
        if op in ("isnull", "notnull"):
            where.append(f"{col} {clause}")
        else:
            if op in ("contains", "startswith"):
                where.append(f"CAST({col} AS TEXT) {clause}")
                params.append(f"%{value}%" if op == "contains" else f"{value}%")
            else:
                where.append(f"{col} {clause}")
                params.append(value)
    joiner = " OR " if match.lower() == "or" else " AND "
    wsql = ("WHERE " + joiner.join(where)) if where else ""
    return wsql, params


@app.get("/api/v1/data/{table}")
def data_rows(table: str, page: int = 1, pageSize: int = 50,
              filter: list[str] = Query(default=[]), match: str = "and",
              sortBy: str = "", sortDirection: str = "desc",
              user: dict = Depends(any_user)):
    if table not in EXPLORER_TABLES:
        raise HTTPException(404, {"code": "UNKNOWN_TABLE",
                                  "message": f"ไม่มีตาราง {table}"})
    cols = EXPLORER_TABLES[table]
    wsql, params = _build_filters(table, filter, match)
    sort = sortBy if sortBy in cols else cols[-1]
    direction = "ASC" if sortDirection.lower() == "asc" else "DESC"
    pageSize = min(pageSize, 500)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table} {wsql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT {', '.join(cols)} FROM {table} {wsql}
                ORDER BY {sort} {direction} LIMIT ? OFFSET ?""",
            params + [pageSize, (page - 1) * pageSize]).fetchall()
    return {"table": table, "columns": cols, "page": page, "pageSize": pageSize,
            "total": total, "rows": [dict(r) for r in rows]}


@app.get("/api/v1/data/{table}/distinct")
def data_distinct(table: str, column: str, limit: int = 200,
                  user: dict = Depends(any_user)):
    """Distinct values of one column — feeds the filter value dropdown."""
    if table not in EXPLORER_TABLES or column not in EXPLORER_TABLES[table]:
        raise HTTPException(404, {"code": "UNKNOWN_COLUMN",
                                  "message": "ไม่รู้จักคอลัมน์นี้"})
    with db() as conn:
        rows = conn.execute(
            f"""SELECT {column} v, COUNT(*) c FROM {table}
                WHERE {column} IS NOT NULL GROUP BY 1 ORDER BY c DESC LIMIT ?""",
            (min(limit, 500),)).fetchall()
    return {"column": column, "values": [dict(r) for r in rows]}


@app.get("/api/v1/data/{table}/aggregate")
def data_aggregate(table: str, groupBy: str, metric: str = "count",
                   metricColumn: str = "", filter: list[str] = Query(default=[]),
                   match: str = "and", limit: int = 50,
                   user: dict = Depends(any_user)):
    """Group-by summary over the same filters as the grid — for analysis."""
    if table not in EXPLORER_TABLES:
        raise HTTPException(404, {"code": "UNKNOWN_TABLE",
                                  "message": f"ไม่มีตาราง {table}"})
    cols = EXPLORER_TABLES[table]
    if groupBy not in cols:
        raise HTTPException(400, {"code": "UNKNOWN_COLUMN",
                                  "message": "ไม่รู้จักคอลัมน์ที่จะ group"})
    metric = metric.lower()
    if metric not in NUMERIC_AGGS:
        raise HTTPException(400, {"code": "UNKNOWN_METRIC",
                                  "message": "metric ไม่รองรับ"})
    if metric == "count":
        expr = "COUNT(*)"
    else:
        if metricColumn not in cols:
            raise HTTPException(400, {"code": "UNKNOWN_METRIC_COLUMN",
                                      "message": "ไม่รู้จักคอลัมน์ของ metric"})
        expr = f"{metric.upper()}({metricColumn})"

    wsql, params = _build_filters(table, filter, match)
    with db() as conn:
        rows = conn.execute(
            f"""SELECT {groupBy} AS bucket, {expr} AS value, COUNT(*) AS rows
                FROM {table} {wsql} GROUP BY 1 ORDER BY value DESC LIMIT ?""",
            params + [min(limit, 200)]).fetchall()
    return {"table": table, "groupBy": groupBy, "metric": metric,
            "metricColumn": metricColumn or None, "buckets": [dict(r) for r in rows]}


@app.get("/api/v1/data/{table}/export")
def data_export(table: str, request: Request, filter: list[str] = Query(default=[]),
                match: str = "and", user: dict = Depends(any_user)):
    if table not in EXPLORER_TABLES:
        raise HTTPException(404, {"code": "UNKNOWN_TABLE",
                                  "message": f"ไม่มีตาราง {table}"})
    cols = EXPLORER_TABLES[table]
    wsql, params = _build_filters(table, filter, match)
    with db() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM {table} {wsql}", params).fetchall()
        ip, ua = client_info(request)
        svc.audit(conn, "EXPORT_DATA", user["username"], "table", table,
                  after={"rows": len(rows), "filters": filter}, ip=ip, user_agent=ua)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for r in rows:
        writer.writerow([r[c] for c in cols])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="{table}_export.csv"'})


# ---------------------------------------------------------------- exports ---

EXPORT_FORMATS = {
    "XLSX": ("xlsx",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "CSV": ("csv", "text/csv"),
    "JSON": ("json", "application/json"),
    "RAW": ("zip", "application/zip"),
}


class ExportFilters(BaseModel):
    status: list[str] = []
    dateFrom: str = ""
    dateTo: str = ""
    search: str = ""


class ExportBody(BaseModel):
    format: str = "XLSX"
    filters: ExportFilters = ExportFilters()


def _run_export(fmt: str, status: str, date_from: str, date_to: str,
                search: str, username: str, request: Request) -> Response:
    fmt = fmt.upper()
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(400, {
            "code": "UNSUPPORTED_FORMAT",
            "message": f"รองรับเฉพาะ {', '.join(EXPORT_FORMATS)}"})
    ext, media = EXPORT_FORMATS[fmt]
    where, params = export_service.build_match_where(status, date_from, date_to,
                                                     search)
    with db() as conn:
        if fmt == "RAW":
            payload = export_service.to_raw_package(conn, where, params)
            count = None
        else:
            data = export_service.collect(conn, where, params)
            count = len(data["Summary"])
            payload = {"XLSX": export_service.to_xlsx,
                       "CSV": export_service.to_csv,
                       "JSON": export_service.to_json}[fmt](data)
        ip, ua = client_info(request)
        svc.audit(conn, "EXPORT_DATA", username, "report", fmt,
                  after={"format": fmt, "rows": count,
                         "filters": {"status": status, "dateFrom": date_from,
                                     "dateTo": date_to, "search": search}},
                  ip=ip, user_agent=ua)
    filename = f"paperless_aot_matches.{ext}"
    return Response(content=payload, media_type=media,
                    headers={"Content-Disposition":
                             f'attachment; filename="{filename}"'})


@app.post("/api/v1/exports")
def create_export(body: ExportBody, request: Request,
                  user: dict = Depends(any_user)):
    f = body.filters
    return _run_export(body.format, ",".join(f.status), f.dateFrom, f.dateTo,
                       f.search, user["username"], request)


@app.get("/api/v1/exports")
def download_export(request: Request, format: str = "XLSX", status: str = "",
                    dateFrom: str = "", dateTo: str = "", search: str = "",
                    user: dict = Depends(any_user)):
    """Same as POST, as a link the browser can follow directly."""
    return _run_export(format, status, dateFrom, dateTo, search,
                       user["username"], request)


# --------------------------------------------------------------- messages ---

@app.get("/api/v1/messages/{message_id}/raw")
def message_raw(message_id: str, user: dict = Depends(any_user)):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cargo_messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "ไม่พบข้อความ"})
    return dict(row)


@app.get("/api/v1/messages/{message_id}/parsed")
def message_parsed(message_id: str, user: dict = Depends(any_user)):
    with db() as conn:
        for table in ("fwb_master", "fhl_house"):
            row = conn.execute(
                f"SELECT parsed_data FROM {table} WHERE message_id = ?",
                (message_id,)).fetchone()
            if row:
                return json.loads(row["parsed_data"])
        rows = conn.execute(
            "SELECT parsed_data FROM fsu_status WHERE message_id = ?",
            (message_id,)).fetchall()
        if rows:
            return {"events": [json.loads(r["parsed_data"]) for r in rows]}
        rows = conn.execute(
            "SELECT parsed_data FROM ffm_flight WHERE message_id = ?",
            (message_id,)).fetchall()
        if rows:
            return json.loads(rows[0]["parsed_data"])
    raise HTTPException(404, {"code": "NOT_FOUND",
                              "message": "ไม่พบข้อมูลที่ parse แล้ว"})


# ------------------------------------------------------ health and metrics ---

@app.get("/health/live")
def health_live():
    return {"status": "UP"}


@app.get("/health/ready")
def health_ready():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"status": "READY"}


@app.get("/metrics")
def metrics():
    """Prometheus text exposition (NFR-005)."""
    with db() as conn:
        messages = {r["t"] or "unknown": r["c"] for r in conn.execute(
            "SELECT message_type t, COUNT(*) c FROM cargo_messages GROUP BY 1")}
        parse = {r["s"]: r["c"] for r in conn.execute(
            "SELECT parse_status s, COUNT(*) c FROM cargo_messages GROUP BY 1")}
        statuses = {r["s"]: r["c"] for r in conn.execute(
            f"""SELECT {EFFECTIVE_STATUS} s, COUNT(*) c
                FROM matching_results mr GROUP BY 1""")}
        batches = conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        houses = conn.execute("SELECT COUNT(*) FROM fhl_house").fetchone()[0]

    lines = [
        "# HELP paperless_aot_messages_total Cargo-IMP messages stored by type",
        "# TYPE paperless_aot_messages_total gauge",
    ]
    lines += [f'paperless_aot_messages_total{{type="{k}"}} {v}'
              for k, v in sorted(messages.items())]
    lines += [
        "# HELP paperless_aot_parse_status_total Messages by parse status",
        "# TYPE paperless_aot_parse_status_total gauge",
    ]
    lines += [f'paperless_aot_parse_status_total{{status="{k}"}} {v}'
              for k, v in sorted(parse.items())]
    lines += [
        "# HELP paperless_aot_match_status_total Matching results by status",
        "# TYPE paperless_aot_match_status_total gauge",
    ]
    lines += [f'paperless_aot_match_status_total{{status="{k}"}} {v}'
              for k, v in sorted(statuses.items())]
    lines += [
        "# HELP paperless_aot_import_batches_total Import batches created",
        "# TYPE paperless_aot_import_batches_total counter",
        f"paperless_aot_import_batches_total {batches}",
        "# HELP paperless_aot_houses_total House waybills stored",
        "# TYPE paperless_aot_houses_total gauge",
        f"paperless_aot_houses_total {houses}",
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
