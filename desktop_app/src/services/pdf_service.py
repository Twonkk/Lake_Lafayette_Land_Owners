from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
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
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=title or output_path.stem,
        author=author,
    )
    document.build(story)
    return output_path


def write_preformatted_pages_pdf(
    output_path: Path,
    pages: Iterable[Iterable[str]],
    *,
    left_margin: float = 0.5 * inch,
    top_margin: float = 0.55 * inch,
    font_name: str = "Courier",
    font_size: float = 11,
    line_height: float | None = None,
    title: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=LETTER)
    pdf.setTitle(title or output_path.stem)
    width, height = LETTER
    step = line_height or (font_size * 1.15)
    for page_lines in pages:
        y = height - top_margin
        pdf.setFont(font_name, font_size)
        for line in page_lines:
            pdf.drawString(left_margin, y, str(line))
            y -= step
        pdf.showPage()
    pdf.save()
    return output_path


def build_report_story(title: str, subtitle_lines: Iterable[str] | None = None) -> list:
    story = [Paragraph(title, TITLE_STYLE)]
    for line in subtitle_lines or []:
        story.append(Paragraph(line, SMALL_BODY_STYLE))
    if subtitle_lines:
        story.append(Spacer(1, 0.15 * inch))
    return story


def build_table(data: list[list[object]], column_widths: list[float], *, repeat_header: bool = True) -> Table:
    table = Table(data, colWidths=column_widths, repeatRows=1 if repeat_header else 0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe7f5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 10),
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
