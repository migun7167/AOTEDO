"""End-to-end API tests using the real sample files."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

os.environ["PAPERLESS_AOT_DB"] = os.path.join(
    os.path.dirname(__file__), "test_api.db")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "samples")


@pytest.fixture(scope="module")
def client():
    if os.path.exists(os.environ["PAPERLESS_AOT_DB"]):
        os.remove(os.environ["PAPERLESS_AOT_DB"])
    from app.database import db, init_db
    from app.services.auth import ensure_default_users
    init_db()
    with db() as conn:
        ensure_default_users(conn)
    with TestClient(main.app) as c:
        c.post("/api/v1/auth/login",
               json={"username": "admin", "password": "admin123"})
        yield c
    os.remove(os.environ["PAPERLESS_AOT_DB"])


def as_role(role: str) -> TestClient:
    """A separate client session logged in as operator or viewer."""
    creds = {"operator": "operator123", "viewer": "viewer123",
             "admin": "admin123"}
    c = TestClient(main.app)
    r = c.post("/api/v1/auth/login",
               json={"username": role, "password": creds[role]})
    assert r.status_code == 200, r.text
    return c


def upload(client, *names):
    """Upload sample files; names may be relative to samples/ (e.g. demo/x.txt)."""
    files = []
    for n in names:
        with open(os.path.join(SAMPLES, n), "rb") as f:
            files.append(("files", (os.path.basename(n), f.read(), "text/plain")))
    return client.post("/api/v1/imports/files", files=files)


@pytest.fixture(scope="module")
def seeded(client):
    """The demo set, giving the API tests every match status to work with."""
    import seed
    upload(client, *[f"demo/{n}" for n in seed.DEMO_FILES])
    return client


def test_full_sample_flow(client):
    # 1) FWB first -> WAITING_FOR_FHL
    r = upload(client, "FWB_21708722685.txt").json()
    assert r["results"][0]["status"] == "PARSED"
    assert r["results"][0]["mawbNumbers"] == ["217-08722685"]
    m = client.get("/api/v1/matches/217-08722685").json()
    assert m["result"]["match_status"] == "WAITING_FOR_FHL"

    # 2) FHL arrives -> auto re-match -> MATCHED score 100
    r = upload(client, "FHL_WM26070003.txt").json()
    assert r["results"][0]["status"] == "PARSED"
    m = client.get("/api/v1/matches/217-08722685").json()
    assert m["result"]["match_status"] == "MATCHED"
    assert m["result"]["match_score"] == 100
    assert m["result"]["fhl_count"] == 1
    assert m["houses"][0]["hawb_number"] == "WM26070003"
    rules = {v["rule_code"]: v["result"] for v in m["validations"]}
    assert rules["MAWB_MATCH"] == "PASS"
    assert rules["WEIGHT_MATCH"] == "PASS"

    # 3) FFM + FSU import fine and enrich the detail view
    r = upload(client, "FFM_TG601_16JUL26.txt", "FSU_21708722685.txt").json()
    assert all(x["status"] == "PARSED" for x in r["results"])
    m = client.get("/api/v1/matches/217-08722685").json()
    assert [e["status_code"] for e in m["fsuEvents"]] == \
        ["RCS", "DEP", "ARR", "RCF", "NFD"]

    # 4) duplicate upload detected by SHA-256, still points back to its MAWB
    r = upload(client, "FWB_21708722685.txt").json()
    dup = r["results"][0]
    assert dup["status"] == "DUPLICATE"
    assert dup["errorCode"] == "DUPLICATE_MESSAGE"
    assert dup["mawbNumbers"] == ["217-08722685"]
    assert dup["duplicateOf"]
    # and it did not create a second fwb_master row
    fwbs = client.get("/api/v1/data/fwb_master", params={
        "filter": ["mawb_number:eq:217-08722685"]}).json()
    assert fwbs["total"] == 1

    # 5) history recorded the WAITING -> MATCHED transition
    events = [h["event_type"] for h in m["history"]]
    assert "IMPORT_TRIGGERED_REMATCH" in events


def test_invalid_file(client):
    r = client.post("/api/v1/imports/files",
                    files=[("files", ("bad.txt", b"HELLO WORLD", "text/plain"))])
    body = r.json()["results"][0]
    assert body["status"] == "INVALID_FORMAT"
    assert body["errorCode"] == "UNSUPPORTED_MESSAGE_TYPE"


def test_paste_text(client):
    raw = open(os.path.join(SAMPLES, "FHL_WM26070003.txt")).read() + "\n"
    r = client.post("/api/v1/imports/text", json={"rawMessage": raw}).json()
    assert r["results"][0]["messageType"] == "FHL"


def test_matches_list_and_filters(client):
    data = client.get("/api/v1/matches", params={"status": "MATCHED"}).json()
    assert data["total"] >= 1
    data = client.get("/api/v1/matches", params={"search": "WM26070003"}).json()
    assert data["total"] == 1
    data = client.get("/api/v1/matches", params={"origin": "SIN"}).json()
    assert data["total"] == 0


def test_dashboard(client):
    s = client.get("/api/v1/dashboard/summary").json()
    assert s["matched"] >= 1
    assert s["typeCounts"]["FWB"] >= 1
    assert s["typeCounts"]["FSU"] >= 1


def test_raw_data_explorer(client):
    tables = client.get("/api/v1/data/tables").json()["tables"]
    names = {t["table"] for t in tables}
    assert {"cargo_messages", "fwb_master", "fhl_house", "fsu_status",
            "matching_results"} <= names

    rows = client.get("/api/v1/data/fhl_house", params={
        "filter": ["mawb_number:eq:217-08722685", "gross_weight:gte:100"],
    }).json()
    assert rows["total"] >= 1
    assert rows["rows"][0]["hawb_number"] == "WM26070003"

    rows = client.get("/api/v1/data/fsu_status", params={
        "filter": ["status_code:eq:NFD"]}).json()
    assert rows["total"] == 1

    rows = client.get("/api/v1/data/cargo_messages", params={
        "filter": ["parse_status:eq:DUPLICATE"]}).json()
    assert rows["total"] >= 1

    # unknown table & injection-shaped input are rejected
    assert client.get("/api/v1/data/sqlite_master").status_code == 404
    rows = client.get("/api/v1/data/fhl_house", params={
        "filter": ["hawb_number;DROP TABLE:eq:x"]}).json()
    assert rows["total"] >= 1  # bad filter ignored, not executed


def test_explorer_and_or_matching(client):
    """Two filters that no single row satisfies: AND finds none, OR finds both."""
    and_rows = client.get("/api/v1/data/cargo_messages", params={
        "match": "and",
        "filter": ["message_type:eq:FWB", "message_type:eq:FHL"]}).json()
    assert and_rows["total"] == 0
    or_rows = client.get("/api/v1/data/cargo_messages", params={
        "match": "or",
        "filter": ["message_type:eq:FWB", "message_type:eq:FHL"]}).json()
    assert or_rows["total"] >= 2


def test_explorer_distinct(client):
    d = client.get("/api/v1/data/cargo_messages/distinct",
                   params={"column": "message_type"}).json()
    types = {v["v"] for v in d["values"]}
    assert {"FWB", "FHL", "FSU", "FFM"} <= types
    assert client.get("/api/v1/data/cargo_messages/distinct",
                      params={"column": "raw_message"}).status_code == 404


def test_explorer_aggregate(client):
    a = client.get("/api/v1/data/fhl_house/aggregate", params={
        "groupBy": "destination", "metric": "sum",
        "metricColumn": "gross_weight"}).json()
    assert a["buckets"][0]["bucket"] == "BKK"
    assert a["buckets"][0]["value"] > 0

    a = client.get("/api/v1/data/matching_results/aggregate", params={
        "groupBy": "match_status", "metric": "count"}).json()
    assert sum(b["value"] for b in a["buckets"]) >= 1

    # aggregation honours the grid filters: same filter, same population
    flt = {"filter": ["hawb_number:eq:WM26070003"]}
    grid = client.get("/api/v1/data/fhl_house", params=flt).json()
    a = client.get("/api/v1/data/fhl_house/aggregate",
                   params={"groupBy": "destination", "metric": "count", **flt}).json()
    assert a["buckets"][0]["value"] == grid["total"]

    # bad metric / column are rejected, never interpolated
    assert client.get("/api/v1/data/fhl_house/aggregate", params={
        "groupBy": "destination", "metric": "drop"}).status_code == 400
    assert client.get("/api/v1/data/fhl_house/aggregate", params={
        "groupBy": "1;DELETE FROM fhl_house", "metric": "count"}).status_code == 400


def test_export_csv(client):
    r = client.get("/api/v1/data/matching_results/export")
    assert r.status_code == 200
    assert "mawb_number" in r.text.splitlines()[0]


def test_review_and_rematch(client):
    r = client.post("/api/v1/matches/217-08722685/review",
                    json={"reviewed": True, "note": "verified"})
    assert r.json()["reviewed"] is True
    r = client.post("/api/v1/matches/217-08722685/rematch").json()
    assert r["status"] == "MATCHED"
    audit = client.get("/api/v1/data/audit_logs", params={
        "filter": ["event_type:eq:MARK_REVIEWED"]}).json()
    assert audit["total"] >= 1


# ------------------------------------------------------------ auth / RBAC ---

def test_unauthenticated_is_rejected():
    anon = TestClient(main.app)
    assert anon.get("/api/v1/matches").status_code == 401
    assert anon.get("/api/v1/dashboard/summary").status_code == 401
    # health and metrics stay open for probes
    assert anon.get("/health/ready").status_code == 200
    assert anon.get("/metrics").status_code == 200


def test_bad_credentials(client):
    anon = TestClient(main.app)
    r = anon.post("/api/v1/auth/login",
                  json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS"


def test_roles_enforced(client):
    viewer = as_role("viewer")
    operator = as_role("operator")

    # everyone can read
    assert viewer.get("/api/v1/matches").status_code == 200
    assert viewer.get("/api/v1/exports?format=CSV").status_code == 200

    # viewer cannot import or review
    up = ("files", ("x.txt", b"FWB/16 217-08722685HKGBKK/T1K149.0", "text/plain"))
    assert viewer.post("/api/v1/imports/files", files=[up]).status_code == 403
    assert viewer.post("/api/v1/matches/217-08722685/review",
                       json={"reviewed": True}).status_code == 403

    # operator can review but not change rules, re-match or link houses
    assert operator.post("/api/v1/matches/217-08722685/review",
                         json={"reviewed": True, "note": "ok"}).status_code == 200
    assert operator.post("/api/v1/matches/217-08722685/rematch").status_code == 403
    assert operator.put("/api/v1/settings",
                        json={"changes": {"score_mawb": "40"}}).status_code == 403
    assert operator.get("/api/v1/audit").status_code == 403

    # admin can do all of it
    assert client.get("/api/v1/audit").status_code == 200


def test_logout_ends_session():
    c = as_role("operator")
    assert c.get("/api/v1/auth/me").status_code == 200
    c.post("/api/v1/auth/logout")
    assert c.get("/api/v1/auth/me").status_code == 401


# --------------------------------------------------------------- settings ---

def test_settings_change_rematches(client, seeded):
    """Widening the tolerance turns the 0.2 KG mismatch into a tolerated match."""
    upload(client, "demo/FWB_21708722689.txt", "demo/FHL_GS26070030.txt")
    before = client.get("/api/v1/matches/217-08722689").json()["result"]
    assert before["match_status"] == "MATCHED_WITH_TOLERANCE"

    r = client.put("/api/v1/settings", json={
        "changes": {"weight_tolerance_abs": "0.01", "weight_tolerance_pct": "0.01"},
        "rematch": True}).json()
    assert r["rematched"] >= 1
    after = client.get("/api/v1/matches/217-08722689").json()["result"]
    assert after["match_status"] == "PARTIAL_MATCH"

    # restore and confirm it flips back
    client.put("/api/v1/settings", json={
        "changes": {"weight_tolerance_abs": "0.5", "weight_tolerance_pct": "0.5"},
        "rematch": True})
    restored = client.get("/api/v1/matches/217-08722689").json()["result"]
    assert restored["match_status"] == "MATCHED_WITH_TOLERANCE"

    audit = client.get("/api/v1/audit", params={"eventType": "UPDATE_RULE"}).json()
    assert audit["total"] >= 2


def test_invalid_setting_rejected(client):
    r = client.put("/api/v1/settings", json={"changes": {"score_mawb": "abc"}})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_SETTING"
    r = client.put("/api/v1/settings", json={"changes": {"nonexistent": "1"}})
    assert r.status_code == 400


# ---------------------------------------------------------- manual match ---

def test_manual_unlink_and_relink(client):
    detail = client.get("/api/v1/matches/217-08722685").json()
    fhl_id = detail["houses"][0]["id"]
    assert detail["result"]["match_status"] == "MATCHED"

    r = client.post(f"/api/v1/matches/217-08722685/houses/{fhl_id}/unlink",
                    json={"reason": "house belongs to another master"}).json()
    assert r["status"] == "WAITING_FOR_FHL"

    detail = client.get("/api/v1/matches/217-08722685").json()
    assert detail["houses"] == []
    assert detail["unlinkedHouses"][0]["id"] == fhl_id

    # a re-match must not silently undo the operator's decision
    client.post("/api/v1/matches/217-08722685/rematch")
    assert client.get("/api/v1/matches/217-08722685").json()["houses"] == []

    client.delete(f"/api/v1/matches/217-08722685/houses/{fhl_id}/link")
    back = client.get("/api/v1/matches/217-08722685").json()
    assert back["result"]["match_status"] == "MATCHED"
    assert len(back["houses"]) == 1

    audit = client.get("/api/v1/audit",
                       params={"eventType": "MANUAL_UNMATCH"}).json()
    assert audit["total"] >= 1


def test_manual_link_across_mawb(client, seeded):
    """An administrator may link a house whose MAWB differs; the rule still reports it."""
    houses = client.get("/api/v1/houses/unassigned",
                        params={"search": "PL26070020"}).json()["items"]
    fhl_id = houses[0]["id"]
    client.post(f"/api/v1/matches/217-08722687/houses/{fhl_id}/link",
                json={"reason": "MAWB typo on the house"})
    detail = client.get("/api/v1/matches/217-08722687").json()
    assert any(h["id"] == fhl_id and h["linked_by"] == "MANUAL"
               for h in detail["houses"])
    rules = {v["rule_code"]: v["result"] for v in detail["validations"]}
    assert rules["MAWB_MATCH"] == "FAIL"
    client.delete(f"/api/v1/matches/217-08722687/houses/{fhl_id}/link")


# ----------------------------------------------------------- status override ---

def test_status_override(client, seeded):
    r = client.post("/api/v1/matches/217-08722686/status",
                    json={"status": "RESOLVED", "reason": "confirmed with airline"})
    assert r.status_code == 200
    detail = client.get("/api/v1/matches/217-08722686").json()["result"]
    assert detail["effective_status"] == "RESOLVED"
    assert detail["match_status"] == "PARTIAL_MATCH"  # computed value preserved

    listed = client.get("/api/v1/matches", params={"status": "RESOLVED"}).json()
    assert any(i["mawb_number"] == "217-08722686" for i in listed["items"])

    assert client.post("/api/v1/matches/217-08722686/status",
                       json={"status": "NONSENSE"}).status_code == 400

    client.post("/api/v1/matches/217-08722686/status", json={"status": None})
    cleared = client.get("/api/v1/matches/217-08722686").json()["result"]
    assert cleared["effective_status"] == "PARTIAL_MATCH"


# --------------------------------------------------------------- exports ---

def test_export_formats(client):
    xlsx = client.post("/api/v1/exports", json={"format": "XLSX"})
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"          # zip container of a real workbook

    import io
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert {"Summary", "FWB", "FHL", "Validation Results", "Errors",
            "Audit Log"} <= set(wb.sheetnames)
    assert wb["Summary"].max_row >= 2

    js = client.post("/api/v1/exports", json={"format": "JSON"}).json()
    assert "Summary" in js["sections"]

    raw = client.post("/api/v1/exports", json={"format": "RAW"})
    assert raw.content[:2] == b"PK"
    import zipfile
    with zipfile.ZipFile(io.BytesIO(raw.content)) as zf:
        names = zf.namelist()
    assert "manifest.json" in names
    assert any(n.startswith("217-08722685/") for n in names)

    assert client.post("/api/v1/exports",
                       json={"format": "PDF"}).status_code == 400


def test_export_honours_filters(client, seeded):
    all_rows = client.post("/api/v1/exports", json={"format": "JSON"}).json()
    matched = client.post("/api/v1/exports", json={
        "format": "JSON", "filters": {"status": ["MATCHED"]}}).json()
    assert len(matched["sections"]["Summary"]) < len(all_rows["sections"]["Summary"])
    assert all(r["status"] == "MATCHED" for r in matched["sections"]["Summary"])


# ------------------------------------------------- errors, history, metrics ---

def test_errors_page_data(client, seeded):
    d = client.get("/api/v1/errors").json()
    assert any(e["parse_error_code"] == "UNSUPPORTED_MESSAGE_TYPE"
               for e in d["parseErrors"])
    assert any(f["rule_code"] == "PIECES_MATCH" for f in d["validationFailures"])
    assert d["duplicates"]


def test_history_records_transitions(client):
    d = client.get("/api/v1/history", params={"mawb": "217-08722685"}).json()
    events = [h["event_type"] for h in d["items"]]
    assert "IMPORT_TRIGGERED_REMATCH" in events
    statuses = [h["new_status"] for h in d["items"]]
    assert "MATCHED" in statuses


def test_metrics_exposition(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert 'paperless_aot_messages_total{type="FWB"}' in body
    assert "paperless_aot_match_status_total" in body
    assert "paperless_aot_houses_total" in body


def test_batch_detail(client, seeded):
    batch_id = upload(client, "demo/FWB_21708722687.txt").json()["batchId"]
    d = client.get(f"/api/v1/imports/{batch_id}").json()
    assert d["batch"]["status"] == "COMPLETED"
    assert len(d["messages"]) == 1


def test_business_key_duplicate_flagged(client):
    """Same MAWB and version, different bytes — a revision, not an exact copy."""
    raw = open(os.path.join(SAMPLES, "FWB_21708722685.txt")).read()
    revised = raw.replace("K149.0", "K150.0")
    r = client.post("/api/v1/imports/text", json={"rawMessage": revised}).json()
    result = r["results"][0]
    assert result["status"] == "PARSED"
    assert result["duplicateType"] == "BUSINESS_KEY"
