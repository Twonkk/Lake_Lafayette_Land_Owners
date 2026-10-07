from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil

from src.db.connection import get_connection
from src.services.pdf_service import build_pdf_path, write_preformatted_pages_pdf


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
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_{suffix}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _normalize_lots(lot_numbers: list[str]) -> list[str]:
    return sorted({lot.strip().upper() for lot in lot_numbers if lot.strip()})


def _validate_owner_lots(connection, owner_code: str, lots: list[str]) -> None:
    placeholders = ",".join("?" for _ in lots)
    rows = connection.execute(
        f"SELECT lot_number FROM lots WHERE owner_code = ? AND lot_number IN ({placeholders})",
        [owner_code, *lots],
    ).fetchall()
    found = {str(row["lot_number"]) for row in rows}
    missing = [lot for lot in lots if lot not in found]
    if missing:
        raise ValueError(f"These lots do not belong to the selected owner: {', '.join(missing)}")


def _refresh_owner_flags(connection, owner_code: str) -> None:
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS lot_count,
            COALESCE(SUM(total_due), 0) AS total_owed,
            MIN(lot_number) AS primary_lot,
            MAX(CASE WHEN lien_flag = 'Y' THEN 1 ELSE 0 END) AS has_lien,
            0 AS unused_collection_value
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
            lien_flag = ?
        WHERE owner_code = ?
        """,
        [
            int(row["lot_count"] or 0),
            round(float(row["total_owed"] or 0), 2),
            str(row["primary_lot"] or ""),
            "Y" if int(row["has_lien"] or 0) else "N",
            owner_code,
        ],
    )


def _record_event(
    connection,
    *,
    event_type: str,
    action: str,
    action_date: str,
    owner_code: str,
    lot_number: str | None,
    amount: float = 0,
    book: str = "",
    page: str = "",
    backup_path: Path,
) -> None:
    connection.execute(
        """
        INSERT INTO encumbrance_events (
            created_at, action_date, event_type, action, owner_code,
            lot_number, amount, book, page, backup_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            datetime.now().isoformat(timespec="seconds"),
            action_date.strip(),
            event_type,
            action,
            owner_code.strip(),
            lot_number,
            round(float(amount or 0), 2),
            book.strip() or None,
            page.strip() or None,
            str(backup_path),
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

    with get_connection(db_path) as connection:
        _validate_owner_lots(connection, owner_code.strip(), lots)
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
            _record_event(
                connection,
                event_type="lien",
                action="filed",
                action_date=lien_date,
                owner_code=owner_code,
                lot_number=lot_number,
                amount=amount,
                book=book,
                page=page,
                backup_path=backup_path,
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

    with get_connection(db_path) as connection:
        _validate_owner_lots(connection, owner_code.strip(), lots)
    backup_path = _make_backup(db_path, "lien_remove")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        for lot_number in lots:
            existing = connection.execute(
                """
                SELECT lien_amount, lien_book, lien_page, lien_book_page
                FROM lots
                WHERE lot_number = ? AND owner_code = ?
                """,
                [lot_number, owner_code.strip()],
            ).fetchone()
            connection.execute(
                """
                UPDATE lots
                SET
                    lien_flag = 'N',
                    lien_off_date = ?
                WHERE lot_number = ? AND owner_code = ?
                """,
                [off_date.strip(), lot_number, owner_code.strip()],
            )
            _record_event(
                connection,
                event_type="lien",
                action="removed",
                action_date=off_date,
                owner_code=owner_code,
                lot_number=lot_number,
                amount=float(existing["lien_amount"] or 0) if existing else 0,
                book=str(existing["lien_book"] or "") if existing else "",
                page=str(existing["lien_page"] or "") if existing else "",
                backup_path=backup_path,
            )
        _refresh_owner_flags(connection, owner_code.strip())
        connection.commit()
    return EncumbranceResult(str(backup_path), owner_code.strip(), lots, "lien_off")


def assign_collection(db_path: Path, owner_code: str, lot_numbers: list[str], assigned_date: str) -> EncumbranceResult:
    lots = _normalize_lots(lot_numbers)
    if not owner_code.strip():
        raise ValueError("Select an owner first.")
    if not assigned_date.strip():
        raise ValueError("Collection date is required.")

    backup_path = _make_backup(db_path, "collection")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        updated = connection.execute(
            """
            UPDATE owners
            SET collection_flag = 'Y', collection_date = ?
            WHERE owner_code = ?
            """,
            [assigned_date.strip(), owner_code.strip()],
        ).rowcount
        if not updated:
            raise ValueError("Owner record not found.")
        _refresh_owner_flags(connection, owner_code.strip())
        _record_event(
            connection,
            event_type="collection_agency",
            action="assigned",
            action_date=assigned_date,
            owner_code=owner_code,
            lot_number=None,
            backup_path=backup_path,
        )
        connection.commit()
    return EncumbranceResult(str(backup_path), owner_code.strip(), lots, "collection_on")


def remove_collection(
    db_path: Path,
    owner_code: str,
    lot_numbers: list[str],
    removed_date: str,
) -> EncumbranceResult:
    lots = _normalize_lots(lot_numbers)
    if not owner_code.strip():
        raise ValueError("Select an owner first.")
    if not removed_date.strip():
        raise ValueError("Removal date is required.")

    backup_path = _make_backup(db_path, "collection_remove")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        updated = connection.execute(
            """
            UPDATE owners
            SET collection_flag = 'N', collection_date = ''
            WHERE owner_code = ?
            """,
            [owner_code.strip()],
        ).rowcount
        if not updated:
            raise ValueError("Owner record not found.")
        _refresh_owner_flags(connection, owner_code.strip())
        _record_event(
            connection,
            event_type="collection_agency",
            action="removed",
            action_date=removed_date,
            owner_code=owner_code,
            lot_number=None,
            backup_path=backup_path,
        )
        connection.commit()
    return EncumbranceResult(str(backup_path), owner_code.strip(), lots, "collection_off")


def list_encumbrance_events(db_path: Path, owner_code: str, limit: int = 200) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT action_date, event_type, action, lot_number, amount, book, page
            FROM encumbrance_events
            WHERE owner_code = ?
            ORDER BY action_date DESC, id DESC
            LIMIT ?
            """,
            [owner_code.strip(), limit],
        ).fetchall()
    return [dict(row) for row in rows]


def render_encumbrance_history_pdf(db_path: Path, owner_code: str, output_dir: Path) -> Path:
    events = list_encumbrance_events(db_path, owner_code, limit=1000)
    if not events:
        raise ValueError("No lien or collection events were found for this owner.")
    with get_connection(db_path) as connection:
        owner = connection.execute(
            "SELECT first_name, last_name FROM owners WHERE owner_code = ?",
            [owner_code.strip()],
        ).fetchone()
    name = " ".join(part for part in [owner["first_name"], owner["last_name"]] if part) if owner else ""
    lines = [
        "LIEN AND COLLECTION CHANGE LOG",
        f"OWNER: {owner_code} {name}".strip(),
        "",
        "DATE        TYPE                ACTION      LOT      AMOUNT      BOOK / PAGE",
        "----------  ------------------  ----------  -------  ----------  -----------",
    ]
    for event in events:
        lines.append(
            f"{str(event['action_date'] or ''):<10}  {str(event['event_type'] or '')[:18]:<18}  "
            f"{str(event['action'] or '')[:10]:<10}  {str(event['lot_number'] or ''):<7}  "
            f"{float(event['amount'] or 0):>10.2f}  "
            f"{str(event['book'] or '')} {str(event['page'] or '')}".rstrip()
        )
    output_path = build_pdf_path(output_dir, f"lien_collection_log_{owner_code}")
    return write_preformatted_pages_pdf(output_path, [lines], title="Lien and Collection Log")
