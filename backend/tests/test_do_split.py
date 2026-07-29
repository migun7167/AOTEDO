"""Splitting a Delivery Order, and releasing a house in parts."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["PAPERLESS_AOT_DB"] = os.path.join(
    os.path.dirname(__file__), "test_split.db")

from app.database import db, init_db  # noqa: E402
from app.services import do_service  # noqa: E402
from app.services import import_service as svc  # noqa: E402
from app.services.auth import ensure_default_users  # noqa: E402

CNE = """CNE/NAVANAKORN ELECTRONICS CO LTD
/111 MOO 20 NAVANAKORN INDUSTRIAL ESTATE
/PATHUMTHANI
/TH/12120"""

MESSAGES = [
    """FWB/16
217-08722800HKGBKK/T20K800.0
FLT/TG601/16
RTG/BKKTG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P20/K800.0/CQ/W800.0/R10.00/T8000.000
/NG/CONSOL
ISU/16JUL26/HKG""",
    f"""FHL/4
MBI/217-08722800HKGBKK/T20K800.0
HBS/SP26070001/HKGBKK/12/K500.0//ELECTRONIC PARTS
{CNE}""",
    f"""FHL/4
MBI/217-08722800HKGBKK/T20K800.0
HBS/SP26070002/HKGBKK/8/K300.0//MACHINE PARTS
{CNE}""",
    "FSU/16 RCF 217-08722800BKK 16JUL26 1435 K800.0",
]

MAWB = "217-08722800"


@pytest.fixture()
def conn():
    """Function scoped: each test starts from a clean release ledger."""
    os.environ["PAPERLESS_AOT_DB"] = os.path.join(
        os.path.dirname(__file__), "test_split.db")
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


def combined(conn):
    return do_service.combine(
        conn, [house(conn, "SP26070001"), house(conn, "SP26070002")],
        "admin", number_start=5300001)


class TestSplitByHouse:
    def test_split_supersedes_and_reissues(self, conn):
        original = combined(conn)
        result = do_service.split(
            conn, original["doNumber"],
            [[house(conn, "SP26070001")], [house(conn, "SP26070002")]],
            "admin", number_start=5300001)

        assert result["splitFrom"]["doNumber"] == original["doNumber"]
        assert [d["doNumber"] for d in result["documents"]] == \
            ["5300002", "5300003"]
        assert all(d["doType"] == "SINGLE" for d in result["documents"])

        old = conn.execute(
            "SELECT status, superseded_by FROM delivery_orders WHERE do_number = ?",
            (original["doNumber"],)).fetchone()
        assert old["status"] == "SUPERSEDED"
        assert old["superseded_by"] == result["documents"][0]["id"]

    def test_each_house_carries_its_own_quantity(self, conn):
        original = combined(conn)
        result = do_service.split(
            conn, original["doNumber"],
            [[house(conn, "SP26070001")], [house(conn, "SP26070002")]],
            "admin", number_start=5300001)
        by_hawb = {d["lines"][0]["hawbNumber"]: d for d in result["documents"]}
        assert by_hawb["SP26070001"]["lines"][0]["pieces"] == 12
        assert by_hawb["SP26070002"]["lines"][0]["pieces"] == 8

    def test_uneven_split_keeps_a_combined_document(self, conn):
        """Three houses split two-and-one leaves one document still combined."""
        svc.import_message(conn, f"""FHL/4
MBI/{MAWB}HKGBKK/T20K800.0
HBS/SP26070003/HKGBKK/3/K90.0//SAMPLES
{CNE}""", "extra.txt",
            svc.create_batch(conn, "WEB_UPLOAD", "test")["id"], user="test")
        ids = [house(conn, h) for h in
               ("SP26070001", "SP26070002", "SP26070003")]
        original = do_service.combine(conn, ids, "admin", number_start=5300001)

        result = do_service.split(conn, original["doNumber"],
                                  [ids[:2], ids[2:]], "admin",
                                  number_start=5300001)
        types = {d["doType"] for d in result["documents"]}
        assert types == {"COMBINED", "SINGLE"}
        combined_doc = next(d for d in result["documents"]
                            if d["doType"] == "COMBINED")
        assert len(combined_doc["lines"]) == 2

    def test_the_split_must_account_for_every_house(self, conn):
        """A group set that is not exactly the DO's houses is refused."""
        original = combined(conn)
        one, two = house(conn, "SP26070001"), house(conn, "SP26070002")

        outsider = svc.create_batch(conn, "WEB_UPLOAD", "test")["id"]
        svc.import_message(conn, f"""FHL/4
MBI/{MAWB}HKGBKK/T20K800.0
HBS/SP26079999/HKGBKK/1/K10.0//NOT ON THIS DO
{CNE}""", "outsider.txt", outsider, user="test")
        stranger = house(conn, "SP26079999")

        # SP26070002 dropped, a house that was never on the DO added instead
        with pytest.raises(do_service.DOError, match="ตกหล่น"):
            do_service.split(conn, original["doNumber"], [[one], [stranger]],
                             "admin")
        with pytest.raises(do_service.DOError, match="ซ้ำ"):
            do_service.split(conn, original["doNumber"], [[one], [one, two]],
                             "admin")

    def test_needs_two_groups(self, conn):
        original = combined(conn)
        ids = [house(conn, "SP26070001"), house(conn, "SP26070002")]
        with pytest.raises(do_service.DOError, match="อย่างน้อย 2 กลุ่ม"):
            do_service.split(conn, original["doNumber"], [ids], "admin")

    def test_single_house_document_cannot_be_split(self, conn):
        single = do_service.issue(conn, MAWB, house(conn, "SP26070001"),
                                  "admin", number_start=5300001)
        with pytest.raises(do_service.DOError, match="house เดียว"):
            do_service.split(conn, single["doNumber"],
                             [[house(conn, "SP26070001")], []], "admin")

    def test_cannot_split_a_superseded_document(self, conn):
        original = combined(conn)
        groups = [[house(conn, "SP26070001")], [house(conn, "SP26070002")]]
        do_service.split(conn, original["doNumber"], groups, "admin",
                         number_start=5300001)
        with pytest.raises(do_service.DOError, match="ยกเลิกหรือถูกแทนที่"):
            do_service.split(conn, original["doNumber"], groups, "admin")


class TestReleaseLedger:
    def test_untouched_house_has_everything_available(self, conn):
        state = do_service.balance(conn, house(conn, "SP26070001"))
        assert state["totalPieces"] == 12
        assert state["releasedPieces"] == 0
        assert state["remainingPieces"] == 12
        assert state["remainingWeight"] == 500.0
        assert state["fullyReleased"] is False

    def test_a_full_release_empties_the_balance(self, conn):
        do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                         number_start=5300001)
        state = do_service.balance(conn, house(conn, "SP26070001"))
        assert state["remainingPieces"] == 0
        assert state["fullyReleased"] is True

    def test_cancelling_returns_the_quantity(self, conn):
        do = do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                              number_start=5300001)
        do_service.cancel(conn, do["doNumber"])
        state = do_service.balance(conn, house(conn, "SP26070001"))
        assert state["remainingPieces"] == 12


class TestPartDelivery:
    def test_releases_part_and_keeps_the_balance(self, conn):
        first = do_service.issue(
            conn, MAWB, house(conn, "SP26070001"), "admin",
            overrides={"releasePieces": 5, "releaseWeight": 200.0},
            number_start=5300001)
        assert first["doType"] == "PARTIAL"
        line = first["lines"][0]
        assert (line["pieces"], line["weight"]) == (5, 200.0)
        assert (line["housePieces"], line["houseWeight"]) == (12, 500.0)
        assert line["isPartial"] is True
        assert (line["balancePieces"], line["balanceWeight"]) == (7, 300.0)

        state = do_service.balance(conn, house(conn, "SP26070001"))
        assert (state["releasedPieces"], state["remainingPieces"]) == (5, 7)

    def test_the_rest_goes_out_on_a_second_document(self, conn):
        do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                         overrides={"releasePieces": 5, "releaseWeight": 200.0},
                         number_start=5300001)
        second = do_service.issue(conn, MAWB, house(conn, "SP26070001"),
                                  "admin", number_start=5300001)
        assert second["doNumber"] == "5300002"
        assert (second["lines"][0]["pieces"], second["lines"][0]["weight"]) == \
            (7, 300.0)
        assert do_service.balance(
            conn, house(conn, "SP26070001"))["remainingPieces"] == 0

    def test_cannot_release_more_than_remains(self, conn):
        do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                         overrides={"releasePieces": 5, "releaseWeight": 200.0},
                         number_start=5300001)
        with pytest.raises(do_service.DOError, match="เหลือให้ปล่อยได้อีก 7"):
            do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                             overrides={"releasePieces": 8},
                             number_start=5300001)

    def test_cannot_release_more_weight_than_remains(self, conn):
        with pytest.raises(do_service.DOError, match="เหลือให้ปล่อยได้อีก"):
            do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                             overrides={"releasePieces": 1,
                                        "releaseWeight": 900.0},
                             number_start=5300001)

    @pytest.mark.parametrize("pieces,weight", [(0, 100.0), (-1, 100.0),
                                               (1, 0), (1, -5)])
    def test_rejects_nonsense_quantities(self, conn, pieces, weight):
        with pytest.raises(do_service.DOError):
            do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                             overrides={"releasePieces": pieces,
                                        "releaseWeight": weight},
                             number_start=5300001)

    def test_nothing_left_names_the_documents(self, conn):
        """Two part deliveries use the house up; a third has nothing to release."""
        do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                         overrides={"releasePieces": 5, "releaseWeight": 200.0},
                         number_start=5300001)
        do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                         overrides={"releasePieces": 7, "releaseWeight": 300.0},
                         number_start=5300001)
        for overrides in ({}, {"releasePieces": 1}):
            with pytest.raises(do_service.DOError, match="5300001, 5300002"):
                do_service.issue(conn, MAWB, house(conn, "SP26070001"),
                                 "admin", overrides=overrides,
                                 number_start=5300001)

    def test_releasing_the_whole_house_at_once_is_an_ordinary_do(self, conn):
        """Asking for everything explicitly is a full release, not a part one."""
        do = do_service.issue(
            conn, MAWB, house(conn, "SP26070001"), "admin",
            overrides={"releasePieces": 12, "releaseWeight": 500.0},
            number_start=5300001)
        assert do["doType"] == "SINGLE"
        assert do["lines"][0]["isPartial"] is False
        # and asking again returns the same document rather than a new one
        again = do_service.issue(conn, MAWB, house(conn, "SP26070001"),
                                 "admin", number_start=5300001)
        assert again["doNumber"] == do["doNumber"]
        assert again["reprint"] is True

    def test_part_deliveries_do_not_collide_on_the_header(self, conn):
        """Several live documents for one house is the whole point."""
        for _ in range(3):
            do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                             overrides={"releasePieces": 4,
                                        "releaseWeight": 100.0},
                             number_start=5300001)
        rows = conn.execute(
            """SELECT COUNT(*) c FROM delivery_order_lines l
               JOIN delivery_orders d ON d.id = l.do_id
               WHERE l.fhl_id = ? AND d.status = 'ACTIVE'""",
            (house(conn, "SP26070001"),)).fetchone()["c"]
        assert rows == 3
        assert do_service.balance(
            conn, house(conn, "SP26070001"))["remainingPieces"] == 0

    def test_a_partly_released_house_cannot_be_combined(self, conn):
        do_service.issue(conn, MAWB, house(conn, "SP26070001"), "admin",
                         overrides={"releasePieces": 5, "releaseWeight": 200.0},
                         number_start=5300001)
        with pytest.raises(do_service.DOError, match="ยังใช้งานอยู่"):
            do_service.check_combinable(
                conn, [house(conn, "SP26070001"), house(conn, "SP26070002")])


class TestPartDeliveryDocument:
    @pytest.fixture()
    def partial(self, conn):
        return do_service.issue(
            conn, MAWB, house(conn, "SP26070001"), "admin",
            overrides={"releasePieces": 5, "releaseWeight": 200.0,
                       "issuedBy": "TG40441"},
            number_start=5300001)

    def test_row_compares_against_the_house_not_the_master(self, partial):
        html = do_service.render_html(partial)
        # 12 is the house total; the master holds 20
        assert "5 of 12" in html
        assert "200 of 500K" in html

    def test_marks_the_row_and_states_the_balance(self, partial):
        html = do_service.render_html(partial)
        assert "PART DELIVERY" in html
        assert "เหลือ 7 ชิ้น" in html
        assert "300K" in html

    def test_pdf_renders(self, partial):
        pdf = do_service.render_pdf(partial)
        assert pdf[:5] == b"%PDF-"

    def test_a_full_release_says_nothing_about_parts(self, conn):
        """An ordinary DO must still print exactly like the carrier's own."""
        full = do_service.issue(conn, MAWB, house(conn, "SP26070002"),
                                "admin", number_start=5300001)
        html = do_service.render_html(full)
        assert "PART DELIVERY" not in html
        assert full["doType"] == "SINGLE"
        # house 8 pieces measured against the master's 20, as on the reference
        assert "8 of 20" in html
