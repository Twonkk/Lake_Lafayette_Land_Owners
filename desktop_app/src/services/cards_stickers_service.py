from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil

from src.db.connection import get_connection
from src.services.pdf_service import build_pdf_path, write_preformatted_pages_pdf


@dataclass(slots=True)
class BoatStickerRequest:
    owner_code: str
    lot_number: str
    sticker_year: str
    quantity: int
    amount: float
    notes: str


@dataclass(slots=True)
class IdCardRequest:
    owner_code: str
    lot_number: str
    issue_date: str
    quantity: int
    notes: str
    owner_quantity: int = 0
    renter_quantity: int = 0


@dataclass(slots=True)
class CardStickerResult:
    backup_path: str
    owner_code: str
    lot_number: str
    quantity: int


def default_issue_date() -> str:
    return date.today().isoformat()


def default_sticker_year() -> str:
    return str(date.today().year)


def _make_backup(db_path: Path, suffix: str) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_{suffix}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def record_boat_sticker_purchase(db_path: Path, request: BoatStickerRequest) -> CardStickerResult:
    if not request.owner_code.strip():
        raise ValueError("Select an owner first.")
    if request.quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if request.amount < 0:
        raise ValueError("Amount cannot be negative.")
    if not request.sticker_year.strip():
        raise ValueError("Sticker year is required.")
    try:
        sticker_year = int(request.sticker_year.strip())
    except ValueError as exc:
        raise ValueError("Sticker year must be a four-digit year.") from exc
    if sticker_year < 1900 or sticker_year > 9999:
        raise ValueError("Sticker year must be a four-digit year.")

    with get_connection(db_path) as connection:
        _validate_owner_eligibility(connection, request.owner_code)
        _validate_owner_lot(connection, request.owner_code, request.lot_number)
        id_count = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM id_card_issues
                 WHERE owner_code = ?
                   AND COALESCE(issue_year, CAST(SUBSTR(issue_date, 1, 4) AS INTEGER)) = ?
                   AND CASE
                         WHEN COALESCE(owner_quantity, 0) + COALESCE(renter_quantity, 0) > 0
                           THEN COALESCE(owner_quantity, 0) + COALESCE(renter_quantity, 0)
                         ELSE COALESCE(quantity, 0)
                       END > 0)
              + (SELECT COUNT(*) FROM legacy_id_history
                 WHERE owner_code = ? AND issue_year = ?
                   AND COALESCE(owner_cards, 0) + COALESCE(renter_cards, 0) > 0)
            """,
            [request.owner_code.strip(), sticker_year, request.owner_code.strip(), sticker_year],
        ).fetchone()[0]
        if not id_count:
            raise ValueError(
                f"An ID card record for {request.sticker_year} is required before recording boat stickers."
            )

    backup_path = _make_backup(db_path, "boat_sticker")
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO boat_sticker_purchases (
                created_at,
                owner_code,
                lot_number,
                sticker_year,
                quantity,
                amount,
                notes,
                backup_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                datetime.now().isoformat(timespec="seconds"),
                request.owner_code.strip(),
                request.lot_number.strip().upper() or None,
                request.sticker_year.strip(),
                request.quantity,
                round(request.amount, 2),
                request.notes.strip(),
                str(backup_path),
            ],
        )
        connection.commit()
    return CardStickerResult(str(backup_path), request.owner_code.strip(), request.lot_number.strip().upper(), request.quantity)


def record_id_card_issue(db_path: Path, request: IdCardRequest) -> CardStickerResult:
    if not request.owner_code.strip():
        raise ValueError("Select an owner first.")
    owner_quantity = int(request.owner_quantity or 0)
    renter_quantity = int(request.renter_quantity or 0)
    total_quantity = owner_quantity + renter_quantity
    if total_quantity <= 0:
        total_quantity = int(request.quantity or 0)
        owner_quantity = total_quantity
    if total_quantity <= 0:
        raise ValueError("Enter at least one owner or renter card.")
    if owner_quantity < 0 or renter_quantity < 0:
        raise ValueError("Card quantities cannot be negative.")
    if not request.issue_date.strip():
        raise ValueError("Issue date is required.")

    with get_connection(db_path) as connection:
        _validate_owner_eligibility(connection, request.owner_code)
        _validate_owner_lot(connection, request.owner_code, request.lot_number)

    backup_path = _make_backup(db_path, "id_card")
    try:
        issue_year = int(request.issue_date.strip()[:4])
    except ValueError as exc:
        raise ValueError("Issue date must begin with a four-digit year.") from exc
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO id_card_issues (
                created_at,
                owner_code,
                lot_number,
                issue_date,
                quantity,
                owner_quantity,
                renter_quantity,
                issue_year,
                completed_flag,
                notes,
                backup_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                datetime.now().isoformat(timespec="seconds"),
                request.owner_code.strip(),
                request.lot_number.strip().upper() or None,
                request.issue_date.strip(),
                total_quantity,
                owner_quantity,
                renter_quantity,
                issue_year,
                "N",
                request.notes.strip(),
                str(backup_path),
            ],
        )
        connection.commit()
    return CardStickerResult(str(backup_path), request.owner_code.strip(), request.lot_number.strip().upper(), total_quantity)


def mark_open_id_orders_completed(db_path: Path) -> tuple[int, Path | None]:
    """Mark every currently open legacy/app ID-card order as filled."""
    with get_connection(db_path) as connection:
        legacy_rows = connection.execute(
            """
            SELECT h.id, h.owner_code
            FROM legacy_id_history h
            WHERE UPPER(COALESCE(h.completed_flag, '')) NOT IN ('T', 'Y', 'TRUE')
              AND COALESCE(h.owner_cards, 0) + COALESCE(h.renter_cards, 0) > 0
              AND NOT EXISTS (
                  SELECT 1 FROM id_card_completion_events e
                  WHERE e.source = 'dBase' AND e.source_record_id = h.id
              )
            """
        ).fetchall()
        app_rows = connection.execute(
            """
            SELECT i.id, i.owner_code
            FROM id_card_issues i
            WHERE UPPER(COALESCE(i.completed_flag, 'N')) NOT IN ('T', 'Y', 'TRUE')
              AND CASE
                    WHEN COALESCE(i.owner_quantity, 0) + COALESCE(i.renter_quantity, 0) > 0
                      THEN COALESCE(i.owner_quantity, 0) + COALESCE(i.renter_quantity, 0)
                    ELSE COALESCE(i.quantity, 0)
                  END > 0
              AND NOT EXISTS (
                  SELECT 1 FROM id_card_completion_events e
                  WHERE e.source = 'App' AND e.source_record_id = i.id
              )
            """
        ).fetchall()
    total = len(legacy_rows) + len(app_rows)
    if total == 0:
        return 0, None

    backup_path = _make_backup(db_path, "id_orders_filled")
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as connection:
        connection.execute("BEGIN")
        connection.executemany(
            """
            INSERT OR IGNORE INTO id_card_completion_events (
                created_at, source, source_record_id, owner_code, backup_path
            ) VALUES (?, 'dBase', ?, ?, ?)
            """,
            [(created_at, row["id"], row["owner_code"], str(backup_path)) for row in legacy_rows],
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO id_card_completion_events (
                created_at, source, source_record_id, owner_code, backup_path
            ) VALUES (?, 'App', ?, ?, ?)
            """,
            [(created_at, row["id"], row["owner_code"], str(backup_path)) for row in app_rows],
        )
        if app_rows:
            placeholders = ",".join("?" for _ in app_rows)
            connection.execute(
                f"UPDATE id_card_issues SET completed_flag = 'Y' WHERE id IN ({placeholders})",
                [row["id"] for row in app_rows],
            )
        connection.commit()
    return total, backup_path


def _validate_owner_eligibility(connection, owner_code: str) -> None:
    owner = connection.execute(
        """
        SELECT total_owed, ineligible_flag
        FROM owners
        WHERE owner_code = ?
        """,
        [owner_code.strip()],
    ).fetchone()
    if owner is None:
        raise ValueError("Owner record was not found.")
    if round(float(owner["total_owed"] or 0), 2) > 0:
        raise ValueError("ID cards and boat stickers cannot be issued while the owner has a balance due.")
    if str(owner["ineligible_flag"] or "").strip().upper() == "Y":
        raise ValueError("This owner is marked ineligible for lake privileges.")


def _validate_owner_lot(connection, owner_code: str, lot_number: str) -> None:
    lot = lot_number.strip().upper()
    if not lot:
        raise ValueError("Choose an owner lot.")
    exists = connection.execute(
        "SELECT 1 FROM lots WHERE lot_number = ? AND owner_code = ?",
        [lot, owner_code.strip()],
    ).fetchone()
    if exists is None:
        raise ValueError("The selected lot does not belong to this owner.")


def _owner_name_and_address(db_path: Path, owner_code: str) -> tuple[str, str]:
    with get_connection(db_path) as connection:
        owner = connection.execute(
            """
            SELECT first_name, last_name, address, city, state, zip
            FROM owners
            WHERE owner_code = ?
            """,
            [owner_code],
        ).fetchone()
    if owner is None:
        return owner_code, ""
    name = " ".join(part for part in [owner["first_name"], owner["last_name"]] if part).strip().upper()
    address = "\n".join(
        part for part in [
            str(owner["address"] or "").strip().upper(),
            " ".join(part for part in [owner["city"], owner["state"], owner["zip"]] if part).strip().upper(),
        ] if part
    )
    return name, address


def render_boat_sticker_receipt_pdf(db_path: Path, request: BoatStickerRequest, output_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = build_pdf_path(output_dir, f"boat_sticker_receipt_{stamp}")
    owner_name, address = _owner_name_and_address(db_path, request.owner_code)
    lines = [
        "BOAT STICKER PURCHASE",
        "",
        f"OWNER: {owner_name}",
        f"OWNER CODE: {request.owner_code}",
        f"LOT: {request.lot_number or '-'}",
        f"YEAR: {request.sticker_year}",
        f"BOAT STICKERS: {request.quantity}",
        f"AMOUNT: ${request.amount:,.2f}",
        "",
        "ADDRESS:",
        *(address.splitlines() or ["-"]),
        "",
        "NOTES:",
        request.notes.strip() or "-",
    ]
    return write_preformatted_pages_pdf(file_path, [lines], title="Boat Sticker Receipt")


def render_id_card_receipt_pdf(db_path: Path, request: IdCardRequest, output_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = build_pdf_path(output_dir, f"id_card_receipt_{stamp}")
    owner_name, address = _owner_name_and_address(db_path, request.owner_code)
    lines = [
        "ID CARD ISSUE",
        "",
        f"OWNER: {owner_name}",
        f"OWNER CODE: {request.owner_code}",
        f"LOT: {request.lot_number or '-'}",
        f"ISSUE DATE: {request.issue_date}",
        f"OWNER CARDS: {request.owner_quantity or request.quantity}",
        f"RENTER CARDS: {request.renter_quantity}",
        f"TOTAL CARDS: {(request.owner_quantity or request.quantity) + request.renter_quantity}",
        "",
        "ADDRESS:",
        *(address.splitlines() or ["-"]),
        "",
        "NOTES:",
        request.notes.strip() or "-",
    ]
    return write_preformatted_pages_pdf(file_path, [lines], title="ID Card Receipt")
