from __future__ import annotations

from html import escape
from pathlib import Path
import re

from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.units import inch

from src.db.connection import get_connection
from src.services.pdf_service import build_pdf_path, build_report_story, build_story_pdf, build_table
from src.services.payment_service import payment_form_label


def _search_term(query: str) -> str:
    return f"%{query.strip()}%" if query.strip() else "%"


def search_lot_payment_history(db_path: Path, query: str, limit: int = 2000) -> list[dict]:
    term = _search_term(query)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT p.id, p.payment_date, p.lot_number, p.owner_code,
                   p.payment_amount, p.payment_form, p.check_number,
                   p.paid_through, p.delinquent_assessment_1,
                   p.delinquent_interest_1, p.current_assessment_1,
                   p.current_interest_1, p.total_posted,
                   o.last_name, o.first_name
            FROM lot_payments p
            LEFT JOIN owners o ON o.owner_code = p.owner_code
            WHERE p.lot_number LIKE ? OR p.owner_code LIKE ?
               OR p.payment_date LIKE ? OR p.check_number LIKE ?
               OR o.last_name LIKE ? OR o.first_name LIKE ?
            ORDER BY p.payment_date DESC, p.id DESC
            LIMIT ?
            """,
            [term, term, term, term, term, term, limit],
        ).fetchall()
    return [dict(row) for row in rows]


def search_ownership_history(db_path: Path, query: str, limit: int = 2000) -> list[dict]:
    term = _search_term(query)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM (
                SELECT 'dBase' AS source, id, sale_date, lot_number,
                       seller_owner_code, buyer_owner_code, entered_date,
                       '' AS status
                FROM legacy_property_sales
                UNION ALL
                SELECT 'App' AS source, id, sale_date, lot_number,
                       seller_owner_code, buyer_owner_code, created_at AS entered_date,
                       CASE WHEN reversed_at IS NULL THEN 'Completed' ELSE 'Reversed' END AS status
                FROM property_sales
            ) h
            WHERE h.lot_number LIKE ? OR h.seller_owner_code LIKE ?
               OR h.buyer_owner_code LIKE ? OR h.sale_date LIKE ?
            ORDER BY h.sale_date DESC, h.id DESC
            LIMIT ?
            """,
            [term, term, term, term, limit],
        ).fetchall()
    return [dict(row) for row in rows]


def search_id_boat_history(db_path: Path, query: str, limit: int = 2000) -> list[dict]:
    term = _search_term(query)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM (
                SELECT 'dBase' AS source, 'ID / Boat' AS record_type, id,
                       owner_code, last_name, lot_number,
                       COALESCE(CAST(issue_year AS TEXT), '') AS record_year,
                       issue_date AS record_date, owner_cards, renter_cards,
                       boat_stickers, completed_flag
                FROM legacy_id_history
                UNION ALL
                SELECT 'App' AS source, 'ID Card' AS record_type, i.id,
                       i.owner_code, COALESCE(o.last_name, ''), i.lot_number,
                       COALESCE(CAST(i.issue_year AS TEXT), SUBSTR(i.issue_date, 1, 4)),
                       i.issue_date,
                       CASE
                         WHEN COALESCE(i.owner_quantity, 0) + COALESCE(i.renter_quantity, 0) > 0
                           THEN COALESCE(i.owner_quantity, 0)
                         ELSE COALESCE(i.quantity, 0)
                       END,
                       COALESCE(i.renter_quantity, 0), 0, i.completed_flag
                FROM id_card_issues i
                LEFT JOIN owners o ON o.owner_code = i.owner_code
                UNION ALL
                SELECT 'App' AS source, 'Boat Sticker' AS record_type, b.id,
                       b.owner_code, COALESCE(o.last_name, ''), b.lot_number,
                       b.sticker_year, SUBSTR(b.created_at, 1, 10), 0, 0,
                       b.quantity, 'Y'
                FROM boat_sticker_purchases b
                LEFT JOIN owners o ON o.owner_code = b.owner_code
            ) h
            WHERE h.owner_code LIKE ? OR h.last_name LIKE ?
               OR h.lot_number LIKE ? OR h.record_year LIKE ?
               OR h.record_date LIKE ?
            ORDER BY h.record_date DESC, h.id DESC
            LIMIT ?
            """,
            [term, term, term, term, term, limit],
        ).fetchall()
    return [dict(row) for row in rows]


def render_history_pdf(
    output_dir: Path,
    title: str,
    headings: list[str],
    rows: list[list[object]],
) -> Path:
    output_path = build_pdf_path(output_dir, title.lower().replace(" ", "_"))
    story = build_report_story(title)
    table_rows = [headings, *rows]
    if not rows:
        table_rows.append(["No matching records.", *([""] * (len(headings) - 1))])

    page_size = landscape(LETTER) if len(headings) >= 6 else LETTER
    usable_width = (page_size[0] - (1.1 * inch)) / inch
    heading_weights = {
        "date": 0.85,
        "owner": 0.58,
        "name": 1.85,
        "owed": 0.75,
        "paid": 0.72,
        "form": 1.15,
        "check": 0.78,
        "lot": 0.55,
        "through": 0.8,
        "seller": 0.72,
        "buyer": 0.72,
        "entered": 0.95,
        "status": 0.72,
        "type": 0.9,
        "owner cards": 0.72,
        "renter cards": 0.72,
        "boat": 0.48,
        "source": 0.62,
    }
    weights = [heading_weights.get(str(heading).strip().lower(), 1.0) for heading in headings]
    scale = usable_width / sum(weights)
    widths = [weight * scale * inch for weight in weights]
    numeric_headings = {"owed", "paid", "owner cards", "renter cards", "boat"}
    alignments = [
        "RIGHT" if str(heading).strip().lower() in numeric_headings else "LEFT"
        for heading in headings
    ]
    story.append(
        build_table(
            table_rows,
            widths,
            wrap_cells=True,
            column_alignments=alignments,
            font_size=7.5 if len(headings) >= 7 else 8,
        )
    )
    return build_story_pdf(
        output_path,
        story,
        title=title,
        footer_text=f"Lake Lafayette Landowners Association - {title}",
        page_size=page_size,
    )


def get_owner_payment_history(db_path: Path, owner_code: str) -> dict:
    """Return one owner's current identity and complete owner-level payment history."""
    normalized_code = owner_code.strip()
    if not normalized_code:
        raise ValueError("An owner code is required.")

    with get_connection(db_path) as connection:
        owner_row = connection.execute(
            """
            SELECT owner_code, last_name, first_name, address, city, state, zip, total_owed
            FROM owners
            WHERE owner_code = ?
            """,
            [normalized_code],
        ).fetchone()
        lot_rows = connection.execute(
            """
            SELECT lot_number
            FROM lots
            WHERE owner_code = ?
            ORDER BY lot_number
            """,
            [normalized_code],
        ).fetchall()
        payment_rows = connection.execute(
            """
            SELECT id, payment_date, total_owed, payment_amount, payment_form, check_number
            FROM owner_payments
            WHERE owner_code = ?
            ORDER BY payment_date DESC, id DESC
            """,
            [normalized_code],
        ).fetchall()

    owner = dict(owner_row) if owner_row is not None else {
        "owner_code": normalized_code,
        "last_name": "",
        "first_name": "",
        "address": "",
        "city": "",
        "state": "",
        "zip": "",
        "total_owed": 0,
    }
    return {
        "owner": owner,
        "lot_numbers": [row["lot_number"] for row in lot_rows],
        "payments": [dict(row) for row in payment_rows],
    }


def render_owner_payment_history_pdf(db_path: Path, output_dir: Path, owner_code: str) -> Path:
    """Create a printable PDF limited to one owner's complete payment history."""
    detail = get_owner_payment_history(db_path, owner_code)
    owner = detail["owner"]
    payments = detail["payments"]

    name = " ".join(
        part for part in [owner.get("first_name") or "", owner.get("last_name") or ""] if part
    ).strip() or "Name unavailable"
    city_line = " ".join(
        part for part in [owner.get("city") or "", owner.get("state") or "", owner.get("zip") or ""] if part
    ).strip()
    address = ", ".join(
        part for part in [owner.get("address") or "", city_line] if part
    ) or "Not available"
    lots = ", ".join(detail["lot_numbers"]) or "None listed"
    total_paid = sum(float(row["payment_amount"] or 0) for row in payments)

    safe_code = re.sub(r"[^A-Za-z0-9_-]+", "_", str(owner["owner_code"])).strip("_") or "owner"
    output_path = build_pdf_path(output_dir, f"owner_{safe_code}_payment_history")
    story = build_report_story(
        "Individual Payment History",
        [
            f"<b>Owner:</b> {escape(str(owner['owner_code']))} - {escape(name)}",
            f"<b>Mailing address:</b> {escape(address)}",
            f"<b>Current lots:</b> {escape(lots)}",
            (
                f"<b>Payment records:</b> {len(payments):,} &nbsp;&nbsp; "
                f"<b>Total recorded payments:</b> ${total_paid:,.2f} &nbsp;&nbsp; "
                f"<b>Current balance:</b> ${float(owner.get('total_owed') or 0):,.2f}"
            ),
        ],
    )
    rows = [
        [
            row["payment_date"] or "",
            f"${float(row['total_owed'] or 0):,.2f}",
            f"${float(row['payment_amount'] or 0):,.2f}",
            payment_form_label(row["payment_form"]),
            row["check_number"] or "",
        ]
        for row in payments
    ]
    if not rows:
        rows.append(["No payment history found.", "", "", "", ""])
    story.append(
        build_table(
            [["Date", "Owed Before", "Paid", "Payment Form", "Check / Reference"], *rows],
            [0.9 * inch, 1.05 * inch, 0.95 * inch, 1.75 * inch, 1.75 * inch],
            wrap_cells=True,
            column_alignments=["LEFT", "RIGHT", "RIGHT", "LEFT", "LEFT"],
        )
    )
    return build_story_pdf(
        output_path,
        story,
        title=f"Payment History - Owner {owner['owner_code']}",
        footer_text="Lake Lafayette Landowners Association - Individual Payment History",
    )
