from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil

from src.db.connection import get_connection


@dataclass(slots=True)
class MigrationReviewItem:
    category: str
    record_key: str
    label: str
    summary: str
    details: str
    recommendation: str
    decision: str = ""
    has_candidate: bool = False
    can_delete: bool = False
    current_lot_count: int = 0


@dataclass(slots=True)
class OwnerReviewUpdate:
    owner_code: str
    last_name: str
    first_name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    current_flag: str = "T"
    resident_flag: str = "N"
    hold_mail_flag: str = "N"
    ineligible_flag: str = "N"


def _make_backup(db_path: Path, suffix: str) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_{suffix}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _candidate_score(row) -> tuple[int, int, int]:
    name = str(row["last_name"] or "").strip().upper()
    useful_name = bool(name and name not in {"AAAUNKNOWN", "UNKNOWN", "MISSING OWNER RECORD"})
    current = str(row["current_flag"] or "").strip().upper() in {"T", "Y", "TRUE"}
    primary_file = str(row["source_file"] or "").upper() == "ONERFILE.DBF"
    return (100 if useful_name else 0, 10 if current else 0, 1 if primary_file else 0)


def _best_candidate(connection, owner_code: str):
    rows = connection.execute(
        """
        SELECT * FROM legacy_owner_candidates
        WHERE owner_code = ?
        ORDER BY source_file, source_record_number
        """,
        [owner_code],
    ).fetchall()
    return max(rows, key=_candidate_score) if rows else None


def _decision_map(connection) -> dict[tuple[str, str], str]:
    return {
        (row["category"], row["record_key"]): row["decision"]
        for row in connection.execute(
            "SELECT category, record_key, decision FROM migration_review_decisions"
        ).fetchall()
    }


def _reference_count(connection, owner_code: str) -> int:
    checks = [
        ("lots", "owner_code = ?"),
        ("owner_payments", "owner_code = ?"),
        ("lot_payments", "owner_code = ?"),
        ("notes", "owner_code = ?"),
        ("property_sales", "seller_owner_code = ? OR buyer_owner_code = ?"),
        ("legacy_property_sales", "seller_owner_code = ? OR buyer_owner_code = ?"),
        ("legacy_id_history", "owner_code = ?"),
        ("boat_sticker_purchases", "owner_code = ?"),
        ("id_card_issues", "owner_code = ?"),
        ("encumbrance_events", "owner_code = ?"),
    ]
    total = 0
    for table, where in checks:
        parameters = [owner_code, owner_code] if " OR " in where else [owner_code]
        total += int(
            connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {where}", parameters
            ).fetchone()[0]
        )
    return total


def list_migration_review_items(db_path: Path) -> list[MigrationReviewItem]:
    items: list[MigrationReviewItem] = []
    with get_connection(db_path) as connection:
        decisions = _decision_map(connection)
        placeholders = connection.execute(
            """
            SELECT o.*,
                   (SELECT COUNT(*) FROM lots l WHERE l.owner_code = o.owner_code) AS lot_count,
                   (SELECT GROUP_CONCAT(lot_number, ', ') FROM lots l WHERE l.owner_code = o.owner_code) AS lots,
                   (SELECT COUNT(*) FROM owner_payments p WHERE p.owner_code = o.owner_code)
                     + (SELECT COUNT(*) FROM lot_payments p WHERE p.owner_code = o.owner_code) AS payment_count
            FROM owners o
            WHERE o.status = 'IMPORT REVIEW REQUIRED'
            ORDER BY CASE WHEN COALESCE(o.number_lots, 0) > 0 THEN 0 ELSE 1 END, o.owner_code
            """
        ).fetchall()
        for row in placeholders:
            owner_code = row["owner_code"]
            candidate = _best_candidate(connection, owner_code)
            lot_count = int(row["lot_count"] or 0)
            payment_count = int(row["payment_count"] or 0)
            if candidate:
                candidate_name = " ".join(
                    part for part in [candidate["first_name"], candidate["last_name"]] if part
                ).strip()
                candidate_text = (
                    f"Recoverable candidate: {candidate_name or 'name unavailable'} from "
                    f"{candidate['source_file']} record {candidate['source_record_number']}"
                    f" ({'deleted' if candidate['deleted_flag'] == 'Y' else 'visible'} record)."
                )
            else:
                candidate_text = "No recoverable owner record was found in ONERFILE.DBF or ONERFILE.BAK."
            current_text = "current" if lot_count else "historical"
            summary = (
                f"{current_text.title()} missing owner; {lot_count} current lot(s), "
                f"{payment_count} payment record(s), ${float(row['total_owed'] or 0):,.2f} due."
            )
            details = "\n".join(
                [
                    f"Owner code: {owner_code}",
                    f"Current lots: {row['lots'] or 'none'}",
                    f"Stored primary lot: {row['primary_lot_number'] or 'none'}",
                    candidate_text,
                    "The original dBase files are never changed by this screen.",
                ]
            )
            recommendation = (
                "Confirm and restore the suggested owner record."
                if candidate and lot_count
                else "Enter the current owner's name and address from the deed or closing record."
                if lot_count
                else "Keep this as a historical reference so its payment history remains available."
            )
            items.append(
                MigrationReviewItem(
                    category="missing_owner",
                    record_key=owner_code,
                    label="Missing owner",
                    summary=summary,
                    details=details,
                    recommendation=recommendation,
                    decision=decisions.get(("missing_owner", owner_code), ""),
                    has_candidate=candidate is not None,
                    can_delete=_reference_count(connection, owner_code) == 0,
                    current_lot_count=lot_count,
                )
            )

        x_lots = connection.execute(
            """
            SELECT o.owner_code, o.last_name, o.first_name, o.number_lots,
                   o.primary_lot_number, COUNT(l.lot_number) AS actual_lots
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            WHERE UPPER(TRIM(COALESCE(o.current_flag, ''))) IN ('T', 'Y', 'TRUE')
              AND UPPER(TRIM(COALESCE(o.primary_lot_number, ''))) LIKE 'X%'
            GROUP BY o.owner_code, o.last_name, o.first_name, o.number_lots, o.primary_lot_number
            HAVING COALESCE(o.number_lots, 0) <> COUNT(l.lot_number)
            ORDER BY o.owner_code
            """
        ).fetchall()
        for row in x_lots:
            key = row["owner_code"]
            name = " ".join(part for part in [row["first_name"], row["last_name"]] if part).strip()
            items.append(
                MigrationReviewItem(
                    category="x_lot_exclusion",
                    record_key=key,
                    label="Excluded X lot",
                    summary=(
                        f"{name or 'Owner'} has {row['number_lots']} stored X lot(s); "
                        f"the current assessment file contains {row['actual_lots']}."
                    ),
                    details=(
                        f"Owner code: {key}\nPrimary X lot: {row['primary_lot_number']}\n"
                        "Older dBase backups show these as frozen special lots. The current dBase "
                        "assessment file intentionally omits them."
                    ),
                    recommendation="Accept the X-lot exclusion unless the client wants to recreate these lots manually.",
                    decision=decisions.get(("x_lot_exclusion", key), ""),
                )
            )

        rounding = connection.execute(
            """
            SELECT o.owner_code, o.last_name, o.first_name, o.total_owed,
                   ROUND(COALESCE(SUM(l.total_due), 0), 2) AS lot_total
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            GROUP BY o.owner_code, o.last_name, o.first_name, o.total_owed
            HAVING ROUND(COALESCE(o.total_owed, 0), 2)
                <> ROUND(COALESCE(SUM(l.total_due), 0), 2)
            ORDER BY ABS(ROUND(COALESCE(o.total_owed, 0), 2)
                - ROUND(COALESCE(SUM(l.total_due), 0), 2)) DESC, o.owner_code
            """
        ).fetchall()
        for row in rounding:
            key = row["owner_code"]
            stored = round(float(row["total_owed"] or 0), 2)
            lot_total = round(float(row["lot_total"] or 0), 2)
            difference = round(stored - lot_total, 2)
            name = " ".join(part for part in [row["first_name"], row["last_name"]] if part).strip()
            items.append(
                MigrationReviewItem(
                    category="owner_rounding",
                    record_key=key,
                    label="Balance rounding",
                    summary=(
                        f"{name or 'Owner'}: owner total ${stored:,.2f}; "
                        f"lot total ${lot_total:,.2f}; difference {difference:+.2f}."
                    ),
                    details=(
                        f"Owner code: {key}\nStored dBase owner total: ${stored:,.2f}\n"
                        f"Sum of stored lot balances: ${lot_total:,.2f}\nDifference: {difference:+.2f}"
                    ),
                    recommendation="Use the sum of the lot balances as the accounting total.",
                    decision=decisions.get(("owner_rounding", key), ""),
                )
            )
    return items


def completed_decision_count(db_path: Path) -> int:
    with get_connection(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM migration_review_decisions").fetchone()[0])


def owner_review_defaults(db_path: Path, owner_code: str) -> dict[str, str]:
    with get_connection(db_path) as connection:
        owner = connection.execute(
            "SELECT * FROM owners WHERE owner_code = ?", [owner_code.strip()]
        ).fetchone()
        if owner is None:
            raise ValueError("Owner record was not found.")
        candidate = _best_candidate(connection, owner_code.strip())

        def preferred(field: str, placeholder_values: set[str] | None = None) -> str:
            existing = str(owner[field] or "").strip()
            blocked = placeholder_values or set()
            if candidate is not None and (not existing or existing.upper() in blocked):
                return str(candidate[field] or "").strip()
            return existing

        return {
            "owner_code": owner_code.strip(),
            "last_name": preferred("last_name", {"MISSING OWNER RECORD", "AAAUNKNOWN", "UNKNOWN"}),
            "first_name": preferred("first_name"),
            "address": preferred("address", {"UNKNOWN"}),
            "city": preferred("city"),
            "state": preferred("state"),
            "zip_code": preferred("zip"),
            "phone": preferred("phone"),
            "current_flag": str(owner["current_flag"] or "F"),
            "resident_flag": preferred("resident_flag") or "N",
            "hold_mail_flag": preferred("hold_mail_flag") or "Y",
            "ineligible_flag": preferred("ineligible_flag") or "Y",
        }


def _record_decision(
    connection,
    category: str,
    record_key: str,
    decision: str,
    notes: str,
    backup_path: Path,
) -> None:
    connection.execute(
        """
        INSERT INTO migration_review_decisions (
            category, record_key, decision, notes, decided_at, backup_path
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(category, record_key) DO UPDATE SET
            decision = excluded.decision,
            notes = excluded.notes,
            decided_at = excluded.decided_at,
            backup_path = excluded.backup_path
        """,
        [
            category,
            record_key,
            decision,
            notes.strip(),
            datetime.now().isoformat(timespec="seconds"),
            str(backup_path),
        ],
    )


def restore_suggested_owner(db_path: Path, owner_code: str) -> Path:
    owner_code = owner_code.strip()
    backup_path = _make_backup(db_path, "migration_owner_restore")
    with get_connection(db_path) as connection:
        owner = connection.execute(
            "SELECT * FROM owners WHERE owner_code = ? AND status = 'IMPORT REVIEW REQUIRED'",
            [owner_code],
        ).fetchone()
        if owner is None:
            raise ValueError("That owner no longer requires migration review.")
        candidate = _best_candidate(connection, owner_code)
        if candidate is None:
            raise ValueError("No recoverable owner record is available for this code.")
        current_flag = "T" if int(
            connection.execute(
                "SELECT COUNT(*) FROM lots WHERE owner_code = ?", [owner_code]
            ).fetchone()[0]
        ) else (owner["current_flag"] or "F")
        connection.execute(
            """
            UPDATE owners SET
                last_name = ?, first_name = ?, secondary_owner_flag = ?, note_number = ?,
                address = ?, city = ?, state = ?, zip = ?, phone = ?,
                status = 'MIGRATION REVIEWED', resident_flag = ?, plat = ?,
                current_flag = ?, sale_date = ?, hold_mail_flag = ?, ineligible_flag = ?,
                collection_flag = ?, collection_date = ?, lien_flag = ?
            WHERE owner_code = ?
            """,
            [
                candidate["last_name"], candidate["first_name"], candidate["secondary_owner_flag"],
                candidate["note_number"], candidate["address"], candidate["city"],
                candidate["state"], candidate["zip"], candidate["phone"],
                candidate["resident_flag"] or "N", candidate["plat"], current_flag,
                candidate["sale_date"], candidate["hold_mail_flag"] or "N",
                candidate["ineligible_flag"] or "N", candidate["collection_flag"] or "N",
                candidate["collection_date"], candidate["lien_flag"] or "N", owner_code,
            ],
        )
        _record_decision(
            connection,
            "missing_owner",
            owner_code,
            "restored_suggested_owner",
            f"Restored from {candidate['source_file']} record {candidate['source_record_number']}",
            backup_path,
        )
    return backup_path


def complete_owner_manually(db_path: Path, request: OwnerReviewUpdate) -> Path:
    owner_code = request.owner_code.strip()
    if not request.last_name.strip():
        raise ValueError("Last name is required.")
    backup_path = _make_backup(db_path, "migration_owner_manual")
    with get_connection(db_path) as connection:
        updated = connection.execute(
            """
            UPDATE owners SET
                last_name = ?, first_name = ?, address = ?, city = ?, state = ?, zip = ?,
                phone = ?, status = 'MIGRATION REVIEWED', current_flag = ?, resident_flag = ?,
                hold_mail_flag = ?, ineligible_flag = ?
            WHERE owner_code = ? AND status = 'IMPORT REVIEW REQUIRED'
            """,
            [
                request.last_name.strip().upper(), request.first_name.strip().upper(),
                request.address.strip().upper(), request.city.strip().upper(),
                request.state.strip().upper(), request.zip_code.strip().upper(),
                request.phone.strip(), request.current_flag.strip().upper() or "F",
                request.resident_flag.strip().upper() or "N",
                request.hold_mail_flag.strip().upper() or "N",
                request.ineligible_flag.strip().upper() or "N", owner_code,
            ],
        ).rowcount
        if updated == 0:
            raise ValueError("That owner no longer requires migration review.")
        _record_decision(
            connection, "missing_owner", owner_code, "completed_manually",
            "Owner information entered by the customer during migration review.", backup_path,
        )
    return backup_path


def keep_historical_owner(db_path: Path, owner_code: str) -> Path:
    owner_code = owner_code.strip()
    backup_path = _make_backup(db_path, "migration_owner_historical")
    with get_connection(db_path) as connection:
        if connection.execute(
            "SELECT COUNT(*) FROM lots WHERE owner_code = ?", [owner_code]
        ).fetchone()[0]:
            raise ValueError("This owner still has current lots and cannot be marked historical.")
        updated = connection.execute(
            """
            UPDATE owners SET status = 'HISTORICAL REFERENCE', current_flag = 'F',
                hold_mail_flag = 'Y', ineligible_flag = 'Y'
            WHERE owner_code = ? AND status = 'IMPORT REVIEW REQUIRED'
            """,
            [owner_code],
        ).rowcount
        if updated == 0:
            raise ValueError("That owner no longer requires migration review.")
        _record_decision(
            connection, "missing_owner", owner_code, "kept_as_historical_reference",
            "Kept so imported payment and property history remains connected.", backup_path,
        )
    return backup_path


def delete_unused_placeholder(db_path: Path, owner_code: str) -> Path:
    owner_code = owner_code.strip()
    backup_path = _make_backup(db_path, "migration_owner_delete")
    with get_connection(db_path) as connection:
        if _reference_count(connection, owner_code):
            raise ValueError(
                "This owner is linked to lots, payments, sales, or history and cannot be deleted safely. "
                "Choose Keep as Historical Reference instead."
            )
        deleted = connection.execute(
            "DELETE FROM owners WHERE owner_code = ? AND status = 'IMPORT REVIEW REQUIRED'",
            [owner_code],
        ).rowcount
        if deleted == 0:
            raise ValueError("That unused placeholder was not found.")
        _record_decision(
            connection, "missing_owner", owner_code, "deleted_unused_placeholder",
            "Deleted only after confirming that no records referenced the placeholder.", backup_path,
        )
    return backup_path


def accept_x_lot_exclusion(db_path: Path, owner_code: str) -> Path:
    owner_code = owner_code.strip()
    backup_path = _make_backup(db_path, "migration_x_lot_review")
    with get_connection(db_path) as connection:
        owner = connection.execute(
            "SELECT primary_lot_number FROM owners WHERE owner_code = ?", [owner_code]
        ).fetchone()
        if owner is None or not str(owner["primary_lot_number"] or "").upper().startswith("X"):
            raise ValueError("This is not an excluded X-lot owner.")
        _record_decision(
            connection, "x_lot_exclusion", owner_code, "accepted_current_dbase_exclusion",
            "Customer accepted that the current dBase assessment file excludes these special X lots.",
            backup_path,
        )
    return backup_path


def use_lot_balance_total(db_path: Path, owner_code: str) -> Path:
    owner_code = owner_code.strip()
    backup_path = _make_backup(db_path, "migration_rounding_reconcile")
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT ROUND(COALESCE(SUM(total_due), 0), 2) AS total FROM lots WHERE owner_code = ?",
            [owner_code],
        ).fetchone()
        if connection.execute(
            "SELECT 1 FROM owners WHERE owner_code = ?", [owner_code]
        ).fetchone() is None:
            raise ValueError("Owner record was not found.")
        lot_total = round(float(row["total"] or 0), 2)
        connection.execute(
            "UPDATE owners SET total_owed = ? WHERE owner_code = ?", [lot_total, owner_code]
        )
        _record_decision(
            connection, "owner_rounding", owner_code, "used_lot_balance_total",
            f"Owner total changed to the sum of lot balances: ${lot_total:,.2f}.", backup_path,
        )
    return backup_path


def keep_dbase_owner_total(db_path: Path, owner_code: str) -> Path:
    owner_code = owner_code.strip()
    backup_path = _make_backup(db_path, "migration_rounding_keep")
    with get_connection(db_path) as connection:
        if connection.execute(
            "SELECT 1 FROM owners WHERE owner_code = ?", [owner_code]
        ).fetchone() is None:
            raise ValueError("Owner record was not found.")
        _record_decision(
            connection, "owner_rounding", owner_code, "kept_dbase_owner_total",
            "Customer chose to retain the original dBase owner-level total.", backup_path,
        )
    return backup_path
