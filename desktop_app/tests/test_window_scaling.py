import unittest

from src.app import preferred_window_size


class WindowScalingTests(unittest.TestCase):
    def test_standard_display_uses_target_size(self) -> None:
        self.assertEqual(preferred_window_size(1920, 1080), (1280, 800))

    def test_scaled_logical_display_never_pushes_below_screen(self) -> None:
        width, height = preferred_window_size(1093, 614)
        self.assertLessEqual(width, 1093)
        self.assertLessEqual(height, 614)
        self.assertEqual((width, height), (1053, 534))

    def test_short_laptop_display_keeps_taskbar_margin(self) -> None:
        self.assertEqual(preferred_window_size(1366, 768), (1280, 688))


if __name__ == "__main__":
    unittest.main()
