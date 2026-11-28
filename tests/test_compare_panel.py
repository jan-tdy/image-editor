import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from image_editor.widgets.compare_panel import NEXT, PREV, ComparePanel

_app = QApplication.instance() or QApplication([])


class ComparePanelTests(unittest.TestCase):
    def test_onion_and_blink_are_mutually_exclusive(self):
        panel = ComparePanel()
        panel.onion_check.setChecked(True)
        panel.blink_check.setChecked(True)
        self.assertFalse(panel.onion_check.isChecked())
        self.assertTrue(panel.blink_check.isChecked())

        panel.onion_check.setChecked(True)
        self.assertFalse(panel.blink_check.isChecked())
        self.assertTrue(panel.onion_check.isChecked())

    def test_opacity_slider_emits_fraction(self):
        panel = ComparePanel()
        seen = []
        panel.opacityChanged.connect(seen.append)
        panel.opacity_slider.setValue(25)
        self.assertEqual(seen, [0.25])
        self.assertEqual(panel.opacity(), 0.25)

    def test_toggle_signals_fire(self):
        panel = ComparePanel()
        onion_seen, blink_seen = [], []
        panel.onionToggled.connect(onion_seen.append)
        panel.blinkToggled.connect(blink_seen.append)
        panel.set_onion_checked(True)
        self.assertEqual(onion_seen, [True])
        panel.set_blink_checked(True)
        self.assertEqual(blink_seen, [True])
        self.assertEqual(onion_seen, [True, False])  # onion was turned off by mutual exclusion

    def test_interval_default_and_change(self):
        panel = ComparePanel()
        self.assertEqual(panel.interval_ms(), 500)
        seen = []
        panel.intervalChanged.connect(seen.append)
        panel.interval_spin.setValue(250)
        self.assertEqual(seen, [250])

    def test_direction_combo_optional(self):
        with_direction = ComparePanel(show_direction=True)
        self.assertIsNotNone(with_direction.direction_combo)
        self.assertEqual(with_direction.direction(), PREV)
        with_direction.direction_combo.setCurrentIndex(1)
        self.assertEqual(with_direction.direction(), NEXT)

        without_direction = ComparePanel(show_direction=False)
        self.assertIsNone(without_direction.direction_combo)
        self.assertEqual(without_direction.direction(), PREV)

    def test_opacity_and_interval_controls_disabled_until_checked(self):
        panel = ComparePanel()
        self.assertFalse(panel.opacity_slider.isEnabled())
        self.assertFalse(panel.interval_spin.isEnabled())
        panel.onion_check.setChecked(True)
        self.assertTrue(panel.opacity_slider.isEnabled())
        panel.blink_check.setChecked(True)
        self.assertTrue(panel.interval_spin.isEnabled())
        self.assertFalse(panel.opacity_slider.isEnabled())


if __name__ == "__main__":
    unittest.main()
