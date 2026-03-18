from pathlib import Path
import sqlite3

from src.db.schema import SCHEMA_STATEMENTS


REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
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
    },
    "financial_monthly": {
        "fiscal_year": "TEXT",
    },
    "property_sales": {
        "reversed_at": "TEXT",
        "reversal_backup_path": "TEXT",
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


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        _run_migrations(connection)
        connection.commit()


def get_connection(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
