"""Parser registry — add new (type, version) parsers here without touching old ones."""
from __future__ import annotations

from . import ffm, fhl_v4, fsu, fwb_v16
from .base import ParseError
from .detector import detect

PARSER_REGISTRY = {
    ("FWB", "16"): fwb_v16.parse,
    ("FHL", "4"): fhl_v4.parse,
    ("FFM", "16"): ffm.parse,
    ("FSU", "16"): fsu.parse,
}


def parse_message(raw: str) -> dict:
    """Detect type/version and run the matching parser."""
    msg_type, version = detect(raw)
    parser = PARSER_REGISTRY.get((msg_type, version))
    if parser is None:
        # fall back to any parser of the same type (forward compatible)
        for (t, _v), fn in PARSER_REGISTRY.items():
            if t == msg_type:
                parser = fn
                break
    if parser is None:
        raise ParseError("UNSUPPORTED_VERSION",
                         f"No parser for {msg_type}/{version}")
    return parser(raw)


__all__ = ["parse_message", "detect", "ParseError", "PARSER_REGISTRY"]
