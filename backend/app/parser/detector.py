"""Message type/version detection from the first token of a message."""
from __future__ import annotations

import re

from .base import ParseError

SUPPORTED_TYPES = {"FWB", "FHL", "FFM", "FSU"}

HEAD_RE = re.compile(r"^\s*(FWB|FHL|FFM|FSU)/(\d+)", re.IGNORECASE)


def detect(raw: str) -> tuple[str, str]:
    """Return (message_type, version) or raise ParseError."""
    if not raw or not raw.strip():
        raise ParseError("EMPTY_FILE", "File is empty")
    m = HEAD_RE.match(raw.strip())
    if not m:
        raise ParseError(
            "UNSUPPORTED_MESSAGE_TYPE",
            "Message does not start with a supported type (FWB/FHL/FFM/FSU)",
        )
    return m.group(1).upper(), m.group(2)
