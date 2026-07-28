"""Parser base types and shared normalization helpers."""
from __future__ import annotations

import re


class ParseError(Exception):
    def __init__(self, code: str, message: str, segment: str | None = None,
                 raw_value: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.segment = segment
        self.raw_value = raw_value

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "segment": self.segment,
            "rawValue": self.raw_value,
            "severity": "ERROR",
        }


MAWB_RE = re.compile(r"^(\d{3})[\s-]?(\d{8})$")


def normalize_mawb(value: str) -> str:
    """Normalize any accepted MAWB input to the canonical 999-99999999 form."""
    value = value.strip().replace(" ", "")
    m = MAWB_RE.match(value.replace("-", ""))
    if not m:
        raise ParseError("INVALID_MAWB", f"Invalid MAWB number: {value}")
    return f"{m.group(1)}-{m.group(2)}"


def normalize_airport(code: str) -> str:
    code = code.strip().upper()
    if not re.match(r"^[A-Z]{3}$", code):
        raise ParseError("INVALID_ORIGIN", f"Invalid airport code: {code}")
    return code


def to_decimal(value: str) -> float:
    return float(value.replace(",", ""))
