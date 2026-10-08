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


@dataclass(slots=True)
class NewOwnerRequest:
    owner_code: str
    last_name: str
    first_name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    resident_flag: str = "N"


@dataclass(slots=True)
class NewLotRequest:
    owner_code: str
    lot_number: str
    current_assessment: float = 0
    delinquent_assessment: float = 0
    delinquent_interest: float = 0
    current_interest: float = 0
    paid_through: str = ""
    development_status: str = "V"
    freeze_flag: str = "N"
    lakefront_flag: str = "N"
    dock_flag: str = "N"
    county_land_trust_flag: str = "N"
    appraised_value: float = 0
    assessed_value: float = 0


def _make_backup(db_path: Path, suffix: str) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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


def create_owner_record(db_path: Path, request: NewOwnerRequest) -> Path:
    owner_code = request.owner_code.strip()
    if not owner_code:
        raise ValueError("Owner code is required.")
    if not request.last_name.strip():
        raise ValueError("Last name is required.")
    backup_path = _make_backup(db_path, "owner_add")
    with get_connection(db_path) as connection:
        if connection.execute("SELECT 1 FROM owners WHERE owner_code = ?", [owner_code]).fetchone():
            raise ValueError("That owner code already exists.")
        connection.execute(
            """
            INSERT INTO owners (
                owner_code, last_name, first_name, address, city, state, zip,
                phone, resident_flag, current_flag, hold_mail_flag,
                ineligible_flag, collection_flag, lien_flag, number_lots,
                total_owed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'T', 'N', 'N', 'N', 'N', 0, 0)
            """,
            [
                owner_code, request.last_name.strip().upper(), request.first_name.strip().upper(),
                request.address.strip().upper(), request.city.strip().upper(), request.state.strip().upper(),
                request.zip_code.strip().upper(), request.phone.strip(),
                request.resident_flag.strip().upper() or "N",
            ],
        )
        connection.commit()
    return backup_path


def create_lot_record(db_path: Path, request: NewLotRequest) -> Path:
    owner_code = request.owner_code.strip()
    lot_number = request.lot_number.strip().upper()
    if not owner_code:
        raise ValueError("Select an owner first.")
    if not lot_number:
        raise ValueError("Lot number is required.")
    amounts = [request.current_assessment, request.delinquent_assessment,
               request.delinquent_interest, request.current_interest]
    if any(value < 0 for value in amounts):
        raise ValueError("Initial assessment amounts cannot be negative.")
    total_due = round(sum(amounts), 2)
    backup_path = _make_backup(db_path, "lot_add")
    with get_connection(db_path) as connection:
        if connection.execute("SELECT 1 FROM owners WHERE owner_code = ?", [owner_code]).fetchone() is None:
            raise ValueError("Owner record was not found.")
        if connection.execute("SELECT 1 FROM lots WHERE lot_number = ?", [lot_number]).fetchone():
            raise ValueError("That lot number already exists.")
        connection.execute(
            """
            INSERT INTO lots (
                lot_number, owner_code, current_assessment, delinquent_assessment,
                delinquent_interest, current_interest, total_due, payment_amount,
                paid_through, lien_flag, lakefront_flag, dock_flag,
                development_status, collection_flag, county_land_trust_flag,
                freeze_flag, appraised_value, assessed_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'N', ?, ?, ?, 'N', ?, ?, ?, ?)
            """,
            [
                lot_number, owner_code, round(request.current_assessment, 2),
                round(request.delinquent_assessment, 2), round(request.delinquent_interest, 2),
                round(request.current_interest, 2), total_due, request.paid_through.strip().upper(),
                request.lakefront_flag.strip().upper() or "N", request.dock_flag.strip().upper() or "N",
                request.development_status.strip().upper() or "V",
                request.county_land_trust_flag.strip().upper() or "N",
                request.freeze_flag.strip().upper() or "N", round(request.appraised_value, 2),
                round(request.assessed_value, 2),
            ],
        )
        summary = connection.execute(
            """
            SELECT COUNT(*) lot_count, MIN(lot_number) primary_lot,
                   ROUND(COALESCE(SUM(total_due), 0), 2) total_owed
            FROM lots WHERE owner_code = ?
            """,
            [owner_code],
        ).fetchone()
        connection.execute(
            """
            UPDATE owners SET number_lots = ?, primary_lot_number = ?, total_owed = ?
            WHERE owner_code = ?
            """,
            [summary["lot_count"], summary["primary_lot"], summary["total_owed"], owner_code],
        )
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
