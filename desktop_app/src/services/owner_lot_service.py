from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil

from src.db.connection import get_connection


@dataclass(slots=True)
class OwnerUpdateRequest:
    owner_code: str
    last_name: str
    first_name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone: str
    status: str
    resident_flag: str
    hold_mail_flag: str
    ineligible_flag: str


@dataclass(slots=True)
class LotUpdateRequest:
    lot_number: str
    paid_through: str
    development_status: str
    freeze_flag: str
    lakefront_flag: str
    dock_flag: str
    appraised_value: float
    assessed_value: float
    previous_review_date: str
    last_review_date: str


def _make_backup(db_path: Path, suffix: str) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{suffix}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def update_owner_record(db_path: Path, request: OwnerUpdateRequest) -> Path:
    owner_code = request.owner_code.strip()
    if not owner_code:
        raise ValueError("Owner code is required.")
    if not request.last_name.strip():
        raise ValueError("Last name is required.")

    backup_path = _make_backup(db_path, "owner_edit")
    with get_connection(db_path) as connection:
        updated = connection.execute(
            """
            UPDATE owners
            SET
                last_name = ?,
                first_name = ?,
                address = ?,
                city = ?,
                state = ?,
                zip = ?,
                phone = ?,
                status = ?,
                resident_flag = ?,
                hold_mail_flag = ?,
                ineligible_flag = ?
            WHERE owner_code = ?
            """,
            [
                request.last_name.strip().upper(),
                request.first_name.strip().upper(),
                request.address.strip().upper(),
                request.city.strip().upper(),
                request.state.strip().upper(),
                request.zip_code.strip().upper(),
                request.phone.strip(),
                request.status.strip().upper(),
                request.resident_flag.strip().upper(),
                request.hold_mail_flag.strip().upper(),
                request.ineligible_flag.strip().upper(),
                owner_code,
            ],
        ).rowcount
        if updated == 0:
            raise ValueError("Owner record was not found.")
        connection.commit()
    return backup_path


def update_lot_record(db_path: Path, owner_code: str, request: LotUpdateRequest) -> Path:
    lot_number = request.lot_number.strip().upper()
    if not owner_code.strip():
        raise ValueError("Owner code is required.")
    if not lot_number:
        raise ValueError("Lot number is required.")

    backup_path = _make_backup(db_path, "lot_edit")
    with get_connection(db_path) as connection:
        updated = connection.execute(
            """
            UPDATE lots
            SET
                paid_through = ?,
                development_status = ?,
                freeze_flag = ?,
                lakefront_flag = ?,
                dock_flag = ?,
                appraised_value = ?,
                assessed_value = ?,
                previous_review_date = ?,
                last_review_date = ?
            WHERE lot_number = ? AND owner_code = ?
            """,
            [
                request.paid_through.strip().upper(),
                request.development_status.strip().upper(),
                request.freeze_flag.strip().upper(),
                request.lakefront_flag.strip().upper(),
                request.dock_flag.strip().upper(),
                round(request.appraised_value, 2),
                round(request.assessed_value, 2),
                request.previous_review_date.strip(),
                request.last_review_date.strip(),
                lot_number,
                owner_code.strip(),
            ],
        ).rowcount
        if updated == 0:
            raise ValueError("Lot record was not found for the selected owner.")
        connection.commit()
    return backup_path


def add_owner_note(db_path: Path, owner_code: str, note_text: str, review_date: str | None = None) -> Path:
    owner_code = owner_code.strip()
    note_text = note_text.strip()
    if not owner_code:
        raise ValueError("Owner code is required.")
    if not note_text:
        raise ValueError("Enter a note before saving.")

    backup_path = _make_backup(db_path, "owner_note")
    review_value = (review_date or date.today().isoformat()).strip()
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(note_number), 0) + 1
            FROM notes
            WHERE owner_code = ?
            """,
            [owner_code],
        ).fetchone()
        next_note = int(row[0] or 1)
        connection.execute(
            """
            INSERT INTO notes (
                owner_code,
                note_number,
                note_text,
                review_date
            ) VALUES (?, ?, ?, ?)
            """,
            [owner_code, next_note, note_text, review_value],
        )
        connection.commit()
    return backup_path
