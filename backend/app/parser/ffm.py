"""FFM (Flight Manifest) parser — lightweight support for analysis views."""
from __future__ import annotations

import re

from .base import ParseError, normalize_mawb, to_decimal
from .segmenter import normalize

# FFM/16 1/TG601/16JUL/HKG/BKK M/217-08722685/HKG/BKK/T1K149.0 ...
FLIGHT_RE = re.compile(r"FFM/(\d+)\s+\d+/([A-Z0-9]+)/(\w+)/([A-Z]{3})/([A-Z]{3})")
AWB_RE = re.compile(r"\bM/(\d{3})-?(\d{8})/([A-Z]{3})/([A-Z]{3})/T(\d+)([KL])([\d.]+)")


def parse(raw: str) -> dict:
    text = normalize(raw)
    fm = FLIGHT_RE.search(text)
    if not fm:
        raise ParseError("INVALID_HEADER", "Unable to parse FFM flight line", "FFM")
    data: dict = {
        "messageType": "FFM",
        "version": fm.group(1),
        "flightNumber": fm.group(2),
        "flightDate": fm.group(3),
        "origin": fm.group(4),
        "destination": fm.group(5),
        "consignments": [],
    }
    for am in AWB_RE.finditer(text):
        data["consignments"].append({
            "mawbNumber": normalize_mawb(f"{am.group(1)}{am.group(2)}"),
            "origin": am.group(3),
            "destination": am.group(4),
            "pieces": int(am.group(5)),
            "weightUnit": am.group(6),
            "weight": to_decimal(am.group(7)),
        })
    ng = re.search(r"/NG/([A-Z0-9 ]+?)(?:\s+/|$)", text)
    if ng and data["consignments"]:
        data["consignments"][-1]["natureOfGoods"] = ng.group(1).strip()
    return data
