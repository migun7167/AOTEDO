"""Delivery Order (Customs Manifestation) generation.

A DO is a house-level document: one per HAWB. Every field is taken from the
matched FWB/FHL/FSU data; the handful the Cargo-IMP messages cannot supply
(aircraft registration, customer code, and the ATA clock time when the carrier
omits it) are accepted as overrides and stored with the document.

Issued DOs are persisted, so reprinting returns the original number rather than
minting a new one.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta

# Airline prefix -> (carrier code, legal name, terminal wording on the footer)
CARRIERS: dict[str, tuple[str, str, str]] = {
    "217": ("TG", "THAI AIRWAYS INTERNATIONAL PUBLIC COMPANY LIMITED",
            "Thai Cargo Terminal Operations Department"),
    "618": ("SQ", "SINGAPORE AIRLINES LIMITED", "Cargo Terminal Operations"),
    "160": ("CX", "CATHAY PACIFIC AIRWAYS LIMITED", "Cargo Terminal Operations"),
    "131": ("JL", "JAPAN AIRLINES CO LTD", "Cargo Terminal Operations"),
    "180": ("KE", "KOREAN AIR LINES CO LTD", "Cargo Terminal Operations"),
    "205": ("NH", "ALL NIPPON AIRWAYS CO LTD", "Cargo Terminal Operations"),
    "020": ("LH", "DEUTSCHE LUFTHANSA AG", "Cargo Terminal Operations"),
    "176": ("EK", "EMIRATES", "Cargo Terminal Operations"),
    "157": ("QR", "QATAR AIRWAYS", "Cargo Terminal Operations"),
}
DEFAULT_CARRIER = ("", "", "Cargo Terminal Operations Department")

# Station name printed on the DO, derived from the destination airport.
AIRPORT_CITY: dict[str, str] = {
    "BKK": "BANGKOK", "DMK": "BANGKOK", "HKT": "PHUKET", "CNX": "CHIANG MAI",
    "HDY": "HAT YAI", "URT": "SURAT THANI", "KBV": "KRABI",
    "HKG": "HONG KONG", "SIN": "SINGAPORE", "NRT": "TOKYO", "HND": "TOKYO",
    "KIX": "OSAKA", "ICN": "SEOUL", "PVG": "SHANGHAI", "PEK": "BEIJING",
    "CAN": "GUANGZHOU", "TPE": "TAIPEI", "KUL": "KUALA LUMPUR",
    "MNL": "MANILA", "SGN": "HO CHI MINH CITY", "HAN": "HANOI",
    "DEL": "DELHI", "BOM": "MUMBAI", "DXB": "DUBAI", "DOH": "DOHA",
    "FRA": "FRANKFURT", "LHR": "LONDON", "CDG": "PARIS", "AMS": "AMSTERDAM",
    "SYD": "SYDNEY", "MEL": "MELBOURNE", "LAX": "LOS ANGELES",
    "JFK": "NEW YORK", "ORD": "CHICAGO",
}

COUNTRY_NAME: dict[str, str] = {
    "TH": "THAILAND", "HK": "HONG KONG", "SG": "SINGAPORE", "JP": "JAPAN",
    "KR": "KOREA", "CN": "CHINA", "TW": "TAIWAN", "MY": "MALAYSIA",
    "PH": "PHILIPPINES", "VN": "VIETNAM", "IN": "INDIA", "AE": "UAE",
    "QA": "QATAR", "DE": "GERMANY", "GB": "UNITED KINGDOM", "FR": "FRANCE",
    "NL": "NETHERLANDS", "AU": "AUSTRALIA", "US": "USA",
}

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

EXPIRY_HOURS = 48

# Movement events that mean "the shipment landed", best first.
ARRIVAL_EVENTS = ("RCF", "ARR")


class DOError(Exception):
    pass


# ------------------------------------------------------------- formatting ---

def parse_imp_date(value: str | None, time_value: str | None = None
                   ) -> datetime | None:
    """Turn Cargo-IMP "16JUL26" (+ optional "1435") into a datetime."""
    if not value:
        return None
    m = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2})$", value.strip().upper())
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2), int(m.group(3))
    if mon not in MONTHS:
        return None
    hour = minute = 0
    if time_value and re.match(r"^\d{4}$", time_value):
        hour, minute = int(time_value[:2]), int(time_value[2:])
    return datetime(2000 + year, MONTHS.index(mon) + 1, day, hour, minute)


def fmt_do_date(dt: datetime | None) -> str:
    """17-Jul-2026"""
    return f"{dt.day:02d}-{MONTHS[dt.month - 1].title()}-{dt.year}" if dt else ""


def fmt_stamp(dt: datetime | None, with_time: bool = True) -> str:
    """16-JUL-2026 14:35"""
    if not dt:
        return ""
    stamp = f"{dt.day:02d}-{MONTHS[dt.month - 1]}-{dt.year}"
    return f"{stamp} {dt:%H:%M}" if with_time else stamp


def fmt_flight(carrier_code: str, flight_number: str | None) -> str:
    """TG601 -> TG0601 (carriers print the number zero-padded to four)."""
    if not flight_number:
        return ""
    m = re.match(r"^([A-Z0-9]{2,3}?)(\d{1,4})([A-Z]?)$", flight_number.strip().upper())
    if not m:
        return flight_number.strip().upper()
    prefix = m.group(1) or carrier_code
    return f"{prefix}{int(m.group(2)):04d}{m.group(3)}"


def fmt_weight(value: float | None) -> str:
    """149.0 -> 149, 480.5 -> 480.5"""
    if value is None:
        return ""
    return str(int(value)) if float(value) == int(value) else f"{float(value):g}"


# ----------------------------------------------------------------- barcode ---

CODE39_PATTERNS = {
    "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn",
    "4": "nnnwwnnnw", "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw",
    "8": "wnnwnnwnn", "9": "nnwwnnwnn", "A": "wnnnnwnnw", "B": "nnwnnwnnw",
    "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn", "F": "nnwnwwnnn",
    "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
    "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww",
    "O": "wnnnwnnwn", "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn",
    "S": "nnwnnnwwn", "T": "nnnnwnwwn", "U": "wwnnnnnnw", "V": "nwwnnnnnw",
    "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn", "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "*": "nwnnwnwnn",
}


def code39_svg(text: str, height: int = 52, narrow: float = 1.6,
               wide_ratio: float = 2.6) -> str:
    """Render a Code 39 barcode as inline SVG (no external dependency)."""
    value = (text or "").upper()
    encoded = "*" + "".join(c for c in value if c in CODE39_PATTERNS) + "*"

    bars, x = [], 0.0
    for index, char in enumerate(encoded):
        pattern = CODE39_PATTERNS[char]
        for position, element in enumerate(pattern):
            width = narrow * (wide_ratio if element == "w" else 1)
            if position % 2 == 0:  # even positions are bars, odd are spaces
                bars.append(f'<rect x="{x:.2f}" y="0" width="{width:.2f}" '
                            f'height="{height}" fill="#000"/>')
            x += width
        if index < len(encoded) - 1:
            x += narrow  # inter-character gap

    return (f'<svg class="barcode" width="{x:.0f}" height="{height}" '
            f'viewBox="0 0 {x:.2f} {height}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="barcode {value}">{"".join(bars)}</svg>')


# ------------------------------------------------------------- DO building ---

def _next_do_number(conn: sqlite3.Connection, start: int) -> str:
    row = conn.execute(
        "SELECT MAX(CAST(do_number AS INTEGER)) n FROM delivery_orders").fetchone()
    current = row["n"] or 0
    return str(max(current + 1, start))


def build_context(conn: sqlite3.Connection, mawb: str, fhl_id: str,
                  overrides: dict | None = None,
                  shc_source: str = "HOUSE") -> dict:
    """Collect every field the DO prints, from the matched data."""
    overrides = overrides or {}

    house = conn.execute(
        "SELECT * FROM fhl_house WHERE id = ? AND mawb_number = ?",
        (fhl_id, mawb)).fetchone()
    if not house:
        raise DOError(f"ไม่พบ house {fhl_id} ใน MAWB {mawb}")

    result = conn.execute(
        "SELECT * FROM matching_results WHERE mawb_number = ?", (mawb,)).fetchone()
    fwb = conn.execute(
        """SELECT w.* FROM fwb_master w
           JOIN matching_results r ON r.fwb_id = w.id
           WHERE r.mawb_number = ?""", (mawb,)).fetchone()

    # Landed on / ATA: prefer the arrival event at the destination station.
    landed = None
    for code in ARRIVAL_EVENTS:
        event = conn.execute(
            """SELECT status_date, status_time FROM fsu_status
               WHERE mawb_number = ? AND status_code = ?
               ORDER BY (status_time IS NOT NULL) DESC, created_at DESC
               LIMIT 1""", (mawb, code)).fetchone()
        if event:
            landed = parse_imp_date(event["status_date"], event["status_time"])
            if landed:
                break
    if overrides.get("landedAt"):
        landed = _parse_iso(overrides["landedAt"]) or landed

    prefix = (fwb["airline_prefix"] if fwb else None) or mawb.split("-")[0]
    carrier_code, carrier_name, terminal = CARRIERS.get(prefix, DEFAULT_CARRIER)

    destination = house["destination"] or (fwb["destination"] if fwb else None)
    origin = house["origin"] or (fwb["origin"] if fwb else None)

    do_date = _parse_iso(overrides.get("doDate")) or datetime.now()
    expiry = landed + timedelta(hours=EXPIRY_HOURS) if landed else None

    # FHL/4 carries no SHC of its own, so the HOUSE setting prints nothing —
    # which is what the carrier's own DO does. MASTER lifts the FWB's SPH codes.
    sph: list[str] = []
    if shc_source == "MASTER" and fwb and fwb["special_handling_codes"]:
        try:
            sph = json.loads(fwb["special_handling_codes"]) or []
        except (ValueError, TypeError):
            sph = []

    return {
        "mawbNumber": mawb,
        "mawbPlain": mawb.replace("-", ""),
        "hawbNumber": house["hawb_number"],
        "fhlId": house["id"],
        "station": overrides.get("station") or AIRPORT_CITY.get(
            destination or "", destination or ""),
        "doDate": do_date,
        "customerCode": overrides.get("customerCode", ""),
        "consignee": {
            "name": house["consignee_name"] or "",
            "address": house["consignee_address"] or "",
            "postalCode": house["consignee_postal_code"] or "",
            "country": COUNTRY_NAME.get(house["consignee_country"] or "",
                                        house["consignee_country"] or ""),
        },
        "shc": " ".join(sph),
        "pieces": house["pieces"],
        "masterPieces": (result["fwb_pieces"] if result else None) or (
            fwb["pieces"] if fwb else None),
        "weight": house["gross_weight"],
        "masterWeight": (result["fwb_weight"] if result else None) or (
            fwb["gross_weight"] if fwb else None),
        "weightUnit": house["weight_unit"] or (fwb["weight_unit"] if fwb else "K"),
        "boardPoint": origin or "",
        "offPoint": destination or "",
        "flightNumber": fmt_flight(carrier_code,
                                   fwb["flight_number"] if fwb else None),
        "aircraftRegistration": overrides.get("aircraftRegistration", ""),
        "landedAt": landed,
        "expiryAt": expiry,
        "natureOfGoods": house["commodity"] or (
            fwb["nature_of_goods"] if fwb else "") or "",
        "issuedBy": overrides.get("issuedBy", ""),
        "carrierCode": carrier_code,
        "carrierName": carrier_name,
        "terminalName": terminal,
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def issue(conn: sqlite3.Connection, mawb: str, fhl_id: str, user: str,
          overrides: dict | None = None, number_start: int = 5000001,
          default_issued_by: str = "", shc_source: str = "HOUSE",
          amend: bool = False) -> dict:
    """Create the DO, or return the existing one for this house (a reprint).

    `amend` rewrites an issued document from the current data and overrides
    while keeping its number — what a carrier does when a detail was wrong.
    """
    ctx = build_context(conn, mawb, fhl_id, overrides, shc_source)
    ctx["issuedBy"] = ctx["issuedBy"] or default_issued_by

    existing = conn.execute(
        """SELECT * FROM delivery_orders
           WHERE mawb_number = ? AND hawb_number = ?""",
        (mawb, ctx["hawbNumber"])).fetchone()

    if existing and amend:
        ctx["doNumber"] = existing["do_number"]
        ctx["id"] = existing["id"]
        ctx["reprint"] = False
        ctx["amended"] = True
        ctx["reprintCount"] = existing["reprint_count"]
        conn.execute(
            """UPDATE delivery_orders SET station=?, do_date=?, customer_code=?,
               consignee_name=?, flight_number=?, aircraft_registration=?,
               landed_at=?, expiry_at=?, issued_by=?, pieces=?, weight=?,
               payload=? WHERE id=?""",
            (ctx["station"], ctx["doDate"].isoformat(timespec="seconds"),
             ctx["customerCode"], ctx["consignee"]["name"], ctx["flightNumber"],
             ctx["aircraftRegistration"],
             ctx["landedAt"].isoformat(timespec="minutes") if ctx["landedAt"] else None,
             ctx["expiryAt"].isoformat(timespec="minutes") if ctx["expiryAt"] else None,
             ctx["issuedBy"], ctx["pieces"], ctx["weight"],
             json.dumps(ctx, default=_json_default), existing["id"]))
        return json.loads(json.dumps(ctx, default=_json_default))

    if existing:
        conn.execute(
            "UPDATE delivery_orders SET reprint_count = reprint_count + 1 WHERE id = ?",
            (existing["id"],))
        stored = json.loads(existing["payload"])
        stored["doNumber"] = existing["do_number"]
        stored["reprint"] = True
        stored["reprintCount"] = existing["reprint_count"] + 1
        return stored

    do_number = _next_do_number(conn, number_start)
    do_id = str(uuid.uuid4())
    ctx["doNumber"] = do_number
    ctx["reprint"] = False
    ctx["reprintCount"] = 0
    ctx["id"] = do_id

    conn.execute(
        """INSERT INTO delivery_orders
           (id, do_number, mawb_number, hawb_number, fhl_id, station, do_date,
            customer_code, consignee_name, flight_number, aircraft_registration,
            landed_at, expiry_at, issued_by, pieces, weight, payload,
            created_by, created_at, reprint_count)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
        (do_id, do_number, mawb, ctx["hawbNumber"], fhl_id, ctx["station"],
         ctx["doDate"].isoformat(timespec="seconds"), ctx["customerCode"],
         ctx["consignee"]["name"], ctx["flightNumber"],
         ctx["aircraftRegistration"],
         ctx["landedAt"].isoformat(timespec="minutes") if ctx["landedAt"] else None,
         ctx["expiryAt"].isoformat(timespec="minutes") if ctx["expiryAt"] else None,
         ctx["issuedBy"], ctx["pieces"], ctx["weight"],
         json.dumps(ctx, default=_json_default), user,
         datetime.now().isoformat(timespec="seconds")))
    return json.loads(json.dumps(ctx, default=_json_default))


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    raise TypeError(f"not serialisable: {type(value)}")


def load(conn: sqlite3.Connection, do_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM delivery_orders WHERE id = ? OR do_number = ?",
        (do_id, do_id)).fetchone()
    if not row:
        raise DOError(f"ไม่พบ Delivery Order {do_id}")
    payload = json.loads(row["payload"])
    payload["doNumber"] = row["do_number"]
    payload["id"] = row["id"]
    payload["reprintCount"] = row["reprint_count"]
    return payload


# ------------------------------------------------------------------ render ---

def _esc(value) -> str:
    text = "" if value is None else str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _ctx_dates(ctx: dict) -> tuple:
    """Payloads come back from JSON with ISO strings, fresh ones with datetimes."""
    def coerce(value):
        return value if isinstance(value, datetime) else _parse_iso(value)
    return (coerce(ctx.get("doDate")), coerce(ctx.get("landedAt")),
            coerce(ctx.get("expiryAt")))


def render_html(ctx: dict) -> str:
    do_date, landed, expiry = _ctx_dates(ctx)
    cne = ctx.get("consignee", {})
    address_lines = [line.strip() for line in
                     (cne.get("address") or "").split("/") if line.strip()]
    last_line = " ".join(x for x in [cne.get("postalCode"), cne.get("country")] if x)

    landed_text = fmt_stamp(landed) if landed else ""
    expiry_text = fmt_stamp(expiry) if expiry else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DO {_esc(ctx.get('doNumber'))} — {_esc(ctx.get('hawbNumber'))}</title>
<style>
  @page {{ size: A4; margin: 14mm 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: Arial, Helvetica, "Liberation Sans", sans-serif;
    font-size: 11px; color: #000; margin: 0; background: #f0f2f6;
  }}
  .sheet {{
    width: 210mm; min-height: 297mm; padding: 14mm 12mm; margin: 16px auto;
    background: #fff; box-shadow: 0 2px 14px rgba(0,0,0,.18); position: relative;
  }}
  .toolbar {{
    max-width: 210mm; margin: 16px auto 0; display: flex; gap: 10px;
    align-items: center; font-family: system-ui, sans-serif;
  }}
  .toolbar button {{
    font: inherit; font-size: 13px; font-weight: 600; padding: 9px 18px;
    border-radius: 9px; border: none; cursor: pointer;
    background: linear-gradient(135deg, #e9c46a, #c9a227); color: #081c3f;
  }}
  .toolbar .muted {{ color: #6b7a99; font-size: 12px; }}
  .barcode-box {{ text-align: right; margin-bottom: 26px; }}
  .barcode-box .num {{
    font-size: 11px; letter-spacing: 2px; margin-top: 2px; margin-right: 6px;
  }}
  .head {{ text-align: right; line-height: 1.9; margin-bottom: 26px; }}
  .head .lbl {{ display: inline-block; }}
  .head .val {{ display: inline-block; min-width: 96px; text-align: left; padding-left: 8px; }}
  .to-row {{ margin-bottom: 16px; }}
  .to-row .k {{ display: inline-block; width: 84px; vertical-align: top; }}
  .title {{ text-align: center; margin: 18px 0 20px; }}
  .deliver {{ margin-left: 84px; margin-bottom: 10px; }}
  .cnee {{ margin-bottom: 22px; }}
  .cnee .k {{ display: inline-block; width: 84px; vertical-align: top; }}
  .cnee .v {{ display: inline-block; vertical-align: top; line-height: 1.55; }}
  table.do {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
  table.do th, table.do td {{
    border: 1px solid #000; padding: 5px 6px; vertical-align: top;
  }}
  table.do th {{ text-align: center; font-size: 11px; }}
  table.do td {{ font-size: 11px; height: 42px; }}
  table.do td.c {{ text-align: center; }}
  table.do td.nowrap {{ white-space: nowrap; }}
  .note {{ margin-bottom: 18px; }}
  .note b {{ display: inline-block; width: 56px; vertical-align: top; }}
  .note .body {{ display: inline-block; width: calc(100% - 60px); line-height: 1.9; font-weight: bold; }}
  .expiry, .issued {{ font-weight: bold; margin-bottom: 18px; }}
  .issued span {{ margin-left: 22px; }}
  .sign {{ text-align: right; margin-top: 30px; }}
  .sign .line {{
    display: inline-block; width: 320px; border-bottom: 1px solid #000;
    margin: 46px 0 4px;
  }}
  .footer-note {{ margin-top: 26px; margin-left: 40px; }}
  .reprint {{
    position: absolute; top: 40mm; left: 50%; transform: translateX(-50%) rotate(-24deg);
    font-size: 58px; font-weight: 800; color: rgba(200, 30, 30, .13);
    letter-spacing: 6px; pointer-events: none;
  }}
  @media print {{
    body {{ background: #fff; }}
    .toolbar {{ display: none; }}
    .sheet {{ margin: 0; box-shadow: none; width: auto; min-height: 0; padding: 0; }}
  }}
</style>
</head>
<body>
<div class="toolbar">
  <button onclick="window.print()">🖨 พิมพ์ / บันทึกเป็น PDF</button>
  <span class="muted">DO {_esc(ctx.get('doNumber'))} · HAWB {_esc(ctx.get('hawbNumber'))}
    {'· พิมพ์ซ้ำครั้งที่ ' + str(ctx.get('reprintCount')) if ctx.get('reprintCount') else ''}</span>
</div>

<div class="sheet">
  {'<div class="reprint">REPRINT</div>' if ctx.get("reprintCount") else ''}

  <div class="barcode-box">
    {code39_svg(ctx.get('hawbNumber') or '')}
    <div class="num">{_esc(ctx.get('hawbNumber'))}</div>
  </div>

  <div class="head">
    <div><span class="lbl">DO Number :</span><span class="val">{_esc(ctx.get('doNumber'))}</span></div>
    <div><span class="lbl">Station :</span><span class="val">{_esc(ctx.get('station'))}</span></div>
    <div><span class="lbl">DO Date :</span><span class="val">{_esc(fmt_do_date(do_date))}</span></div>
    <div><span class="lbl">CUSTOMER CODE:</span><span class="val">{_esc(ctx.get('customerCode'))}</span></div>
  </div>

  <div class="to-row"><span class="k">TO</span>H.M.CUSTOMS,</div>
  <div class="to-row">DEAR SIRS,</div>

  <div class="title">DELIVERY ORDER(CUSTOMS MANIFESTATION)</div>

  <div class="deliver">PLEASE DELIVER TO :</div>
  <div class="cnee">
    <span class="k">CNEE :</span><span class="v">{_esc(cne.get('name'))}<br>
      {'<br>'.join(_esc(line) for line in address_lines)}{'<br>' if address_lines else ''}
      {_esc(last_line)}</span>
  </div>

  <table class="do">
    <thead><tr>
      <th style="width:24%">Air Waybill No</th>
      <th style="width:5%">SHC</th>
      <th style="width:9%">Pieces</th>
      <th style="width:11%">Weight</th>
      <th style="width:6%">Brd.<br>Pnt</th>
      <th style="width:6%">Off.<br>Pnt</th>
      <th style="width:9%">Flight No</th>
      <th style="width:16%">Landed on<br>Date/ATA</th>
      <th style="width:14%">Nature of Goods</th>
    </tr></thead>
    <tbody><tr>
      <td>MAWB {_esc(ctx.get('mawbPlain'))}/<br>HAWB {_esc(ctx.get('hawbNumber'))}</td>
      <td class="c">{_esc(ctx.get('shc'))}</td>
      <td class="c">{_esc(ctx.get('pieces'))} of {_esc(ctx.get('masterPieces'))}</td>
      <td class="c">{_esc(fmt_weight(ctx.get('weight')))} of {_esc(fmt_weight(ctx.get('masterWeight')))}{_esc(ctx.get('weightUnit'))}</td>
      <td class="c">{_esc(ctx.get('boardPoint'))}</td>
      <td class="c">{_esc(ctx.get('offPoint'))}</td>
      <td>{_esc(ctx.get('flightNumber'))}<br>{_esc(ctx.get('aircraftRegistration'))}</td>
      <td class="c nowrap">{_esc(landed_text)}</td>
      <td class="c">{_esc(ctx.get('natureOfGoods'))}</td>
    </tr></tbody>
  </table>

  <div class="note"><b>Note:</b><span class="body">In case the above details are
    incorrect, please contact {_esc(ctx.get('carrierCode'))} office for amendment
    within 48 hours after flight arrival to avoid customs penalty, otherwise
    {_esc(ctx.get('carrierCode'))} will not be responsible for any expenses
    incurred.</span></div>

  <div class="expiry">Date and time of expiry (48 hours) : {_esc(expiry_text)}</div>
  <div class="issued">Issued By:<span>{_esc(ctx.get('issuedBy'))}</span></div>

  <div class="sign">
    Yours faithfully,
    <div><span class="line"></span></div>
    <div>{_esc(ctx.get('carrierName'))}.</div>
  </div>

  <div class="footer-note">*** Note:Import Cargo Charges as per
    {_esc(ctx.get('terminalName'))}'s Announcement.</div>
</div>
</body>
</html>"""


def render_pdf(ctx: dict) -> bytes:
    """Same layout drawn straight to A4 with ReportLab."""
    import io

    from reportlab.graphics.barcode import code39
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    do_date, landed, expiry = _ctx_dates(ctx)
    cne = ctx.get("consignee", {})
    width, height = A4
    left, right = 12 * mm, width - 12 * mm

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"DO {ctx.get('doNumber')} - {ctx.get('hawbNumber')}")

    y = height - 20 * mm

    # barcode, right aligned
    bc = code39.Standard39(str(ctx.get("hawbNumber") or ""), barHeight=13 * mm,
                           barWidth=0.5 * mm, checksum=0, quiet=0)
    bc.drawOn(c, right - bc.width, y - 13 * mm)
    c.setFont("Helvetica", 8)
    c.drawRightString(right - 2, y - 18 * mm, str(ctx.get("hawbNumber") or ""))
    y -= 30 * mm

    # header block
    c.setFont("Helvetica", 9)
    for label, value in (("DO Number :", ctx.get("doNumber")),
                         ("Station :", ctx.get("station")),
                         ("DO Date :", fmt_do_date(do_date)),
                         ("CUSTOMER CODE:", ctx.get("customerCode"))):
        c.drawRightString(right - 42 * mm, y, label)
        c.drawString(right - 40 * mm, y, str(value or ""))
        y -= 5.5 * mm
    y -= 6 * mm

    c.drawString(left, y, "TO"); c.drawString(left + 26 * mm, y, "H.M.CUSTOMS,")
    y -= 8 * mm
    c.drawString(left, y, "DEAR SIRS,")
    y -= 10 * mm
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, y, "DELIVERY ORDER(CUSTOMS MANIFESTATION)")
    y -= 9 * mm
    c.drawString(left + 26 * mm, y, "PLEASE DELIVER TO :")
    y -= 7 * mm

    c.drawString(left, y, "CNEE :")
    text_y = y
    c.drawString(left + 26 * mm, text_y, str(cne.get("name") or ""))
    for line in [x.strip() for x in (cne.get("address") or "").split("/") if x.strip()]:
        text_y -= 4.6 * mm
        c.drawString(left + 26 * mm, text_y, line)
    tail = " ".join(x for x in [cne.get("postalCode"), cne.get("country")] if x)
    if tail:
        text_y -= 4.6 * mm
        c.drawString(left + 26 * mm, text_y, tail)
    y = text_y - 10 * mm

    # table
    cols = [24, 5, 9, 11, 6, 6, 9, 15, 15]
    total = sum(cols)
    usable = right - left
    xs, acc = [left], left
    for share in cols:
        acc += usable * share / total
        xs.append(acc)
    head_h, row_h = 9 * mm, 11 * mm
    top = y

    c.setLineWidth(0.7)
    c.rect(left, top - head_h - row_h, usable, head_h + row_h)
    c.line(left, top - head_h, right, top - head_h)
    for x in xs[1:-1]:
        c.line(x, top - head_h - row_h, x, top)

    c.setFont("Helvetica-Bold", 7.5)
    headers = ["Air Waybill No", "SHC", "Pieces", "Weight", "Brd.|Pnt",
               "Off.|Pnt", "Flight No", "Landed on|Date/ATA", "Nature of Goods"]
    for i, title in enumerate(headers):
        cx = (xs[i] + xs[i + 1]) / 2
        parts = title.split("|")
        ty = top - 4 * mm if len(parts) == 1 else top - 3 * mm
        for part in parts:
            c.drawCentredString(cx, ty, part)
            ty -= 3.4 * mm

    c.setFont("Helvetica", 7.5)
    body_top = top - head_h - 4 * mm
    c.drawString(xs[0] + 1.5 * mm, body_top, f"MAWB {ctx.get('mawbPlain')}/")
    c.drawString(xs[0] + 1.5 * mm, body_top - 3.6 * mm,
                 f"HAWB {ctx.get('hawbNumber')}")
    centred = [
        (1, str(ctx.get("shc") or "")),
        (2, f"{ctx.get('pieces')} of {ctx.get('masterPieces')}"),
        (3, f"{fmt_weight(ctx.get('weight'))} of "
            f"{fmt_weight(ctx.get('masterWeight'))}{ctx.get('weightUnit') or ''}"),
        (4, str(ctx.get("boardPoint") or "")),
        (5, str(ctx.get("offPoint") or "")),
        (7, fmt_stamp(landed) if landed else ""),
        (8, str(ctx.get("natureOfGoods") or "")),
    ]
    for i, value in centred:
        c.drawCentredString((xs[i] + xs[i + 1]) / 2, body_top, value)
    c.drawString(xs[6] + 1.5 * mm, body_top, str(ctx.get("flightNumber") or ""))
    c.drawString(xs[6] + 1.5 * mm, body_top - 3.6 * mm,
                 str(ctx.get("aircraftRegistration") or ""))

    y = top - head_h - row_h - 12 * mm

    carrier = ctx.get("carrierCode") or "the carrier"
    c.setFont("Helvetica-Bold", 8)
    c.drawString(left, y, "Note:")
    for line in (f"In case the above details are incorrect, please contact {carrier} "
                 "office for amendment within 48 hours",
                 f"after flight arrival to avoid customs penalty, otherwise {carrier} "
                 "will not be responsible for any expenses",
                 "incurred."):
        c.drawString(left + 16 * mm, y, line)
        y -= 5.5 * mm
    y -= 5 * mm

    c.drawString(left, y, "Date and time of expiry (48 hours) : "
                          f"{fmt_stamp(expiry) if expiry else ''}")
    y -= 9 * mm
    c.drawString(left, y, "Issued By:")
    c.drawString(left + 22 * mm, y, str(ctx.get("issuedBy") or ""))
    y -= 14 * mm

    c.setFont("Helvetica", 9)
    c.drawRightString(right - 30 * mm, y, "Yours faithfully,")
    y -= 26 * mm
    c.setLineWidth(0.5)
    c.line(right - 84 * mm, y, right, y)
    y -= 5 * mm
    c.drawRightString(right, y, str(ctx.get("carrierName") or "") + ".")
    y -= 12 * mm
    c.setFont("Helvetica", 8)
    c.drawString(left + 10 * mm, y, "*** Note:Import Cargo Charges as per "
                 f"{ctx.get('terminalName')}'s Announcement.")

    if ctx.get("reprintCount"):
        c.saveState()
        c.setFont("Helvetica-Bold", 54)
        c.setFillColorRGB(0.78, 0.12, 0.12, 0.12)
        c.translate(width / 2, height / 2)
        c.rotate(24)
        c.drawCentredString(0, 0, "REPRINT")
        c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()
