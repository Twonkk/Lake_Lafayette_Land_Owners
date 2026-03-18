from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
import re

from src.services.pdf_service import convert_html_to_pdf

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


def _render_owner_notice(owner: NoticeOwner, season_label: str) -> str:
    has_freeze = any(lot.freeze_flag == "Y" for lot in owner.lots)
    due_total = owner_notice_total(owner)
    collection_note = owner_has_collection_lots(owner)
    rows = []
    for lot in owner.lots:
        total_display = lot.current_assessment if has_freeze else lot.total_due
        marker = "**" if collection_note and lot.collection_flag == "Y" else ""
        rows.append(
            f"{lot.lot_number:<6}{marker:<3}"
            f"{lot.delinquent_assessment:>12.2f}"
            f"{lot.delinquent_interest:>12.2f}"
            f"{lot.current_assessment:>12.2f}"
            f"{lot.current_interest:>12.2f}"
            f"{total_display:>12.2f}"
        )

    notes = []
    if collection_note:
        notes.append(
            'Lots marked with "**" are in collection / county-taken status and need special follow-up language.'
        )
    if has_freeze:
        notes.append(
            "Freeze note: this temporary layout shows current assessment totals for frozen accounts."
        )

    note_html = "".join(f"<p>{escape(note)}</p>" for note in notes)
    owner_name = owner_display_name(owner).upper()
    owner_address = (owner.address or "").upper()
    owner_city = (owner.city or "").upper()
    owner_state = (owner.state or "").upper()
    total_line = (
        f"{'':<9}"
        f"{sum(lot.delinquent_assessment for lot in owner.lots):>12.2f}"
        f"{sum(lot.delinquent_interest for lot in owner.lots):>12.2f}"
        f"{sum(lot.current_assessment for lot in owner.lots):>12.2f}"
        f"{sum(lot.current_interest for lot in owner.lots):>12.2f}"
        f"{due_total:>12.2f}"
    )
    return f"""
    <section class="notice-page">
      <div class="address-block">
        <div>{escape(owner_name)}</div>
        <div>{escape(owner_address)}</div>
        <div>{escape(owner_city)}&nbsp;&nbsp;&nbsp;&nbsp;{escape(owner_state)}&nbsp;&nbsp;{escape(owner.zip_code)}</div>
      </div>
      <div class="owner-code">{escape(owner.owner_code)}</div>
      <div class="due-line">Due: $ {due_total:,.2f}</div>

      <div class="table-block">
        <pre class="table-text">LOT     DELINQUENT  DELINQUENT    CURRENT      CURRENT        TOTAL
NUMBER  ASSESSMENT   INTEREST   ASSESSMENT    INTEREST         DUE
{escape(chr(10).join(rows))}
        ------     ----------   ----------   ----------   ----------   ----------
{escape(total_line)}</pre>
      </div>

      <div class="season-label">{escape(season_label)}</div>

      <div class="remit">
        <p>PLEASE REMIT PAYMENT IN THE AMOUNT OF ${due_total:,.2f}</p>
      </div>

      <div class="notes">
        {note_html}
      </div>
    </section>
    """


def render_notice_html(
    owners: list[NoticeOwner],
    output_dir: Path,
    season_label: str,
    file_stem: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{file_stem}_{timestamp}.html"
    pages = [_render_owner_notice(owner, season_label) for owner in owners]
    document = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Notice Print Preview</title>
      <style>
        @page {{
          size: letter;
          margin: 0.5in;
        }}
        body {{
          font-family: "Courier New", Courier, monospace;
          color: #111827;
          margin: 0;
          background: #f5f5f5;
        }}
        .notice-page {{
          background: white;
          position: relative;
          width: 8in;
          height: 10.2in;
          margin: 0.25in auto;
          padding: 0;
          box-sizing: border-box;
          page-break-after: always;
          overflow: hidden;
        }}
        .address-block {{
          position: absolute;
          top: 0.55in;
          left: 0.45in;
          font-size: 14px;
          line-height: 1.25;
          letter-spacing: 1px;
        }}
        .owner-code {{
          position: absolute;
          top: 0.58in;
          left: 4.9in;
          font-size: 14px;
          letter-spacing: 2px;
        }}
        .due-line {{
          position: absolute;
          top: 0.95in;
          left: 5.55in;
          font-size: 14px;
        }}
        .table-block {{
          position: absolute;
          top: 4.65in;
          left: 0.22in;
          right: 0.22in;
        }}
        .table-text {{
          font-family: "Courier New", Courier, monospace;
          font-size: 13px;
          line-height: 1.22;
          margin: 0;
          white-space: pre;
        }}
        .season-label {{
          position: absolute;
          left: 0.45in;
          bottom: 1.2in;
          font-size: 12px;
        }}
        .remit {{
          position: absolute;
          left: 0.45in;
          bottom: 0.8in;
          right: 0.45in;
          font-size: 14px;
          letter-spacing: 1px;
        }}
        .notes {{
          position: absolute;
          left: 0.45in;
          right: 0.45in;
          bottom: 0.18in;
          font-size: 12px;
        }}
        .notes p {{
          margin: 0.08in 0 0;
        }}
        @media print {{
          body {{
            background: white;
          }}
          .notice-page {{
            margin: 0;
            border: none;
            width: auto;
            min-height: auto;
          }}
        }}
      </style>
    </head>
    <body>
      {''.join(pages)}
    </body>
    </html>
    """
    output_path.write_text(document, encoding="utf-8")
    return output_path


def convert_notice_html_to_pdf(html_path: Path) -> Path:
    return convert_html_to_pdf(html_path, "Failed to convert notice preview to PDF.")
