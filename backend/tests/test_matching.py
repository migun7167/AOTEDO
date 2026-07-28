import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.matching.engine import MatchingConfig, match_fwb_fhl  # noqa: E402


def fwb(pieces=1, weight=149.0, origin="HKG", dest="BKK", unit="K", version="16"):
    return {"mawb_number": "217-08722685", "origin": origin, "destination": dest,
            "pieces": pieces, "gross_weight": weight, "weight_unit": unit,
            "message_version": version}


def fhl(hawb="WM26070003", pieces=1, weight=149.0, origin="HKG", dest="BKK",
        unit="K", version="4", mawb="217-08722685"):
    return {"mawb_number": mawb, "hawb_number": hawb, "origin": origin,
            "destination": dest, "pieces": pieces, "gross_weight": weight,
            "weight_unit": unit, "message_version": version}


def rules(result):
    return {v["rule_code"]: v["result"] for v in result["validations"]}


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
    """A wider tolerance turns a mismatch into an accepted match."""
    strict = match_fwb_fhl(fwb(weight=149.0), [fhl(weight=147.0)])
    assert strict["status"] == "PARTIAL_MATCH"
    lenient = match_fwb_fhl(fwb(weight=149.0), [fhl(weight=147.0)],
                            MatchingConfig(weight_tolerance_abs=Decimal("5")))
    assert lenient["status"] == "MATCHED_WITH_TOLERANCE"


def test_custom_scores_change_total():
    cfg = MatchingConfig(score_mawb=40, score_origin=15, score_destination=15,
                         score_pieces=15, score_weight=15)
    r = match_fwb_fhl(fwb(), [fhl()], cfg)
    assert r["status"] == "MATCHED"
    assert r["score"] == 100


def test_weight_unit_mismatch_is_rejected():
    """Kilograms against pounds are not comparable, so the match is refused."""
    r = match_fwb_fhl(fwb(unit="K"), [fhl(unit="L")])
    assert r["status"] == "REJECTED"
    assert rules(r)["WEIGHT_UNIT_MATCH"] == "FAIL"


def test_missing_hawb_is_rejected():
    r = match_fwb_fhl(fwb(), [fhl(hawb="")])
    assert r["status"] == "REJECTED"
    assert rules(r)["HAWB_PRESENT"] == "FAIL"


def test_unsupported_version_fails_rule_but_still_scores():
    r = match_fwb_fhl(fwb(), [fhl(version="99")])
    assert rules(r)["VERSION_SUPPORTED"] == "FAIL"
    assert r["status"] == "MATCHED"  # not a blocking rule


def test_supported_versions_are_configurable():
    cfg = MatchingConfig(supported_fhl_versions=["4", "99"])
    r = match_fwb_fhl(fwb(), [fhl(version="99")], cfg)
    assert rules(r)["VERSION_SUPPORTED"] == "PASS"


def test_mawb_mismatch_reported_for_manually_linked_house():
    r = match_fwb_fhl(fwb(), [fhl(mawb="217-99999999")])
    assert rules(r)["MAWB_MATCH"] == "FAIL"


def test_all_default_rules_present():
    r = match_fwb_fhl(fwb(), [fhl()])
    assert set(rules(r)) == {
        "MAWB_MATCH", "ORIGIN_MATCH", "DESTINATION_MATCH", "PIECES_MATCH",
        "WEIGHT_MATCH", "WEIGHT_UNIT_MATCH", "DUPLICATE_HAWB", "HAWB_PRESENT",
        "MASTER_PRESENT", "VERSION_SUPPORTED"}
    assert all(v == "PASS" for v in rules(r).values())


def test_severity_is_configurable():
    cfg = MatchingConfig(pieces_severity="ERROR")
    r = match_fwb_fhl(fwb(pieces=2), [fhl(pieces=1)], cfg)
    pieces = next(v for v in r["validations"] if v["rule_code"] == "PIECES_MATCH")
    assert pieces["severity"] == "ERROR"
