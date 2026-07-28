import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.matching.engine import match_fwb_fhl  # noqa: E402


def fwb(pieces=1, weight=149.0, origin="HKG", dest="BKK"):
    return {"mawb_number": "217-08722685", "origin": origin, "destination": dest,
            "pieces": pieces, "gross_weight": weight}


def fhl(hawb="WM26070003", pieces=1, weight=149.0, origin="HKG", dest="BKK"):
    return {"hawb_number": hawb, "origin": origin, "destination": dest,
            "pieces": pieces, "gross_weight": weight}


def test_exact_match():
    r = match_fwb_fhl(fwb(), [fhl()])
    assert r["status"] == "MATCHED"
    assert r["score"] == 100


def test_one_to_many_match():
    houses = [fhl("A", 3, 100.0), fhl("B", 2, 80.0), fhl("C", 5, 220.0)]
    r = match_fwb_fhl(fwb(pieces=10, weight=400.0), houses)
    assert r["status"] == "MATCHED"
    assert r["fhl_total_pieces"] == 10
    assert r["fhl_total_weight"] == 400.0


def test_weight_tolerance():
    r = match_fwb_fhl(fwb(weight=149.0), [fhl(weight=148.8)])
    assert r["status"] == "MATCHED_WITH_TOLERANCE"
    assert 90 <= r["score"] < 100


def test_weight_mismatch():
    r = match_fwb_fhl(fwb(weight=149.0), [fhl(weight=140.0)])
    assert r["status"] == "PARTIAL_MATCH"
    assert r["weight_match"] is False


def test_duplicate_hawb():
    r = match_fwb_fhl(fwb(pieces=2, weight=298.0), [fhl("X"), fhl("X")])
    assert r["status"] == "DUPLICATE"
    assert r["duplicate_hawb"] is True


def test_wrong_destination():
    r = match_fwb_fhl(fwb(), [fhl(dest="SIN")])
    assert r["destination_match"] is False
    assert r["status"] in ("PARTIAL_MATCH", "NEEDS_REVIEW")


def test_waiting_for_fwb():
    r = match_fwb_fhl(None, [fhl()])
    assert r["status"] == "WAITING_FOR_FWB"
    assert r["score"] == 0


def test_waiting_for_fhl():
    r = match_fwb_fhl(fwb(), [])
    assert r["status"] == "WAITING_FOR_FHL"
    assert r["score"] == 50


def test_custom_tolerance():
    r = match_fwb_fhl(fwb(weight=149.0), [fhl(weight=147.0)],
                      absolute_weight_tolerance=Decimal("5"))
    assert r["status"] == "MATCHED_WITH_TOLERANCE"
