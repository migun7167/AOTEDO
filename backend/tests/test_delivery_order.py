"""Delivery Order generation, checked against the carrier's own DO layout."""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["PAPERLESS_AOT_DB"] = os.path.join(
    os.path.dirname(__file__), "test_do.db")

from app.database import db, init_db  # noqa: E402
from app.services import do_service  # noqa: E402
from app.services import import_service as svc  # noqa: E402
from app.services.auth import ensure_default_users  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "samples")

# The arrival event a carrier sends with the ATA clock time on it.
FSU_WITH_ATA = """FSU/16 RCS 217-08722685HKG 16JUL26 TG601 K149.0
FSU/16 DEP 217-08722685HKG TG601 16JUL26
FSU/16 ARR 217-08722685BKK TG601 16JUL26 1435
FSU/16 RCF 217-08722685BKK 16JUL26 1435 K149.0
FSU/16 NFD 217-08722685BKK WM26070003 16JUL26"""


@pytest.fixture(scope="module")
def conn():
    os.environ["PAPERLESS_AOT_DB"] = os.path.join(
        os.path.dirname(__file__), "test_do.db")
    if os.path.exists(os.environ["PAPERLESS_AOT_DB"]):
        os.remove(os.environ["PAPERLESS_AOT_DB"])
    init_db()
    with db() as c:
        ensure_default_users(c)
        batch = svc.create_batch(c, "WEB_UPLOAD", "test")
        for name in ("FWB_21708722685.txt", "FHL_WM26070003.txt"):
            with open(os.path.join(SAMPLES, name)) as f:
                svc.import_message(c, f.read(), name, batch["id"], user="test")
        svc.import_message(c, FSU_WITH_ATA, "FSU.txt", batch["id"], user="test")
        yield c
    os.remove(os.environ["PAPERLESS_AOT_DB"])


@pytest.fixture(scope="module")
def house_id(conn):
    return conn.execute(
        "SELECT id FROM fhl_house WHERE hawb_number = 'WM26070003'").fetchone()["id"]


@pytest.fixture(scope="module")
def do(conn, house_id):
    return do_service.issue(
        conn, "217-08722685", house_id, "admin",
        overrides={"aircraftRegistration": "HSTKO", "issuedBy": "TG40441",
                   "doDate": "2026-07-17"},
        number_start=5144857)


class TestFieldsMatchTheCarrierDO:
    """Every value on the reference DO, rebuilt from the matched messages."""

    def test_document_header(self, do):
        assert do["doNumber"] == "5144857"
        assert do["station"] == "BANGKOK"          # from destination BKK
        assert do_service.fmt_do_date(
            do_service._parse_iso(do["doDate"])) == "17-Jul-2026"

    def test_consignee_block(self, do):
        cne = do["consignee"]
        assert cne["name"] == "SEIKO PRECISION THAILAND CO LTD"
        assert "NAVANAKORN INDUSTRIAL ESTATE ZONE 3" in cne["address"]
        assert "PATHUMTHANI" in cne["address"]
        assert cne["postalCode"] == "12120"
        assert cne["country"] == "THAILAND"

    def test_waybill_row(self, do):
        assert do["mawbPlain"] == "21708722685"    # printed without the dash
        assert do["hawbNumber"] == "WM26070003"
        assert (do["pieces"], do["masterPieces"]) == (1, 1)
        assert (do["weight"], do["masterWeight"]) == (149.0, 149.0)
        assert do["weightUnit"] == "K"
        assert (do["boardPoint"], do["offPoint"]) == ("HKG", "BKK")
        assert do["natureOfGoods"] == "DRY BATTERY"

    def test_flight_is_zero_padded(self, do):
        assert do["flightNumber"] == "TG0601"      # FWB carries TG601
        assert do["aircraftRegistration"] == "HSTKO"

    def test_ata_and_expiry_come_from_the_fsu(self, do):
        landed = do_service._parse_iso(do["landedAt"])
        assert do_service.fmt_stamp(landed) == "16-JUL-2026 14:35"
        expiry = do_service._parse_iso(do["expiryAt"])
        assert do_service.fmt_stamp(expiry) == "18-JUL-2026 14:35"
        assert (expiry - landed).total_seconds() == 48 * 3600

    def test_carrier_from_airline_prefix(self, do):
        assert do["carrierCode"] == "TG"
        assert do["carrierName"] == \
            "THAI AIRWAYS INTERNATIONAL PUBLIC COMPANY LIMITED"
        assert do["issuedBy"] == "TG40441"

    def test_shc_blank_by_default(self, do):
        """The reference DO leaves SHC empty; master SPH is opt-in."""
        assert do["shc"] == ""

    def test_shc_from_master_when_configured(self, conn, house_id):
        ctx = do_service.build_context(conn, "217-08722685", house_id,
                                       shc_source="MASTER")
        assert ctx["shc"] == "HEA SPX"


class TestNumbering:
    def test_reprint_keeps_the_same_number(self, conn, house_id, do):
        again = do_service.issue(conn, "217-08722685", house_id, "admin",
                                 number_start=5144857)
        assert again["doNumber"] == do["doNumber"]
        assert again["reprint"] is True
        assert again["reprintCount"] >= 1

    def test_second_house_gets_the_next_number(self, conn):
        batch = svc.create_batch(conn, "WEB_UPLOAD", "test")
        svc.import_message(conn, """FHL/4
MBI/217-08722685HKGBKK/T1K149.0
HBS/WM26070099/HKGBKK/1/K149.0//SPARE PARTS
CNE/ANOTHER CONSIGNEE CO LTD
/1 SUKHUMVIT ROAD
/BANGKOK
/TH/10110""", "extra.txt", batch["id"], user="test")
        other = conn.execute(
            "SELECT id FROM fhl_house WHERE hawb_number = 'WM26070099'").fetchone()
        second = do_service.issue(conn, "217-08722685", other["id"], "admin",
                                  number_start=5144857)
        assert second["doNumber"] == "5144858"
        assert second["hawbNumber"] == "WM26070099"


    def test_amend_rewrites_in_place(self, conn, house_id, do):
        """A corrected ATA must not mint a second document for the same house."""
        amended = do_service.issue(
            conn, "217-08722685", house_id, "admin",
            overrides={"landedAt": "2026-07-16T09:05",
                       "aircraftRegistration": "HSTKZ"},
            number_start=5144857, amend=True)
        assert amended["doNumber"] == do["doNumber"]
        assert amended["amended"] is True
        assert amended["aircraftRegistration"] == "HSTKZ"

        reloaded = do_service.load(conn, amended["doNumber"])
        assert do_service.fmt_stamp(
            do_service._parse_iso(reloaded["landedAt"])) == "16-JUL-2026 09:05"
        assert do_service.fmt_stamp(
            do_service._parse_iso(reloaded["expiryAt"])) == "18-JUL-2026 09:05"

        count = conn.execute(
            """SELECT COUNT(*) c FROM delivery_orders
               WHERE mawb_number = ? AND hawb_number = ?""",
            ("217-08722685", "WM26070003")).fetchone()["c"]
        assert count == 1

        # put the reference values back for the rendering tests
        do_service.issue(conn, "217-08722685", house_id, "admin",
                         overrides={"aircraftRegistration": "HSTKO",
                                    "issuedBy": "TG40441",
                                    "doDate": "2026-07-17"},
                         number_start=5144857, amend=True)


class TestRendering:
    def test_html_contains_every_printed_value(self, do):
        html = do_service.render_html(do)
        for expected in ("5144857", "BANGKOK", "17-Jul-2026", "H.M.CUSTOMS",
                         "DELIVERY ORDER(CUSTOMS MANIFESTATION)",
                         "SEIKO PRECISION THAILAND CO LTD", "12120 THAILAND",
                         "MAWB 21708722685/", "HAWB WM26070003", "1 of 1",
                         "149 of 149K", "HKG", "BKK", "TG0601", "HSTKO",
                         "16-JUL-2026 14:35", "DRY BATTERY",
                         "18-JUL-2026 14:35", "TG40441",
                         "THAI AIRWAYS INTERNATIONAL PUBLIC COMPANY LIMITED"):
            assert expected in html, f"missing from the DO: {expected}"

    def test_html_embeds_a_barcode(self, do):
        html = do_service.render_html(do)
        assert '<svg class="barcode"' in html
        assert html.count("<rect") > 50      # one per bar

    def test_pdf_is_a_single_a4_page(self, do):
        pdf = do_service.render_pdf(do)
        assert pdf[:5] == b"%PDF-"
        assert pdf.count(b"/Type /Page") >= 1

    def test_reprint_is_watermarked(self, conn, house_id):
        reprinted = do_service.issue(conn, "217-08722685", house_id, "admin")
        assert "REPRINT" in do_service.render_html(reprinted)


class TestHelpers:
    @pytest.mark.parametrize("raw,time,expected", [
        ("16JUL26", None, datetime(2026, 7, 16, 0, 0)),
        ("16JUL26", "1435", datetime(2026, 7, 16, 14, 35)),
        ("1JAN27", "0005", datetime(2027, 1, 1, 0, 5)),
    ])
    def test_parse_imp_date(self, raw, time, expected):
        assert do_service.parse_imp_date(raw, time) == expected

    def test_parse_imp_date_rejects_junk(self):
        assert do_service.parse_imp_date("NOTADATE") is None
        assert do_service.parse_imp_date(None) is None

    @pytest.mark.parametrize("flight,expected", [
        ("TG601", "TG0601"), ("TG0601", "TG0601"), ("SQ1", "SQ0001"),
        ("TG601A", "TG0601A"),
    ])
    def test_flight_padding(self, flight, expected):
        assert do_service.fmt_flight("TG", flight) == expected

    @pytest.mark.parametrize("value,expected", [
        (149.0, "149"), (480.5, "480.5"), (0.0, "0"), (None, ""),
    ])
    def test_weight_formatting(self, value, expected):
        assert do_service.fmt_weight(value) == expected

    def test_barcode_is_valid_code39(self):
        svg = do_service.code39_svg("WM26070003")
        # 12 characters (10 + start/stop) x 5 bars each
        assert svg.count("<rect") == 12 * 5
        assert 'width="' in svg

    def test_unknown_airline_prefix_degrades_gracefully(self, conn, house_id):
        ctx = do_service.build_context(conn, "217-08722685", house_id)
        assert ctx["carrierName"]          # 217 is known
        code, name, terminal = do_service.CARRIERS.get(
            "999", do_service.DEFAULT_CARRIER)
        assert (code, name) == ("", "")
        assert terminal


def test_missing_house_is_reported(conn):
    with pytest.raises(do_service.DOError):
        do_service.build_context(conn, "217-08722685", "no-such-id")
