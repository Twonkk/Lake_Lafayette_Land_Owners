import tempfile
import unittest
from pathlib import Path

from src.db.connection import get_connection, initialize_database
from src.db.repositories import OwnerRepository, PaymentRepository
from src.services.history_service import get_owner_payment_history, render_owner_payment_history_pdf
from src.services.payment_service import payment_form_label


class PaymentHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "payment-history.sqlite3"
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO owners (
                    owner_code, last_name, first_name, address, city, state, zip, total_owed
                ) VALUES ('1001', 'Martin', 'Alex', '1 Lake Rd', 'Lafayette', 'MO', '64000', 75)
                """
            )
            connection.executemany(
                "INSERT INTO lots (lot_number, owner_code) VALUES (?, '1001')",
                [("A1",), ("A2",)],
            )
            connection.execute(
                """
                INSERT INTO owner_payments (
                    owner_code, payment_amount, total_owed, payment_date, payment_form, check_number
                ) VALUES ('1001', 25, 100, '2025-01-15', '1', '421')
                """
            )
            cursor = connection.execute(
                """
                INSERT INTO owner_payments (
                    owner_code, payment_amount, total_owed, payment_date, payment_form, check_number
                ) VALUES ('1001', 50, 125, '2026-06-20', 'CK', '9001')
                """
            )
            self.app_payment_id = cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO payment_audit (
                    created_at, owner_code, lot_number, payment_amount, payment_date,
                    payment_form, check_number, paid_through,
                    paid_current_assessment, paid_current_interest,
                    paid_delinquent_assessment, paid_delinquent_interest,
                    backup_path, previous_total_due, new_total_due,
                    previous_owner_total, new_owner_total
                ) VALUES (?, '1001', ?, 25, '2026-06-20', 'CK', '9001',
                          '2026-1', 20, 0, 5, 0, 'backup.sqlite3', 50, 25, 125, 75)
                """,
                [
                    ("2026-06-20T10:00:00", "A1"),
                    ("2026-06-20T10:00:00", "A2"),
                ],
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_owner_detail_contains_imported_and_app_payment_history(self) -> None:
        detail = OwnerRepository(self.db_path).get_owner_detail("1001")

        self.assertIsNotNone(detail)
        payments = detail["payments"]
        self.assertEqual([row["payment_date"] for row in payments], ["2026-06-20", "2025-01-15"])
        self.assertEqual([float(row["payment_amount"]) for row in payments], [50.0, 25.0])

    def test_classic_history_search_reads_owner_payments(self) -> None:
        repository = PaymentRepository(self.db_path)

        by_name = repository.search_history("Martin")
        by_check = repository.search_history("421")
        by_form = repository.search_history("Check")

        self.assertEqual(len(by_name), 2)
        self.assertEqual(by_name[0]["id"], self.app_payment_id)
        self.assertEqual(len(by_check), 1)
        self.assertEqual(by_check[0]["payment_date"], "2025-01-15")
        self.assertEqual(len(by_form), 2)

    def test_app_payment_detail_keeps_lot_distribution(self) -> None:
        detail = PaymentRepository(self.db_path).get_history_detail(self.app_payment_id)

        self.assertIsNotNone(detail)
        self.assertEqual(len(detail["app_details"]), 2)
        self.assertEqual(
            {row["lot_number"] for row in detail["app_details"]},
            {"A1", "A2"},
        )

    def test_legacy_and_app_payment_forms_use_familiar_labels(self) -> None:
        self.assertEqual(payment_form_label("1"), "Check")
        self.assertEqual(payment_form_label("CK"), "Check")
        self.assertEqual(payment_form_label("8"), "Negotiated Adjustment")
        self.assertEqual(payment_form_label("custom"), "CUSTOM")

    def test_individual_history_is_limited_to_selected_owner(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO owners (owner_code, last_name, first_name, total_owed)
                VALUES ('2002', 'Other', 'Owner', 10)
                """
            )
            connection.execute(
                """
                INSERT INTO owner_payments (
                    owner_code, payment_amount, total_owed, payment_date, payment_form, check_number
                ) VALUES ('2002', 10, 20, '2026-07-01', 'CS', '')
                """
            )

        detail = get_owner_payment_history(self.db_path, "1001")

        self.assertEqual(detail["owner"]["last_name"], "Martin")
        self.assertEqual(detail["lot_numbers"], ["A1", "A2"])
        self.assertEqual(len(detail["payments"]), 2)
        self.assertTrue(all(row["payment_amount"] != 10 for row in detail["payments"]))

    def test_individual_history_pdf_is_created(self) -> None:
        output = render_owner_payment_history_pdf(
            self.db_path,
            Path(self.temp_dir.name) / "reports",
            "1001",
        )

        self.assertEqual(output.name, "owner_1001_payment_history.pdf")
        self.assertTrue(output.exists())
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
