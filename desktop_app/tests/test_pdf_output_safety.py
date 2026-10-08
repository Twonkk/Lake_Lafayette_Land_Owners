from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from reportlab.lib.pagesizes import LETTER, landscape

from src.services.history_service import render_history_pdf
from src.services.notice_service import NoticeLotLine, NoticeOwner, render_notice_pdf
from src.services.pdf_service import write_preformatted_pages_pdf
from src.services.property_sale_service import PropertySaleReceiptLine, render_property_sale_receipt_pdf
from src.services.utility_service import UtilityCheckResult, render_migration_readiness_pdf


def page_count(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", path.read_bytes()))


class PdfOutputSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_preformatted_output_wraps_and_continues_instead_of_leaving_page(self) -> None:
        output = self.output_dir / "long_preformatted.pdf"
        write_preformatted_pages_pdf(
            output,
            [
                [
                    "A long printable line " + ("with useful details " * 12),
                    *[f"Review item {index:03d}" for index in range(100)],
                ]
            ],
            footer_text="Safe print test",
        )

        self.assertGreater(page_count(output), 1)
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))

    def test_wide_history_uses_landscape_wrapped_table(self) -> None:
        output = render_history_pdf(
            self.output_dir,
            "Owner Payment History",
            ["Date", "Owner", "Name", "Owed", "Paid", "Form", "Check"],
            [
                [
                    "2026-10-07",
                    "9001",
                    "A very long owner name that must stay inside its own column",
                    "$1,234.56",
                    "$100.00",
                    "Negotiated Adjustment With Details",
                    "REFERENCE-123456",
                ]
            ],
        )

        expected_media_box = f"0 0 {landscape(LETTER)[0]:.0f} {landscape(LETTER)[1]:.0f}".encode()
        self.assertIn(expected_media_box, output.read_bytes())

    def test_large_owner_notice_continues_without_footer_overlap(self) -> None:
        owner = NoticeOwner(
            owner_code="9001",
            last_name="TEST",
            first_name="OWNER",
            address="1 LAKE ROAD",
            city="ODESSA",
            state="MO",
            zip_code="64076",
            total_owed=1725.0,
            lien_flag="N",
            hold_mail_flag="N",
            current_flag="Y",
            lots=[
                NoticeLotLine(f"A{index:03d}", 0, 0, 25, 0, 25, "N", "N")
                for index in range(69)
            ],
        )

        output = render_notice_pdf([owner], self.output_dir, "Fall 2026", "large_notice")

        self.assertEqual(page_count(output), 3)

    def test_large_migration_review_report_paginates(self) -> None:
        results = [
            UtilityCheckResult(
                title="Records needing client review",
                issue_count=120,
                details=[
                    f"Owner {index:04d}: a deliberately long explanation that must wrap cleanly"
                    for index in range(120)
                ],
            )
        ]
        with patch("src.services.utility_service.run_data_health_checks", return_value=results):
            output = render_migration_readiness_pdf(Path("unused.sqlite3"), self.output_dir)

        self.assertGreater(page_count(output), 1)

    def test_property_sale_receipts_keep_one_wrapped_sale_per_page(self) -> None:
        long_name = "A very long owner name with several words that must remain inside its column"
        lines = [
            PropertySaleReceiptLine(
                lot_number=f"A10{index}",
                sale_date="2026-10-07",
                seller_owner_code="1000",
                buyer_owner_code="2000",
                seller_name=long_name,
                buyer_name=long_name,
                recorded_on="2026-10-07T12:00:00",
                seller_note="A long seller note that must wrap safely inside the receipt.",
                buyer_note="A long buyer note that must wrap safely inside the receipt.",
            )
            for index in range(2)
        ]

        output = render_property_sale_receipt_pdf(lines, self.output_dir, "property_sale_test")

        self.assertEqual(page_count(output), 2)


if __name__ == "__main__":
    unittest.main()
