"""Segment splitter for Cargo-IMP messages.

Handles both canonical format (one segment per line, continuation lines
starting with "/") and word-wrapped exports where segments are separated
only by whitespace. Both are normalized to a single-space-joined string,
then split at segment keywords that are preceded by whitespace.
"""
from __future__ import annotations

import re

FWB_SEGMENT_KEYS = [
    "FLT", "RTG", "SHP", "CNE", "AGT", "SSR", "NFY", "ACC", "CVD", "RTD",
    "OTH", "PPD", "COL", "CER", "ISU", "OSI", "REF", "SPH", "NOM", "COR",
]
FHL_SEGMENT_KEYS = [
    "MBI", "HBS", "HTS", "OCI", "SHP", "CNE", "CVD", "RTD", "SSR", "NFY", "TXT",
]


def normalize(raw: str) -> str:
    """Collapse all whitespace (incl. line breaks) into single spaces."""
    return re.sub(r"\s+", " ", raw.replace("=", " ")).strip()


def split_segments(raw: str, keys: list[str]) -> tuple[str, list[tuple[str, str]]]:
    """Split a message into (header, [(segment_key, content), ...]).

    A segment starts at a keyword preceded by whitespace (or start of string)
    and followed by "/" or whitespace. Keywords embedded inside other tokens
    (e.g. the party code CNE inside "OCI/TH/CNE/T/...") are not split because
    they are preceded by "/" rather than whitespace.
    """
    text = normalize(raw)
    pattern = re.compile(
        r"(?:(?<=\s)|^)(" + "|".join(keys) + r")(?=/|\s|$)"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return text, []
    header = text[: matches[0].start()].strip()
    segments: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = m.group(1)
        content = text[m.end(): end].strip()
        segments.append((key, content))
    return header, segments


def party_lines(content: str) -> list[str]:
    """Split a party segment (SHP/CNE/AGT) content into its "/" lines.

    Content looks like "/NAME /ADDR1 /CITY /CC" or "NAME /ADDR1 /CITY /CC/POST".
    """
    content = content.strip()
    if content.startswith("/"):
        content = content[1:]
    return [p.strip() for p in re.split(r"\s+/", content) if p.strip()]
