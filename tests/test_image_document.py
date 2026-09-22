import tempfile
import unittest
from pathlib import Path

from PIL import Image

from image_editor.core.image_document import Adjustments, ImageDocument, MAX_UNDO_DEPTH


class ImageDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "source.png"
        Image.new("RGB", (3, 2), (80, 40, 20)).save(self.path)

    def test_load_initializes_clean_independent_base_image(self):
        document = ImageDocument(str(self.path))
        self.assertEqual(document.size, (3, 2))
        self.assertFalse(document.dirty)
        self.assertIsNot(document.original, document.base_image)
        self.assertEqual(document.adjustments, Adjustments())

    def test_preview_is_cached_until_adjustments_change(self):
        document = ImageDocument(str(self.path))
        document.set_adjustments(brightness=25)
        first = document.preview_image()
        second = document.preview_image()
        self.assertIs(first, second)

        document.set_adjustments(contrast=10)
        self.assertIsNot(document.preview_image(), first)

    def test_commit_adjustments_is_an_undoable_edit(self):
        document = ImageDocument(str(self.path))
        document.set_adjustments(brightness=100)
        self.assertTrue(document.commit_adjustments())
        self.assertEqual(document.adjustments, Adjustments())
        self.assertEqual(document.base_image.getpixel((0, 0)), (160, 80, 40))

        self.assertTrue(document.undo())
        self.assertEqual(document.base_image.getpixel((0, 0)), (80, 40, 20))
        self.assertTrue(document.redo())
        self.assertEqual(document.base_image.getpixel((0, 0)), (160, 80, 40))

    def test_identity_commit_is_a_noop(self):
        document = ImageDocument(str(self.path))
        self.assertFalse(document.commit_adjustments())
        self.assertFalse(document.can_undo())

    def test_geometry_commits_pending_adjustment_before_transform(self):
        document = ImageDocument(str(self.path))
        document.set_adjustments(brightness=100)
        document.rotate90()
        self.assertEqual(document.size, (2, 3))

        self.assertTrue(document.undo())
        self.assertEqual(document.size, (3, 2))
        self.assertEqual(document.base_image.getpixel((0, 0)), (160, 80, 40))
        self.assertTrue(document.undo())
        self.assertEqual(document.base_image.getpixel((0, 0)), (80, 40, 20))

    def test_new_edit_clears_redo_history(self):
        document = ImageDocument(str(self.path))
        document.flip_horizontal()
        document.undo()
        self.assertTrue(document.can_redo())
        document.flip_vertical()
        self.assertFalse(document.can_redo())

    def test_undo_history_is_bounded(self):
        document = ImageDocument(str(self.path))
        for _ in range(MAX_UNDO_DEPTH + 7):
            document.flip_horizontal()
        undo_count = 0
        while document.undo():
            undo_count += 1
        self.assertEqual(undo_count, MAX_UNDO_DEPTH)

    def test_save_bakes_live_adjustments_into_memory_and_disk(self):
        document = ImageDocument(str(self.path))
        document.set_adjustments(brightness=100)

        document.save()

        with Image.open(self.path) as saved:
            saved.load()
            self.assertEqual(list(saved.getdata()), list(document.base_image.getdata()))
        self.assertEqual(document.adjustments, Adjustments())
        self.assertFalse(document.dirty)
        self.assertIs(document.preview_image(), document.base_image)
        self.assertTrue(document.can_undo())

    def test_save_as_updates_path_and_flattens_alpha_for_jpeg(self):
        rgba_path = Path(self.tempdir.name) / "alpha.png"
        target = Path(self.tempdir.name) / "converted.jpg"
        Image.new("RGBA", (2, 2), (10, 20, 30, 40)).save(rgba_path)
        document = ImageDocument(str(rgba_path))

        self.assertEqual(document.save(str(target), quality=80), str(target))

        self.assertEqual(document.path, str(target))
        with Image.open(target) as saved:
            self.assertEqual(saved.mode, "RGB")

    def test_revert_restores_loaded_pixels_and_is_undoable(self):
        document = ImageDocument(str(self.path))
        document.flip_horizontal()
        edited = document.base_image.copy()
        document.revert_to_original()
        self.assertEqual(list(document.base_image.getdata()), list(document.original.getdata()))
        document.undo()
        self.assertEqual(list(document.base_image.getdata()), list(edited.getdata()))

    def test_unloaded_document_rejects_preview_and_save(self):
        document = ImageDocument()
        with self.assertRaises(RuntimeError):
            document.preview_image()
        with self.assertRaises(RuntimeError):
            document.save(str(Path(self.tempdir.name) / "out.png"))


if __name__ == "__main__":
    unittest.main()
