from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.app import LakeLotApp


class RefreshFolderSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.selected_dir = Path(self.temp.name).resolve()
        self.app = SimpleNamespace(
            legacy_dir=Path("C:/previous-dbase"),
            import_legacy_data=Mock(),
        )

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


if __name__ == "__main__":
    unittest.main()
