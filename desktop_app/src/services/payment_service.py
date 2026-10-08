from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import shutil

from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.units import inch

from src.db.connection import get_connection
from src.services.pdf_service import (
    build_pdf_path,
    build_report_story,
    build_story_pdf,
    build_table,
    paragraph,
)


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
PAYMENT_FORM_LABELS = {
    "1": "Check",
    "2": "Cash",
    "3": "Money Order",
    "4": "Services",
    "5": "Tax Sale Adjustment",
    "6": "Private Sale Adjustment",
    "7": "Inheritance Adjustment",
    "8": "Negotiated Adjustment",
    **{code: label for label, code in PAYMENT_FORM_CODES.items()},
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


def payment_form_label(value: object) -> str:
    """Return the familiar payment-form wording for legacy and app codes."""
    code = str(value or "").strip().upper()
    return PAYMENT_FORM_LABELS.get(code, code)


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
    session_id: int | None = None


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
    session_id: int


def _safe_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _money(value: object) -> float:
    return float(Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def _make_backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_{stamp}.sqlite3"
    shutil.copy2(db_path, backup_path)
    return backup_path


def validate_lot_allocation(
    allocation: LotAllocation,
    lot: Mapping[str, object],
    *,
    allow_single_lot_credit: bool = False,
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
    if total > total_due and not allow_single_lot_credit:
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
            SELECT owner_code, total_owed, first_name, last_name,
                   (SELECT COUNT(*) FROM lots WHERE owner_code = owners.owner_code) AS lot_count
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
        allow_single_lot_credit = (
            int(owner["lot_count"] or 0) == 1
            and len(request.allocations) == 1
        )
        if new_owner_total < 0 and not allow_single_lot_credit:
            raise ValueError("Payment amount cannot exceed the owner's total owed.")

        form_code = PAYMENT_FORM_CODES[request.payment_form]
        timestamp = datetime.now().isoformat(timespec="seconds")
        lot_results: list[PaymentLotResult] = []

        connection.execute("BEGIN")
        session_id = request.session_id
        if session_id is None:
            session_id = int(
                connection.execute(
                    """
                    INSERT INTO payment_sessions (created_at, posting_date)
                    VALUES (?, ?)
                    """,
                    [timestamp, request.payment_date],
                ).lastrowid
            )
        else:
            session = connection.execute(
                "SELECT closed_at FROM payment_sessions WHERE id = ?",
                [session_id],
            ).fetchone()
            if session is None or session["closed_at"]:
                raise ValueError("That payment session is already closed. Start a new session.")

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
                    , county_land_trust_flag
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
            applied = validate_lot_allocation(
                allocation,
                dict(lot),
                allow_single_lot_credit=allow_single_lot_credit,
            )
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
                    , county_land_trust_flag = CASE
                        WHEN ? = 'TA' AND ? <= 0 THEN 'N'
                        ELSE county_land_trust_flag
                      END
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
                    form_code,
                    new_total_due,
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
                    , session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    session_id,
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
                , session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                request.owner_code,
                request.payment_amount,
                previous_owner_total,
                request.payment_date,
                form_code,
                request.check_number.strip() or None,
                session_id,
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
        session_id=session_id,
    )


def render_payment_session_deposit_pdf(
    db_path: Path,
    session_id: int,
    output_dir: Path,
    *,
    close_session: bool = True,
) -> Path:
    with get_connection(db_path) as connection:
        session = connection.execute(
            "SELECT * FROM payment_sessions WHERE id = ?",
            [session_id],
        ).fetchone()
        if session is None:
            raise ValueError("Payment session was not found.")
        payments = connection.execute(
            """
            SELECT p.owner_code, p.payment_amount, p.payment_form, p.check_number,
                   p.payment_date, o.first_name, o.last_name,
                   GROUP_CONCAT(a.lot_number, ', ') AS lots,
                   GROUP_CONCAT(DISTINCT a.paid_through) AS paid_through
            FROM owner_payments p
            LEFT JOIN owners o ON o.owner_code = p.owner_code
            LEFT JOIN payment_audit a
              ON a.session_id = p.session_id AND a.owner_code = p.owner_code
             AND a.payment_date = p.payment_date
             AND COALESCE(a.check_number, '') = COALESCE(p.check_number, '')
            WHERE p.session_id = ?
            GROUP BY p.id
            ORDER BY p.id
            """,
            [session_id],
        ).fetchall()
        if not payments:
            raise ValueError("No payments have been recorded in this session.")
        if close_session and not session["closed_at"]:
            connection.execute(
                "UPDATE payment_sessions SET closed_at = ? WHERE id = ?",
                [datetime.now().isoformat(timespec="seconds"), session_id],
            )
            connection.commit()

    total_received = sum(float(row["payment_amount"] or 0) for row in payments)
    deposit_total = sum(
        float(row["payment_amount"] or 0)
        for row in payments
        if str(row["payment_form"] or "").upper() in {"1", "2", "3", "CK", "CS", "MO"}
    )
    rows: list[list[object]] = [["Owner", "Name", "Amount", "Form / Check", "Lots", "Paid Through"]]
    for row in payments:
        name = " ".join(part for part in [row["first_name"], row["last_name"]] if part)
        form = payment_form_label(row["payment_form"])
        if row["check_number"]:
            form = f"{form} {row['check_number']}"
        rows.append(
            [
                str(row["owner_code"] or ""),
                name,
                f"${float(row['payment_amount'] or 0):,.2f}",
                form,
                str(row["lots"] or ""),
                str(row["paid_through"] or ""),
            ]
        )
    story = build_report_story(
        "Payment Session / Deposit Slip",
        [
            "Lake Lafayette Landowners Association, Inc.",
            f"<b>Posting date:</b> {session['posting_date']}",
        ],
    )
    story.append(
        build_table(
            rows,
            [0.65 * inch, 1.75 * inch, 0.85 * inch, 1.45 * inch, 3.0 * inch, 1.35 * inch],
            wrap_cells=True,
            column_alignments=["LEFT", "LEFT", "RIGHT", "LEFT", "LEFT", "LEFT"],
            font_size=8,
        )
    )
    lot_postings = sum(len(str(row["lots"] or "").split(", ")) for row in payments)
    story.extend(
        [
            paragraph(f"<b>Total number of payments:</b> {len(payments)}", small=True),
            paragraph(f"<b>Total number of lot postings:</b> {lot_postings}", small=True),
            paragraph(
                f"<b>Total amount received and recorded:</b> ${total_received:,.2f}",
                small=True,
            ),
            paragraph(
                "<b>Total cash, checks, and money orders for deposit:</b> "
                f"${deposit_total:,.2f}",
                small=True,
            ),
        ]
    )
    output_path = build_pdf_path(output_dir, f"payment_session_{session_id}_deposit_slip")
    return build_story_pdf(
        output_path,
        story,
        title="Payment Session Deposit Slip",
        footer_text="Lake Lafayette Landowners Association - Payment Session Deposit Slip",
        page_size=landscape(LETTER),
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
