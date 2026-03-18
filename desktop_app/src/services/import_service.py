from dataclasses import dataclass
from pathlib import Path

from src.db.connection import get_connection
from src.importers.dbf_importer import import_legacy_directory, import_legacy_financials_only


@dataclass(slots=True)
class ImportResult:
    owners_imported: int
    lots_imported: int
    owner_payments_imported: int
    lot_payments_imported: int
    notes_imported: int
    financial_accounts_imported: int = 0
    financial_monthly_imported: int = 0
    financial_transactions_imported: int = 0


REQUIRED_LEGACY_FILES = [
    "ONERFILE.DBF",
    "ASMTFILE.DBF",
    "OPAYFILE.DBF",
    "LPAYFILE.DBF",
    "NOTEFILE.DBF",
    "STDBUDFL.DBF",
    "INEXFILE.DBF",
    "TRANSFIL.DBF",
]


def database_has_core_data(sqlite_path: Path) -> bool:
    with get_connection(sqlite_path) as connection:
        owner_count = connection.execute("SELECT COUNT(*) FROM owners").fetchone()[0]
        lot_count = connection.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
    return bool(owner_count and lot_count)


def validate_legacy_directory(source_dir: Path) -> list[str]:
    source_dir = source_dir.resolve()
    missing: list[str] = []
    for filename in REQUIRED_LEGACY_FILES:
        if not (source_dir / filename).exists():
            missing.append(filename)
    return missing


def run_legacy_import(source_dir: Path, sqlite_path: Path) -> ImportResult:
    result = import_legacy_directory(source_dir=source_dir, sqlite_path=sqlite_path)
    return ImportResult(
        owners_imported=result["owners_imported"],
        lots_imported=result["lots_imported"],
        owner_payments_imported=result["owner_payments_imported"],
        lot_payments_imported=result["lot_payments_imported"],
        notes_imported=result["notes_imported"],
        financial_accounts_imported=result.get("financial_accounts_imported", 0),
        financial_monthly_imported=result.get("financial_monthly_imported", 0),
        financial_transactions_imported=result.get("financial_transactions_imported", 0),
    )


def backfill_financial_import_if_empty(source_dir: Path, sqlite_path: Path) -> ImportResult | None:
    with get_connection(sqlite_path) as connection:
        accounts = connection.execute("SELECT COUNT(*) FROM financial_accounts").fetchone()[0]
        monthly = connection.execute("SELECT COUNT(*) FROM financial_monthly").fetchone()[0]
        transactions = connection.execute("SELECT COUNT(*) FROM financial_transactions").fetchone()[0]
    if accounts or monthly or transactions:
        return None

    result = import_legacy_financials_only(source_dir=source_dir, sqlite_path=sqlite_path)
    return ImportResult(
        owners_imported=0,
        lots_imported=0,
        owner_payments_imported=0,
        lot_payments_imported=0,
        notes_imported=0,
        financial_accounts_imported=result.get("financial_accounts_imported", 0),
        financial_monthly_imported=result.get("financial_monthly_imported", 0),
        financial_transactions_imported=result.get("financial_transactions_imported", 0),
    )
