from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from src.services.pdf_service import build_pdf_path


@dataclass(slots=True)
class NoticeLotLine:
    lot_number: str
    delinquent_assessment: float
    delinquent_interest: float
    current_assessment: float
    current_interest: float
    total_due: float
    collection_flag: str
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
    if owner.last_name in {"LL COMPANY", "ASSOCIATION"}:
        return True
    if owner.address in {"UNKNOWN", "DECEASED"}:
        return True
    if owner.hold_mail_flag == "Y":
        return True
    if owner.current_flag not in {"T", "Y", "True", "TRUE", ""}:
        return True
    if lien_only and owner.lien_flag != "Y":
        return True
    return False


def owner_display_name(owner: NoticeOwner) -> str:
    return " ".join(part for part in [owner.first_name, owner.last_name] if part).strip()


def owner_notice_total(owner: NoticeOwner) -> float:
    if any(lot.freeze_flag == "Y" for lot in owner.lots):
        return round(sum(lot.current_assessment for lot in owner.lots), 2)
    return round(sum(lot.total_due for lot in owner.lots), 2)


def owner_has_collection_lots(owner: NoticeOwner) -> bool:
    return any(lot.collection_flag == "Y" for lot in owner.lots)


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
    collection_note = owner_has_collection_lots(owner)
    lot_rows = []
    for lot in owner.lots:
        total_display = lot.current_assessment if has_freeze else lot.total_due
        marker = "**" if collection_note and lot.collection_flag == "Y" else ""
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
        f"{sum(lot.delinquent_assessment for lot in owner.lots):>12.2f}"
        f"{sum(lot.delinquent_interest for lot in owner.lots):>12.2f}"
        f"{sum(lot.current_assessment for lot in owner.lots):>12.2f}"
        f"{sum(lot.current_interest for lot in owner.lots):>12.2f}"
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
        owner_name = owner_display_name(owner).upper()
        owner_address = (owner.address or "").upper()
        owner_city = (owner.city or "").upper()
        owner_state = (owner.state or "").upper()
        city_state_zip = f"{owner_city}    {owner_state}  {owner.zip_code}".strip()

        pdf.setFont("Courier", 14)
        top_y = page_height - (0.55 * 72)
        pdf.drawString(0.45 * 72, top_y, owner_name)
        pdf.drawString(0.45 * 72, top_y - 18, owner_address)
        pdf.drawString(0.45 * 72, top_y - 36, city_state_zip)
        pdf.drawString(4.9 * 72, page_height - (0.58 * 72), owner.owner_code)
        pdf.drawString(5.55 * 72, page_height - (0.95 * 72), f"Due: $ {due_total:,.2f}")

        pdf.setFont("Courier", 13)
        table_y = page_height - (4.65 * 72)
        line_step = 15.5
        for line in table_lines:
            pdf.drawString(0.22 * 72, table_y, line)
            table_y -= line_step

        pdf.setFont("Courier", 12)
        pdf.drawString(0.45 * 72, 1.2 * 72, season_label)
        pdf.setFont("Courier-Bold", 14)
        pdf.drawString(0.45 * 72, 0.8 * 72, f"PLEASE REMIT PAYMENT IN THE AMOUNT OF ${due_total:,.2f}")

        note_y = 0.45 * 72
        pdf.setFont("Courier", 12)
        if collection_note:
            pdf.drawString(
                0.45 * 72,
                note_y,
                'Lots marked with "**" are in collection / county-taken status and need special follow-up language.',
            )
            note_y -= 12
        if has_freeze:
            pdf.drawString(
                0.45 * 72,
                note_y,
                "Freeze note: this notice shows current assessment totals for frozen accounts.",
            )

        pdf.showPage()

    pdf.save()
    return output_path
