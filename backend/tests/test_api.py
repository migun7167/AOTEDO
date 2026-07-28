"""End-to-end API tests using the real sample files."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["PAPERLESS_AOT_DB"] = os.path.join(
    os.path.dirname(__file__), "test_api.db")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "samples")


@pytest.fixture(scope="module")
def client():
    if os.path.exists(os.environ["PAPERLESS_AOT_DB"]):
        os.remove(os.environ["PAPERLESS_AOT_DB"])
    from app.database import init_db
    init_db()
    with TestClient(main.app) as c:
        yield c
    os.remove(os.environ["PAPERLESS_AOT_DB"])


def upload(client, *names):
    files = []
    for n in names:
        with open(os.path.join(SAMPLES, n), "rb") as f:
            files.append(("files", (n, f.read(), "text/plain")))
    return client.post("/api/v1/imports/files", files=files)


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
                    json={"reviewed": True, "note": "verified", "reviewer": "op1"})
    assert r.json()["reviewed"] is True
    r = client.post("/api/v1/matches/217-08722685/rematch").json()
    assert r["status"] == "MATCHED"
    audit = client.get("/api/v1/data/audit_logs", params={
        "filter": ["event_type:eq:MARK_REVIEWED"]}).json()
    assert audit["total"] >= 1
