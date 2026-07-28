"""Configurable matching rules (FR-010, FR-012) stored in app_settings."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from ..matching.engine import MatchingConfig

# key -> (type, default, label)
SETTING_DEFS: dict[str, tuple[str, object, str]] = {
    "weight_tolerance_abs": ("decimal", "0.5",
                             "Weight tolerance — absolute (KG)"),
    "weight_tolerance_pct": ("decimal", "0.5",
                             "Weight tolerance — percentage (%)"),
    "score_mawb": ("int", 50, "Score — MAWB match"),
    "score_origin": ("int", 10, "Score — origin match"),
    "score_destination": ("int", 10, "Score — destination match"),
    "score_pieces": ("int", 15, "Score — pieces match"),
    "score_weight": ("int", 15, "Score — weight exact match"),
    "score_weight_tolerance": ("int", 10, "Score — weight within tolerance"),
    "pieces_severity": ("severity", "WARNING", "Severity — PIECES_MATCH"),
    "weight_severity": ("severity", "WARNING", "Severity — WEIGHT_MATCH"),
    "supported_fwb_versions": ("csv", "16", "Supported FWB versions"),
    "supported_fhl_versions": ("csv", "4", "Supported FHL versions"),
    "max_file_size_kb": ("int", 2048, "Maximum upload size per file (KB)"),
}

SEVERITIES = ("ERROR", "WARNING", "INFO")


class SettingError(ValueError):
    pass


def get_all(conn: sqlite3.Connection) -> dict[str, object]:
    stored = {r["key"]: r["value"] for r in
              conn.execute("SELECT key, value FROM app_settings")}
    out: dict[str, object] = {}
    for key, (kind, default, _label) in SETTING_DEFS.items():
        out[key] = _coerce(kind, stored.get(key, default))
    return out


def describe(conn: sqlite3.Connection) -> list[dict]:
    values = get_all(conn)
    return [{"key": key, "type": kind, "label": label,
             "value": values[key], "default": _coerce(kind, default)}
            for key, (kind, default, label) in SETTING_DEFS.items()]


def update(conn: sqlite3.Connection, changes: dict, user: str) -> dict:
    """Validate and persist changes; returns {key: (before, after)}."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    before = get_all(conn)
    applied: dict[str, tuple] = {}
    for key, raw in changes.items():
        if key not in SETTING_DEFS:
            raise SettingError(f"unknown setting: {key}")
        kind = SETTING_DEFS[key][0]
        value = _validate(key, kind, raw)
        conn.execute(
            """INSERT INTO app_settings (key, value, updated_at, updated_by)
               VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value, updated_at=excluded.updated_at,
                 updated_by=excluded.updated_by""",
            (key, str(value), ts, user))
        applied[key] = (before[key], _coerce(kind, value))
    return applied


def _validate(key: str, kind: str, raw) -> str:
    text = str(raw).strip()
    if kind == "decimal":
        try:
            value = Decimal(text)
        except InvalidOperation:
            raise SettingError(f"{key} must be a number")
        if value < 0:
            raise SettingError(f"{key} must not be negative")
        return text
    if kind == "int":
        if not text.lstrip("-").isdigit():
            raise SettingError(f"{key} must be an integer")
        if int(text) < 0:
            raise SettingError(f"{key} must not be negative")
        return text
    if kind == "severity":
        if text.upper() not in SEVERITIES:
            raise SettingError(f"{key} must be one of {', '.join(SEVERITIES)}")
        return text.upper()
    if kind == "csv":
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if not parts:
            raise SettingError(f"{key} must list at least one value")
        return ",".join(parts)
    raise SettingError(f"unsupported setting type: {kind}")


def _coerce(kind: str, value):
    if kind == "decimal":
        return float(Decimal(str(value)))
    if kind == "int":
        return int(value)
    if kind == "csv":
        return [p.strip() for p in str(value).split(",") if p.strip()]
    return str(value)


def matching_config(conn: sqlite3.Connection) -> MatchingConfig:
    s = get_all(conn)
    return MatchingConfig(
        weight_tolerance_abs=Decimal(str(s["weight_tolerance_abs"])),
        weight_tolerance_pct=Decimal(str(s["weight_tolerance_pct"])),
        score_mawb=s["score_mawb"],
        score_origin=s["score_origin"],
        score_destination=s["score_destination"],
        score_pieces=s["score_pieces"],
        score_weight=s["score_weight"],
        score_weight_tolerance=s["score_weight_tolerance"],
        pieces_severity=s["pieces_severity"],
        weight_severity=s["weight_severity"],
        supported_fwb_versions=list(s["supported_fwb_versions"]),
        supported_fhl_versions=list(s["supported_fhl_versions"]),
    )
