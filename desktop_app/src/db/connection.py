from pathlib import Path
import sqlite3
from contextlib import closing, contextmanager
from collections.abc import Iterator

from src.db.schema import SCHEMA_STATEMENTS


REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
    "lot_payments": {
        "paid_through": "TEXT",
    },
    "payment_audit": {
        "paid_through": "TEXT",
        "paid_current_assessment": "NUMERIC DEFAULT 0",
        "paid_current_interest": "NUMERIC DEFAULT 0",
        "paid_delinquent_assessment": "NUMERIC DEFAULT 0",
        "paid_delinquent_interest": "NUMERIC DEFAULT 0",
        "session_id": "INTEGER",
    },
    "owner_payments": {
        "session_id": "INTEGER",
    },
    "financial_transactions": {
        "fiscal_year": "TEXT",
        "month_number": "INTEGER",
        "entry_date": "TEXT",
        "reference_number": "TEXT",
        "check_number": "TEXT",
        "paper_check_flag": "TEXT",
        "payment_method": "TEXT",
        "pc_transaction_number": "TEXT",
        "disposition": "TEXT",
        # Existing pre-migration transactions came from TRANSFIL.DBF.
        # New databases use the schema's 'app' default for newly posted rows.
        "source": "TEXT NOT NULL DEFAULT 'legacy'",
        "source_account_code": "TEXT",
        "destination_account_code": "TEXT",
        "correction_of_id": "INTEGER",
    },
    "financial_monthly": {
        "fiscal_year": "TEXT",
    },
    "property_sales": {
        "reversed_at": "TEXT",
        "reversal_backup_path": "TEXT",
    },
    "lots": {
        "county_land_trust_flag": "TEXT DEFAULT 'N'",
    },
    "assessment_runs": {
        "assessment_season": "TEXT",
        "assessment_year": "TEXT",
    },
    "id_card_issues": {
        "owner_quantity": "INTEGER DEFAULT 0",
        "renter_quantity": "INTEGER DEFAULT 0",
        "issue_year": "INTEGER",
        "completed_flag": "TEXT DEFAULT 'N'",
    },
}


def _existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _migrate_financial_monthly_table(connection: sqlite3.Connection) -> None:
    rows = connection.execute("PRAGMA table_info(financial_monthly)").fetchall()
    if not rows:
        return
    pk_columns = [row[1] for row in rows if row[5] > 0]
    if pk_columns == ["account_code", "fiscal_year", "fiscal_month"]:
        return

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_monthly_v2 (
            account_code TEXT NOT NULL,
            fiscal_year TEXT DEFAULT '',
            fiscal_month INTEGER NOT NULL,
            calendar_month INTEGER,
            previous_balance NUMERIC DEFAULT 0,
            month_expense NUMERIC DEFAULT 0,
            month_deposit NUMERIC DEFAULT 0,
            year_to_date NUMERIC DEFAULT 0,
            budget_to_date NUMERIC DEFAULT 0,
            monthly_budget NUMERIC DEFAULT 0,
            yearly_budget NUMERIC DEFAULT 0,
            file_status TEXT,
            PRIMARY KEY (account_code, fiscal_year, fiscal_month),
            FOREIGN KEY (account_code) REFERENCES financial_accounts(account_code)
        )
        """
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO financial_monthly_v2 (
            account_code,
            fiscal_year,
            fiscal_month,
            calendar_month,
            previous_balance,
            month_expense,
            month_deposit,
            year_to_date,
            budget_to_date,
            monthly_budget,
            yearly_budget,
            file_status
        )
        SELECT
            m.account_code,
            COALESCE(NULLIF(TRIM(m.fiscal_year), ''), NULLIF(TRIM(a.fiscal_year), ''), '') AS fiscal_year,
            m.fiscal_month,
            m.calendar_month,
            m.previous_balance,
            m.month_expense,
            m.month_deposit,
            m.year_to_date,
            m.budget_to_date,
            m.monthly_budget,
            m.yearly_budget,
            m.file_status
        FROM financial_monthly m
        LEFT JOIN financial_accounts a ON a.account_code = m.account_code
        """
    )
    connection.execute("DROP TABLE financial_monthly")
    connection.execute("ALTER TABLE financial_monthly_v2 RENAME TO financial_monthly")


def _run_migrations(connection: sqlite3.Connection) -> None:
    for table_name, columns in REQUIRED_COLUMNS.items():
        existing = _existing_columns(connection, table_name)
        for column_name, column_type in columns.items():
            if column_name in existing:
                continue
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )
    _migrate_financial_monthly_table(connection)
    marker = connection.execute(
        "SELECT value FROM app_meta WHERE key = 'separate_collection_and_land_trust_v1'"
    ).fetchone()
    if marker is None:
        # Before this migration the lot-level column represented dBase CLT, but
        # the collection screen also wrote to it. Preserve every existing Y as
        # land-trust data, then retire the ambiguous lot collection value. New
        # collection-agency activity is stored only on the owner and in events.
        connection.execute(
            """
            UPDATE lots
            SET county_land_trust_flag = CASE
                WHEN UPPER(COALESCE(collection_flag, '')) = 'Y' THEN 'Y'
                ELSE COALESCE(NULLIF(county_land_trust_flag, ''), 'N')
            END,
                collection_flag = 'N'
            """
        )
        connection.execute(
            "INSERT INTO app_meta (key, value) VALUES ('separate_collection_and_land_trust_v1', 'complete')"
        )


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            _run_migrations(connection)


@contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()
