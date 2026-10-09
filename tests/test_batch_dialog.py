import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication

from image_editor.dialogs.batch_dialog import BatchDialog

_app = QApplication.instance() or QApplication([])


class _FakeMessageBox:
    warning_calls = []
    information_calls = []

    @classmethod
    def warning(cls, *args):
        cls.warning_calls.append(args)

    @classmethod
    def information(cls, *args):
        cls.information_calls.append(args)


class BatchDialogConflictTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name)
        _FakeMessageBox.warning_calls = []
        _FakeMessageBox.information_calls = []

    def make_image(self, name, color=(80, 40, 20)):
        path = self.folder / name
        Image.new("RGB", (4, 2), color).save(path)
        return path

    def make_dialog(self, paths):
        dialog = BatchDialog(initial_paths=[str(p) for p in paths])
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_build_jobs_blocks_a_same_stem_different_extension_conversion_collision(self):
        # image-editor#2: sunset.png + sunset.bmp both converting to JPEG
        # into one output folder must not silently drop one of them.
        png = self.make_image("sunset.png")
        bmp = self.make_image("sunset.bmp")
        dialog = self.make_dialog([png, bmp])

        dialog.convert_group.setChecked(True)
        dialog.format_combo.setCurrentText("JPEG")
        dialog.radio_folder.setChecked(True)
        dialog.folder_edit.setText(str(self.folder / "out"))

        settings = dialog._build_settings()
        with patch("image_editor.dialogs.batch_dialog.QMessageBox", _FakeMessageBox):
            jobs = dialog._build_jobs(settings)

        self.assertIsNone(jobs)
        self.assertEqual(len(_FakeMessageBox.warning_calls), 1)
        message = str(_FakeMessageBox.warning_calls[0])
        self.assertIn("conflict", message.lower())

    def test_preview_flags_the_same_collision_shown_at_run_time(self):
        png = self.make_image("sunset.png")
        bmp = self.make_image("sunset.bmp")
        dialog = self.make_dialog([png, bmp])

        dialog.convert_group.setChecked(True)
        dialog.format_combo.setCurrentText("JPEG")

        texts = {dialog.table.item(row, 2).text() for row in range(dialog.table.rowCount())}
        self.assertTrue(any("conflict" in t for t in texts))

    def test_build_jobs_allows_non_colliding_conversion(self):
        png = self.make_image("sunrise.png")
        bmp = self.make_image("sunset.bmp")
        dialog = self.make_dialog([png, bmp])

        dialog.convert_group.setChecked(True)
        dialog.format_combo.setCurrentText("JPEG")
        dialog.radio_folder.setChecked(True)
        dialog.folder_edit.setText(str(self.folder / "out"))

        settings = dialog._build_settings()
        with patch("image_editor.dialogs.batch_dialog.QMessageBox", _FakeMessageBox):
            jobs = dialog._build_jobs(settings)

        self.assertIsNotNone(jobs)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(_FakeMessageBox.warning_calls, [])

    def test_build_jobs_blocks_writing_into_a_pre_existing_output_file(self):
        png = self.make_image("sunset.png")
        out_dir = self.folder / "out"
        out_dir.mkdir()
        (out_dir / "sunset.png").write_bytes(b"already here")
        dialog = self.make_dialog([png])

        dialog.radio_folder.setChecked(True)
        dialog.folder_edit.setText(str(out_dir))

        settings = dialog._build_settings()
        with patch("image_editor.dialogs.batch_dialog.QMessageBox", _FakeMessageBox):
            jobs = dialog._build_jobs(settings)

        self.assertIsNone(jobs)
        self.assertEqual(len(_FakeMessageBox.warning_calls), 1)


if __name__ == "__main__":
    unittest.main()
