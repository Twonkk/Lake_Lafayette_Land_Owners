from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import shutil

from src.db.connection import get_connection


EXEMPT_OWNER_CODES = {"2489", "2642", "2959"}
INTEREST_RATE = 0.035


@dataclass(slots=True)
class AssessmentPreview:
    assessment_amount: float
    eligible_lots: int
    exempt_lots: int
    freeze_lots: int
    owner_count: int
    projected_current_assessment: float


@dataclass(slots=True)
class AssessmentResult:
    backup_path: str
    lots_updated: int
    owners_updated: int
    exempt_lots: int
    freeze_lots: int


def default_assessment_date() -> str:
    return date.today().isoformat()


def _safe_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _make_backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_assessment_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def preview_assessment_run(db_path: Path, assessment_amount: float) -> AssessmentPreview:
    if assessment_amount <= 0:
        raise ValueError("Assessment amount must be greater than zero.")

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT lot_number, owner_code, current_assessment, freeze_flag
            FROM lots
            """
        ).fetchall()

    eligible_lots = 0
    exempt_lots = 0
    freeze_lots = 0
    owner_codes: set[str] = set()
    projected_current = 0.0

    for row in rows:
        owner_code = str(row["owner_code"] or "")
        if owner_code in EXEMPT_OWNER_CODES:
            exempt_lots += 1
            continue
        owner_codes.add(owner_code)
        eligible_lots += 1
        if row["freeze_flag"] == "Y":
            freeze_lots += 1
            projected_current += _safe_float(row["current_assessment"])
        else:
            projected_current += assessment_amount

    return AssessmentPreview(
        assessment_amount=assessment_amount,
        eligible_lots=eligible_lots,
        exempt_lots=exempt_lots,
        freeze_lots=freeze_lots,
        owner_count=len(owner_codes),
        projected_current_assessment=round(projected_current, 2),
    )


def apply_assessment_run(db_path: Path, assessment_amount: float, assessment_date: str) -> AssessmentResult:
    preview = preview_assessment_run(db_path, assessment_amount)
    backup_path = _make_backup(db_path)
    created_at = datetime.now().isoformat(timespec="seconds")

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                lot_number,
                owner_code,
                delinquent_assessment,
                delinquent_interest,
                current_assessment,
                current_interest,
                total_due,
                freeze_flag,
                previous_review_date,
                last_review_date
            FROM lots
            ORDER BY lot_number
            """
        ).fetchall()

        lot_updates = []
        lots_updated = 0

        for row in rows:
            owner_code = str(row["owner_code"] or "")
            if owner_code in EXEMPT_OWNER_CODES:
                if _safe_float(row["total_due"]) != 0:
                    lot_updates.append(
                        (
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                            assessment_date,
                            assessment_date,
                            row["lot_number"],
                        )
                    )
                    lots_updated += 1
                continue

            delinquent_interest = round(
                _safe_float(row["delinquent_interest"]) + _safe_float(row["current_interest"]), 2
            )
            if row["freeze_flag"] == "Y":
                current_interest = 0.0
                current_assessment = _safe_float(row["current_assessment"]) + assessment_amount
                delinquent_assessment = _safe_float(row["delinquent_assessment"])
            else:
                delinquent_assessment = round(
                    _safe_float(row["delinquent_assessment"]) + _safe_float(row["current_assessment"]),
                    2,
                )
                total_delinquent = round(delinquent_assessment + delinquent_interest, 2)
                current_interest = round(INTEREST_RATE * total_delinquent, 2) if total_delinquent > 0 else 0.0
                current_assessment = round(assessment_amount, 2)

            total_due = round(delinquent_assessment + delinquent_interest + current_interest + current_assessment, 2)
            lot_updates.append(
                (
                    delinquent_assessment,
                    delinquent_interest,
                    current_interest,
                    current_assessment,
                    total_due,
                    row["last_review_date"] or assessment_date,
                    assessment_date,
                    row["lot_number"],
                )
            )
            lots_updated += 1

        connection.execute("BEGIN")
        connection.executemany(
            """
            UPDATE lots
            SET
                delinquent_assessment = ?,
                delinquent_interest = ?,
                current_interest = ?,
                current_assessment = ?,
                total_due = ?,
                payment_amount = 0,
                previous_review_date = ?,
                last_review_date = ?
            WHERE lot_number = ?
            """,
            lot_updates,
        )

        owner_rows = connection.execute(
            """
            SELECT owner_code
            FROM owners
            ORDER BY owner_code
            """
        ).fetchall()
        owners_updated = 0
        for owner in owner_rows:
            owner_code = owner["owner_code"]
            total_owed = connection.execute(
                """
                SELECT COALESCE(SUM(total_due), 0)
                FROM lots
                WHERE owner_code = ?
                """,
                [owner_code],
            ).fetchone()[0]
            changed = connection.execute(
                """
                UPDATE owners
                SET total_owed = ?
                WHERE owner_code = ? AND COALESCE(total_owed, 0) <> ?
                """,
                [total_owed, owner_code, total_owed],
            ).rowcount
            owners_updated += changed

        connection.execute(
            """
            INSERT INTO assessment_runs (
                created_at,
                assessment_amount,
                assessment_date,
                backup_path,
                lots_updated,
                owners_updated,
                excluded_lots,
                freeze_lots,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                created_at,
                assessment_amount,
                assessment_date,
                str(backup_path),
                lots_updated,
                owners_updated,
                preview.exempt_lots,
                preview.freeze_lots,
                "Legacy-style assessment roll-forward",
            ],
        )
        connection.commit()

    return AssessmentResult(
        backup_path=str(backup_path),
        lots_updated=lots_updated,
        owners_updated=owners_updated,
        exempt_lots=preview.exempt_lots,
        freeze_lots=preview.freeze_lots,
    )
