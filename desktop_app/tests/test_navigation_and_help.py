import json
from pathlib import Path
import tempfile
import unittest

from src.runtime import load_navigation_mode, save_navigation_mode
from src.services.help_service import get_screen_help
from src.ui.classic_menu import CLASSIC_MENU_GROUPS


class NavigationPreferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp.name) / "update_config.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_classic_menu_is_the_safe_default(self) -> None:
        self.assertEqual(load_navigation_mode(self.config_path), "classic")

    def test_navigation_choice_is_saved_without_losing_other_settings(self) -> None:
        self.config_path.write_text(
            json.dumps({"legacy_dir": "C:/legacy", "seen_screen_help": {"payments": True}}),
            encoding="utf-8",
        )

        save_navigation_mode(self.config_path, "simple")

        self.assertEqual(load_navigation_mode(self.config_path), "simple")
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["legacy_dir"], "C:/legacy")
        self.assertTrue(payload["seen_screen_help"]["payments"])

    def test_unknown_navigation_choice_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown navigation mode"):
            save_navigation_mode(self.config_path, "surprise")


class ClassicMenuMappingTests(unittest.TestCase):
    def test_legacy_group_and_option_order_is_preserved(self) -> None:
        self.assertEqual([group.number for group in CLASSIC_MENU_GROUPS], [1, 2, 3])
        self.assertEqual([len(group.items) for group in CLASSIC_MENU_GROUPS], [13, 10, 2])
        for group in CLASSIC_MENU_GROUPS:
            self.assertEqual(
                [item.number for item in group.items],
                list(range(1, len(group.items) + 1)),
            )

    def test_familiar_payment_option_keeps_its_number_and_wording(self) -> None:
        payment = CLASSIC_MENU_GROUPS[0].items[1]
        self.assertEqual(payment.number, 2)
        self.assertEqual(payment.label, "Record Assessment Payment")
        self.assertEqual(payment.destination, "payments")

    def test_every_classic_destination_has_dbase_help(self) -> None:
        destinations = {
            item.destination
            for group in CLASSIC_MENU_GROUPS
            for item in group.items
        }
        for destination in destinations:
            help_info = get_screen_help(destination)
            self.assertIsNotNone(help_info, destination)
            self.assertTrue(help_info.legacy_reference, destination)


if __name__ == "__main__":
    unittest.main()
