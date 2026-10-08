from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from src.services.pdf_service import build_pdf_path
from src.db.connection import get_connection


@dataclass(slots=True)
class NoticeLotLine:
    lot_number: str
    delinquent_assessment: float
    delinquent_interest: float
    current_assessment: float
    current_interest: float
    total_due: float
    county_land_trust_flag: str
    freeze_flag: str


@dataclass(slots=True)
class NoticeOwner:
    owner_code: str
    last_name: str
    first_name: str
    address: str
    city: str
    state: str
    zip_code: str
    total_owed: float
    lien_flag: str
    hold_mail_flag: str
    current_flag: str
    lots: list[NoticeLotLine]


@dataclass(slots=True)
class NoticeBatch:
    batch_number: int
    start_name: str
    end_name: str
    owners: list[NoticeOwner]


def should_omit_notice(owner: NoticeOwner, lien_only: bool) -> bool:
    last_name = owner.last_name.strip().upper()
    address = owner.address.strip().upper()
    if last_name in {"LL CO", "LL CO.", "LL COMPANY", "ASSOCIATION"}:
        return True
    if address in {"UNKNOWN", "DECEASED"}:
        return True
    if owner.hold_mail_flag.strip().upper() == "Y":
        return True
    if owner.current_flag.strip().upper() not in {"T", "Y", "TRUE", ""}:
        return True
    if lien_only and owner.lien_flag.strip().upper() != "Y":
        return True
    return False


def owner_display_name(owner: NoticeOwner) -> str:
    return " ".join(part for part in [owner.first_name, owner.last_name] if part).strip()


def owner_notice_total(owner: NoticeOwner) -> float:
    billable_lots = [lot for lot in owner.lots if lot.county_land_trust_flag != "Y"]
    if any(lot.freeze_flag == "Y" for lot in owner.lots):
        return round(sum(lot.current_assessment for lot in billable_lots), 2)
    return round(sum(lot.total_due for lot in billable_lots), 2)


def owner_has_county_land_trust_lots(owner: NoticeOwner) -> bool:
    return any(lot.county_land_trust_flag == "Y" for lot in owner.lots)


def default_notice_season_label(db_path: Path) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT TRIM(COALESCE(season, '')) AS season,
                   TRIM(COALESCE(year, '')) AS year
            FROM legacy_system_history
            WHERE TRIM(COALESCE(season, '')) <> ''
               OR TRIM(COALESCE(year, '')) <> ''
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return str(datetime.now().year)
    return " ".join(part for part in [row["season"], row["year"]] if part).strip()


def build_notice_batches(owners: list[NoticeOwner], batch_size: int) -> list[NoticeBatch]:
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    batches: list[NoticeBatch] = []
    for index in range(0, len(owners), batch_size):
        chunk = owners[index : index + batch_size]
        if not chunk:
            continue
        batches.append(
            NoticeBatch(
                batch_number=len(batches) + 1,
                start_name=chunk[0].last_name or chunk[0].owner_code,
                end_name=chunk[-1].last_name or chunk[-1].owner_code,
                owners=chunk,
            )
        )
    return batches


def notice_query_for_mode(mode: str, search_text: str) -> str:
    """Only an individual notice lookup may narrow the owner candidate list."""
    return search_text.strip() if mode == "individual" else ""


def render_notice_batch_pdfs(
    owners: list[NoticeOwner],
    batch_size: int,
    output_dir: Path,
    season_label: str,
) -> list[Path]:
    """Render every owner across one multi-page PDF per configured batch."""
    batches = build_notice_batches(owners, batch_size)
    created_files: list[Path] = []
    batch_count = len(batches)
    for batch in batches:
        start_name = re.sub(r"[^A-Za-z0-9]+", "_", batch.start_name).strip("_") or "START"
        end_name = re.sub(r"[^A-Za-z0-9]+", "_", batch.end_name).strip("_") or "END"
        file_stem = (
            f"assessment_notices_batch_{batch.batch_number:03d}_"
            f"{start_name}_to_{end_name}"
        )
        created_files.append(
            render_notice_pdf(
                owners=batch.owners,
                output_dir=output_dir,
                season_label=(
                    f"{season_label} - Batch {batch.batch_number} of {batch_count}"
                ),
                file_stem=file_stem,
            )
        )
    return created_files


def build_notice_file_stem(owner: NoticeOwner, timestamp: datetime | None = None) -> str:
    stamp = (timestamp or datetime.now()).strftime("%m-%d-%y_%H%M%S")
    last_name = owner.last_name or owner.owner_code
    first_name = owner.first_name or "OWNER"
    raw = f"{last_name}_{first_name}_{stamp}"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("_")
    return cleaned or f"notice_{stamp}"


def _notice_table_lines(owner: NoticeOwner) -> tuple[list[str], float, bool, bool]:
    has_freeze = any(lot.freeze_flag == "Y" for lot in owner.lots)
    due_total = owner_notice_total(owner)
    collection_note = owner_has_county_land_trust_lots(owner)
    billable_lots = [lot for lot in owner.lots if lot.county_land_trust_flag != "Y"]
    lot_rows = []
    for lot in owner.lots:
        total_display = lot.current_assessment if has_freeze else lot.total_due
        marker = "**" if lot.county_land_trust_flag == "Y" else ""
        lot_rows.append(
            f"{lot.lot_number:<6}{marker:<3}"
            f"{lot.delinquent_assessment:>12.2f}"
            f"{lot.delinquent_interest:>12.2f}"
            f"{lot.current_assessment:>12.2f}"
            f"{lot.current_interest:>12.2f}"
            f"{total_display:>12.2f}"
        )

    total_line = (
        f"{'':<9}"
        f"{sum(lot.delinquent_assessment for lot in billable_lots):>12.2f}"
        f"{sum(lot.delinquent_interest for lot in billable_lots):>12.2f}"
        f"{sum(lot.current_assessment for lot in billable_lots):>12.2f}"
        f"{sum(lot.current_interest for lot in billable_lots):>12.2f}"
        f"{due_total:>12.2f}"
    )
    lines = [
        "LOT     DELINQUENT  DELINQUENT    CURRENT      CURRENT        TOTAL",
        "NUMBER  ASSESSMENT   INTEREST   ASSESSMENT    INTEREST         DUE",
        *lot_rows,
        "        ------     ----------   ----------   ----------   ----------   ----------",
        total_line,
    ]
    return lines, due_total, has_freeze, collection_note


def render_notice_pdf(
    owners: list[NoticeOwner],
    output_dir: Path,
    season_label: str,
    file_stem: str,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = build_pdf_path(output_dir, f"{file_stem}_{timestamp}")
    pdf = canvas.Canvas(str(output_path), pagesize=LETTER)
    pdf.setTitle("Notice Print Preview")
    page_width, page_height = LETTER

    for owner in owners:
        table_lines, due_total, has_freeze, collection_note = _notice_table_lines(owner)
        table_header = table_lines[:2]
        lot_rows = table_lines[2:-2]
        table_total = table_lines[-2:]
        owner_name = owner_display_name(owner).upper()
        owner_address = (owner.address or "").upper()
        owner_city = (owner.city or "").upper()
        owner_state = (owner.state or "").upper()
        city_state_zip = f"{owner_city}    {owner_state}  {owner.zip_code}".strip()
        first_page_capacity = 18
        continuation_capacity = 30
        page_count = 1
        if len(lot_rows) > first_page_capacity:
            page_count += (len(lot_rows) - first_page_capacity + continuation_capacity - 1) // continuation_capacity

        remaining_rows = list(lot_rows)
        owner_page = 1
        while owner_page == 1 or remaining_rows:
            row_capacity = first_page_capacity if owner_page == 1 else continuation_capacity
            page_rows = remaining_rows[:row_capacity]
            remaining_rows = remaining_rows[row_capacity:]
            is_last_page = not remaining_rows

            top_y = page_height - (0.55 * 72)
            if owner_page == 1:
                pdf.setFont("Courier", 14)
                pdf.drawString(0.45 * 72, top_y, owner_name)
                pdf.drawString(0.45 * 72, top_y - 18, owner_address)
                pdf.drawString(0.45 * 72, top_y - 36, city_state_zip)
                table_y = page_height - (4.65 * 72)
            else:
                pdf.setFont("Courier-Bold", 13)
                pdf.drawString(0.45 * 72, top_y, "ASSESSMENT NOTICE - CONTINUED")
                pdf.setFont("Courier", 11)
                pdf.drawString(0.45 * 72, top_y - 20, owner_name)
                table_y = page_height - (1.55 * 72)

            pdf.setFont("Courier", 12)
            pdf.drawString(4.9 * 72, page_height - (0.58 * 72), owner.owner_code)
            pdf.drawString(5.55 * 72, page_height - (0.95 * 72), f"Due: $ {due_total:,.2f}")
            pdf.setFont("Courier", 8)
            pdf.drawRightString(
                page_width - (0.45 * 72),
                page_height - (0.4 * 72),
                f"Page {owner_page} of {page_count}",
            )

            pdf.setFont("Courier", 10.5)
            line_step = 13.2
            for line in [*table_header, *page_rows, *(table_total if is_last_page else [])]:
                pdf.drawString(0.35 * 72, table_y, line)
                table_y -= line_step

            if not is_last_page:
                pdf.setFont("Courier-Bold", 10)
                pdf.drawString(0.45 * 72, max(table_y - 8, 1.1 * 72), "LOT LIST CONTINUES ON NEXT PAGE")
            else:
                pdf.setFont("Courier", 10)
                pdf.drawString(0.45 * 72, 1.7 * 72, season_label)
                pdf.setFont("Courier-Bold", 12)
                pdf.drawString(
                    0.45 * 72,
                    1.35 * 72,
                    f"PLEASE REMIT PAYMENT IN THE AMOUNT OF ${due_total:,.2f}",
                )

                note_lines: list[str] = []
                if collection_note:
                    note_lines.extend(
                        [
                            'LOTS MARKED WITH "**" ARE NO LONGER OWNED BY YOU.',
                            "THEY HAVE BEEN TAKEN OVER BY LAFAYETTE COUNTY FOR NON-PAYMENT OF TAXES.",
                            "CONTACT LAFAYETTE COUNTY OFFICES IF YOU WANT TO RECLAIM THIS PROPERTY.",
                            "ASSESSMENTS ON THESE LOTS ARE NOT OWED UNLESS YOU RECLAIM THE PROPERTY.",
                        ]
                    )
                if has_freeze:
                    note_lines.append(
                        "Freeze note: this notice shows current assessment totals for frozen accounts."
                    )
                note_y = 1.0 * 72
                pdf.setFont("Courier", 8.5)
                for warning_line in note_lines:
                    pdf.drawString(0.45 * 72, note_y, warning_line)
                    note_y -= 9.5

            pdf.showPage()
            owner_page += 1

    pdf.save()
    return output_path
