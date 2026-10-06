from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.app import LakeLotApp
from src.services.import_service import NativeActivityError


class RefreshFolderSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.selected_dir = Path(self.temp.name).resolve()
        self.app = SimpleNamespace(
            db_path=self.selected_dir / "test.sqlite3",
            legacy_dir=Path("C:/previous-dbase"),
            import_legacy_data=Mock(),
            logger=Mock(),
            _show_refresh_safety_warning=Mock(),
        )
        self.ensure_safe_patcher = patch("src.app.ensure_legacy_refresh_is_safe")
        self.ensure_safe = self.ensure_safe_patcher.start()
        self.addCleanup(self.ensure_safe_patcher.stop)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_selected_complete_folder_is_confirmed_and_imported(self) -> None:
        with (
            patch("src.app.filedialog.askdirectory", return_value=str(self.selected_dir)),
            patch("src.app.validate_legacy_directory", return_value=[]),
            patch("src.app.messagebox.askyesno", return_value=True) as confirm,
            patch("src.app.messagebox.showerror") as show_error,
        ):
            LakeLotApp.refresh_from_legacy_data(self.app)

        show_error.assert_not_called()
        confirm.assert_called_once()
        self.app.import_legacy_data.assert_called_once_with(self.selected_dir)

    def test_incomplete_folder_is_rejected_before_confirmation(self) -> None:
        with (
            patch("src.app.filedialog.askdirectory", return_value=str(self.selected_dir)),
            patch(
                "src.app.validate_legacy_directory",
                return_value=["ONERFILE.DBF", "ASMTFILE.DBF"],
            ),
            patch("src.app.messagebox.askyesno") as confirm,
            patch("src.app.messagebox.showerror") as show_error,
        ):
            LakeLotApp.refresh_from_legacy_data(self.app)

        confirm.assert_not_called()
        show_error.assert_called_once()
        self.app.import_legacy_data.assert_not_called()

    def test_canceling_folder_picker_changes_nothing(self) -> None:
        with (
            patch("src.app.filedialog.askdirectory", return_value=""),
            patch("src.app.validate_legacy_directory") as validate,
            patch("src.app.messagebox.askyesno") as confirm,
        ):
            LakeLotApp.refresh_from_legacy_data(self.app)

        validate.assert_not_called()
        confirm.assert_not_called()
        self.app.import_legacy_data.assert_not_called()

    def test_protected_activity_is_explained_before_folder_selection(self) -> None:
        activity = {"payment_audit": 1, "property_sales": 2}
        self.ensure_safe.side_effect = NativeActivityError(activity)
        with patch("src.app.filedialog.askdirectory") as choose_folder:
            LakeLotApp.refresh_from_legacy_data(self.app)

        choose_folder.assert_not_called()
        self.app._show_refresh_safety_warning.assert_called_once_with(activity)
        self.app.import_legacy_data.assert_not_called()

    def test_safety_warning_uses_plain_language_and_next_steps(self) -> None:
        with patch("src.app.messagebox.showwarning") as show_warning:
            LakeLotApp._show_refresh_safety_warning(
                self.app,
                {"payment_audit": 1, "assessment_runs": 2},
            )

        title, message = show_warning.call_args.args
        self.assertEqual(title, "Refresh safely stopped")
        self.assertIn("Nothing was changed.", message)
        self.assertIn("Assessment payment entries: 1", message)
        self.assertIn("Assessment updates: 2", message)
        self.assertIn("contact the app administrator", message)
        self.assertNotIn("payment_audit", message)
        self.assertNotIn("assessment_runs", message)


if __name__ == "__main__":
    unittest.main()
