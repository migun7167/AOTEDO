"""FWB–FHL matching engine (design doc §10, FR-008..FR-012)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

ABSOLUTE_WEIGHT_TOLERANCE = Decimal("0.5")   # KG
PERCENTAGE_WEIGHT_TOLERANCE = Decimal("0.5")  # %


def match_fwb_fhl(
    fwb: Any,
    fhl_list: Iterable[Any],
    absolute_weight_tolerance: Decimal = ABSOLUTE_WEIGHT_TOLERANCE,
    percentage_weight_tolerance: Decimal = PERCENTAGE_WEIGHT_TOLERANCE,
) -> dict:
    """fwb / fhl items are dict-like rows with keys:
    origin, destination, pieces, gross_weight, hawb_number (FHL only).
    """
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
            "score": 50,
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
    weight_tol = (weight_difference <= absolute_weight_tolerance
                  or weight_percentage <= percentage_weight_tolerance)

    hawbs = [x["hawb_number"] for x in fhl_list]
    duplicate_hawb = len(set(hawbs)) != len(hawbs)

    score = 50
    if origin_match:
        score += 10
    if destination_match:
        score += 10
    if pieces_match:
        score += 15
    if weight_exact:
        score += 15
    elif weight_tol:
        score += 10

    if duplicate_hawb:
        status = "DUPLICATE"
    elif origin_match and destination_match and pieces_match and weight_exact:
        status = "MATCHED"
    elif origin_match and destination_match and pieces_match and weight_tol:
        status = "MATCHED_WITH_TOLERANCE"
    elif score >= 70:
        status = "PARTIAL_MATCH"
    else:
        status = "NEEDS_REVIEW"

    validations = [
        _v("MAWB_MATCH", "ERROR", True, fwb["mawb_number"], fwb["mawb_number"]),
        _v("ORIGIN_MATCH", "ERROR", origin_match, fwb["origin"],
           ",".join(sorted({x["origin"] or "?" for x in fhl_list}))),
        _v("DESTINATION_MATCH", "ERROR", destination_match, fwb["destination"],
           ",".join(sorted({x["destination"] or "?" for x in fhl_list}))),
        _v("PIECES_MATCH", "WARNING", pieces_match, str(fwb["pieces"]),
           str(total_pieces), str(total_pieces - (fwb["pieces"] or 0))),
        _v("WEIGHT_MATCH", "WARNING", weight_exact or weight_tol,
           str(fwb["gross_weight"]), str(total_weight), str(weight_difference)),
        _v("DUPLICATE_HAWB", "ERROR", not duplicate_hawb,
           None, ",".join(hawbs)),
    ]

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
        "validations": validations,
    }


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
