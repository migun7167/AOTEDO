"""FWB–FHL matching engine (design doc §10, FR-008..FR-012).

Scoring and tolerances are configuration, not constants: the values here are
only the defaults used when no MatchingConfig is supplied. The running system
reads them from app_settings via services.settings_service.matching_config().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable


@dataclass
class MatchingConfig:
    weight_tolerance_abs: Decimal = Decimal("0.5")
    weight_tolerance_pct: Decimal = Decimal("0.5")
    score_mawb: int = 50
    score_origin: int = 10
    score_destination: int = 10
    score_pieces: int = 15
    score_weight: int = 15
    score_weight_tolerance: int = 10
    pieces_severity: str = "WARNING"
    weight_severity: str = "WARNING"
    supported_fwb_versions: list[str] = field(default_factory=lambda: ["16"])
    supported_fhl_versions: list[str] = field(default_factory=lambda: ["4"])


DEFAULT_CONFIG = MatchingConfig()

# Failing one of these makes the two messages structurally incomparable, so the
# result is rejected outright rather than scored. A route mismatch is NOT one of
# them: the pieces and weights still mean something, so it stays a partial match
# for a human to judge.
BLOCKING_RULES = ("WEIGHT_UNIT_MATCH", "HAWB_PRESENT", "MASTER_PRESENT")


def match_fwb_fhl(
    fwb: Any,
    fhl_list: Iterable[Any],
    config: MatchingConfig | None = None,
) -> dict:
    """fwb / fhl items are dict-like rows with keys:
    mawb_number, origin, destination, pieces, gross_weight, weight_unit,
    message_version, and hawb_number (FHL only).
    """
    cfg = config or DEFAULT_CONFIG
    fhl_list = list(fhl_list)

    if fwb is None:
        return {
            "status": "WAITING_FOR_FWB",
            "score": 0,
            "fhl_count": len(fhl_list),
            "fhl_total_pieces": sum(x["pieces"] or 0 for x in fhl_list),
            "fhl_total_weight": float(sum(
                Decimal(str(x["gross_weight"] or 0)) for x in fhl_list)),
            "validations": [],
        }

    if not fhl_list:
        return {
            "status": "WAITING_FOR_FHL",
            "score": cfg.score_mawb,
            "fhl_count": 0,
            "fwb_pieces": fwb["pieces"],
            "fwb_weight": fwb["gross_weight"],
            "validations": [],
        }

    total_pieces = sum(x["pieces"] or 0 for x in fhl_list)
    total_weight = sum(Decimal(str(x["gross_weight"] or 0)) for x in fhl_list)
    fwb_weight = Decimal(str(fwb["gross_weight"] or 0))

    origin_match = all(x["origin"] == fwb["origin"] for x in fhl_list)
    destination_match = all(
        x["destination"] == fwb["destination"] for x in fhl_list)
    pieces_match = total_pieces == (fwb["pieces"] or 0)

    weight_difference = abs(fwb_weight - total_weight)
    weight_percentage = (
        weight_difference / fwb_weight * 100 if fwb_weight else Decimal("0"))
    weight_exact = weight_difference == 0
    weight_tol = (weight_difference <= cfg.weight_tolerance_abs
                  or weight_percentage <= cfg.weight_tolerance_pct)

    hawbs = [x["hawb_number"] for x in fhl_list]
    duplicate_hawb = len(set(hawbs)) != len(hawbs)

    fwb_unit = fwb["weight_unit"]
    unit_match = all(x["weight_unit"] == fwb_unit for x in fhl_list)
    hawb_present = all(x["hawb_number"] for x in fhl_list)
    master_present = all(x["mawb_number"] for x in fhl_list)
    version_supported = _version_supported(fwb, fhl_list, cfg)

    score = cfg.score_mawb
    if origin_match:
        score += cfg.score_origin
    if destination_match:
        score += cfg.score_destination
    if pieces_match:
        score += cfg.score_pieces
    if weight_exact:
        score += cfg.score_weight
    elif weight_tol:
        score += cfg.score_weight_tolerance

    # Normally guaranteed by the query, but a manually linked house (FR-014)
    # can carry a different MAWB — report that honestly instead of assuming.
    mawb_match = all(x["mawb_number"] == fwb["mawb_number"] for x in fhl_list)

    validations = [
        _v("MAWB_MATCH", "ERROR", mawb_match, fwb["mawb_number"],
           _join({x["mawb_number"] for x in fhl_list})),
        _v("ORIGIN_MATCH", "ERROR", origin_match, fwb["origin"],
           _join({x["origin"] for x in fhl_list})),
        _v("DESTINATION_MATCH", "ERROR", destination_match, fwb["destination"],
           _join({x["destination"] for x in fhl_list})),
        _v("PIECES_MATCH", cfg.pieces_severity, pieces_match, str(fwb["pieces"]),
           str(total_pieces), str(total_pieces - (fwb["pieces"] or 0))),
        _v("WEIGHT_MATCH", cfg.weight_severity, weight_exact or weight_tol,
           str(fwb["gross_weight"]), str(total_weight), str(weight_difference)),
        _v("WEIGHT_UNIT_MATCH", "ERROR", unit_match, fwb_unit,
           _join({x["weight_unit"] for x in fhl_list})),
        _v("DUPLICATE_HAWB", "ERROR", not duplicate_hawb, None, _join(hawbs)),
        _v("HAWB_PRESENT", "ERROR", hawb_present, None,
           f"{sum(1 for x in fhl_list if x['hawb_number'])}/{len(fhl_list)}"),
        _v("MASTER_PRESENT", "ERROR", master_present, fwb["mawb_number"],
           f"{sum(1 for x in fhl_list if x['mawb_number'])}/{len(fhl_list)}"),
        _v("VERSION_SUPPORTED", "ERROR", version_supported,
           _version_of(fwb), _join([_version_of(x) for x in fhl_list])),
    ]

    blocking_failed = [v["rule_code"] for v in validations
                       if v["result"] == "FAIL" and v["rule_code"] in BLOCKING_RULES]

    if blocking_failed:
        status = "REJECTED"
    elif duplicate_hawb:
        status = "DUPLICATE"
    elif origin_match and destination_match and pieces_match and weight_exact:
        status = "MATCHED"
    elif origin_match and destination_match and pieces_match and weight_tol:
        status = "MATCHED_WITH_TOLERANCE"
    elif score >= 70:
        status = "PARTIAL_MATCH"
    else:
        status = "NEEDS_REVIEW"

    return {
        "status": status,
        "score": score,
        "fhl_count": len(fhl_list),
        "fwb_pieces": fwb["pieces"],
        "fhl_total_pieces": total_pieces,
        "pieces_difference": total_pieces - (fwb["pieces"] or 0),
        "fwb_weight": float(fwb_weight),
        "fhl_total_weight": float(total_weight),
        "weight_difference": float(weight_difference),
        "weight_difference_percentage": float(weight_percentage),
        "origin_match": origin_match,
        "destination_match": destination_match,
        "pieces_match": pieces_match,
        "weight_match": weight_exact,
        "duplicate_hawb": duplicate_hawb,
        "blocking_failures": blocking_failed,
        "validations": validations,
    }


def _version_of(row: Any) -> str | None:
    try:
        return row["message_version"]
    except (KeyError, IndexError, TypeError):
        return None


def _version_supported(fwb, fhl_list, cfg: MatchingConfig) -> bool:
    """Unknown versions (rows without the column) are not treated as failures."""
    fwb_version = _version_of(fwb)
    if fwb_version is not None and fwb_version not in cfg.supported_fwb_versions:
        return False
    for item in fhl_list:
        version = _version_of(item)
        if version is not None and version not in cfg.supported_fhl_versions:
            return False
    return True


def _join(values) -> str:
    return ",".join(sorted(str(v) for v in values if v is not None)) or "—"


def _v(rule: str, severity: str, passed: bool, fwb_value, fhl_value,
       diff=None) -> dict:
    return {
        "rule_code": rule,
        "severity": severity,
        "result": "PASS" if passed else "FAIL",
        "fwb_value": fwb_value,
        "fhl_value": fhl_value,
        "difference_value": diff,
    }
