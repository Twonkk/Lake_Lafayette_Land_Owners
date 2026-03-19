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
                l.collection_flag,
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
        "Collection",
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
                str(lot["collection_flag"] or ""),
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


def render_mailing_labels_pdf(db_path: Path, output_dir: Path) -> Path:
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
            ORDER BY last_name, first_name, owner_code
            """
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
