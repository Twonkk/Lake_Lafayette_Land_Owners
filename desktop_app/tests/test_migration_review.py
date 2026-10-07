from pathlib import Path
import tempfile
import unittest

from src.db.connection import get_connection, initialize_database
from src.services.import_service import active_native_activity
from src.services.migration_review_service import (
    OwnerReviewUpdate,
    accept_x_lot_exclusion,
    complete_owner_manually,
    delete_unused_placeholder,
    keep_dbase_owner_total,
    keep_historical_owner,
    list_migration_review_items,
    restore_suggested_owner,
    use_lot_balance_total,
)
from src.services.utility_service import run_data_health_checks


class MigrationReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "review.sqlite3"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_placeholder(self, owner_code: str, *, current_lot: str = "") -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO owners (
                    owner_code, last_name, address, status, current_flag,
                    hold_mail_flag, ineligible_flag, number_lots,
                    primary_lot_number, total_owed
                ) VALUES (?, 'MISSING OWNER RECORD', 'UNKNOWN',
                    'IMPORT REVIEW REQUIRED', ?, 'Y', 'Y', ?, ?, ?)
                """,
                [
                    owner_code,
                    "T" if current_lot else "F",
                    1 if current_lot else 0,
                    current_lot or None,
                    25 if current_lot else 0,
                ],
            )
            if current_lot:
                connection.execute(
                    """
                    INSERT INTO lots (
                        lot_number, owner_code, current_assessment, total_due
                    ) VALUES (?, ?, 25, 25)
                    """,
                    [current_lot, owner_code],
                )

    def test_restore_recoverable_owner_records_decision_and_protects_refresh(self) -> None:
        self.add_placeholder("3423", current_lot="H218")
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO legacy_owner_candidates (
                    owner_code, source_file, source_record_number, deleted_flag,
                    last_name, first_name, address, city, state, zip, phone,
                    resident_flag, current_flag, hold_mail_flag, ineligible_flag
                ) VALUES (
                    '3423', 'ONERFILE.DBF', 2061, 'Y', 'KEYS', 'PATRICIA',
                    '1004 GITTUS PARK', 'ODESSA', 'MO', '64076', '660-624-6449',
                    'Y', 'T', 'N', 'N'
                )
                """
            )

        items = list_migration_review_items(self.db_path)
        item = next(row for row in items if row.record_key == "3423")
        self.assertTrue(item.has_candidate)
        backup = restore_suggested_owner(self.db_path, "3423")

        self.assertTrue(backup.exists())
        with get_connection(self.db_path) as connection:
            owner = connection.execute(
                "SELECT last_name, first_name, address, status, total_owed FROM owners WHERE owner_code = '3423'"
            ).fetchone()
        self.assertEqual(tuple(owner), ("KEYS", "PATRICIA", "1004 GITTUS PARK", "MIGRATION REVIEWED", 25))
        self.assertEqual(active_native_activity(self.db_path), {"migration_review_decisions": 1})

    def test_manual_owner_completion_and_historical_choice_preserve_links(self) -> None:
        self.add_placeholder("3613", current_lot="E050")
        self.add_placeholder("2574")
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO owner_payments (owner_code, payment_amount)
                VALUES ('2574', 25)
                """
            )

        complete_owner_manually(
            self.db_path,
            OwnerReviewUpdate(
                "3613", "VERIFIED", "OWNER", "1 MAIN", "ODESSA", "MO", "64076",
                current_flag="T", hold_mail_flag="N", ineligible_flag="N",
            ),
        )
        keep_historical_owner(self.db_path, "2574")

        with get_connection(self.db_path) as connection:
            current = connection.execute(
                "SELECT last_name, status, current_flag FROM owners WHERE owner_code = '3613'"
            ).fetchone()
            historical = connection.execute(
                "SELECT status, current_flag FROM owners WHERE owner_code = '2574'"
            ).fetchone()
            payment_count = connection.execute(
                "SELECT COUNT(*) FROM owner_payments WHERE owner_code = '2574'"
            ).fetchone()[0]
        self.assertEqual(tuple(current), ("VERIFIED", "MIGRATION REVIEWED", "T"))
        self.assertEqual(tuple(historical), ("HISTORICAL REFERENCE", "F"))
        self.assertEqual(payment_count, 1)

    def test_delete_is_blocked_for_referenced_owner_and_allowed_when_unused(self) -> None:
        self.add_placeholder("1000")
        self.add_placeholder("1001")
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO owner_payments (owner_code, payment_amount) VALUES ('1000', 1)"
            )
        with self.assertRaisesRegex(ValueError, "cannot be deleted safely"):
            delete_unused_placeholder(self.db_path, "1000")

        delete_unused_placeholder(self.db_path, "1001")
        with get_connection(self.db_path) as connection:
            self.assertIsNone(
                connection.execute("SELECT 1 FROM owners WHERE owner_code = '1001'").fetchone()
            )

    def test_x_lot_and_rounding_decisions_clear_health_warnings(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO owners (
                    owner_code, last_name, current_flag, number_lots,
                    primary_lot_number, total_owed
                ) VALUES ('1171', 'SORENSON', 'T', 2, 'XB049', 0)
                """
            )
            connection.execute(
                """
                INSERT INTO owners (
                    owner_code, last_name, current_flag, number_lots,
                    primary_lot_number, total_owed
                ) VALUES ('2591', 'TARWATER', 'T', 1, 'A019', 10.02)
                """
            )
            connection.execute(
                """
                INSERT INTO lots (
                    lot_number, owner_code, current_assessment, total_due
                ) VALUES ('A019', '2591', 10, 10)
                """
            )

        before = {row.title: row.issue_count for row in run_data_health_checks(self.db_path)}
        self.assertEqual(before["Current-owner lot-count mismatches"], 1)
        self.assertEqual(before["Owner total mismatches"], 1)

        accept_x_lot_exclusion(self.db_path, "1171")
        keep_dbase_owner_total(self.db_path, "2591")
        after = {row.title: row.issue_count for row in run_data_health_checks(self.db_path)}
        self.assertEqual(after["Current-owner lot-count mismatches"], 0)
        self.assertEqual(after["Owner total mismatches"], 0)

    def test_using_lot_total_changes_only_owner_summary(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO owners (owner_code, last_name, total_owed) VALUES ('1', 'TEST', 10.05)"
            )
            connection.execute(
                "INSERT INTO lots (lot_number, owner_code, current_assessment, total_due) VALUES ('A1', '1', 10, 10)"
            )

        use_lot_balance_total(self.db_path, "1")
        with get_connection(self.db_path) as connection:
            owner_total = connection.execute(
                "SELECT total_owed FROM owners WHERE owner_code = '1'"
            ).fetchone()[0]
            lot_total = connection.execute(
                "SELECT total_due FROM lots WHERE lot_number = 'A1'"
            ).fetchone()[0]
        self.assertEqual(owner_total, 10)
        self.assertEqual(lot_total, 10)


if __name__ == "__main__":
    unittest.main()
