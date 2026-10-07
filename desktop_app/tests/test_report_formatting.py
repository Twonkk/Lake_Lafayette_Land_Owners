import tempfile
import unittest
from pathlib import Path
import re

from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph

from src.db.connection import get_connection, initialize_database
from src.services.pdf_service import build_table
from src.services.report_service import (
    render_lot_report_pdf,
    render_mailing_labels_pdf,
    render_owner_report_pdf,
)


class ReportFormattingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "reports.sqlite3"
        self.output_dir = Path(self.temp_dir.name) / "reports"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO owners (
                    owner_code, last_name, first_name, address, city, state, zip, phone,
                    number_lots, total_owed, current_flag, resident_flag, lien_flag
                ) VALUES (
                    '9001', 'A Very Long Family Name', 'Alexandria & Benjamin',
                    '12345 A Particularly Long Rural Route Address',
                    'A City With A Long Name', 'MO', '64000-1234', '816-555-0199',
                    3, 12345.67, 'T', 'Y', 'Y'
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO lots (
                    lot_number, owner_code, total_due, current_assessment,
                    delinquent_assessment, delinquent_interest, current_interest,
                    lien_flag, county_land_trust_flag
                ) VALUES (?, '9001', 4115.22, 25, 4000, 75.22, 15, 'Y', 'N')
                """,
                [("A100",), ("A101",), ("A102",)],
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_wrapped_table_uses_paragraph_cells(self) -> None:
        table = build_table(
            [["Long heading", "Amount"], ["Words that must wrap inside a narrow column", "1,234.56"]],
            [0.8 * inch, 0.8 * inch],
            wrap_cells=True,
            column_alignments=["LEFT", "RIGHT"],
        )

        self.assertIsInstance(table._cellvalues[0][0], Paragraph)
        self.assertIsInstance(table._cellvalues[1][0], Paragraph)
        _, wrapped_height = table._cellvalues[1][0].wrap(0.72 * inch, 10 * inch)
        self.assertGreater(wrapped_height, 12)

    def test_wide_reports_render_as_landscape_pdfs(self) -> None:
        owner_output = render_owner_report_pdf(self.db_path, self.output_dir)
        lot_output = render_lot_report_pdf(self.db_path, self.output_dir)

        self.assertTrue(owner_output.read_bytes().startswith(b"%PDF"))
        self.assertTrue(lot_output.read_bytes().startswith(b"%PDF"))
        expected_media_box = f"0 0 {landscape(LETTER)[0]:.0f} {landscape(LETTER)[1]:.0f}".encode()
        self.assertIn(expected_media_box, owner_output.read_bytes())
        self.assertIn(expected_media_box, lot_output.read_bytes())

    def test_mailing_labels_keep_nine_complete_labels_per_page(self) -> None:
        with get_connection(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO owners (
                    owner_code, last_name, first_name, address, city, state, zip,
                    primary_lot_number
                ) VALUES (?, ?, 'Sample', '123 Long Mailing Address', 'Odessa', 'MO', '64076', ?)
                """,
                [(f"91{index:02d}", f"Owner {index}", f"B{index:03d}") for index in range(9)],
            )

        output = render_mailing_labels_pdf(self.db_path, self.output_dir)
        page_count = len(re.findall(rb"/Type\s*/Page\b", output.read_bytes()))

        self.assertEqual(page_count, 2)


if __name__ == "__main__":
    unittest.main()
