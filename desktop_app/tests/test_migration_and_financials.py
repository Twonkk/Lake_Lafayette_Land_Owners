from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from src.db.connection import initialize_database
from src.services.financial_service import FinancialTransactionRequest, post_financial_transaction
from src.services.import_service import run_legacy_import
from src.services.migration_service import reconcile_migration


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.sqlite3"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()


class FinancialYearTests(DatabaseTestCase):
    def test_transaction_uses_selected_fiscal_year_not_calendar_year(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute(
                "INSERT INTO financial_accounts (account_code, account_name, fiscal_year) VALUES ('AA', 'Test', '2026')"
            )
            connection.execute(
                """
                INSERT INTO financial_monthly (
                    account_code, fiscal_year, fiscal_month, month_expense, month_deposit, year_to_date
                ) VALUES ('AA', '2026', 4, 0, 0, 0)
                """
            )

        number = post_financial_transaction(
            self.db_path,
            FinancialTransactionRequest(
                account_code="AA",
                fiscal_year="2026",
                month_number=4,
                transaction_date="2025-12-15",
                transaction_type="Expense",
                amount=25.0,
                payee="Test",
                memo="Earlier transaction",
            ),
        )

        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            row = connection.execute(
                "SELECT fiscal_year, transaction_date, source FROM financial_transactions WHERE transaction_number = ?",
                [str(number)],
            ).fetchone()
        self.assertEqual(row, ("2026", "2025-12-15", "app"))
        self.assertTrue(any((self.db_path.parent / "backups").glob("*financial_transaction*.sqlite3")))


class RefreshSafetyTests(DatabaseTestCase):
    def test_refresh_is_blocked_after_native_activity(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO assessment_runs (
                    created_at, assessment_amount, assessment_date, backup_path,
                    lots_updated, owners_updated, excluded_lots, freeze_lots
                ) VALUES ('now', 1, '2026-01-01', 'backup', 0, 0, 0, 0)
                """
            )
        with patch("src.services.import_service.import_legacy_directory") as importer:
            with self.assertRaisesRegex(RuntimeError, "Refresh stopped"):
                run_legacy_import(Path(self.temp.name), self.db_path)
            importer.assert_not_called()


class ReconciliationTests(DatabaseTestCase):
    def test_reconciliation_reports_only_aggregate_results(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute(
                "INSERT INTO owners (owner_code, number_lots, total_owed) VALUES ('1', 2, 10)"
            )
            connection.execute(
                """
                INSERT INTO lots (
                    lot_number, owner_code, total_due, current_assessment
                ) VALUES ('A', '1', 12, 11)
                """
            )
        result = reconcile_migration(self.db_path)
        self.assertEqual(result.owner_lot_count_mismatches, 1)
        self.assertEqual(result.owner_total_mismatches, 1)
        self.assertEqual(result.lot_component_mismatches, 1)
        self.assertEqual(result.owner_lot_total_difference, 2.0)
        self.assertEqual(result.lot_component_difference, 1.0)


if __name__ == "__main__":
    unittest.main()
