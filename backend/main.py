"""Paperless AOT — FWB/FHL Matching Portal API + frontend host."""
from __future__ import annotations

import csv
import io
import json
import os
import sys

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

from app.database import db, init_db  # noqa: E402
from app.services import import_service as svc  # noqa: E402

app = FastAPI(title="Paperless AOT — FWB/FHL Matching Portal", version="1.0.0")
init_db()

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


# ---------------------------------------------------------------- imports ---

@app.post("/api/v1/imports/files")
async def import_files(request: Request, files: list[UploadFile] = File(...),
                       autoMatch: bool = True):
    with db() as conn:
        batch = svc.create_batch(conn, "WEB_UPLOAD")
        results = []
        ok = fail = 0
        for f in files:
            raw = (await f.read()).decode("utf-8", errors="replace")
            r = svc.import_message(conn, raw, f.filename, batch["id"])
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
def import_text(body: TextImport):
    with db() as conn:
        batch = svc.create_batch(conn, "PASTE_TEXT")
        r = svc.import_message(conn, body.rawMessage, None, batch["id"],
                               source_channel="PASTE_TEXT")
        ok = 1 if r["status"] in ("PARSED", "DUPLICATE") else 0
        conn.execute(
            """UPDATE import_batches SET total_files=1, success_files=?,
               failed_files=?, status='COMPLETED', updated_at=? WHERE id=?""",
            (ok, 1 - ok, svc.now(), batch["id"]))
    return {"batchId": batch["id"], "batchNo": batch["batch_no"], "results": [r]}


# ---------------------------------------------------------------- matches ---

@app.get("/api/v1/matches")
def list_matches(page: int = 1, pageSize: int = 25, search: str = "",
                 status: str = "", origin: str = "", destination: str = "",
                 reviewed: str = "", sortBy: str = "last_matched_at",
                 sortDirection: str = "desc"):
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
                      OR UPPER(w.shipper_name) LIKE ? OR UPPER(w.consignee_name) LIKE ?)))""")
        params += [like] * 7
    if status:
        placeholders = ",".join("?" * len(status.split(",")))
        where.append(f"mr.match_status IN ({placeholders})")
        params += status.split(",")
    if origin:
        where.append("(SELECT origin FROM fwb_master WHERE id = mr.fwb_id) = ?")
        params.append(origin.upper())
    if destination:
        where.append(
            "(SELECT destination FROM fwb_master WHERE id = mr.fwb_id) = ?")
        params.append(destination.upper())
    if reviewed in ("true", "false"):
        where.append("mr.reviewed = ?")
        params.append(1 if reviewed == "true" else 0)

    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    allowed_sort = {"mawb_number", "match_status", "match_score", "fhl_count",
                    "last_matched_at", "created_at"}
    sort = sortBy if sortBy in allowed_sort else "last_matched_at"
    direction = "ASC" if sortDirection.lower() == "asc" else "DESC"

    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM matching_results mr {wsql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT mr.*, w.origin, w.destination, w.flight_number,
                       w.airline_prefix,
                  (SELECT GROUP_CONCAT(DISTINCT hawb_number) FROM fhl_house h
                   WHERE h.mawb_number = mr.mawb_number) hawb_numbers
                FROM matching_results mr
                LEFT JOIN fwb_master w ON w.id = mr.fwb_id
                {wsql} ORDER BY mr.{sort} {direction} LIMIT ? OFFSET ?""",
            params + [pageSize, (page - 1) * pageSize]).fetchall()
    return {"page": page, "pageSize": pageSize, "total": total,
            "items": [dict(r) for r in rows]}


@app.get("/api/v1/matches/{mawb}")
def match_detail(mawb: str):
    with db() as conn:
        mr = conn.execute(
            "SELECT * FROM matching_results WHERE mawb_number = ?",
            (mawb,)).fetchone()
        if not mr:
            return JSONResponse(status_code=404, content={
                "code": "NOT_FOUND", "message": f"No match result for {mawb}"})
        fwb = conn.execute(
            "SELECT * FROM fwb_master WHERE id = ?", (mr["fwb_id"],)).fetchone() \
            if mr["fwb_id"] else None
        houses = conn.execute(
            """SELECT h.* FROM fhl_house h
               JOIN matching_result_houses mh ON mh.fhl_id = h.id
               WHERE mh.matching_result_id = ?""", (mr["id"],)).fetchall()
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
                      parse_status, imported_at, raw_message
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
        "validations": [dict(v) for v in validations],
        "history": [dict(h) for h in history],
        "fsuEvents": [dict(e) for e in fsu],
        "rawMessages": [dict(m) for m in raw_msgs],
    }


@app.post("/api/v1/matches/{mawb}/rematch")
def rematch_endpoint(mawb: str):
    with db() as conn:
        result = svc.rematch(conn, mawb, event="MANUAL_REMATCH")
        svc.audit(conn, "REMATCH_MESSAGE", "system", "matching_results",
                  result["id"])
    return result


class ReviewBody(BaseModel):
    reviewed: bool = True
    note: str = ""
    reviewer: str = "operator"


@app.post("/api/v1/matches/{mawb}/review")
def review(mawb: str, body: ReviewBody):
    with db() as conn:
        prev = conn.execute(
            "SELECT reviewed, review_note FROM matching_results WHERE mawb_number=?",
            (mawb,)).fetchone()
        if not prev:
            return JSONResponse(status_code=404, content={
                "code": "NOT_FOUND", "message": f"No match result for {mawb}"})
        conn.execute(
            """UPDATE matching_results SET reviewed=?, reviewed_by=?,
               reviewed_at=?, review_note=?, updated_at=? WHERE mawb_number=?""",
            (1 if body.reviewed else 0, body.reviewer, svc.now(), body.note,
             svc.now(), mawb))
        svc.audit(conn, "MARK_REVIEWED", body.reviewer, "matching_results", mawb,
                  before=dict(prev), after=body.model_dump())
    return {"mawbNumber": mawb, "reviewed": body.reviewed}


# -------------------------------------------------------------- dashboard ---

@app.get("/api/v1/dashboard/summary")
def dashboard_summary():
    with db() as conn:
        today = svc.now()[:10]
        imported_today = conn.execute(
            "SELECT COUNT(*) FROM cargo_messages WHERE substr(imported_at,1,10)=?",
            (today,)).fetchone()[0]
        status_counts = {r["match_status"]: r["c"] for r in conn.execute(
            "SELECT match_status, COUNT(*) c FROM matching_results GROUP BY 1")}
        type_counts = {r["message_type"] or "INVALID": r["c"] for r in conn.execute(
            "SELECT message_type, COUNT(*) c FROM cargo_messages GROUP BY 1")}
        parse_errors = conn.execute(
            """SELECT COUNT(*) FROM cargo_messages
               WHERE parse_status IN ('PARSE_ERROR','INVALID_FORMAT')""").fetchone()[0]
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM cargo_messages WHERE parse_status='DUPLICATE'"
        ).fetchone()[0]
        by_day = [dict(r) for r in conn.execute(
            """SELECT substr(imported_at,1,10) day, COUNT(*) c
               FROM cargo_messages GROUP BY 1 ORDER BY 1 DESC LIMIT 14""")]
        recent = [dict(r) for r in conn.execute(
            """SELECT mawb_number, match_status, match_score, fhl_count,
                      last_matched_at FROM matching_results
               ORDER BY last_matched_at DESC LIMIT 8""")]
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
        "errors": parse_errors,
        "duplicates": duplicates,
        "statusCounts": status_counts,
        "typeCounts": type_counts,
        "importsByDay": list(reversed(by_day)),
        "recent": recent,
    }


# ---------------------------------------------------- raw data explorer -----

EXPLORER_TABLES: dict[str, list[str]] = {
    "cargo_messages": ["id", "batch_id", "message_type", "message_version",
                       "original_filename", "file_size", "source_channel",
                       "message_hash", "parse_status", "parse_error_code",
                       "parse_error_message", "imported_by", "imported_at"],
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
                   "status_date", "weight", "weight_unit", "hawb_number",
                   "raw_line", "created_at"],
    "matching_results": ["id", "mawb_number", "match_status", "match_score",
                         "fhl_count", "fwb_pieces", "fhl_total_pieces",
                         "pieces_difference", "fwb_weight", "fhl_total_weight",
                         "weight_difference", "weight_difference_percentage",
                         "origin_match", "destination_match", "pieces_match",
                         "weight_match", "duplicate_hawb", "reviewed",
                         "reviewed_by", "review_note", "last_matched_at"],
    "validation_results": ["id", "matching_result_id", "rule_code", "severity",
                           "result", "fwb_value", "fhl_value",
                           "difference_value", "created_at"],
    "match_history": ["id", "mawb_number", "event_type", "previous_status",
                      "new_status", "previous_score", "new_score",
                      "performed_by", "performed_at"],
    "import_batches": ["id", "batch_no", "imported_by", "imported_at",
                       "source_channel", "total_files", "success_files",
                       "failed_files", "status"],
    "audit_logs": ["id", "event_type", "user_id", "entity_type", "entity_id",
                   "reason", "created_at"],
}

FILTER_OPS = {
    "eq": "= ?", "ne": "!= ?", "gt": "> ?", "gte": ">= ?", "lt": "< ?",
    "lte": "<= ?", "contains": "LIKE ?", "startswith": "LIKE ?",
    "isnull": "IS NULL", "notnull": "IS NOT NULL",
}


@app.get("/api/v1/data/tables")
def data_tables():
    with db() as conn:
        out = []
        for t, cols in EXPLORER_TABLES.items():
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            out.append({"table": t, "columns": cols, "rowCount": count})
    return {"tables": out}


NUMERIC_AGGS = {"count", "sum", "avg", "min", "max"}


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
              sortBy: str = "", sortDirection: str = "desc"):
    if table not in EXPLORER_TABLES:
        return JSONResponse(status_code=404, content={
            "code": "UNKNOWN_TABLE", "message": f"Table {table} not available"})
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
def data_distinct(table: str, column: str, limit: int = 200):
    """Distinct values of one column — feeds the filter value dropdown."""
    if table not in EXPLORER_TABLES or column not in EXPLORER_TABLES[table]:
        return JSONResponse(status_code=404, content={"code": "UNKNOWN_COLUMN"})
    with db() as conn:
        rows = conn.execute(
            f"""SELECT {column} v, COUNT(*) c FROM {table}
                WHERE {column} IS NOT NULL GROUP BY 1 ORDER BY c DESC LIMIT ?""",
            (min(limit, 500),)).fetchall()
    return {"column": column, "values": [dict(r) for r in rows]}


@app.get("/api/v1/data/{table}/aggregate")
def data_aggregate(table: str, groupBy: str, metric: str = "count",
                   metricColumn: str = "", filter: list[str] = Query(default=[]),
                   match: str = "and", limit: int = 50):
    """Group-by summary over the same filters as the grid — for analysis."""
    if table not in EXPLORER_TABLES:
        return JSONResponse(status_code=404, content={"code": "UNKNOWN_TABLE"})
    cols = EXPLORER_TABLES[table]
    if groupBy not in cols:
        return JSONResponse(status_code=400, content={"code": "UNKNOWN_COLUMN"})
    metric = metric.lower()
    if metric not in NUMERIC_AGGS:
        return JSONResponse(status_code=400, content={"code": "UNKNOWN_METRIC"})
    if metric == "count":
        expr = "COUNT(*)"
    else:
        if metricColumn not in cols:
            return JSONResponse(status_code=400,
                                content={"code": "UNKNOWN_METRIC_COLUMN"})
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
def data_export(table: str, filter: list[str] = Query(default=[]),
                match: str = "and"):
    if table not in EXPLORER_TABLES:
        return JSONResponse(status_code=404, content={"code": "UNKNOWN_TABLE"})
    cols = EXPLORER_TABLES[table]
    wsql, params = _build_filters(table, filter, match)
    with db() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM {table} {wsql}", params).fetchall()
        svc.audit(conn, "EXPORT_DATA", "system", "table", table,
                  after={"rows": len(rows), "filters": filter})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for r in rows:
        writer.writerow([r[c] for c in cols])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="{table}_export.csv"'})


# --------------------------------------------------------------- messages ---

@app.get("/api/v1/messages/{message_id}/raw")
def message_raw(message_id: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM cargo_messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND"})
    return dict(row)


@app.get("/api/v1/messages/{message_id}/parsed")
def message_parsed(message_id: str):
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
    return JSONResponse(status_code=404, content={"code": "NOT_FOUND"})


# ----------------------------------------------------------------- health ---

@app.get("/health/live")
def health_live():
    return {"status": "UP"}


@app.get("/health/ready")
def health_ready():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"status": "READY"}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
