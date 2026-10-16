import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication

from image_editor.core.autostack_ops import AutoStackResult
from image_editor.dialogs.autostack_dialog import AutoStackDialog

_app = QApplication.instance() or QApplication([])


class AutoStackDialogDroppedMarkersTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.paths = []
        for name in ("a.png", "b.png", "c.png", "d.png"):
            path = Path(self.tempdir.name) / name
            Image.new("RGB", (4, 4), (10, 20, 30)).save(path)
            self.paths.append(str(path))

        self.dialog = AutoStackDialog(initial_paths=self.paths)
        self.addCleanup(self.dialog.deleteLater)
        self.dialog._run_paths = self.paths

    def _item_texts(self):
        return [self.dialog.list_widget.item(i).text() for i in range(self.dialog.list_widget.count())]

    def test_marks_only_the_photos_left_out_of_the_result(self):
        result = AutoStackResult(
            image=Image.new("RGB", (10, 10)),
            mode_used="flat",
            used_indices=[0, 2],  # a.png and c.png were used; b.png and d.png were not
            total_count=4,
        )
        self.dialog._mark_dropped_photos(result)
        self.assertEqual(
            self._item_texts(),
            ["a.png", "b.png  (not used)", "c.png", "d.png  (not used)"],
        )

    def test_clearing_restores_plain_filenames(self):
        result = AutoStackResult(
            image=Image.new("RGB", (10, 10)),
            mode_used="flat",
            used_indices=[0],
            total_count=4,
        )
        self.dialog._mark_dropped_photos(result)
        self.dialog._clear_dropped_markers()
        self.assertEqual(self._item_texts(), ["a.png", "b.png", "c.png", "d.png"])

    def test_all_used_marks_nothing(self):
        result = AutoStackResult(
            image=Image.new("RGB", (10, 10)),
            mode_used="panorama",
            used_indices=[0, 1, 2, 3],
            total_count=4,
        )
        self.dialog._mark_dropped_photos(result)
        self.assertEqual(self._item_texts(), ["a.png", "b.png", "c.png", "d.png"])


if __name__ == "__main__":
    unittest.main()
