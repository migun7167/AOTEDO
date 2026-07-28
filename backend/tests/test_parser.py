import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.parser import ParseError, detect, parse_message  # noqa: E402
from app.parser.base import normalize_mawb  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "samples")


def load(name: str) -> str:
    with open(os.path.join(SAMPLES, name)) as f:
        return f.read()


CANONICAL_FWB = """FWB/16
217-08722685HKGBKK/T1K149.0
FLT/TG601/16
RTG/BKKTG
SHP
/WM LOGISTICS WORLDWIDE LIMITED
/58 66 TAI LIN PAI ROAD KWAI CHUNG
/HONG KONG
/HK
CNE
/PLANET INTER LOGISTICS CO LTD
/2 59 60 BANGNA COMPLEX OFFICE TOWER
/BANGKOK
/TH
AGT//1316077
/NARITA EXPRESS HK LTD
/HONG KONG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P1/K149.0/CQ/W149.0/R10.76/T1603.240
/NG/CONSOL
/2/NV/MC0.44
/3/ND//NDA
OTH/P/AWC13MCC250.4MYC223.5
PPD/WT1603.24
/OC486.9/CT2090.14
ISU/16JUL26/HKG
REF/HKGFMCR
SPH/HEA/SPX"""


class TestDetect:
    def test_fwb(self):
        assert detect("FWB/16\nxxx") == ("FWB", "16")

    def test_fhl(self):
        assert detect("FHL/4 MBI/...") == ("FHL", "4")

    def test_invalid(self):
        with pytest.raises(ParseError) as e:
            detect("HELLO WORLD")
        assert e.value.code == "UNSUPPORTED_MESSAGE_TYPE"

    def test_empty(self):
        with pytest.raises(ParseError) as e:
            detect("   ")
        assert e.value.code == "EMPTY_FILE"


class TestNormalizeMawb:
    @pytest.mark.parametrize("raw", ["21708722685", "217-08722685", "217 08722685"])
    def test_forms(self, raw):
        assert normalize_mawb(raw) == "217-08722685"

    def test_invalid(self):
        with pytest.raises(ParseError):
            normalize_mawb("12345")


class TestFwbParser:
    def test_wrapped_sample_file(self):
        p = parse_message(load("FWB_21708722685.txt"))
        assert p["mawbNumber"] == "217-08722685"
        assert p["origin"] == "HKG"
        assert p["destination"] == "BKK"
        assert p["pieces"] == 1
        assert p["weight"] == 149.0
        assert p["weightUnit"] == "K"
        assert p["flightNumber"] == "TG601"
        assert p["natureOfGoods"] == "CONSOL"
        assert p["shipper"]["name"] == "WM LOGISTICS WORLDWIDE LIMITED"
        assert p["consignee"]["country"] == "TH"
        assert p["agent"]["code"] == "1316077"
        assert p["issueDate"] == "16JUL26"
        assert p["specialHandlingCodes"] == ["HEA", "SPX"]

    def test_canonical_format_same_result(self):
        wrapped = parse_message(load("FWB_21708722685.txt"))
        canonical = parse_message(CANONICAL_FWB)
        for key in ("mawbNumber", "origin", "destination", "pieces", "weight",
                    "flightNumber", "natureOfGoods"):
            assert wrapped[key] == canonical[key]


class TestFhlParser:
    def test_sample_file(self):
        p = parse_message(load("FHL_WM26070003.txt"))
        assert p["mawbNumber"] == "217-08722685"
        assert p["hawbNumber"] == "WM26070003"
        assert p["origin"] == "HKG"
        assert p["destination"] == "BKK"
        assert p["pieces"] == 1
        assert p["weight"] == 149.0
        assert p["commodity"] == "DRY BATTERY"
        assert p["hsCode"] == "85061012"
        assert p["consigneeTaxId"] == "0105531040228"
        assert p["consignee"]["phone"] == "66252921626"
        assert p["consignee"]["postalCode"] == "12120"

    def test_oci_cne_not_split(self):
        # the CNE token inside OCI/TH/CNE/T/... must not break segmentation
        p = parse_message(load("FHL_WM26070003.txt"))
        assert p["oci"]["partyType"] == "CNE"
        assert p["consignee"]["name"] == "SEIKO PRECISION THAILAND CO LTD"


class TestFfmFsu:
    def test_ffm(self):
        p = parse_message(load("FFM_TG601_16JUL26.txt"))
        assert p["flightNumber"] == "TG601"
        assert p["consignments"][0]["mawbNumber"] == "217-08722685"

    def test_fsu(self):
        p = parse_message(load("FSU_21708722685.txt"))
        codes = [e["statusCode"] for e in p["events"]]
        assert codes == ["RCS", "DEP", "ARR", "RCF", "NFD"]
        assert p["events"][-1]["hawbNumber"] == "WM26070003"
