from __future__ import annotations

from pathlib import Path

from src.db.connection import get_connection
from src.services.pdf_service import build_pdf_path, build_report_story, build_story_pdf, build_table


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
    story.append(build_table(table_rows))
    return build_story_pdf(output_path, story, title=title)
