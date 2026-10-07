from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.db.connection import get_connection, initialize_database
from src.importers.dbf_importer import import_legacy_directory
from src.services.cards_stickers_service import (
    BoatStickerRequest,
    IdCardRequest,
    mark_open_id_orders_completed,
    record_boat_sticker_purchase,
    record_id_card_issue,
)
from src.services.encumbrance_service import (
    assign_collection,
    list_encumbrance_events,
    record_lien,
    remove_collection,
)
from src.services.import_service import active_native_activity
from src.services.notice_service import NoticeLotLine, NoticeOwner, owner_notice_total
from src.services.payment_service import (
    LotAllocation,
    PaymentRequest,
    post_lot_payment,
    render_payment_session_deposit_pdf,
)


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.db_path = self.temp_path / "test.sqlite3"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_owner_lot(
        self,
        *,
        owner_code: str = "1000",
        lot_number: str = "A1",
        total_due: float = 0,
        county_trust: str = "N",
        ineligible: str = "N",
    ) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO owners (
                    owner_code, last_name, current_flag, total_owed,
                    number_lots, primary_lot_number, ineligible_flag
                ) VALUES (?, 'TEST', 'T', ?, 1, ?, ?)
                """,
                [owner_code, total_due, lot_number, ineligible],
            )
            connection.execute(
                """
                INSERT INTO lots (
                    lot_number, owner_code, total_due, delinquent_assessment,
                    county_land_trust_flag, collection_flag
                ) VALUES (?, ?, ?, ?, ?, 'N')
                """,
                [lot_number, owner_code, total_due, total_due, county_trust],
            )


class ImportPreservationTests(DatabaseTestCase):
    def test_missing_owner_codes_are_preserved_as_review_placeholders(self) -> None:
        rows = {
            "ONERFILE.DBF": [{
                "OWNR_CODE": 1000, "LAST_NAME": "KNOWN", "CURRENT": "T",
                "NUMBR_LOTS": 1, "LOT_NUMBER": "A1", "TOTAL_OWED": 10,
            }],
            "ASMTFILE.DBF": [
                {"LOT_NUMBER": "A1", "OWNR_CODE": 1000, "TOT_DUE": 10, "CURR_ASMT": 10},
                {"LOT_NUMBER": "B1", "OWNR_CODE": 9999, "TOT_DUE": 20, "CURR_ASMT": 20},
            ],
            "OPAYFILE.DBF": [{"OWNR_CODE": 9999, "PAY_AMT": 5}],
            "LPAYFILE.DBF": [{"LOT_NUMBER": "B1", "OWNR_CODE": 9999, "PAY_AMT": 5}],
        }

        def fake_read(path: Path) -> list[dict]:
            return rows.get(path.name, [])

        with patch("src.importers.dbf_importer._read_dbf", side_effect=fake_read):
            result = import_legacy_directory(self.temp_path, self.db_path)

        self.assertEqual(result["placeholder_owners_imported"], 1)
        self.assertEqual(result["owner_payments_imported"], 1)
        with get_connection(self.db_path) as connection:
            owner = connection.execute(
                "SELECT * FROM owners WHERE owner_code = '9999'"
            ).fetchone()
            lot = connection.execute("SELECT owner_code FROM lots WHERE lot_number = 'B1'").fetchone()
        self.assertEqual(owner["status"], "IMPORT REVIEW REQUIRED")
        self.assertEqual(owner["hold_mail_flag"], "Y")
        self.assertEqual(owner["ineligible_flag"], "Y")
        self.assertEqual(owner["total_owed"], 20)
        self.assertEqual(lot["owner_code"], "9999")


class EncumbranceSeparationTests(DatabaseTestCase):
    def test_collection_never_changes_county_land_trust_or_lot_collection(self) -> None:
        self.add_owner_lot(county_trust="Y")

        assign_collection(self.db_path, "1000", [], "2026-10-07")
        remove_collection(self.db_path, "1000", [], "2026-10-08")

        with get_connection(self.db_path) as connection:
            owner = connection.execute(
                "SELECT collection_flag FROM owners WHERE owner_code = '1000'"
            ).fetchone()
            lot = connection.execute(
                "SELECT county_land_trust_flag, collection_flag FROM lots WHERE lot_number = 'A1'"
            ).fetchone()
        self.assertEqual(owner["collection_flag"], "N")
        self.assertEqual(tuple(lot), ("Y", "N"))
        self.assertEqual([row["action"] for row in list_encumbrance_events(self.db_path, "1000")],
                         ["removed", "assigned"])

    def test_lien_rejects_a_lot_that_does_not_belong_to_owner(self) -> None:
        self.add_owner_lot()
        with self.assertRaisesRegex(ValueError, "do not belong"):
            record_lien(self.db_path, "1000", ["B1"], "2026-10-07", 25, "1", "2")


class CardAndStickerTests(DatabaseTestCase):
    def test_boat_sticker_requires_same_year_id_and_orders_can_be_completed(self) -> None:
        self.add_owner_lot()
        with self.assertRaisesRegex(ValueError, "ID card record"):
            record_boat_sticker_purchase(
                self.db_path,
                BoatStickerRequest("1000", "A1", "2026", 1, 10, ""),
            )

        record_id_card_issue(
            self.db_path,
            IdCardRequest("1000", "A1", "2026-10-07", 0, "", owner_quantity=1, renter_quantity=2),
        )
        record_boat_sticker_purchase(
            self.db_path,
            BoatStickerRequest("1000", "A1", "2026", 1, 10, ""),
        )
        count, backup = mark_open_id_orders_completed(self.db_path)

        self.assertEqual(count, 1)
        self.assertIsNotNone(backup)
        with get_connection(self.db_path) as connection:
            card = connection.execute(
                "SELECT quantity, owner_quantity, renter_quantity, completed_flag FROM id_card_issues"
            ).fetchone()
        self.assertEqual(tuple(card), (3, 1, 2, "Y"))
        activity = active_native_activity(self.db_path)
        self.assertEqual(activity["id_card_issues"], 1)
        self.assertEqual(activity["id_card_completion_events"], 1)

    def test_cards_are_blocked_for_an_owner_with_a_balance(self) -> None:
        self.add_owner_lot(total_due=25)
        with self.assertRaisesRegex(ValueError, "balance due"):
            record_id_card_issue(
                self.db_path,
                IdCardRequest("1000", "A1", "2026-10-07", 1, ""),
            )


class PaymentSessionTests(DatabaseTestCase):
    def test_single_lot_credit_and_deposit_session_match_dbase(self) -> None:
        self.add_owner_lot(total_due=10)
        result = post_lot_payment(
            self.db_path,
            PaymentRequest(
                owner_code="1000",
                payment_amount=12,
                payment_date="2026-10-07",
                payment_form="Cash",
                allocations=[LotAllocation("A1", delinquent_assessment=12, paid_through="F26")],
            ),
        )
        output = render_payment_session_deposit_pdf(
            self.db_path, result.session_id, self.temp_path / "reports"
        )

        self.assertEqual(result.new_owner_total, -2)
        self.assertTrue(output.exists())
        with get_connection(self.db_path) as connection:
            lot = connection.execute(
                "SELECT total_due, delinquent_assessment FROM lots WHERE lot_number = 'A1'"
            ).fetchone()
            session = connection.execute(
                "SELECT closed_at FROM payment_sessions WHERE id = ?", [result.session_id]
            ).fetchone()
        self.assertEqual(tuple(lot), (-2, -2))
        self.assertTrue(session["closed_at"])


class NoticeTrustTests(unittest.TestCase):
    def test_county_land_trust_lots_are_shown_but_not_billed(self) -> None:
        owner = NoticeOwner(
            owner_code="1000", last_name="TEST", first_name="", address="1 MAIN",
            city="ODESSA", state="MO", zip_code="64076", total_owed=75,
            lien_flag="N", hold_mail_flag="N", current_flag="T",
            lots=[
                NoticeLotLine("A1", 0, 0, 25, 0, 25, "N", "N"),
                NoticeLotLine("A2", 25, 0, 25, 0, 50, "Y", "N"),
            ],
        )
        self.assertEqual(owner_notice_total(owner), 25)


if __name__ == "__main__":
    unittest.main()
