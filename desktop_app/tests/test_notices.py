from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.services.notice_service import (
    NoticeOwner,
    notice_query_for_mode,
    render_notice_batch_pdfs,
)


def make_owner(code: str, last_name: str) -> NoticeOwner:
    return NoticeOwner(
        owner_code=code,
        last_name=last_name,
        first_name="Test",
        address="1 Lake Road",
        city="Tallahassee",
        state="FL",
        zip_code="32301",
        total_owed=100.0,
        lien_flag="N",
        hold_mail_flag="N",
        current_flag="Y",
        lots=[],
    )


class NoticeModeTests(unittest.TestCase):
    def test_all_owner_mode_ignores_a_leftover_search(self) -> None:
        self.assertEqual(notice_query_for_mode("all", "Smith"), "")

    def test_lien_mode_ignores_a_leftover_search(self) -> None:
        self.assertEqual(notice_query_for_mode("liens", "Smith"), "")

    def test_individual_mode_uses_the_search(self) -> None:
        self.assertEqual(notice_query_for_mode("individual", "  Smith  "), "Smith")


class NoticeBatchRenderingTests(unittest.TestCase):
    def test_every_owner_is_rendered_across_multi_page_batch_pdfs(self) -> None:
        owners = [
            make_owner("1", "Alpha"),
            make_owner("2", "Bravo"),
            make_owner("3", "Charlie"),
            make_owner("4", "Delta"),
            make_owner("5", "Echo"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = [Path(temp_dir) / f"batch-{number}.pdf" for number in range(1, 4)]
            with patch(
                "src.services.notice_service.render_notice_pdf",
                side_effect=outputs,
            ) as renderer:
                result = render_notice_batch_pdfs(
                    owners=owners,
                    batch_size=2,
                    output_dir=Path(temp_dir),
                    season_label="Fall 2026",
                )

        self.assertEqual(result, outputs)
        self.assertEqual(renderer.call_count, 3)
        rendered_owner_codes = [
            owner.owner_code
            for call in renderer.call_args_list
            for owner in call.kwargs["owners"]
        ]
        self.assertEqual(rendered_owner_codes, ["1", "2", "3", "4", "5"])
        self.assertEqual(
            [len(call.kwargs["owners"]) for call in renderer.call_args_list],
            [2, 2, 1],
        )
        self.assertEqual(
            [call.kwargs["season_label"] for call in renderer.call_args_list],
            [
                "Fall 2026 - Batch 1 of 3",
                "Fall 2026 - Batch 2 of 3",
                "Fall 2026 - Batch 3 of 3",
            ],
        )


if __name__ == "__main__":
    unittest.main()
