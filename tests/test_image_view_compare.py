import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from image_editor.widgets.image_view import ImageView

_app = QApplication.instance() or QApplication([])


def _pixmap(w, h, color=(255, 0, 0)):
    pix = QPixmap(w, h)
    pix.fill(QColor(*color))
    return pix


class ImageViewCompareTests(unittest.TestCase):
    def setUp(self):
        self.view = ImageView()

    def test_no_overlay_until_a_compare_pixmap_is_set(self):
        self.view.set_pixmap(_pixmap(100, 60))
        self.assertFalse(self.view.has_compare_pixmap())

    def test_compare_pixmap_is_scaled_to_the_base_image_size(self):
        self.view.set_pixmap(_pixmap(100, 60))
        self.view.set_compare_pixmap(_pixmap(400, 300))
        self.assertTrue(self.view.has_compare_pixmap())
        self.assertEqual(self.view._compare_item.pixmap().size().width(), 100)
        self.assertEqual(self.view._compare_item.pixmap().size().height(), 60)

    def test_visibility_and_opacity_setters(self):
        self.view.set_pixmap(_pixmap(100, 60))
        self.view.set_compare_pixmap(_pixmap(100, 60))
        self.assertFalse(self.view._compare_item.isVisible())
        self.view.set_compare_visible(True)
        self.assertTrue(self.view._compare_item.isVisible())
        self.view.set_compare_opacity(0.3)
        self.assertAlmostEqual(self.view._compare_item.opacity(), 0.3)

    def test_overlay_survives_set_pixmap_without_rescaling_same_size(self):
        self.view.set_pixmap(_pixmap(100, 60))
        self.view.set_compare_pixmap(_pixmap(400, 300))
        self.view.set_compare_visible(True)
        self.view.set_compare_opacity(0.4)
        scaled_before = self.view._compare_scaled

        # A same-size refresh (e.g. a live adjustment preview tick) must not
        # pay a rescale cost, and must keep the overlay's state.
        self.view.set_pixmap(_pixmap(100, 60), recenter=False)
        self.assertIs(self.view._compare_scaled, scaled_before)
        self.assertTrue(self.view.has_compare_pixmap())
        self.assertTrue(self.view._compare_item.isVisible())
        self.assertAlmostEqual(self.view._compare_item.opacity(), 0.4)

    def test_overlay_is_rescaled_when_base_image_size_changes(self):
        self.view.set_pixmap(_pixmap(100, 60))
        self.view.set_compare_pixmap(_pixmap(400, 300))
        scaled_before = self.view._compare_scaled
        self.view.set_pixmap(_pixmap(50, 30))
        self.assertIsNot(self.view._compare_scaled, scaled_before)
        self.assertEqual(self.view._compare_item.pixmap().size().width(), 50)

    def test_set_compare_pixmap_none_clears_overlay(self):
        self.view.set_pixmap(_pixmap(100, 60))
        self.view.set_compare_pixmap(_pixmap(100, 60))
        self.view.set_compare_pixmap(None)
        self.assertFalse(self.view.has_compare_pixmap())

    def test_clear_drops_compare_state(self):
        self.view.set_pixmap(_pixmap(100, 60))
        self.view.set_compare_pixmap(_pixmap(100, 60))
        self.view.clear()
        self.assertFalse(self.view.has_compare_pixmap())
        self.view.set_pixmap(_pixmap(100, 60))
        self.assertFalse(self.view.has_compare_pixmap())


if __name__ == "__main__":
    unittest.main()
