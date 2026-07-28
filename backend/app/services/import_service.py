"""Import pipeline: detect → dedupe → parse → persist → re-match → audit."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from ..matching.engine import match_fwb_fhl
from ..parser import ParseError, detect, parse_message
from . import settings_service


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


def create_batch(conn: sqlite3.Connection, source_channel: str,
                 user: str = "system") -> dict:
    ts = now()
    seq = conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] + 1
    batch_no = f"IMP-{datetime.now():%Y%m%d}-{seq:06d}"
    batch_id = new_id()
    conn.execute(
        """INSERT INTO import_batches
           (id, batch_no, imported_by, imported_at, source_channel,
            total_files, success_files, failed_files, status, created_at, updated_at)
           VALUES (?,?,?,?,?,0,0,0,'PROCESSING',?,?)""",
        (batch_id, batch_no, user, ts, source_channel, ts, ts))
    return {"id": batch_id, "batch_no": batch_no}


def import_message(conn: sqlite3.Connection, raw: str, filename: str | None,
                   batch_id: str, source_channel: str = "WEB_UPLOAD",
                   user: str = "system") -> dict:
    """Import one raw message. Returns per-file result dict."""
    ts = now()
    msg_id = new_id()
    msg_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    dup = conn.execute(
        "SELECT id, original_filename FROM cargo_messages WHERE message_hash = ?",
        (msg_hash,)).fetchone()

    msg_type = version = None
    parse_status = "PARSED"
    error_code = error_message = None
    duplicate_type = None
    parsed = None

    try:
        msg_type, version = detect(raw)
    except ParseError as e:
        parse_status, error_code, error_message = "INVALID_FORMAT", e.code, e.message

    if parse_status == "PARSED" and dup:
        parse_status = "DUPLICATE"
        duplicate_type = "EXACT"
        error_code = "DUPLICATE_MESSAGE"
        error_message = f"Exact duplicate of message {dup['id']}"

    if parse_status == "PARSED":
        try:
            parsed = parse_message(raw)
        except ParseError as e:
            parse_status, error_code, error_message = "PARSE_ERROR", e.code, e.message
        except Exception as e:  # defensive: never lose the raw message
            parse_status, error_code = "PARSE_ERROR", "INTERNAL_PARSE_ERROR"
            error_message = str(e)

    # FR-007 business key: same shipment identity, different bytes — a revision
    # rather than a duplicate, so it is still parsed and stored, only flagged.
    if parsed and _business_key_exists(conn, parsed, version):
        duplicate_type = "BUSINESS_KEY"

    conn.execute(
        """INSERT INTO cargo_messages
           (id, batch_id, message_type, message_version, original_filename,
            file_size, source_channel, raw_message, message_hash, parse_status,
            parse_error_code, parse_error_message, duplicate_of, duplicate_type,
            imported_by, imported_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (msg_id, batch_id, msg_type, version, filename, len(raw.encode()),
         source_channel, raw, msg_hash, parse_status, error_code, error_message,
         dup["id"] if dup else None, duplicate_type, user, ts, ts, ts))

    affected_mawbs: set[str] = set()
    if parsed:
        affected_mawbs = _persist_parsed(conn, msg_id, parsed, ts)

    # A duplicate is not re-parsed, but the operator still needs a way back to
    # the record it duplicates, so report the original message's MAWBs.
    duplicate_mawbs: list[str] = []
    if parse_status == "DUPLICATE" and dup:
        duplicate_mawbs = [r["mawb_number"] for r in conn.execute(
            """SELECT mawb_number FROM fwb_master WHERE message_id = ?
               UNION SELECT mawb_number FROM fhl_house WHERE message_id = ?
               UNION SELECT mawb_number FROM fsu_status WHERE message_id = ?
               UNION SELECT mawb_number FROM ffm_flight WHERE message_id = ?""",
            (dup["id"],) * 4) if r["mawb_number"]]

    audit(conn, "IMPORT_FILE", user, "cargo_messages", msg_id,
          after={"filename": filename, "type": msg_type, "status": parse_status,
                 "duplicateType": duplicate_type})

    for mawb in affected_mawbs:
        rematch(conn, mawb, user=user, event="IMPORT_TRIGGERED_REMATCH")

    return {
        "messageId": msg_id,
        "filename": filename,
        "messageType": msg_type,
        "version": version,
        "status": parse_status,
        "duplicateType": duplicate_type,
        "errorCode": error_code,
        "errorMessage": error_message,
        "mawbNumbers": sorted(affected_mawbs) or duplicate_mawbs,
        "duplicateOf": dup["id"] if (parse_status == "DUPLICATE" and dup) else None,
    }


def _business_key_exists(conn: sqlite3.Connection, parsed: dict,
                         version: str | None) -> bool:
    """FWB key: type+mawb+version. FHL key: type+mawb+hawb+version."""
    if parsed["messageType"] == "FWB":
        row = conn.execute(
            """SELECT 1 FROM fwb_master f JOIN cargo_messages m ON m.id = f.message_id
               WHERE f.mawb_number = ? AND m.message_version = ?""",
            (parsed["mawbNumber"], version)).fetchone()
        return row is not None
    if parsed["messageType"] == "FHL":
        row = conn.execute(
            """SELECT 1 FROM fhl_house f JOIN cargo_messages m ON m.id = f.message_id
               WHERE f.mawb_number = ? AND f.hawb_number = ?
                 AND m.message_version = ?""",
            (parsed["mawbNumber"], parsed["hawbNumber"], version)).fetchone()
        return row is not None
    return False


def _persist_parsed(conn: sqlite3.Connection, msg_id: str, p: dict,
                    ts: str) -> set[str]:
    mawbs: set[str] = set()
    if p["messageType"] == "FWB":
        shp, cne, agt = p.get("shipper", {}), p.get("consignee", {}), p.get("agent", {})
        ppd = p.get("prepaid", {})
        conn.execute(
            """INSERT INTO fwb_master
               (id, message_id, mawb_number, airline_prefix, serial_number,
                origin, destination, pieces, gross_weight, weight_unit,
                chargeable_weight, flight_number, flight_date, routing,
                shipper_name, shipper_address, shipper_country,
                consignee_name, consignee_address, consignee_country,
                agent_code, agent_name, currency, payment_type, rate,
                freight_charge, other_charge, total_charge, nature_of_goods,
                issue_date, issue_place, reference_number,
                special_handling_codes, parsed_data, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_id(), msg_id, p["mawbNumber"], p.get("airlinePrefix"),
             p.get("serialNumber"), p.get("origin"), p.get("destination"),
             p.get("pieces"), p.get("weight"), p.get("weightUnit"),
             p.get("chargeableWeight"), p.get("flightNumber"), p.get("flightDate"),
             p.get("routing"), shp.get("name"), shp.get("address"),
             shp.get("country"), cne.get("name"), cne.get("address"),
             cne.get("country"), agt.get("code"), agt.get("name"),
             (p.get("chargeDeclaration") or {}).get("currency"),
             (p.get("chargeDeclaration") or {}).get("chargeCode"),
             p.get("rate"), p.get("freightCharge"), ppd.get("otherCharge"),
             ppd.get("totalCharge"), p.get("natureOfGoods"),
             p.get("issueDate"), p.get("issuePlace"), p.get("reference"),
             json.dumps(p.get("specialHandlingCodes")), json.dumps(p),
             ts, ts))
        mawbs.add(p["mawbNumber"])
    elif p["messageType"] == "FHL":
        shp, cne = p.get("shipper", {}), p.get("consignee", {})
        oci = p.get("oci", {})
        conn.execute(
            """INSERT INTO fhl_house
               (id, message_id, mawb_number, hawb_number, origin, destination,
                pieces, gross_weight, weight_unit, commodity, hs_code,
                customs_country, customs_party_type, customs_info_type,
                consignee_tax_id, shipper_name, shipper_address,
                shipper_country, shipper_postal_code, consignee_name,
                consignee_address, consignee_country, consignee_postal_code,
                consignee_phone, parsed_data, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_id(), msg_id, p["mawbNumber"], p["hawbNumber"], p.get("origin"),
             p.get("destination"), p.get("pieces"), p.get("weight"),
             p.get("weightUnit"), p.get("commodity"), p.get("hsCode"),
             oci.get("country"), oci.get("partyType"), oci.get("infoType"),
             p.get("consigneeTaxId"), shp.get("name"), shp.get("address"),
             shp.get("country"), shp.get("postalCode"), cne.get("name"),
             cne.get("address"), cne.get("country"), cne.get("postalCode"),
             cne.get("phone"), json.dumps(p), ts, ts))
        mawbs.add(p["mawbNumber"])
    elif p["messageType"] == "FFM":
        for c in p.get("consignments", []):
            conn.execute(
                """INSERT INTO ffm_flight
                   (id, message_id, flight_number, flight_date, origin,
                    destination, mawb_number, pieces, gross_weight,
                    weight_unit, nature_of_goods, parsed_data, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_id(), msg_id, p.get("flightNumber"), p.get("flightDate"),
                 c.get("origin"), c.get("destination"), c.get("mawbNumber"),
                 c.get("pieces"), c.get("weight"), c.get("weightUnit"),
                 c.get("natureOfGoods"), json.dumps(p), ts))
    elif p["messageType"] == "FSU":
        for ev in p.get("events", []):
            conn.execute(
                """INSERT INTO fsu_status
                   (id, message_id, mawb_number, status_code, airport,
                    flight_number, status_date, weight, weight_unit,
                    hawb_number, raw_line, parsed_data, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_id(), msg_id, ev.get("mawbNumber"), ev.get("statusCode"),
                 ev.get("airport"), ev.get("flightNumber"), ev.get("date"),
                 ev.get("weight"), ev.get("weightUnit"), ev.get("hawbNumber"),
                 ev.get("rawLine"), json.dumps(ev), ts))
    return mawbs


def houses_for(conn: sqlite3.Connection, mawb: str) -> list[sqlite3.Row]:
    """Houses that count towards this MAWB.

    Latest row per HAWB (a re-import supersedes the earlier one), minus houses
    an administrator unlinked, plus houses an administrator linked in manually.
    """
    rows = conn.execute(
        """SELECT * FROM (
             SELECT f.*, m.message_version, ROW_NUMBER() OVER (
               PARTITION BY f.hawb_number
               ORDER BY f.created_at DESC, f.rowid DESC) rn
             FROM fhl_house f
             JOIN cargo_messages m ON m.id = f.message_id
             WHERE f.mawb_number = ?)
           WHERE rn = 1""", (mawb,)).fetchall()

    overrides = {r["fhl_id"]: r["action"] for r in conn.execute(
        "SELECT fhl_id, action FROM house_link_overrides WHERE mawb_number = ?",
        (mawb,))}

    kept = [r for r in rows if overrides.get(r["id"]) != "UNLINK"]
    linked_ids = [fid for fid, action in overrides.items() if action == "LINK"]
    present = {r["id"] for r in kept}
    for fhl_id in linked_ids:
        if fhl_id in present:
            continue
        extra = conn.execute(
            """SELECT f.*, m.message_version FROM fhl_house f
               JOIN cargo_messages m ON m.id = f.message_id WHERE f.id = ?""",
            (fhl_id,)).fetchone()
        if extra:
            kept.append(extra)
    return kept


def rematch(conn: sqlite3.Connection, mawb: str, user: str = "system",
            event: str = "REMATCH") -> dict:
    """Recompute the matching result for one MAWB and persist it."""
    ts = now()
    fwb = conn.execute(
        """SELECT w.*, m.message_version FROM fwb_master w
           JOIN cargo_messages m ON m.id = w.message_id
           WHERE w.mawb_number = ?
           ORDER BY w.created_at DESC, w.rowid DESC LIMIT 1""", (mawb,)).fetchone()
    fhls = houses_for(conn, mawb)

    config = settings_service.matching_config(conn)
    result = match_fwb_fhl(dict(fwb) if fwb else None,
                           [dict(x) for x in fhls], config)

    prev = conn.execute(
        "SELECT * FROM matching_results WHERE mawb_number = ?", (mawb,)).fetchone()

    if prev:
        mr_id = prev["id"]
        conn.execute(
            """UPDATE matching_results SET fwb_id=?, match_status=?, match_score=?,
               fhl_count=?, fwb_pieces=?, fhl_total_pieces=?, pieces_difference=?,
               fwb_weight=?, fhl_total_weight=?, weight_difference=?,
               weight_difference_percentage=?, origin_match=?, destination_match=?,
               pieces_match=?, weight_match=?, duplicate_hawb=?,
               last_matched_at=?, updated_at=? WHERE id=?""",
            (fwb["id"] if fwb else None, result["status"], result["score"],
             result.get("fhl_count", 0), result.get("fwb_pieces"),
             result.get("fhl_total_pieces"), result.get("pieces_difference"),
             result.get("fwb_weight"), result.get("fhl_total_weight"),
             result.get("weight_difference"),
             result.get("weight_difference_percentage"),
             result.get("origin_match"), result.get("destination_match"),
             result.get("pieces_match"), result.get("weight_match"),
             result.get("duplicate_hawb"), ts, ts, mr_id))
        conn.execute(
            "DELETE FROM validation_results WHERE matching_result_id = ?", (mr_id,))
        conn.execute(
            "DELETE FROM matching_result_houses WHERE matching_result_id = ?",
            (mr_id,))
    else:
        mr_id = new_id()
        conn.execute(
            """INSERT INTO matching_results
               (id, mawb_number, fwb_id, match_status, match_score, fhl_count,
                fwb_pieces, fhl_total_pieces, pieces_difference, fwb_weight,
                fhl_total_weight, weight_difference, weight_difference_percentage,
                origin_match, destination_match, pieces_match, weight_match,
                duplicate_hawb, reviewed, last_matched_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?)""",
            (mr_id, mawb, fwb["id"] if fwb else None, result["status"],
             result["score"], result.get("fhl_count", 0),
             result.get("fwb_pieces"), result.get("fhl_total_pieces"),
             result.get("pieces_difference"), result.get("fwb_weight"),
             result.get("fhl_total_weight"), result.get("weight_difference"),
             result.get("weight_difference_percentage"),
             result.get("origin_match"), result.get("destination_match"),
             result.get("pieces_match"), result.get("weight_match"),
             result.get("duplicate_hawb"), ts, ts, ts))

    manual = {r["fhl_id"] for r in conn.execute(
        """SELECT fhl_id FROM house_link_overrides
           WHERE mawb_number = ? AND action = 'LINK'""", (mawb,))}
    for fhl in fhls:
        conn.execute(
            """INSERT OR IGNORE INTO matching_result_houses
               (matching_result_id, fhl_id, linked_by, linked_by_user, linked_at)
               VALUES (?,?,?,?,?)""",
            (mr_id, fhl["id"], "MANUAL" if fhl["id"] in manual else "AUTO",
             user, ts))

    for v in result.get("validations", []):
        conn.execute(
            """INSERT INTO validation_results
               (id, matching_result_id, rule_code, severity, result,
                fwb_value, fhl_value, difference_value, message, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (new_id(), mr_id, v["rule_code"], v["severity"], v["result"],
             v["fwb_value"], v["fhl_value"], v["difference_value"], None, ts))

    conn.execute(
        """INSERT INTO match_history
           (id, mawb_number, event_type, previous_status, new_status,
            previous_score, new_score, details, performed_by, performed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (new_id(), mawb, event,
         prev["match_status"] if prev else None, result["status"],
         prev["match_score"] if prev else None, result["score"],
         json.dumps({k: v for k, v in result.items() if k != "validations"}),
         user, ts))

    return {"id": mr_id, **{k: v for k, v in result.items() if k != "validations"}}


def rematch_all(conn: sqlite3.Connection, user: str, event: str) -> int:
    """Re-run matching for every known MAWB — used after a rule change."""
    mawbs = [r["mawb_number"] for r in conn.execute(
        """SELECT mawb_number FROM matching_results
           UNION SELECT mawb_number FROM fwb_master
           UNION SELECT mawb_number FROM fhl_house""")]
    for mawb in mawbs:
        rematch(conn, mawb, user=user, event=event)
    return len(mawbs)


def set_house_link(conn: sqlite3.Connection, mawb: str, fhl_id: str,
                   action: str, reason: str, user: str) -> dict:
    """Link or unlink a house from a MAWB (FR-014), then re-match."""
    house = conn.execute(
        "SELECT * FROM fhl_house WHERE id = ?", (fhl_id,)).fetchone()
    if not house:
        raise LookupError(f"FHL {fhl_id} not found")

    before = {"linked": house["id"] in {h["id"] for h in houses_for(conn, mawb)}}
    conn.execute(
        """INSERT INTO house_link_overrides
           (id, mawb_number, fhl_id, action, reason, performed_by, performed_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(mawb_number, fhl_id) DO UPDATE SET
             action=excluded.action, reason=excluded.reason,
             performed_by=excluded.performed_by, performed_at=excluded.performed_at""",
        (new_id(), mawb, fhl_id, action, reason, user, now()))

    result = rematch(conn, mawb, user=user,
                     event="MANUAL_LINK" if action == "LINK" else "MANUAL_UNLINK")
    audit(conn, "MANUAL_MATCH" if action == "LINK" else "MANUAL_UNMATCH",
          user, "fhl_house", fhl_id, before=before,
          after={"linked": action == "LINK", "mawb": mawb,
                 "hawb": house["hawb_number"]}, reason=reason)
    return result


def clear_house_link(conn: sqlite3.Connection, mawb: str, fhl_id: str,
                     user: str) -> dict:
    """Drop a manual decision and fall back to automatic matching."""
    conn.execute(
        "DELETE FROM house_link_overrides WHERE mawb_number = ? AND fhl_id = ?",
        (mawb, fhl_id))
    result = rematch(conn, mawb, user=user, event="MANUAL_LINK_CLEARED")
    audit(conn, "MANUAL_UNMATCH", user, "fhl_house", fhl_id,
          after={"override": "cleared", "mawb": mawb})
    return result


def audit(conn: sqlite3.Connection, event_type: str, user: str,
          entity_type: str | None = None, entity_id: str | None = None,
          before: dict | None = None, after: dict | None = None,
          reason: str | None = None, ip: str | None = None,
          user_agent: str | None = None) -> None:
    conn.execute(
        """INSERT INTO audit_logs
           (id, event_type, user_id, entity_type, entity_id, before_value,
            after_value, reason, ip_address, user_agent, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (new_id(), event_type, user, entity_type, entity_id,
         json.dumps(before) if before else None,
         json.dumps(after) if after else None, reason, ip, user_agent, now()))
