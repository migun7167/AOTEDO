"""FHL/4 (House Air Waybill) parser."""
from __future__ import annotations

import re

from .base import ParseError, normalize_airport, normalize_mawb, to_decimal
from .segmenter import FHL_SEGMENT_KEYS, party_lines, split_segments

# MBI/217-08722685HKGBKK/T1K149.0
MBI_RE = re.compile(
    r"(\d{3})-?(\d{8})\s*([A-Z]{3})([A-Z]{3})/T(\d+)([KL])([\d.]+)"
)
# HBS/WM26070003/HKGBKK/1/K149.0//DRY BATTERY
HBS_RE = re.compile(
    r"([A-Z0-9]+)/([A-Z]{3})([A-Z]{3})/(\d+)/([KL])([\d.]+)(?:/(\d*))?(?:/(.*))?$"
)


def parse(raw: str) -> dict:
    header, segments = split_segments(raw, FHL_SEGMENT_KEYS)
    m = re.match(r"FHL/(\d+)", header)
    if not m:
        raise ParseError("INVALID_HEADER", "Missing FHL header line", "FHL", header)

    data: dict = {"messageType": "FHL", "version": m.group(1)}

    for key, content in segments:
        if key == "MBI":
            mm = MBI_RE.search(content)
            if not mm:
                raise ParseError("INVALID_MBI_SEGMENT",
                                 "Unable to parse MBI segment", "MBI", content)
            data["mawbNumber"] = normalize_mawb(f"{mm.group(1)}{mm.group(2)}")
            data["masterOrigin"] = normalize_airport(mm.group(3))
            data["masterDestination"] = normalize_airport(mm.group(4))
            data["masterPieces"] = int(mm.group(5))
            data["masterWeightUnit"] = mm.group(6)
            data["masterWeight"] = to_decimal(mm.group(7))
        elif key == "HBS":
            hm = HBS_RE.match(content.lstrip("/"))
            if not hm:
                raise ParseError("INVALID_HBS_SEGMENT",
                                 "Unable to parse HBS segment", "HBS", content)
            data["hawbNumber"] = hm.group(1)
            data["origin"] = normalize_airport(hm.group(2))
            data["destination"] = normalize_airport(hm.group(3))
            data["pieces"] = int(hm.group(4))
            data["weightUnit"] = hm.group(5)
            data["weight"] = to_decimal(hm.group(6))
            data["slac"] = hm.group(7) or None
            data["commodity"] = (hm.group(8) or "").strip() or None
        elif key == "HTS":
            data["hsCode"] = content.lstrip("/").split("/")[0].strip()
        elif key == "OCI":
            parts = content.lstrip("/").split("/")
            oci = {
                "country": parts[0] if parts else None,
                "partyType": parts[1] if len(parts) > 1 else None,
                "infoType": parts[2] if len(parts) > 2 else None,
                "value": parts[3] if len(parts) > 3 else None,
            }
            data["oci"] = oci
            if oci["value"]:
                tid = re.search(r"(\d{5,})", oci["value"])
                if tid:
                    data["consigneeTaxId"] = tid.group(1)
        elif key == "SHP":
            data["shipper"] = _party(party_lines(content))
        elif key == "CNE":
            data["consignee"] = _party(party_lines(content))

    if "mawbNumber" not in data:
        raise ParseError("MISSING_MAWB", "FHL has no MBI/MAWB reference", "MBI")
    if "hawbNumber" not in data:
        raise ParseError("MISSING_HAWB", "FHL has no HBS/HAWB", "HBS")
    return data


def _party(lines: list[str]) -> dict:
    """lines: [name, addr..., city, CC(/postal)(/TE/phone)]"""
    name = lines[0] if lines else None
    country = postal = phone = None
    rest = lines[1:]
    if rest:
        tail = rest[-1]
        tm = re.match(r"^([A-Z]{2})(?:/([A-Z0-9]+))?(?:/TE/(\S+))?$", tail)
        if tm:
            country, postal, phone = tm.group(1), tm.group(2), tm.group(3)
            rest = rest[:-1]
    return {
        "name": name,
        "address": " / ".join(rest) if rest else None,
        "country": country,
        "postalCode": postal,
        "phone": phone,
    }
