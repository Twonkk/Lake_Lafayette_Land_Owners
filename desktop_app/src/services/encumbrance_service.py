from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil

from src.db.connection import get_connection


@dataclass(slots=True)
class EncumbranceResult:
    backup_path: str
    owner_code: str
    lot_numbers: list[str]
    action: str


def default_action_date() -> str:
    return date.today().isoformat()


def _make_backup(db_path: Path, suffix: str) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{suffix}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _normalize_lots(lot_numbers: list[str]) -> list[str]:
    return sorted({lot.strip().upper() for lot in lot_numbers if lot.strip()})


def _refresh_owner_flags(connection, owner_code: str) -> None:
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS lot_count,
            COALESCE(SUM(total_due), 0) AS total_owed,
            MIN(lot_number) AS primary_lot,
            MAX(CASE WHEN lien_flag = 'Y' THEN 1 ELSE 0 END) AS has_lien,
            MAX(CASE WHEN collection_flag = 'Y' THEN 1 ELSE 0 END) AS has_collection
        FROM lots
        WHERE owner_code = ?
        """,
        [owner_code],
    ).fetchone()
    connection.execute(
        """
        UPDATE owners
        SET
            number_lots = ?,
            total_owed = ?,
            primary_lot_number = ?,
            lien_flag = ?,
            collection_flag = ?,
            collection_date = CASE WHEN ? = 'Y' THEN collection_date ELSE '' END
        WHERE owner_code = ?
        """,
        [
            int(row["lot_count"] or 0),
            round(float(row["total_owed"] or 0), 2),
            str(row["primary_lot"] or ""),
            "Y" if int(row["has_lien"] or 0) else "N",
            "Y" if int(row["has_collection"] or 0) else "N",
            "Y" if int(row["has_collection"] or 0) else "N",
            owner_code,
        ],
    )


def record_lien(
    db_path: Path,
    owner_code: str,
    lot_numbers: list[str],
    lien_date: str,
    amount: float,
    book: str,
    page: str,
) -> EncumbranceResult:
    lots = _normalize_lots(lot_numbers)
    if not owner_code.strip():
        raise ValueError("Select an owner first.")
    if not lots:
        raise ValueError("Select at least one lot.")
    if not lien_date.strip():
        raise ValueError("Lien date is required.")

    backup_path = _make_backup(db_path, "lien")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        for lot_number in lots:
            connection.execute(
                """
                UPDATE lots
                SET
                    lien_flag = 'Y',
                    lien_on_date = ?,
                    lien_off_date = '',
                    lien_amount = ?,
                    lien_book_page = ?,
                    lien_book = ?,
                    lien_page = ?
                WHERE lot_number = ? AND owner_code = ?
                """,
                [
                    lien_date.strip(),
                    round(amount, 2),
                    f"{book.strip()} {page.strip()}".strip(),
                    int(book) if book.strip().isdigit() else None,
                    int(page) if page.strip().isdigit() else None,
                    lot_number,
                    owner_code.strip(),
                ],
            )
        _refresh_owner_flags(connection, owner_code.strip())
        connection.commit()
    return EncumbranceResult(str(backup_path), owner_code.strip(), lots, "lien_on")


def remove_lien(db_path: Path, owner_code: str, lot_numbers: list[str], off_date: str) -> EncumbranceResult:
    lots = _normalize_lots(lot_numbers)
    if not owner_code.strip():
        raise ValueError("Select an owner first.")
    if not lots:
        raise ValueError("Select at least one lot.")
    if not off_date.strip():
        raise ValueError("Removal date is required.")

    backup_path = _make_backup(db_path, "lien_remove")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        for lot_number in lots:
            connection.execute(
                """
                UPDATE lots
                SET
                    lien_flag = 'N',
                    lien_off_date = ?,
                    lien_amount = 0,
                    lien_book_page = '',
                    lien_book = NULL,
                    lien_page = NULL
                WHERE lot_number = ? AND owner_code = ?
                """,
                [off_date.strip(), lot_number, owner_code.strip()],
            )
        _refresh_owner_flags(connection, owner_code.strip())
        connection.commit()
    return EncumbranceResult(str(backup_path), owner_code.strip(), lots, "lien_off")


def assign_collection(db_path: Path, owner_code: str, lot_numbers: list[str], assigned_date: str) -> EncumbranceResult:
    lots = _normalize_lots(lot_numbers)
    if not owner_code.strip():
        raise ValueError("Select an owner first.")
    if not lots:
        raise ValueError("Select at least one lot.")
    if not assigned_date.strip():
        raise ValueError("Collection date is required.")

    backup_path = _make_backup(db_path, "collection")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        for lot_number in lots:
            connection.execute(
                """
                UPDATE lots
                SET collection_flag = 'Y'
                WHERE lot_number = ? AND owner_code = ?
                """,
                [lot_number, owner_code.strip()],
            )
        connection.execute(
            """
            UPDATE owners
            SET collection_flag = 'Y', collection_date = ?
            WHERE owner_code = ?
            """,
            [assigned_date.strip(), owner_code.strip()],
        )
        _refresh_owner_flags(connection, owner_code.strip())
        connection.execute(
            """
            UPDATE owners
            SET collection_date = ?
            WHERE owner_code = ? AND collection_flag = 'Y'
            """,
            [assigned_date.strip(), owner_code.strip()],
        )
        connection.commit()
    return EncumbranceResult(str(backup_path), owner_code.strip(), lots, "collection_on")


def remove_collection(db_path: Path, owner_code: str, lot_numbers: list[str]) -> EncumbranceResult:
    lots = _normalize_lots(lot_numbers)
    if not owner_code.strip():
        raise ValueError("Select an owner first.")
    if not lots:
        raise ValueError("Select at least one lot.")

    backup_path = _make_backup(db_path, "collection_remove")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        for lot_number in lots:
            connection.execute(
                """
                UPDATE lots
                SET collection_flag = 'N'
                WHERE lot_number = ? AND owner_code = ?
                """,
                [lot_number, owner_code.strip()],
            )
        _refresh_owner_flags(connection, owner_code.strip())
        connection.commit()
    return EncumbranceResult(str(backup_path), owner_code.strip(), lots, "collection_off")
