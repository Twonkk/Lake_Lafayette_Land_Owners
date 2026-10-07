from __future__ import annotations

from pathlib import Path

from reportlab.lib.units import inch
from reportlab.platypus import Spacer, TableStyle

from src.db.connection import get_connection
from src.services.pdf_service import (
    build_pdf_path,
    build_report_story,
    build_story_pdf,
    build_table,
    page_break,
    paragraph,
)


def render_owner_report_pdf(db_path: Path, output_dir: Path) -> Path:
    with get_connection(db_path) as connection:
        owners = connection.execute(
            """
            SELECT
                o.owner_code,
                o.last_name,
                o.first_name,
                o.address,
                o.city,
                o.state,
                o.zip,
                o.phone,
                o.number_lots,
                o.total_owed,
                o.lien_flag,
                o.resident_flag
            FROM owners o
            WHERE UPPER(TRIM(COALESCE(o.current_flag, ''))) IN ('T', 'Y', 'TRUE')
            ORDER BY o.last_name, o.first_name, o.owner_code
            """
        ).fetchall()

        rows: list[list[object]] = [[
            "Code",
            "Name",
            "Address",
            "City/State/ZIP",
            "Phone",
            "Lots",
            "Resident",
            "Lien",
            "Owned Lots",
            "Total Owed",
        ]]
        for owner in owners:
            lots = connection.execute(
                """
                SELECT lot_number
                FROM lots
                WHERE owner_code = ?
                ORDER BY lot_number
                """,
                [owner["owner_code"]],
            ).fetchall()
            city_line = " ".join(
                part
                for part in [
                    str(owner["city"] or "").strip(),
                    str(owner["state"] or "").strip(),
                    str(owner["zip"] or "").strip(),
                ]
                if part
            )
            rows.append(
                [
                    str(owner["owner_code"] or ""),
                    " ".join(part for part in [owner["last_name"], owner["first_name"]] if part).strip(),
                    str(owner["address"] or ""),
                    city_line,
                    str(owner["phone"] or ""),
                    str(int(owner["number_lots"] or 0)),
                    str(owner["resident_flag"] or ""),
                    str(owner["lien_flag"] or ""),
                    ", ".join(row["lot_number"] for row in lots),
                    f"{float(owner['total_owed'] or 0):,.2f}",
                ]
            )

    output_path = build_pdf_path(output_dir, "owner_report")
    story = build_report_story("Owner Report")
    table = build_table(
        rows,
        [0.55 * inch, 1.2 * inch, 1.45 * inch, 1.2 * inch, 0.8 * inch, 0.38 * inch, 0.5 * inch, 0.4 * inch, 1.45 * inch, 0.72 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (5, 1), (7, -1), "CENTER"),
                ("ALIGN", (9, 1), (9, -1), "RIGHT"),
            ]
        )
    )
    story.append(table)
    return build_story_pdf(output_path, story, title="Owner Report")


def render_lot_report_pdf(db_path: Path, output_dir: Path) -> Path:
    with get_connection(db_path) as connection:
        lots = connection.execute(
            """
            SELECT
                l.lot_number,
                l.owner_code,
                o.last_name,
                o.first_name,
                o.address,
                o.phone,
                l.lien_flag,
                l.county_land_trust_flag,
                l.total_due,
                l.current_assessment,
                l.delinquent_assessment,
                l.delinquent_interest,
                l.current_interest
            FROM lots l
            LEFT JOIN owners o ON o.owner_code = l.owner_code
            ORDER BY l.lot_number
            """
        ).fetchall()

    rows: list[list[object]] = [[
        "Lot",
        "Owner Code",
        "Owner",
        "Address",
        "Phone",
        "Lien",
        "County Trust",
        "Delinq. Assess.",
        "Delinq. Interest",
        "Current Assess.",
        "Current Interest",
        "Total Due",
    ]]
    for lot in lots:
        rows.append(
            [
                str(lot["lot_number"] or ""),
                str(lot["owner_code"] or ""),
                " ".join(part for part in [lot["last_name"], lot["first_name"]] if part).strip(),
                str(lot["address"] or ""),
                str(lot["phone"] or ""),
                str(lot["lien_flag"] or ""),
                str(lot["county_land_trust_flag"] or ""),
                f"{float(lot['delinquent_assessment'] or 0):,.2f}",
                f"{float(lot['delinquent_interest'] or 0):,.2f}",
                f"{float(lot['current_assessment'] or 0):,.2f}",
                f"{float(lot['current_interest'] or 0):,.2f}",
                f"{float(lot['total_due'] or 0):,.2f}",
            ]
        )

    output_path = build_pdf_path(output_dir, "lot_report")
    story = build_report_story("Lot Report")
    table = build_table(
        rows,
        [0.42 * inch, 0.6 * inch, 1.0 * inch, 1.0 * inch, 0.7 * inch, 0.35 * inch, 0.5 * inch, 0.6 * inch, 0.62 * inch, 0.62 * inch, 0.62 * inch, 0.62 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (5, 1), (6, -1), "CENTER"),
                ("ALIGN", (7, 1), (11, -1), "RIGHT"),
            ]
        )
    )
    story.append(table)
    return build_story_pdf(output_path, story, title="Lot Report")


def render_mailing_labels_pdf(
    db_path: Path,
    output_dir: Path,
    *,
    resident_filter: str = "All",
    lien_only: bool = False,
) -> Path:
    with get_connection(db_path) as connection:
        owners = connection.execute(
            """
            SELECT
                owner_code,
                primary_lot_number,
                last_name,
                first_name,
                address,
                city,
                state,
                zip
            FROM owners
            WHERE TRIM(COALESCE(address, '')) <> ''
              AND UPPER(TRIM(COALESCE(address, ''))) <> 'UNKNOWN'
              AND UPPER(TRIM(COALESCE(last_name, ''))) <> 'LL CO'
              AND (? = 'All'
                   OR (? = 'Residents' AND UPPER(COALESCE(resident_flag, '')) = 'Y')
                   OR (? = 'Nonresidents' AND UPPER(COALESCE(resident_flag, '')) <> 'Y'))
              AND (? = 0 OR UPPER(COALESCE(lien_flag, '')) = 'Y')
            ORDER BY last_name, first_name, owner_code
            """,
            [resident_filter, resident_filter, resident_filter, 1 if lien_only else 0],
        ).fetchall()

    output_path = build_pdf_path(output_dir, "mailing_labels")
    story = []
    labels_per_page = 9
    current_page = 0
    for index, owner in enumerate(owners):
        name = " ".join(part for part in [owner["first_name"], owner["last_name"]] if part).strip().upper()
        address = str(owner["address"] or "").strip().upper()
        city_line = " ".join(
            part
            for part in [owner["city"], owner["state"], owner["zip"]]
            if str(part or "").strip()
        ).strip().upper()
        top_line = f"{str(owner['primary_lot_number'] or '').strip().upper():<8}{str(owner['owner_code'] or '').strip().upper():>10}".rstrip()
        story.append(paragraph(top_line, small=True))
        story.append(paragraph(name, small=True))
        story.append(paragraph(address or "-", small=True))
        story.append(paragraph(city_line or "-", small=True))
        current_page += 1
        if current_page < labels_per_page and index != len(owners) - 1:
            story.append(Spacer(1, 0.22 * inch))
        elif index != len(owners) - 1:
            story.append(Spacer(1, 0.05 * inch))
            story.append(page_break())
            current_page = 0

    return build_story_pdf(
        output_path,
        story,
        title="Mailing Labels",
        left_margin=0.12 * inch,
        right_margin=4.0 * inch,
        top_margin=0.3 * inch,
        bottom_margin=0.3 * inch,
    )


def render_voter_list_pdf(db_path: Path, output_dir: Path) -> Path:
    excluded_codes = ("2489", "2642", "2959")
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT owner_code, last_name, first_name, city, state,
                   number_lots, primary_lot_number
            FROM owners
            WHERE UPPER(TRIM(COALESCE(current_flag, ''))) IN ('T', 'Y', 'TRUE')
              AND ROUND(COALESCE(total_owed, 0), 2) <= 0
              AND UPPER(COALESCE(ineligible_flag, '')) <> 'Y'
              AND owner_code NOT IN (?, ?, ?)
              AND UPPER(SUBSTR(COALESCE(primary_lot_number, ''), 1, 1)) <> 'X'
            ORDER BY last_name, first_name, owner_code
            """,
            excluded_codes,
        ).fetchall()
    table_rows = [["Votes", "Owner", "City", "State", "Lots"]]
    for row in rows:
        table_rows.append([
            str(int(row["number_lots"] or 0)),
            " ".join(part for part in [row["last_name"], row["first_name"]] if part),
            str(row["city"] or ""), str(row["state"] or ""),
            str(int(row["number_lots"] or 0)),
        ])
    output_path = build_pdf_path(output_dir, "eligible_voter_list")
    story = build_report_story("List of Owners Eligible to Vote")
    story.append(build_table(table_rows))
    return build_story_pdf(output_path, story, title="Eligible Voter List")


def render_custom_owner_report_pdf(
    db_path: Path,
    output_dir: Path,
    *,
    zip_code: str = "",
    resident_filter: str = "All",
    lien_filter: str = "All",
    collection_filter: str = "All",
    unknown_only: bool = False,
    minimum_owed: float | None = None,
    maximum_owed: float | None = None,
) -> Path:
    with get_connection(db_path) as connection:
        owners = connection.execute(
            """
            SELECT o.*,
                   GROUP_CONCAT(l.lot_number, ', ') AS owned_lots
            FROM owners o
            LEFT JOIN lots l ON l.owner_code = o.owner_code
            WHERE UPPER(TRIM(COALESCE(o.current_flag, ''))) IN ('T', 'Y', 'TRUE')
            GROUP BY o.owner_code
            ORDER BY o.last_name, o.first_name, o.owner_code
            """
        ).fetchall()

    filtered = []
    for row in owners:
        if zip_code.strip() and str(row["zip"] or "").strip() != zip_code.strip():
            continue
        resident = str(row["resident_flag"] or "").upper() == "Y"
        if resident_filter == "Residents" and not resident:
            continue
        if resident_filter == "Nonresidents" and resident:
            continue
        lien = str(row["lien_flag"] or "").upper() == "Y"
        if lien_filter == "With lien" and not lien:
            continue
        if lien_filter == "Without lien" and lien:
            continue
        collection = str(row["collection_flag"] or "").upper() == "Y"
        if collection_filter == "In collection" and not collection:
            continue
        if collection_filter == "Not in collection" and collection:
            continue
        address_unknown = str(row["address"] or "").strip().upper() == "UNKNOWN"
        if unknown_only and not address_unknown:
            continue
        owed = float(row["total_owed"] or 0)
        if minimum_owed is not None and owed < minimum_owed:
            continue
        if maximum_owed is not None and owed > maximum_owed:
            continue
        filtered.append(row)

    table_rows = [["Code", "Owner", "Address", "Phone", "Lots", "Owed", "Lien", "Collection", "Resident"]]
    for row in filtered:
        table_rows.append([
            row["owner_code"],
            " ".join(part for part in [row["last_name"], row["first_name"]] if part),
            " ".join(part for part in [row["address"], row["city"], row["state"], row["zip"]] if part),
            row["phone"] or "", row["owned_lots"] or "",
            f"{float(row['total_owed'] or 0):,.2f}", row["lien_flag"] or "",
            row["collection_flag"] or "", row["resident_flag"] or "",
        ])
    output_path = build_pdf_path(output_dir, "custom_owner_report")
    story = build_report_story("Custom Owner Report")
    story.append(build_table(table_rows))
    return build_story_pdf(output_path, story, title="Custom Owner Report")


def render_custom_lot_report_pdf(
    db_path: Path,
    output_dir: Path,
    *,
    plat: str = "",
    lien_filter: str = "All",
    current_only: bool = False,
    minimum_owed: float | None = None,
    maximum_owed: float | None = None,
    lakefront_only: bool = False,
    development_status: str = "",
    trust_filter: str = "All",
) -> Path:
    with get_connection(db_path) as connection:
        lots = connection.execute(
            """
            SELECT l.*, o.last_name, o.first_name, o.address, o.phone, o.plat
            FROM lots l
            LEFT JOIN owners o ON o.owner_code = l.owner_code
            ORDER BY l.lot_number
            """
        ).fetchall()
    filtered = []
    for row in lots:
        if plat.strip() and str(row["plat"] or "").strip().upper() != plat.strip().upper():
            continue
        lien = str(row["lien_flag"] or "").upper() == "Y"
        if lien_filter == "With lien" and not lien:
            continue
        if lien_filter == "Without lien" and lien:
            continue
        owed = float(row["total_due"] or 0)
        if current_only and round(owed, 2) > 0:
            continue
        if minimum_owed is not None and owed < minimum_owed:
            continue
        if maximum_owed is not None and owed > maximum_owed:
            continue
        if lakefront_only and str(row["lakefront_flag"] or "").upper() != "Y":
            continue
        if development_status.strip() and str(row["development_status"] or "").strip().upper() != development_status.strip().upper():
            continue
        trust = str(row["county_land_trust_flag"] or "").upper() == "Y"
        if trust_filter == "County trust" and not trust:
            continue
        if trust_filter == "Not county trust" and trust:
            continue
        filtered.append(row)

    table_rows = [["Lot", "Owner", "Address", "Phone", "Lien", "Trust", "Development", "Lakefront", "Total Due"]]
    for row in filtered:
        table_rows.append([
            row["lot_number"],
            " ".join(part for part in [row["last_name"], row["first_name"]] if part),
            row["address"] or "", row["phone"] or "", row["lien_flag"] or "",
            row["county_land_trust_flag"] or "", row["development_status"] or "",
            row["lakefront_flag"] or "", f"{float(row['total_due'] or 0):,.2f}",
        ])
    output_path = build_pdf_path(output_dir, "custom_lot_report")
    story = build_report_story("Custom Lot Report")
    story.append(build_table(table_rows))
    return build_story_pdf(output_path, story, title="Custom Lot Report")


def render_card_sticker_summary_pdf(
    db_path: Path,
    output_dir: Path,
    *,
    mode: str,
    year: int,
    sort_by: str = "Name",
) -> Path:
    order_clause = "last_name, lot_number" if sort_by == "Name" else "lot_number, last_name"
    with get_connection(db_path) as connection:
        if mode == "Open ID orders":
            rows = connection.execute(
                f"""
                SELECT source, owner_code, last_name, lot_number, owner_cards, renter_cards,
                       boat_stickers, record_date
                FROM (
                    SELECT 'dBase' source, owner_code, last_name, lot_number,
                           owner_cards, renter_cards, boat_stickers, issue_date record_date
                    FROM legacy_id_history h
                    WHERE UPPER(COALESCE(completed_flag, '')) NOT IN ('T', 'Y', 'TRUE')
                      AND COALESCE(owner_cards, 0) + COALESCE(renter_cards, 0) > 0
                      AND NOT EXISTS (
                          SELECT 1 FROM id_card_completion_events e
                          WHERE e.source = 'dBase' AND e.source_record_id = h.id
                      )
                    UNION ALL
                    SELECT 'App', i.owner_code, COALESCE(o.last_name, ''), i.lot_number,
                           CASE
                             WHEN COALESCE(i.owner_quantity, 0) + COALESCE(i.renter_quantity, 0) > 0
                               THEN COALESCE(i.owner_quantity, 0)
                             ELSE COALESCE(i.quantity, 0)
                           END,
                           COALESCE(i.renter_quantity, 0), 0, i.issue_date
                    FROM id_card_issues i LEFT JOIN owners o ON o.owner_code=i.owner_code
                    WHERE UPPER(COALESCE(i.completed_flag, 'N')) <> 'Y'
                      AND NOT EXISTS (
                          SELECT 1 FROM id_card_completion_events e
                          WHERE e.source = 'App' AND e.source_record_id = i.id
                      )
                ) ORDER BY {order_clause}
                """
            ).fetchall()
        elif mode == "Cards by year":
            rows = connection.execute(
                f"""
                SELECT source, owner_code, last_name, lot_number, owner_cards, renter_cards,
                       boat_stickers, record_date FROM (
                    SELECT 'dBase' source, owner_code, last_name, lot_number, owner_cards, renter_cards,
                           boat_stickers, issue_date record_date, issue_year record_year
                    FROM legacy_id_history
                    UNION ALL
                    SELECT 'App', i.owner_code, COALESCE(o.last_name, ''), i.lot_number,
                           CASE
                             WHEN COALESCE(i.owner_quantity, 0) + COALESCE(i.renter_quantity, 0) > 0
                               THEN COALESCE(i.owner_quantity, 0)
                             ELSE COALESCE(i.quantity, 0)
                           END,
                           COALESCE(i.renter_quantity, 0), 0,
                           i.issue_date,
                           COALESCE(i.issue_year, CAST(SUBSTR(i.issue_date, 1, 4) AS INTEGER))
                    FROM id_card_issues i LEFT JOIN owners o ON o.owner_code=i.owner_code
                ) WHERE record_year=? AND owner_cards+renter_cards>0 ORDER BY {order_clause}
                """,
                [year],
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT source, owner_code, last_name, lot_number, owner_cards, renter_cards,
                       boat_stickers, record_date FROM (
                    SELECT 'dBase' source, owner_code, last_name, lot_number, owner_cards, renter_cards,
                           boat_stickers, boat_date record_date, issue_year record_year
                    FROM legacy_id_history
                    UNION ALL
                    SELECT 'App', b.owner_code, COALESCE(o.last_name, ''), b.lot_number, 0, 0,
                           b.quantity, SUBSTR(b.created_at,1,10), CAST(b.sticker_year AS INTEGER)
                    FROM boat_sticker_purchases b LEFT JOIN owners o ON o.owner_code=b.owner_code
                ) WHERE record_year=? AND boat_stickers>0 ORDER BY {order_clause}
                """,
                [year],
            ).fetchall()
    table_rows = [["Lot", "Owner", "Name", "Owner Cards", "Renter Cards", "Boat", "Date", "Source"]]
    for row in rows:
        table_rows.append([row["lot_number"] or "", row["owner_code"] or "", row["last_name"] or "",
                           row["owner_cards"] or 0, row["renter_cards"] or 0, row["boat_stickers"] or 0,
                           row["record_date"] or "", row["source"]])
    title = mode if mode == "Open ID orders" else f"{mode} - {year}"
    output_path = build_pdf_path(output_dir, mode.lower().replace(" ", "_"))
    story = build_report_story(title)
    story.append(build_table(table_rows))
    return build_story_pdf(output_path, story, title=title)
