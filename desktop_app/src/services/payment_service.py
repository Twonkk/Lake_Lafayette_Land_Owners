from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import shutil

from src.db.connection import get_connection


PAYMENT_FORM_CODES = {
    "Check": "CK",
    "Cash": "CS",
    "Money Order": "MO",
    "Services": "SV",
    "Tax Sale Adjustment": "TA",
    "Private Sale Adjustment": "PA",
    "Inheritance Adjustment": "IA",
    "Negotiated Adjustment": "NA",
}

PAYMENT_CATEGORY_FIELDS = (
    "current_assessment",
    "current_interest",
    "delinquent_assessment",
    "delinquent_interest",
)
PAYMENT_CATEGORY_LABELS = {
    "current_assessment": "Current assessment",
    "current_interest": "Current interest",
    "delinquent_assessment": "Delinquent assessment",
    "delinquent_interest": "Delinquent interest",
}
MONEY_QUANTUM = Decimal("0.01")


@dataclass(slots=True)
class LotAllocation:
    lot_number: str
    current_assessment: float = 0.0
    current_interest: float = 0.0
    delinquent_assessment: float = 0.0
    delinquent_interest: float = 0.0
    paid_through: str = ""

    @property
    def payment_amount(self) -> float:
        return _money(sum(self.category_amounts().values()))

    def category_amounts(self) -> dict[str, float]:
        return {
            field: _money(getattr(self, field))
            for field in PAYMENT_CATEGORY_FIELDS
        }


@dataclass(slots=True)
class PaymentRequest:
    owner_code: str
    payment_amount: float
    payment_date: str
    payment_form: str
    allocations: list[LotAllocation]
    check_number: str = ""
    note_text: str = ""


@dataclass(slots=True)
class PaymentLotResult:
    lot_number: str
    previous_total_due: float
    new_total_due: float


@dataclass(slots=True)
class PaymentResult:
    backup_path: str
    previous_owner_total: float
    new_owner_total: float
    lot_results: list[PaymentLotResult]


def _safe_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _money(value: object) -> float:
    return float(Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def _make_backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def validate_lot_allocation(
    allocation: LotAllocation,
    lot: Mapping[str, object],
) -> dict[str, float]:
    applied = allocation.category_amounts()
    for field, amount in applied.items():
        if amount < 0:
            raise ValueError(f"{PAYMENT_CATEGORY_LABELS[field]} payment cannot be negative.")
        balance = _money(lot[field])
        if field != "delinquent_assessment" and amount > balance:
            raise ValueError(
                f"{PAYMENT_CATEGORY_LABELS[field]} payment cannot exceed the "
                f"${balance:,.2f} balance for lot {allocation.lot_number}."
            )

    total = allocation.payment_amount
    total_due = _money(lot["total_due"])
    if total <= 0:
        raise ValueError(f"Distribution for lot {allocation.lot_number} must be greater than zero.")
    if total > total_due:
        raise ValueError(
            f"Distribution for lot {allocation.lot_number} cannot exceed its "
            f"${total_due:,.2f} total balance."
        )
    return applied


def post_lot_payment(db_path: Path, request: PaymentRequest) -> PaymentResult:
    if request.payment_amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    if request.payment_form not in PAYMENT_FORM_CODES:
        raise ValueError("Choose a valid payment form.")
    if request.payment_form == "Check" and not request.check_number.strip():
        raise ValueError("A check number is required for check payments.")
    if not request.allocations:
        raise ValueError("Allocate the payment to at least one lot.")

    total_allocated = _money(sum(item.payment_amount for item in request.allocations))
    if total_allocated <= 0:
        raise ValueError("Allocated payment total must be greater than zero.")
    if _money(request.payment_amount) != total_allocated:
        raise ValueError("Payment amount must match the total allocated across lots.")

    backup_path = _make_backup(db_path)

    with get_connection(db_path) as connection:
        owner = connection.execute(
            """
            SELECT owner_code, total_owed, first_name, last_name
            FROM owners
            WHERE owner_code = ?
            """,
            [request.owner_code],
        ).fetchone()
        if owner is None:
            raise ValueError("Owner record not found.")

        previous_owner_total = _money(
            connection.execute(
                "SELECT COALESCE(SUM(total_due), 0) FROM lots WHERE owner_code = ?",
                [request.owner_code],
            ).fetchone()[0]
        )
        new_owner_total = _money(previous_owner_total - request.payment_amount)
        if new_owner_total < 0:
            raise ValueError("Payment amount cannot exceed the owner's total owed.")

        form_code = PAYMENT_FORM_CODES[request.payment_form]
        timestamp = datetime.now().isoformat(timespec="seconds")
        lot_results: list[PaymentLotResult] = []

        connection.execute("BEGIN")

        for allocation in request.allocations:
            lot = connection.execute(
                """
                SELECT
                    lot_number,
                    owner_code,
                    total_due,
                    delinquent_assessment,
                    delinquent_interest,
                    current_assessment,
                    current_interest,
                    paid_through
                FROM lots
                WHERE lot_number = ?
                """,
                [allocation.lot_number],
            ).fetchone()
            if lot is None:
                raise ValueError(f"Lot {allocation.lot_number} was not found.")
            if str(lot["owner_code"] or "") != request.owner_code:
                raise ValueError(f"Lot {allocation.lot_number} does not belong to this owner.")

            previous_total_due = _safe_float(lot["total_due"])
            if previous_total_due <= 0:
                raise ValueError(f"Lot {allocation.lot_number} does not currently have a balance due.")
            applied = validate_lot_allocation(allocation, dict(lot))
            new_delinquent_interest = _money(
                _safe_float(lot["delinquent_interest"]) - applied["delinquent_interest"]
            )
            new_delinquent_assessment = _money(
                _safe_float(lot["delinquent_assessment"]) - applied["delinquent_assessment"]
            )
            new_current_interest = _money(
                _safe_float(lot["current_interest"]) - applied["current_interest"]
            )
            new_current_assessment = _money(
                _safe_float(lot["current_assessment"]) - applied["current_assessment"]
            )
            new_total_due = _money(previous_total_due - allocation.payment_amount)

            connection.execute(
                """
                UPDATE lots
                SET
                    delinquent_interest = ?,
                    delinquent_assessment = ?,
                    current_interest = ?,
                    current_assessment = ?,
                    total_due = ?,
                    payment_amount = ?,
                    pay_date = ?,
                    paid_through = ?,
                    payment_form = ?
                WHERE lot_number = ?
                """,
                [
                    new_delinquent_interest,
                    new_delinquent_assessment,
                    new_current_interest,
                    new_current_assessment,
                    new_total_due,
                    allocation.payment_amount,
                    request.payment_date,
                    allocation.paid_through.strip().upper() or lot["paid_through"],
                    form_code,
                    allocation.lot_number,
                ],
            )
            connection.execute(
                """
                INSERT INTO lot_payments (
                    lot_number,
                    owner_code,
                    payment_amount,
                    payment_date,
                    payment_form,
                    check_number,
                    paid_through,
                    number_lots,
                    delinquent_assessment_1,
                    delinquent_interest_1,
                    current_assessment_1,
                    current_interest_1,
                    delinquent_assessment_2,
                    delinquent_interest_2,
                    current_assessment_2,
                    current_interest_2,
                    total_posted,
                    posted_flag,
                    payment_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    allocation.lot_number,
                    request.owner_code,
                    allocation.payment_amount,
                    request.payment_date,
                    form_code,
                    request.check_number.strip() or None,
                    allocation.paid_through.strip().upper() or lot["paid_through"],
                    len(request.allocations),
                    applied["delinquent_assessment"],
                    applied["delinquent_interest"],
                    applied["current_assessment"],
                    applied["current_interest"],
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    allocation.payment_amount,
                    "Y",
                    form_code,
                ],
            )
            connection.execute(
                """
                INSERT INTO payment_audit (
                    created_at,
                    owner_code,
                    lot_number,
                    payment_amount,
                    payment_date,
                    payment_form,
                    check_number,
                    note_text,
                    paid_through,
                    paid_current_assessment,
                    paid_current_interest,
                    paid_delinquent_assessment,
                    paid_delinquent_interest,
                    backup_path,
                    previous_total_due,
                    new_total_due,
                    previous_owner_total,
                    new_owner_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    timestamp,
                    request.owner_code,
                    allocation.lot_number,
                    allocation.payment_amount,
                    request.payment_date,
                    form_code,
                    request.check_number.strip() or None,
                    request.note_text.strip() or None,
                    allocation.paid_through.strip().upper() or lot["paid_through"],
                    applied["current_assessment"],
                    applied["current_interest"],
                    applied["delinquent_assessment"],
                    applied["delinquent_interest"],
                    str(backup_path),
                    previous_total_due,
                    new_total_due,
                    previous_owner_total,
                    new_owner_total,
                ],
            )
            lot_results.append(
                PaymentLotResult(
                    lot_number=allocation.lot_number,
                    previous_total_due=previous_total_due,
                    new_total_due=new_total_due,
                )
            )

        connection.execute(
            """
            UPDATE owners
            SET total_owed = ?
            WHERE owner_code = ?
            """,
            [new_owner_total, request.owner_code],
        )
        connection.execute(
            """
            INSERT INTO owner_payments (
                owner_code,
                payment_amount,
                total_owed,
                payment_date,
                payment_form,
                check_number
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                request.owner_code,
                request.payment_amount,
                previous_owner_total,
                request.payment_date,
                form_code,
                request.check_number.strip() or None,
            ],
        )
        if request.note_text.strip():
            connection.execute(
                """
                INSERT INTO notes (
                    owner_code,
                    note_number,
                    note_text,
                    review_date
                ) VALUES (?, NULL, ?, ?)
                """,
                [request.owner_code, request.note_text.strip(), request.payment_date],
            )
        connection.commit()

    return PaymentResult(
        backup_path=str(backup_path),
        previous_owner_total=previous_owner_total,
        new_owner_total=new_owner_total,
        lot_results=lot_results,
    )


def default_payment_date() -> str:
    return date.today().isoformat()


def default_paid_through(db_path: Path) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT paid_through
            FROM legacy_system_history
            WHERE TRIM(COALESCE(paid_through, '')) <> ''
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    return str(row["paid_through"] or "") if row is not None else ""
