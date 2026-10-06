import unittest

from src.services.help_service import get_screen_help
from src.ui.classic_menu import CLASSIC_MENU_GROUPS, MENU_SIDEBAR_LABEL


class ClassicMenuMappingTests(unittest.TestCase):
    def test_sidebar_has_one_plain_menu_button(self) -> None:
        self.assertEqual(MENU_SIDEBAR_LABEL, "Menu")

    def test_menu_help_uses_the_plain_name(self) -> None:
        help_info = get_screen_help("menu")
        self.assertIsNotNone(help_info)
        self.assertEqual(help_info.title, "Menu")

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
