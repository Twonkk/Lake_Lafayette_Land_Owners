from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfReader

from src.services.notice_service import (
    NoticeOwner,
    build_notice_batches,
    merge_notice_batch_pdfs,
    notice_query_for_mode,
    render_notice_batch_pdfs,
)
from src.ui.notices import NoticesFrame


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
            progress = []
            with patch(
                "src.services.notice_service.render_notice_pdf",
                side_effect=outputs,
            ) as renderer:
                result = render_notice_batch_pdfs(
                    owners=owners,
                    batch_size=2,
                    output_dir=Path(temp_dir),
                    season_label="Fall 2026",
                    after_batch=lambda batch, count, path: progress.append(
                        (batch.batch_number, count, path)
                    ),
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
        self.assertEqual(
            progress,
            [(1, 3, outputs[0]), (2, 3, outputs[1]), (3, 3, outputs[2])],
        )

    def test_completed_batches_are_merged_in_order(self) -> None:
        owners = [
            make_owner("1", "Alpha"),
            make_owner("2", "Bravo"),
            make_owner("3", "Charlie"),
            make_owner("4", "Delta"),
            make_owner("5", "Echo"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            batch_files = render_notice_batch_pdfs(
                owners=owners,
                batch_size=2,
                output_dir=output_dir,
                season_label="Fall 2026",
            )
            combined = merge_notice_batch_pdfs(batch_files, output_dir, "Fall 2026")
            reader = PdfReader(str(combined))

            self.assertEqual(len(batch_files), 3)
            self.assertEqual(len(reader.pages), 5)
            self.assertEqual(reader.metadata.title, "Assessment Notices - Fall 2026")


class NoticeBatchUserFlowTests(unittest.TestCase):
    def test_operator_is_prompted_between_batches_then_combined_pdf_opens(self) -> None:
        owners = [
            make_owner("1", "Alpha"),
            make_owner("2", "Bravo"),
            make_owner("3", "Charlie"),
            make_owner("4", "Delta"),
            make_owner("5", "Echo"),
        ]
        output_dir = Path("C:/test/generated_notices")
        batch_files = [output_dir / f"batch-{number}.pdf" for number in range(1, 4)]
        combined_file = output_dir / "complete.pdf"
        frame = SimpleNamespace(
            filtered_owners=owners,
            batch_size_var=SimpleNamespace(get=lambda: "2"),
            output_dir=output_dir,
            _season_label=lambda: "Fall 2026",
            _open_created_file=MagicMock(),
        )

        def render_with_progress(**kwargs):
            batches = build_notice_batches(kwargs["owners"], kwargs["batch_size"])
            for batch, path in zip(batches, batch_files, strict=True):
                kwargs["after_batch"](batch, len(batches), path)
            return batch_files

        with (
            patch("src.ui.notices.render_notice_batch_pdfs", side_effect=render_with_progress),
            patch("src.ui.notices.merge_notice_batch_pdfs", return_value=combined_file),
            patch("src.ui.notices.messagebox.showinfo") as showinfo,
        ):
            NoticesFrame.pdf_batch_run(frame)

        self.assertEqual(showinfo.call_count, 3)
        self.assertEqual(showinfo.call_args_list[0].args[0], "Batch 1 of 3 complete")
        self.assertIn("Press OK to create batch 2 of 3", showinfo.call_args_list[0].args[1])
        self.assertEqual(showinfo.call_args_list[1].args[0], "Batch 2 of 3 complete")
        self.assertIn("Press OK to create batch 3 of 3", showinfo.call_args_list[1].args[1])
        self.assertEqual(showinfo.call_args_list[2].args[0], "All notice batches complete")
        frame._open_created_file.assert_called_once_with(
            combined_file,
            "Combined notice PDF preview failed",
            ["Combined PDF saved to:", str(combined_file)],
        )


if __name__ == "__main__":
    unittest.main()
