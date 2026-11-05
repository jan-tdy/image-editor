import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication

from image_editor.dialogs.batch_dialog import BatchDialog
from image_editor.workers.batch_journal import read_journal
from image_editor.workers.batch_worker import BatchFileJob, BatchSettings, process_one

_app = QApplication.instance() or QApplication([])


class BatchDialogJournalTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name)
        self.dialog = BatchDialog()
        self.addCleanup(self.dialog.close)

    def run_batch_to_dialog(self, settings):
        source = self.folder / "photo.png"
        Image.new("RGB", (6, 4), (90, 30, 10)).save(source)
        jobs = [BatchFileJob(str(source))]
        self.dialog._run_jobs = jobs
        self.dialog._run_settings = settings
        log = [process_one(jobs[0], settings)]
        self.dialog._on_finished(log)
        return source, log

    def test_finished_run_writes_journal_and_enables_undo(self):
        settings = BatchSettings(do_adjust=True, brightness=20, backup_before_overwrite=True)
        _, log = self.run_batch_to_dialog(settings)

        self.assertTrue(self.dialog.last_run_changed_files)
        self.assertIsNotNone(self.dialog.last_journal_path)
        self.assertTrue(self.dialog.last_journal_path.exists())
        self.assertEqual(read_journal(self.dialog.last_journal_path), log)
        self.assertTrue(self.dialog.btn_undo.isEnabled())

    def test_dialog_undo_removes_journal(self):
        from unittest.mock import patch
        from PyQt6.QtWidgets import QMessageBox

        source, _ = self.run_batch_to_dialog(
            BatchSettings(do_adjust=True, brightness=20, backup_before_overwrite=True)
        )
        journal = self.dialog.last_journal_path
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
                patch.object(QMessageBox, "information"):
            self.dialog._undo_last_run()

        self.assertFalse(journal.exists())
        self.assertIsNone(self.dialog.last_journal_path)
        self.assertEqual(Image.open(source).getpixel((0, 0)), (90, 30, 10))

    def test_run_with_no_changes_writes_no_journal(self):
        self.run_batch_to_dialog(BatchSettings())  # no edits: rename/copy only, nothing to undo
        self.assertFalse(self.dialog.last_run_changed_files)
        self.assertIsNone(self.dialog.last_journal_path)
        self.assertFalse(self.dialog.btn_undo.isEnabled())


if __name__ == "__main__":
    unittest.main()
