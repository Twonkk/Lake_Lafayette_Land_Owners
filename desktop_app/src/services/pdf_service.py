from __future__ import annotations

from html import escape
from importlib.util import find_spec
from pathlib import Path
import textwrap
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas


BODY_STYLE = ParagraphStyle(
    "LakeLotBody",
    parent=getSampleStyleSheet()["BodyText"],
    fontName="Helvetica",
    fontSize=10,
    leading=12,
    spaceAfter=6,
)

SMALL_BODY_STYLE = ParagraphStyle(
    "LakeLotSmallBody",
    parent=BODY_STYLE,
    fontSize=9,
    leading=11,
)

TITLE_STYLE = ParagraphStyle(
    "LakeLotTitle",
    parent=getSampleStyleSheet()["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=16,
    leading=18,
    spaceAfter=6,
)

SUBTITLE_STYLE = ParagraphStyle(
    "LakeLotSubtitle",
    parent=BODY_STYLE,
    fontName="Helvetica-Bold",
    fontSize=10,
    leading=12,
    spaceAfter=4,
)


def pdf_runtime_available() -> tuple[bool, str]:
    if find_spec("reportlab") is None:
        return False, "ReportLab is not installed. Reinstall the app to restore PDF output."
    return True, "ReportLab PDF generation is available."


def build_pdf_path(output_dir: Path, file_stem: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{file_stem}.pdf"


def build_story_pdf(
    output_path: Path,
    story: list,
    *,
    title: str | None = None,
    author: str = "Lake Lafayette Landowners Association",
    left_margin: float = 0.55 * inch,
    right_margin: float = 0.55 * inch,
    top_margin: float = 0.6 * inch,
    bottom_margin: float = 0.55 * inch,
    footer_text: str | None = None,
    page_size: tuple[float, float] = LETTER,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=page_size,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=title or output_path.stem,
        author=author,
    )
    if footer_text:
        def draw_footer(pdf_canvas, _document) -> None:
            pdf_canvas.saveState()
            pdf_canvas.setFillColor(colors.HexColor("#5f6b7a"))
            pdf_canvas.setFont("Helvetica", 8)
            pdf_canvas.drawString(document.leftMargin, 0.3 * inch, footer_text)
            pdf_canvas.drawRightString(
                page_size[0] - document.rightMargin,
                0.3 * inch,
                f"Page {pdf_canvas.getPageNumber()}",
            )
            pdf_canvas.restoreState()

        document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    else:
        document.build(story)
    return output_path


def write_preformatted_pages_pdf(
    output_path: Path,
    pages: Iterable[Iterable[str]],
    *,
    left_margin: float = 0.5 * inch,
    right_margin: float = 0.5 * inch,
    top_margin: float = 0.55 * inch,
    bottom_margin: float = 0.55 * inch,
    font_name: str = "Courier",
    font_size: float = 11,
    line_height: float | None = None,
    title: str | None = None,
    footer_text: str | None = None,
    page_size: tuple[float, float] = LETTER,
) -> Path:
    """Write fixed-width text without allowing long or numerous lines to leave the page.

    Each iterable in ``pages`` still starts on a new physical page, preserving the
    legacy receipt-per-page behavior. Oversized logical pages are continued onto as
    many physical pages as necessary, and long lines are wrapped at the printable
    right margin.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=page_size)
    pdf.setTitle(title or output_path.stem)
    width, height = page_size
    step = line_height or (font_size * 1.15)
    printable_width = max(1, width - left_margin - right_margin)
    # Courier is fixed width at roughly 0.6 em. All current callers use Courier,
    # but this conservative calculation also prevents clipping for other fonts.
    max_characters = max(1, int(printable_width / (font_size * 0.6)))
    line_capacity = max(1, int((height - top_margin - bottom_margin) // step) + 1)

    def wrapped_lines(page_lines: Iterable[str]) -> list[str]:
        result: list[str] = []
        for value in page_lines:
            line = str(value)
            if not line:
                result.append("")
                continue
            if pdf.stringWidth(line, font_name, font_size) <= printable_width:
                result.append(line)
                continue
            result.extend(
                textwrap.wrap(
                    line,
                    width=max_characters,
                    replace_whitespace=False,
                    drop_whitespace=True,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
                or [""]
            )
        return result

    def finish_page() -> None:
        if footer_text:
            pdf.setFont("Helvetica", 8)
            pdf.setFillColor(colors.HexColor("#5f6b7a"))
            pdf.drawString(left_margin, 0.25 * inch, footer_text)
            pdf.drawRightString(
                width - right_margin,
                0.25 * inch,
                f"Page {pdf.getPageNumber()}",
            )
            pdf.setFillColor(colors.black)
        pdf.showPage()

    for page_lines in pages:
        lines = wrapped_lines(page_lines)
        if not lines:
            lines = [""]
        for start in range(0, len(lines), line_capacity):
            y = height - top_margin
            pdf.setFont(font_name, font_size)
            for line in lines[start : start + line_capacity]:
                pdf.drawString(left_margin, y, line)
                y -= step
            finish_page()
    pdf.save()
    return output_path


def build_report_story(title: str, subtitle_lines: Iterable[str] | None = None) -> list:
    story = [Paragraph(title, TITLE_STYLE)]
    for line in subtitle_lines or []:
        story.append(Paragraph(line, SMALL_BODY_STYLE))
    if subtitle_lines:
        story.append(Spacer(1, 0.15 * inch))
    return story


def build_table(
    data: list[list[object]],
    column_widths: list[float] | None = None,
    *,
    repeat_header: bool = True,
    wrap_cells: bool = False,
    column_alignments: list[str] | None = None,
    font_size: float = 8.5,
) -> Table:
    table_data = data
    if wrap_cells:
        alignment_values = {
            "LEFT": TA_LEFT,
            "CENTER": TA_CENTER,
            "RIGHT": TA_RIGHT,
        }
        leading = max(font_size + 1.5, font_size * 1.18)
        header_style = ParagraphStyle(
            "LakeLotTableHeader",
            parent=SMALL_BODY_STYLE,
            fontName="Helvetica-Bold",
            fontSize=font_size,
            leading=leading,
            alignment=TA_CENTER,
            spaceAfter=0,
            splitLongWords=True,
        )
        body_styles = {
            key: ParagraphStyle(
                f"LakeLotTableCell{key.title()}",
                parent=SMALL_BODY_STYLE,
                fontName="Helvetica",
                fontSize=font_size,
                leading=leading,
                alignment=value,
                spaceAfter=0,
                splitLongWords=True,
            )
            for key, value in alignment_values.items()
        }

        table_data = []
        for row_index, row in enumerate(data):
            wrapped_row = []
            for column_index, value in enumerate(row):
                if isinstance(value, Paragraph):
                    wrapped_row.append(value)
                    continue
                text = escape(str(value if value is not None else "")).replace("\n", "<br/>")
                if row_index == 0 and repeat_header:
                    style = header_style
                else:
                    requested = (
                        column_alignments[column_index].upper()
                        if column_alignments and column_index < len(column_alignments)
                        else "LEFT"
                    )
                    style = body_styles.get(requested, body_styles["LEFT"])
                wrapped_row.append(Paragraph(text, style))
            table_data.append(wrapped_row)

    table = Table(table_data, colWidths=column_widths, repeatRows=1 if repeat_header else 0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe7f5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEADING", (0, 0), (-1, -1), max(font_size + 1.5, font_size * 1.18)),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c6d0dd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def paragraph(text: str, *, small: bool = False) -> Paragraph:
    return Paragraph(text, SMALL_BODY_STYLE if small else BODY_STYLE)


def page_break() -> PageBreak:
    return PageBreak()
