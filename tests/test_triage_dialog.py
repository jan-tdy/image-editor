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

    def test_summary_lists_changes(self):
        s = self.dlg.session
        s.decide(ops.FAVOURITE)
        s.decide(ops.TRASH)
        plan = ops.build_plan(s, "/fav")
        summary = TriageSummaryDialog(None, s, plan, "/fav")
        self.assertEqual(summary.table.rowCount(), 2)
        self.assertTrue(summary.execute_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
