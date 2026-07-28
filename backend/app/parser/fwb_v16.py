"""FWB/16 (Master Air Waybill) parser."""
from __future__ import annotations

import re

from .base import ParseError, normalize_airport, normalize_mawb, to_decimal
from .segmenter import FWB_SEGMENT_KEYS, party_lines, split_segments

# e.g. "217-08722685HKGBKK/T1K149.0"
HEADER_RE = re.compile(
    r"(\d{3})-?(\d{8})\s*([A-Z]{3})([A-Z]{3})/T(\d+)([KL])([\d.]+)"
)


def parse(raw: str) -> dict:
    header, segments = split_segments(raw, FWB_SEGMENT_KEYS)

    m = re.match(r"FWB/(\d+)\s+(.*)$", header)
    if not m:
        raise ParseError("INVALID_HEADER", "Missing FWB header line", "FWB", header)
    version = m.group(1)

    hm = HEADER_RE.search(m.group(2))
    if not hm:
        raise ParseError("INVALID_HEADER",
                         "Unable to parse AWB consignment line", "FWB", m.group(2))
    prefix, serial = hm.group(1), hm.group(2)
    data: dict = {
        "messageType": "FWB",
        "version": version,
        "mawbNumber": normalize_mawb(f"{prefix}{serial}"),
        "airlinePrefix": prefix,
        "serialNumber": serial,
        "origin": normalize_airport(hm.group(3)),
        "destination": normalize_airport(hm.group(4)),
        "pieces": int(hm.group(5)),
        "weightUnit": hm.group(6),
        "weight": to_decimal(hm.group(7)),
    }

    for key, content in segments:
        if key == "FLT":
            parts = content.lstrip("/").split("/")
            data["flightNumber"] = parts[0] if parts else None
            data["flightDate"] = parts[1] if len(parts) > 1 else None
        elif key == "RTG":
            data["routing"] = content.lstrip("/")
        elif key == "SHP":
            lines = party_lines(content)
            data["shipper"] = _party(lines)
        elif key == "CNE":
            lines = party_lines(content)
            data["consignee"] = _party(lines)
        elif key == "AGT":
            body = content.lstrip("/")
            lines = [p.strip() for p in re.split(r"\s+/", body) if p.strip()]
            code = lines[0].lstrip("/") if lines else None
            data["agent"] = {
                "code": code,
                "name": lines[1] if len(lines) > 1 else None,
                "place": lines[2] if len(lines) > 2 else None,
            }
        elif key == "CVD":
            parts = content.lstrip("/").split("/")
            data["chargeDeclaration"] = {
                "currency": parts[0] if parts else None,
                "chargeCode": parts[1] if len(parts) > 1 else None,
                "weightValuationPayment": parts[2] if len(parts) > 2 else None,
                "declaredValueCarriage": parts[3] if len(parts) > 3 else None,
                "declaredValueCustoms": parts[4] if len(parts) > 4 else None,
                "amountOfInsurance": parts[5] if len(parts) > 5 else None,
            }
        elif key == "RTD":
            data["rateDescription"] = _parse_rtd(content)
        elif key == "OTH":
            data["otherCharges"] = content.lstrip("/")
        elif key == "PPD":
            data["prepaid"] = _parse_charges(content)
        elif key == "COL":
            data["collect"] = _parse_charges(content)
        elif key == "ISU":
            parts = content.lstrip("/").split("/")
            data["issueDate"] = parts[0] if parts else None
            data["issuePlace"] = parts[1] if len(parts) > 1 else None
        elif key == "REF":
            data["reference"] = content.lstrip("/")
        elif key == "SPH":
            data["specialHandlingCodes"] = [
                c for c in content.lstrip("/").split("/") if c
            ]

    rtd = data.get("rateDescription") or {}
    if rtd.get("natureOfGoods"):
        data["natureOfGoods"] = rtd["natureOfGoods"]
    if rtd.get("chargeableWeight") is not None:
        data["chargeableWeight"] = rtd["chargeableWeight"]
    if rtd.get("rate") is not None:
        data["rate"] = rtd["rate"]
    if rtd.get("total") is not None:
        data["freightCharge"] = rtd["total"]
    return data


def _party(lines: list[str]) -> dict:
    """lines: [name, addr..., city?, country(/postal)]"""
    name = lines[0] if lines else None
    country = None
    postal = None
    rest = lines[1:]
    if rest:
        tail = rest[-1]
        tm = re.match(r"^([A-Z]{2})(?:/(\S+))?$", tail)
        if tm:
            country, postal = tm.group(1), tm.group(2)
            rest = rest[:-1]
    return {
        "name": name,
        "address": " / ".join(rest) if rest else None,
        "country": country,
        "postalCode": postal,
    }


def _parse_rtd(content: str) -> dict:
    """RTD/1/P1/K149.0/CQ/W149.0/R10.76/T1603.240 /NG/CONSOL ..."""
    out: dict = {}
    ng = re.search(r"/NG/([^/]+?)(?:\s+/|$)", content)
    if ng:
        out["natureOfGoods"] = ng.group(1).strip()
    p = re.search(r"/P(\d+)", content)
    if p:
        out["pieces"] = int(p.group(1))
    w = re.search(r"/([KL])([\d.]+)/", content)
    if w:
        out["grossWeight"] = to_decimal(w.group(2))
        out["weightUnit"] = w.group(1)
    cw = re.search(r"/W([\d.]+)", content)
    if cw:
        out["chargeableWeight"] = to_decimal(cw.group(1))
    r = re.search(r"/R([\d.]+)", content)
    if r:
        out["rate"] = to_decimal(r.group(1))
    t = re.search(r"/T([\d.]+)", content)
    if t:
        out["total"] = to_decimal(t.group(1))
    return out


def _parse_charges(content: str) -> dict:
    """PPD/WT1603.24 /OC486.9/CT2090.14"""
    out: dict = {}
    wt = re.search(r"WT([\d.]+)", content)
    if wt:
        out["weightCharge"] = to_decimal(wt.group(1))
    oc = re.search(r"OC([\d.]+)", content)
    if oc:
        out["otherCharge"] = to_decimal(oc.group(1))
    ct = re.search(r"CT([\d.]+)", content)
    if ct:
        out["totalCharge"] = to_decimal(ct.group(1))
    return out
