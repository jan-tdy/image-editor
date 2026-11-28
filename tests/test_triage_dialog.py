import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication

from image_editor.core import triage_ops as ops
from image_editor.dialogs.triage_dialog import TriageReviewDialog, TriageSummaryDialog

_app = QApplication.instance() or QApplication([])


class TriageReviewDialogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = []
        for n in ("a.png", "b.png", "c.png"):
            p = Path(self.tmp.name, n)
            Image.new("RGB", (40, 30), (200, 10, 10)).save(p)
            self.paths.append(str(p))
        self.dlg = TriageReviewDialog(None, ops.TriageSession(self.paths), os.path.join(self.tmp.name, "fav"))

    def test_buttons_drive_session(self):
        d = self.dlg
        self.assertFalse(d.back_button.isEnabled())
        d.next_button.click()
        self.assertEqual(os.path.basename(d.session.current), "b.png")
        self.assertTrue(d.back_button.isEnabled())
        d.back_button.click()
        self.assertEqual(os.path.basename(d.session.current), "a.png")
        self.assertIn("a.png", d.info.text())

    def test_rename_applies_to_current(self):
        d = self.dlg
        d.name_edit.setText("sunset")
        d.rename_button.click()
        self.assertEqual(d.session.renames[self.paths[0]], "sunset.png")
        self.assertEqual(d.name_edit.text(), "sunset.png")

    def test_key_shortcuts_not_swallowed_by_name_field(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        d = self.dlg
        d.show()
        self.assertFalse(d.name_edit.hasFocus())
        d.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(d.session.decisions[self.paths[0]], ops.FAVOURITE)

    def test_next_on_decided_photo_keeps_decision_in_place(self):
        d = self.dlg
        d.trash_button.click()  # a -> trash, current b
        d.back_button.click()   # back to a, decision kept
        self.assertEqual(d.session.decisions[self.paths[0]], ops.TRASH)
        d.next_button.click()   # "Next" on an already-decided photo
        self.assertEqual(os.path.basename(d.session.current), "b.png")
        self.assertEqual(d.session.decisions.get(self.paths[0]), ops.TRASH)
        self.assertEqual([os.path.basename(p) for p in d.session.queue], ["c.png"])

    def test_clear_button_undecides_current_photo(self):
        d = self.dlg
        d.trash_button.click()  # a -> trash, current b
        d.back_button.click()   # back to a
        self.assertTrue(d.clear_button.isEnabled())
        d.clear_button.click()
        self.assertNotIn(self.paths[0], d.session.decisions)
        self.assertEqual(os.path.basename(d.session.current), "a.png")
        self.assertFalse(d.clear_button.isEnabled())

    def test_summary_lists_changes(self):
        s = self.dlg.session
        s.decide(ops.FAVOURITE)
        s.decide(ops.TRASH)
        plan = ops.build_plan(s, "/fav")
        summary = TriageSummaryDialog(None, s, plan, "/fav")
        self.assertEqual(summary.table.rowCount(), 2)
        self.assertTrue(summary.execute_button.isEnabled())


class TriageReviewDialogCompareTests(unittest.TestCase):
    """Onion skin / blink comparison against the previously shown photo."""

    def setUp(self):
        from PyQt6.QtGui import QColor

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = []
        for n, color in (("a.png", (255, 0, 0)), ("b.png", (0, 255, 0)), ("c.png", (0, 0, 255))):
            p = Path(self.tmp.name, n)
            Image.new("RGB", (20, 10), color).save(p)
            self.paths.append(str(p))
        self.dlg = TriageReviewDialog(None, ops.TriageSession(self.paths), os.path.join(self.tmp.name, "fav"))
        self._QColor = QColor

    def test_no_reference_for_the_first_photo(self):
        self.assertIsNone(self.dlg._reference_path())

    def test_reference_is_the_previously_shown_photo(self):
        d = self.dlg
        d.next_button.click()  # a deferred, current -> b
        self.assertEqual(d._reference_path(), self.paths[0])
        d.next_button.click()  # b deferred, current -> c
        self.assertEqual(d._reference_path(), self.paths[1])

    def test_onion_skin_blends_the_reference_photo(self):
        d = self.dlg
        d.next_button.click()  # current -> b (green), reference -> a (red)
        d.compare_panel.set_onion_checked(True)
        d.compare_panel.opacity_slider.setValue(50)
        pixmap = d.photo._pixmap
        color = pixmap.toImage().pixelColor(0, 0)
        # Roughly an even mix of green (current) and red (reference).
        self.assertGreater(color.red(), 100)
        self.assertGreater(color.green(), 100)
        self.assertLess(color.blue(), 50)

    def test_blink_mode_flips_between_current_and_reference(self):
        d = self.dlg
        d.next_button.click()  # current -> b (green), reference -> a (red)
        d.compare_panel.set_blink_checked(True)
        self.assertTrue(d.blink_timer.isActive())
        d._blink_tick()
        color = d.photo._pixmap.toImage().pixelColor(0, 0)
        self.assertEqual(color, self._QColor(255, 0, 0))  # showing the reference
        d._blink_tick()
        color = d.photo._pixmap.toImage().pixelColor(0, 0)
        self.assertEqual(color, self._QColor(0, 255, 0))  # back to the current photo

    def test_onion_and_blink_are_mutually_exclusive_and_stop_the_timer(self):
        d = self.dlg
        d.next_button.click()
        d.compare_panel.set_blink_checked(True)
        self.assertTrue(d.blink_timer.isActive())
        d.compare_panel.set_onion_checked(True)
        self.assertFalse(d.blink_timer.isActive())
        self.assertEqual(d.compare_mode, "onion")

    def test_o_and_b_shortcuts_toggle_the_modes(self):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        d = self.dlg
        d.show()
        d.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_O, Qt.KeyboardModifier.NoModifier))
        self.assertTrue(d.compare_panel.onion_check.isChecked())
        d.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier))
        self.assertTrue(d.compare_panel.blink_check.isChecked())
        self.assertFalse(d.compare_panel.onion_check.isChecked())


if __name__ == "__main__":
    unittest.main()
