from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil

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
    legacy_property_sales_imported: int = 0
    legacy_id_history_imported: int = 0
    legacy_collection_lots_imported: int = 0
    legacy_system_history_imported: int = 0
    backup_path: str = ""


REQUIRED_LEGACY_FILES = [
    "ONERFILE.DBF",
    "ASMTFILE.DBF",
    "OPAYFILE.DBF",
    "LPAYFILE.DBF",
    "NOTEFILE.DBF",
    "STDBUDFL.DBF",
    "INEXFILE.DBF",
    "TRANSFIL.DBF",
    "EXLOTFIL.DBF",
    "IDFILE.DBF",
    "CLTRUST.DBF",
    "PERMFILE.DBF",
]

NATIVE_ACTIVITY_LABELS = {
    "payment_audit": "Assessment payment entries",
    "assessment_runs": "Assessment updates",
    "property_sales": "Property sales or reversals",
    "boat_sticker_purchases": "Boat sticker purchases",
    "id_card_issues": "ID cards issued",
    "financial_transactions": "Financial transactions",
}


class NativeActivityError(RuntimeError):
    """Raised when a dBase refresh could erase work entered in this app."""

    def __init__(self, activity: dict[str, int]) -> None:
        self.activity = activity
        super().__init__("Refresh safely stopped to protect work entered in this app.")


def native_activity_counts(sqlite_path: Path) -> dict[str, int]:
    """Return app-native activity that a destructive dBase refresh would replace."""
    tables = [
        "payment_audit",
        "assessment_runs",
        "property_sales",
        "boat_sticker_purchases",
        "id_card_issues",
    ]
    with get_connection(sqlite_path) as connection:
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
        counts["financial_transactions"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM financial_transactions WHERE COALESCE(source, 'legacy') = 'app'"
            ).fetchone()[0]
        )
        return counts


def active_native_activity(sqlite_path: Path) -> dict[str, int]:
    return {
        name: count
        for name, count in native_activity_counts(sqlite_path).items()
        if count
    }


def native_activity_display_lines(activity: dict[str, int]) -> list[str]:
    return [
        f"{NATIVE_ACTIVITY_LABELS.get(name, 'Other app activity')}: {count}"
        for name, count in activity.items()
        if count
    ]


def ensure_legacy_refresh_is_safe(sqlite_path: Path) -> None:
    activity = active_native_activity(sqlite_path)
    if activity:
        raise NativeActivityError(activity)


def _backup_before_import(sqlite_path: Path) -> Path | None:
    if not sqlite_path.exists() or sqlite_path.stat().st_size == 0:
        return None
    backup_dir = sqlite_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{sqlite_path.stem}_before_legacy_import_{stamp}.sqlite3"
    shutil.copy2(sqlite_path, backup_path)
    return backup_path


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


def run_legacy_import(
    source_dir: Path,
    sqlite_path: Path,
    *,
    allow_native_activity: bool = False,
) -> ImportResult:
    if not allow_native_activity:
        ensure_legacy_refresh_is_safe(sqlite_path)
    backup_path = _backup_before_import(sqlite_path)
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
        legacy_property_sales_imported=result.get("legacy_property_sales_imported", 0),
        legacy_id_history_imported=result.get("legacy_id_history_imported", 0),
        legacy_collection_lots_imported=result.get("legacy_collection_lots_imported", 0),
        legacy_system_history_imported=result.get("legacy_system_history_imported", 0),
        backup_path=str(backup_path or ""),
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
