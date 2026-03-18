from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
import shutil

from src.db.connection import get_connection
from src.services.pdf_service import convert_html_to_pdf


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
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    if request.quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if not request.issue_date.strip():
        raise ValueError("Issue date is required.")

    backup_path = _make_backup(db_path, "id_card")
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO id_card_issues (
                created_at,
                owner_code,
                lot_number,
                issue_date,
                quantity,
                notes,
                backup_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                datetime.now().isoformat(timespec="seconds"),
                request.owner_code.strip(),
                request.lot_number.strip().upper() or None,
                request.issue_date.strip(),
                request.quantity,
                request.notes.strip(),
                str(backup_path),
            ],
        )
        connection.commit()
    return CardStickerResult(str(backup_path), request.owner_code.strip(), request.lot_number.strip().upper(), request.quantity)


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


def render_boat_sticker_receipt_html(db_path: Path, request: BoatStickerRequest, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = output_dir / f"boat_sticker_receipt_{stamp}.html"
    owner_name, address = _owner_name_and_address(db_path, request.owner_code)
    document = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Boat Sticker Receipt</title>
      <style>
        @page {{ size: letter; margin: 0.6in; }}
        body {{ font-family: "Courier New", Courier, monospace; margin: 0; }}
        .receipt {{ white-space: pre-wrap; font-size: 12pt; line-height: 1.2; }}
      </style>
    </head>
    <body>
      <div class="receipt">{escape(f'''BOAT STICKER PURCHASE\n\nOWNER: {owner_name}\nOWNER CODE: {request.owner_code}\nLOT: {request.lot_number or '-'}\nYEAR: {request.sticker_year}\nQUANTITY: {request.quantity}\nAMOUNT: ${request.amount:,.2f}\n\nADDRESS:\n{address or '-'}\n\nNOTES:\n{request.notes.strip() or '-'}''')}</div>
    </body>
    </html>
    """
    file_path.write_text(document, encoding="utf-8")
    return file_path


def render_id_card_receipt_html(db_path: Path, request: IdCardRequest, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = output_dir / f"id_card_receipt_{stamp}.html"
    owner_name, address = _owner_name_and_address(db_path, request.owner_code)
    document = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>ID Card Receipt</title>
      <style>
        @page {{ size: letter; margin: 0.6in; }}
        body {{ font-family: "Courier New", Courier, monospace; margin: 0; }}
        .receipt {{ white-space: pre-wrap; font-size: 12pt; line-height: 1.2; }}
      </style>
    </head>
    <body>
      <div class="receipt">{escape(f'''ID CARD ISSUE\n\nOWNER: {owner_name}\nOWNER CODE: {request.owner_code}\nLOT: {request.lot_number or '-'}\nISSUE DATE: {request.issue_date}\nQUANTITY: {request.quantity}\n\nADDRESS:\n{address or '-'}\n\nNOTES:\n{request.notes.strip() or '-'}''')}</div>
    </body>
    </html>
    """
    file_path.write_text(document, encoding="utf-8")
    return file_path


def convert_cards_stickers_html_to_pdf(html_path: Path) -> Path:
    return convert_html_to_pdf(html_path, "Failed to convert receipt to PDF.")
