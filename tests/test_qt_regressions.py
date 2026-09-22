import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QMessageBox

from image_editor.app import MainWindow
from image_editor.core.convert import make_thumbnail_qimage, pil_to_qimage
from image_editor.models.file_model import MediaEntry
from image_editor.widgets.thumbnail_panel import _ThumbnailWorker
from image_editor.widgets.video_view import MULTIMEDIA_AVAILABLE, VideoView, _format_ms


class QtConversionTests(unittest.TestCase):
    def test_rgb_rows_with_unaligned_widths_preserve_every_pixel(self):
        for width in range(1, 8):
            with self.subTest(width=width):
                image = Image.new("RGB", (width, 3))
                pixels = [
                    ((x * 31 + y * 7) % 256, (x * 13 + y * 41) % 256, (x * 19 + y * 23) % 256)
                    for y in range(3)
                    for x in range(width)
                ]
                image.putdata(pixels)
                converted = pil_to_qimage(image)
                actual = [
                    converted.pixelColor(x, y).getRgb()[:3]
                    for y in range(3)
                    for x in range(width)
                ]
                self.assertEqual(actual, pixels)

    def test_rgba_conversion_preserves_alpha(self):
        image = Image.new("RGBA", (1, 1), (11, 22, 33, 44))
        self.assertEqual(pil_to_qimage(image).pixelColor(0, 0).getRgb(), (11, 22, 33, 44))

    def test_qimage_owns_a_copy_of_the_source_pixels(self):
        image = Image.new("RGB", (2, 1), (10, 20, 30))
        converted = pil_to_qimage(image)
        image.putpixel((0, 0), (200, 210, 220))
        self.assertEqual(converted.pixelColor(0, 0).getRgb()[:3], (10, 20, 30))

    def test_thumbnail_qimage_fits_box_without_upscaling(self):
        large = make_thumbnail_qimage(Image.new("RGB", (200, 100)), 50)
        small = make_thumbnail_qimage(Image.new("RGB", (10, 5)), 50)
        self.assertIsInstance(large, QImage)
        self.assertEqual((large.width(), large.height()), (50, 25))
        self.assertEqual((small.width(), small.height()), (10, 5))

    def test_thumbnail_worker_emits_qimage_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.png"
            Image.new("RGB", (20, 10), "red").save(path)
            received = []
            worker = _ThumbnailWorker(str(path))
            worker.signals.ready.connect(lambda emitted_path, image: received.append((emitted_path, image)))
            worker.run()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], str(path))
        self.assertIsInstance(received[0][1], QImage)

    def test_thumbnail_worker_swallows_unreadable_image(self):
        worker = _ThumbnailWorker("/definitely/missing/image.png")
        received = []
        worker.signals.ready.connect(lambda *args: received.append(args))
        worker.run()
        self.assertEqual(received, [])


class VideoHelpersTests(unittest.TestCase):
    def test_format_ms_handles_negative_minutes_and_hours(self):
        self.assertEqual(_format_ms(-1), "0:00")
        self.assertEqual(_format_ms(65_999), "1:05")
        self.assertEqual(_format_ms(3_661_000), "1:01:01")

    @unittest.skipUnless(MULTIMEDIA_AVAILABLE, "Qt multimedia classes are unavailable")
    def test_stop_and_release_uses_null_qurl(self):
        player = Mock()
        VideoView.stop_and_release(SimpleNamespace(player=player))
        player.stop.assert_called_once_with()
        source = player.setSource.call_args.args[0]
        self.assertIsInstance(source, QUrl)
        self.assertTrue(source.isEmpty())


class _FakeMessageBox:
    Icon = QMessageBox.Icon
    StandardButton = QMessageBox.StandardButton
    choice = QMessageBox.StandardButton.Cancel
    critical_calls = []

    def __init__(self, _parent=None):
        self.text = ""

    def setIcon(self, _icon):
        pass

    def setWindowTitle(self, _title):
        pass

    def setText(self, text):
        self.text = text

    def setStandardButtons(self, _buttons):
        pass

    def setDefaultButton(self, _button):
        pass

    def exec(self):
        return self.choice

    @classmethod
    def critical(cls, *args):
        cls.critical_calls.append(args)

    @classmethod
    def warning(cls, *args):
        cls.warning_calls.append(args)


class MainWindowRegressionTests(unittest.TestCase):
    def setUp(self):
        _FakeMessageBox.critical_calls = []
        _FakeMessageBox.warning_calls = []

    def confirm(self, document, choice):
        _FakeMessageBox.choice = choice
        window = SimpleNamespace(document=document)
        with patch("image_editor.app.QMessageBox", _FakeMessageBox):
            return MainWindow._confirm_discard_if_dirty(window)

    def test_clean_or_missing_document_never_prompts(self):
        self.assertTrue(self.confirm(None, QMessageBox.StandardButton.Cancel))
        self.assertTrue(self.confirm(SimpleNamespace(dirty=False), QMessageBox.StandardButton.Cancel))

    def test_unsaved_changes_cancel_aborts_operation(self):
        document = SimpleNamespace(dirty=True, path="/tmp/photo.png")
        self.assertFalse(self.confirm(document, QMessageBox.StandardButton.Cancel))
        self.assertTrue(document.dirty)

    def test_unsaved_changes_discard_clears_dirty_flag(self):
        document = SimpleNamespace(dirty=True, path="/tmp/photo.png")
        self.assertTrue(self.confirm(document, QMessageBox.StandardButton.Discard))
        self.assertFalse(document.dirty)

    def test_unsaved_changes_save_invokes_document_save(self):
        document = SimpleNamespace(dirty=True, path="/tmp/photo.png", save=Mock())
        self.assertTrue(self.confirm(document, QMessageBox.StandardButton.Save))
        document.save.assert_called_once_with()

    def test_failed_save_aborts_and_reports_error(self):
        document = SimpleNamespace(
            dirty=True,
            path="/tmp/photo.png",
            save=Mock(side_effect=OSError("disk full")),
        )
        self.assertFalse(self.confirm(document, QMessageBox.StandardButton.Save))
        self.assertEqual(len(_FakeMessageBox.critical_calls), 1)
        self.assertIn("disk full", str(_FakeMessageBox.critical_calls[0]))

    def test_clear_view_releases_video_before_resetting_state(self):
        video_view = Mock()
        window = SimpleNamespace(
            document=object(),
            is_video=True,
            video_view=video_view,
            image_view=Mock(),
            path_label=Mock(),
            size_label=Mock(),
            zoom_label=Mock(),
            setWindowTitle=Mock(),
        )
        MainWindow._clear_view(window)
        video_view.stop_and_release.assert_called_once_with()
        self.assertIsNone(window.document)
        self.assertFalse(window.is_video)
        window.image_view.clear.assert_called_once_with()

    def test_open_folder_does_nothing_when_dirty_guard_is_cancelled(self):
        window = SimpleNamespace(
            _confirm_discard_if_dirty=Mock(return_value=False),
            navigator=Mock(),
            thumbnail_panel=Mock(),
            settings=Mock(),
        )
        MainWindow.open_folder(window, "/new/folder")
        window.navigator.set_folder.assert_not_called()
        window.thumbnail_panel.load_folder.assert_not_called()

    def test_rename_rejects_path_separator_before_filesystem_mutation(self):
        entry = MediaEntry("/tmp/original.png", is_video=False)
        window = SimpleNamespace(
            navigator=SimpleNamespace(current=Mock(return_value=entry)),
            _confirm_discard_if_dirty=Mock(return_value=True),
        )
        with (
            patch("image_editor.app.QInputDialog.getText", return_value=("nested/name", True)),
            patch("image_editor.app.QMessageBox", _FakeMessageBox),
        ):
            MainWindow.rename_current(window)
        self.assertEqual(len(_FakeMessageBox.warning_calls), 1)
        self.assertIn("path separator", str(_FakeMessageBox.warning_calls[0]))


if __name__ == "__main__":
    unittest.main()
