"""FSU (Status Update) parser — one file may contain several FSU lines."""
from __future__ import annotations

import re

from .base import ParseError, normalize_mawb, to_decimal

# FSU/16 RCS 217-08722685HKG 16JUL26 TG601 K149.0
# FSU/16 NFD 217-08722685BKK WM26070003 16JUL26
LINE_RE = re.compile(
    r"FSU/(\d+)\s+([A-Z]{3})\s+(\d{3})-?(\d{8})([A-Z]{3})\s+(.*)$"
)
# Date, plus the HHMM that carriers append to movement events when they have
# it (e.g. "16JUL26 1435" or "16JUL26/1435"). A Delivery Order needs that time
# for the ATA and the 48-hour expiry, so capture it when present.
DATE_RE = re.compile(r"\b(\d{1,2}[A-Z]{3}\d{2})\b(?:[/ ]([0-2]\d[0-5]\d)\b)?")
FLIGHT_RE = re.compile(r"\b([A-Z]{2}\d{2,4}[A-Z]?)\b")
WEIGHT_RE = re.compile(r"\b([KL])([\d.]+)\b")
HAWB_RE = re.compile(r"\b([A-Z]{2,3}\d{6,})\b")


def parse(raw: str) -> dict:
    events = []
    version = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        version = version or m.group(1)
        rest = m.group(6)
        ev: dict = {
            "statusCode": m.group(2),
            "mawbNumber": normalize_mawb(f"{m.group(3)}{m.group(4)}"),
            "airport": m.group(5),
            "rawLine": line,
        }
        d = DATE_RE.search(rest)
        if d:
            ev["date"] = d.group(1)
            if d.group(2):
                ev["time"] = d.group(2)
        f = FLIGHT_RE.search(rest)
        if f:
            ev["flightNumber"] = f.group(1)
        w = WEIGHT_RE.search(rest)
        if w:
            ev["weightUnit"] = w.group(1)
            ev["weight"] = to_decimal(w.group(2))
        h = HAWB_RE.search(rest)
        if h and (not f or h.group(1) != f.group(1)):
            ev["hawbNumber"] = h.group(1)
        events.append(ev)
    if not events:
        raise ParseError("INVALID_HEADER", "No parsable FSU status lines found", "FSU")
    return {"messageType": "FSU", "version": version, "events": events}
