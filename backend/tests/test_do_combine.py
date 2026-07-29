"""Combining several house waybills onto one Delivery Order."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["PAPERLESS_AOT_DB"] = os.path.join(
    os.path.dirname(__file__), "test_combine.db")

from app.database import db, init_db  # noqa: E402
from app.services import do_service  # noqa: E402
from app.services import import_service as svc  # noqa: E402
from app.services.auth import ensure_default_users  # noqa: E402

SEIKO = """CNE/SEIKO PRECISION THAILAND CO LTD
/NAVANAKORN INDUSTRIAL ESTATE ZONE 3
/PATHUMTHANI
/TH/12120"""
# Same importer, spelled the way a different forwarder types it.
SEIKO_ALT = """CNE/SEIKO PRECISION (THAILAND) COMPANY LIMITED
/NAVANAKORN INDUSTRIAL ESTATE ZONE 3
/PATHUMTHANI
/TH/12120"""
OTHER = """CNE/BANGKOK APPAREL IMPORT CO LTD
/128 PRACHACHUEN ROAD
/NONTHABURI
/TH/11000"""

MESSAGES = [
    """FWB/16
217-08722750HKGBKK/T11K360.0
FLT/TG601/16
RTG/BKKTG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P11/K360.0/CQ/W360.0/R10.00/T3600.000
/NG/CONSOL
ISU/16JUL26/HKG""",
    f"""FHL/4
MBI/217-08722750HKGBKK/T11K360.0
HBS/AA26070001/HKGBKK/4/K120.0//ELECTRONIC PARTS
{SEIKO}""",
    f"""FHL/4
MBI/217-08722750HKGBKK/T11K360.0
HBS/AA26070002/HKGBKK/5/K180.0//MACHINE PARTS
{SEIKO_ALT}""",
    f"""FHL/4
MBI/217-08722750HKGBKK/T11K360.0
HBS/AA26070003/HKGBKK/2/K60.0//GARMENT
{OTHER}""",
    # a second master for the same importer, on another flight
    """FWB/16
217-08722751HKGBKK/T2K60.0
FLT/TG603/17
RTG/BKKTG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P2/K60.0/CQ/W60.0/R10.00/T600.000
/NG/CONSOL
ISU/17JUL26/HKG""",
    f"""FHL/4
MBI/217-08722751HKGBKK/T2K60.0
HBS/BB26070004/HKGBKK/2/K60.0//SPARE PARTS
{SEIKO}""",
    # a house landing at a different station
    """FWB/16
217-08722752HKGCNX/T1K25.0
FLT/TG605/18
RTG/CNXTG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P1/K25.0/CQ/W25.0/R10.00/T250.000
/NG/CONSOL
ISU/18JUL26/HKG""",
    f"""FHL/4
MBI/217-08722752HKGCNX/T1K25.0
HBS/CC26070005/HKGCNX/1/K25.0//SAMPLES
{SEIKO}""",
    """FSU/16 RCF 217-08722750BKK 16JUL26 1435 K360.0
FSU/16 RCF 217-08722751BKK 17JUL26 0910 K60.0""",
]


@pytest.fixture(scope="module")
def conn():
    os.environ["PAPERLESS_AOT_DB"] = os.path.join(
        os.path.dirname(__file__), "test_combine.db")
    if os.path.exists(os.environ["PAPERLESS_AOT_DB"]):
        os.remove(os.environ["PAPERLESS_AOT_DB"])
    init_db()
    with db() as c:
        ensure_default_users(c)
        batch = svc.create_batch(c, "WEB_UPLOAD", "test")
        for i, raw in enumerate(MESSAGES):
            svc.import_message(c, raw, f"m{i}.txt", batch["id"], user="test")
        yield c
    os.remove(os.environ["PAPERLESS_AOT_DB"])


def house(conn, hawb: str) -> str:
    return conn.execute("SELECT id FROM fhl_house WHERE hawb_number = ?",
                        (hawb,)).fetchone()["id"]


class TestNormalisation:
    @pytest.mark.parametrize("a,b", [
        ("SEIKO PRECISION THAILAND CO LTD",
         "SEIKO PRECISION (THAILAND) COMPANY LIMITED"),
        ("YAMATO INTERNATIONAL LOGISTICS KK", "Yamato Logistics K.K."),
        ("ACME CORP.", "ACME Corporation"),
    ])
    def test_same_importer_folds_together(self, a, b):
        assert do_service.normalise_party(a) == do_service.normalise_party(b)

    def test_different_importers_stay_apart(self):
        assert (do_service.normalise_party("SEIKO PRECISION THAILAND CO LTD")
                != do_service.normalise_party("BANGKOK APPAREL IMPORT CO LTD"))


class TestCombinableGroups:
    def test_groups_by_consignee_and_destination(self, conn):
        groups = do_service.combinable_groups(conn)
        seiko = next(g for g in groups
                     if "SEIKO" in (g["consignee"] or "").upper()
                     and g["destination"] == "BKK")
        hawbs = {h["hawb_number"] for h in seiko["houses"]}
        # spelled two ways, across two masters — still one group
        assert hawbs == {"AA26070001", "AA26070002", "BB26070004"}
        assert seiko["mawbCount"] == 2
        assert seiko["totalPieces"] == 11
        assert seiko["totalWeight"] == 360.0

    def test_other_station_is_a_separate_group(self, conn):
        groups = do_service.combinable_groups(conn)
        # the Chiang Mai house is alone, so it is not offered for combining
        assert not any(g["destination"] == "CNX" for g in groups)

    def test_single_house_consignees_are_not_offered(self, conn):
        groups = do_service.combinable_groups(conn)
        assert all(g["houseCount"] > 1 for g in groups)
        assert not any("APPAREL" in (g["consignee"] or "").upper()
                       for g in groups)


class TestCombineRules:
    def test_needs_at_least_two_houses(self, conn):
        with pytest.raises(do_service.DOError, match="อย่างน้อย 2"):
            do_service.check_combinable(conn, [house(conn, "AA26070001")])

    def test_rejects_duplicate_selection(self, conn):
        one = house(conn, "AA26070001")
        with pytest.raises(do_service.DOError, match="ซ้ำ"):
            do_service.check_combinable(conn, [one, one])

    def test_different_destinations_cannot_be_combined(self, conn):
        with pytest.raises(do_service.DOError, match="ปลายทางไม่ตรงกัน"):
            do_service.check_combinable(
                conn, [house(conn, "AA26070001"), house(conn, "CC26070005")])

    def test_different_consignees_blocked_then_forceable(self, conn):
        pair = [house(conn, "AA26070001"), house(conn, "AA26070003")]
        with pytest.raises(do_service.DOError, match="ผู้รับปลายทางไม่ตรงกัน"):
            do_service.check_combinable(conn, pair)
        forced = do_service.check_combinable(conn, pair, force_consignee=True)
        assert forced["consigneeMismatch"] is True

    def test_spelling_variants_need_no_override(self, conn):
        check = do_service.check_combinable(
            conn, [house(conn, "AA26070001"), house(conn, "AA26070002")])
        assert check["consigneeMismatch"] is False


class TestCombinedDocument:
    def test_combine_across_masters(self, conn):
        ids = [house(conn, h) for h in
               ("AA26070001", "AA26070002", "BB26070004")]
        do = do_service.combine(conn, ids, "admin",
                                overrides={"issuedBy": "TG40441"},
                                number_start=5200001)
        assert do["doType"] == "COMBINED"
        assert do["doNumber"] == "5200001"
        assert len(do["lines"]) == 3
        assert do["hawbNumber"] is None
        assert do["totalPieces"] == 11
        assert do["totalWeight"] == 360.0
        # two masters and two flights appear on their own lines
        assert {x["mawbNumber"] for x in do["lines"]} == {
            "217-08722750", "217-08722751"}
        assert {x["flightNumber"] for x in do["lines"]} == {"TG0601", "TG0603"}

    def test_expiry_runs_from_the_last_arrival(self, conn):
        do = do_service.load(conn, "5200001")
        # TG603 landed 17JUL 09:10, later than TG601's 16JUL 14:35
        assert do_service.fmt_stamp(
            do_service._parse_iso(do["landedAt"])) == "17-JUL-2026 09:10"
        assert do_service.fmt_stamp(
            do_service._parse_iso(do["expiryAt"])) == "19-JUL-2026 09:10"

    def test_lines_are_stored(self, conn):
        rows = conn.execute(
            """SELECT l.* FROM delivery_order_lines l
               JOIN delivery_orders d ON d.id = l.do_id
               WHERE d.do_number = '5200001' ORDER BY l.line_no""").fetchall()
        assert len(rows) == 3
        assert [r["line_no"] for r in rows] == [1, 2, 3]
        assert all(r["fhl_id"] for r in rows)

    def test_houses_are_no_longer_offered_for_combining(self, conn):
        groups = do_service.combinable_groups(conn)
        assert not any(
            h["hawb_number"] in {"AA26070001", "AA26070002", "BB26070004"}
            for g in groups for h in g["houses"])

    def test_a_house_cannot_be_released_twice(self, conn):
        """A single DO for a house already on a combined DO is refused."""
        with pytest.raises(do_service.DOError, match="DO รวม"):
            do_service.issue(conn, "217-08722750", house(conn, "AA26070001"),
                             "admin", number_start=5200001)

    def test_cannot_combine_houses_already_on_a_do(self, conn):
        ids = [house(conn, "AA26070001"), house(conn, "AA26070002")]
        with pytest.raises(do_service.DOError, match="ยังใช้งานอยู่"):
            do_service.check_combinable(conn, ids)

    def test_supersede_replaces_the_earlier_do(self, conn):
        ids = [house(conn, h) for h in ("AA26070001", "AA26070002")]
        replacement = do_service.combine(conn, ids, "admin", supersede=True,
                                         number_start=5200001)
        assert replacement["doNumber"] == "5200002"

        old = conn.execute(
            "SELECT status, superseded_by FROM delivery_orders WHERE do_number='5200001'"
        ).fetchone()
        assert old["status"] == "SUPERSEDED"
        assert old["superseded_by"] == replacement["id"]

        # the house left off the replacement is released again — it is alone
        # now, so it shows up as free rather than as a combinable group
        assert do_service.active_do_for_house(
            conn, house(conn, "BB26070004")) is None


class TestRendering:
    def test_html_lists_every_house_and_a_total(self, conn):
        do = do_service.load(conn, "5200002")
        html = do_service.render_html(do)
        assert "AA26070001" in html and "AA26070002" in html
        assert "รวม 2 House" in html
        # the barcode identifies the document, not any one house
        assert "5200002" in html

    def test_pdf_grows_with_the_line_count(self, conn):
        two = do_service.render_pdf(do_service.load(conn, "5200002"))
        assert two[:5] == b"%PDF-"
        assert b"TOTAL 2 HOUSE" not in two  # text is compressed in the stream
        assert len(two) > 3000

    def test_single_do_keeps_the_original_layout(self, conn):
        """Combining must not have changed how an ordinary DO prints."""
        single = do_service.issue(conn, "217-08722752",
                                  house(conn, "CC26070005"), "admin",
                                  number_start=5200001)
        html = do_service.render_html(single)
        assert single["doType"] == "SINGLE"
        assert "รวม" not in html          # no total row
        assert "HAWB CC26070005" in html
        assert 'aria-label="barcode CC26070005"' in html


class TestCancel:
    def test_cancel_frees_the_houses(self, conn):
        do_service.cancel(conn, "5200002")
        groups = do_service.combinable_groups(conn)
        freed = {h["hawb_number"] for g in groups for h in g["houses"]}
        assert {"AA26070001", "AA26070002"} <= freed

    def test_cancelling_twice_is_refused(self, conn):
        with pytest.raises(do_service.DOError, match="ยกเลิก"):
            do_service.cancel(conn, "5200002")

    def test_unknown_do(self, conn):
        with pytest.raises(do_service.DOError):
            do_service.cancel(conn, "does-not-exist")
