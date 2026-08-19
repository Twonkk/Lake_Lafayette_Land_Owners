from pathlib import Path
import tempfile
import unittest

from src.db.connection import get_connection, initialize_database
from src.services.assessment_service import apply_assessment_run, preview_assessment_run
from src.services.payment_service import LotAllocation, PaymentRequest, post_lot_payment


class LegacyParityDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.sqlite3"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_lot(
        self,
        lot_number: str,
        *,
        owner_code: str = "1000",
        delinquent_assessment: float = 0,
        delinquent_interest: float = 0,
        current_interest: float = 0,
        current_assessment: float = 0,
        total_due: float = 0,
        freeze_flag: str = "",
    ) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO owners (owner_code, total_owed) VALUES (?, ?)",
                [owner_code, total_due],
            )
            connection.execute(
                """
                INSERT INTO lots (
                    lot_number, owner_code, delinquent_assessment, delinquent_interest,
                    current_interest, current_assessment, total_due, freeze_flag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    lot_number,
                    owner_code,
                    delinquent_assessment,
                    delinquent_interest,
                    current_interest,
                    current_assessment,
                    total_due,
                    freeze_flag,
                ],
            )
            connection.commit()

    def balances(self, lot_number: str) -> tuple[float, float, float, float, float]:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT delinquent_assessment, delinquent_interest, current_interest,
                       current_assessment, total_due
                FROM lots WHERE lot_number = ?
                """,
                [lot_number],
            ).fetchone()
        return tuple(float(value or 0) for value in row)


class AssessmentLegacyParityTests(LegacyParityDatabaseTestCase):
    def test_three_assessment_runs_match_dbase_compounding_example(self) -> None:
        self.add_lot("A1")
        expected = [
            (0, 0, 0, 25, 25),
            (25, 0, 0.88, 25, 50.88),
            (50, 0.88, 1.78, 25, 77.66),
        ]

        for run_number, balances in enumerate(expected, start=1):
            apply_assessment_run(self.db_path, 25, f"2026-0{run_number}-01")
            self.assertEqual(self.balances("A1"), balances)

    def test_frozen_regular_lot_accumulates_assessment_and_recomputes_total(self) -> None:
        self.add_lot(
            "A-FROZEN",
            delinquent_assessment=10,
            delinquent_interest=2,
            current_interest=1,
            current_assessment=5,
            total_due=18,
            freeze_flag="Y",
        )

        apply_assessment_run(self.db_path, 25, "2026-01-01")

        self.assertEqual(self.balances("A-FROZEN"), (10, 3, 0, 30, 43))

    def test_frozen_x_lot_receives_no_new_assessment_or_interest(self) -> None:
        self.add_lot(
            "X-FROZEN",
            delinquent_assessment=10,
            delinquent_interest=2,
            current_interest=1,
            current_assessment=5,
            total_due=18,
            freeze_flag="Y",
        )

        apply_assessment_run(self.db_path, 25, "2026-01-01")

        self.assertEqual(self.balances("X-FROZEN"), (10, 3, 0, 0, 13))

    def test_preview_matches_frozen_rules(self) -> None:
        self.add_lot("A1", current_assessment=5, total_due=5, freeze_flag="Y")
        self.add_lot("X1", current_assessment=5, total_due=5, freeze_flag="Y")
        self.add_lot("B1")

        preview = preview_assessment_run(self.db_path, 25)

        self.assertEqual(preview.freeze_lots, 2)
        self.assertEqual(preview.projected_current_assessment, 55)

    def test_assessment_amount_is_saved_to_cents(self) -> None:
        self.add_lot("A1")

        apply_assessment_run(self.db_path, 25.005, "2026-01-01")

        self.assertEqual(self.balances("A1"), (0, 0, 0, 25.01, 25.01))


class PaymentLegacyParityTests(LegacyParityDatabaseTestCase):
    def payment_request(self, amount: float, allocation: LotAllocation) -> PaymentRequest:
        return PaymentRequest(
            owner_code="1000",
            payment_amount=amount,
            payment_date="2026-01-15",
            payment_form="Cash",
            allocations=[allocation],
        )

    def test_partial_payment_uses_operator_category_distribution(self) -> None:
        self.add_lot(
            "A1",
            delinquent_assessment=10,
            delinquent_interest=5,
            current_interest=2,
            current_assessment=8,
            total_due=25,
        )
        allocation = LotAllocation(
            "A1",
            current_assessment=7,
            delinquent_interest=5,
            paid_through="F26",
        )

        post_lot_payment(self.db_path, self.payment_request(12, allocation))

        self.assertEqual(self.balances("A1"), (10, 0, 2, 1, 13))
        with get_connection(self.db_path) as connection:
            lot = connection.execute(
                "SELECT paid_through FROM lots WHERE lot_number = 'A1'"
            ).fetchone()
            audit = connection.execute(
                """
                SELECT paid_current_assessment, paid_current_interest,
                       paid_delinquent_assessment, paid_delinquent_interest, paid_through
                FROM payment_audit
                """
            ).fetchone()
        self.assertEqual(lot["paid_through"], "F26")
        self.assertEqual(tuple(audit), (7, 0, 0, 5, "F26"))

    def test_full_payment_clears_every_category(self) -> None:
        self.add_lot(
            "A1",
            delinquent_assessment=10,
            delinquent_interest=5,
            current_interest=2,
            current_assessment=8,
            total_due=25,
        )
        allocation = LotAllocation(
            "A1",
            current_assessment=8,
            current_interest=2,
            delinquent_assessment=10,
            delinquent_interest=5,
            paid_through="F26",
        )

        result = post_lot_payment(self.db_path, self.payment_request(25, allocation))

        self.assertEqual(self.balances("A1"), (0, 0, 0, 0, 0))
        self.assertEqual(result.new_owner_total, 0)

    def test_only_delinquent_assessment_may_exceed_its_category_balance(self) -> None:
        self.add_lot(
            "A1",
            delinquent_assessment=3,
            current_assessment=10,
            total_due=13,
        )

        post_lot_payment(
            self.db_path,
            self.payment_request(5, LotAllocation("A1", delinquent_assessment=5)),
        )

        self.assertEqual(self.balances("A1"), (-2, 0, 0, 10, 8))

    def test_other_category_overpayment_is_rejected(self) -> None:
        self.add_lot(
            "A1",
            delinquent_assessment=5,
            current_assessment=5,
            total_due=10,
        )

        with self.assertRaisesRegex(ValueError, "Current assessment payment cannot exceed"):
            post_lot_payment(
                self.db_path,
                self.payment_request(
                    10,
                    LotAllocation("A1", current_assessment=6, delinquent_assessment=4),
                ),
            )

    def test_owner_total_is_recalculated_from_lots_before_payment(self) -> None:
        self.add_lot("A1", current_assessment=25, total_due=25)
        with get_connection(self.db_path) as connection:
            connection.execute("UPDATE owners SET total_owed = 999 WHERE owner_code = '1000'")
            connection.commit()

        result = post_lot_payment(
            self.db_path,
            self.payment_request(5, LotAllocation("A1", current_assessment=5)),
        )

        self.assertEqual(result.previous_owner_total, 25)
        self.assertEqual(result.new_owner_total, 20)


if __name__ == "__main__":
    unittest.main()
