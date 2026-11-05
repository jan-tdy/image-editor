import tempfile
import unittest
from pathlib import Path

from PIL import Image

from image_editor.core.image_document import MAX_UNDO_DEPTH, ImageDocument


class UndoBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "square.png"
        Image.new("RGB", (100, 100), (30, 60, 90)).save(self.path)
        self.step_bytes = 100 * 100 * 3  # one RGB snapshot

    def test_history_is_trimmed_to_the_byte_budget(self):
        document = ImageDocument(str(self.path))
        document.undo_budget_bytes = self.step_bytes * 3 + 1
        for _ in range(10):
            document.flip_horizontal()
        self.assertEqual(len(document._undo_stack), 3)
        self.assertLessEqual(document._history_nbytes(), document.undo_budget_bytes)

    def test_newest_undo_step_survives_even_when_it_exceeds_the_budget(self):
        document = ImageDocument(str(self.path))
        document.undo_budget_bytes = 1
        document.flip_horizontal()
        document.flip_vertical()
        self.assertEqual(len(document._undo_stack), 1)
        self.assertTrue(document.can_undo())
        self.assertTrue(document.undo())

    def test_count_limit_still_applies_for_small_images(self):
        document = ImageDocument(str(self.path))
        for _ in range(MAX_UNDO_DEPTH + 5):
            document.flip_horizontal()
        self.assertEqual(len(document._undo_stack), MAX_UNDO_DEPTH)

    def test_undo_then_redo_restores_the_same_pixels(self):
        document = ImageDocument(str(self.path))
        document.set_adjustments(red=50)
        document.flip_horizontal()
        edited = document.base_image.tobytes()
        self.assertTrue(document.undo())
        self.assertTrue(document.redo())
        self.assertEqual(document.base_image.tobytes(), edited)

    def test_snapshots_reference_the_previous_image_instead_of_copying(self):
        document = ImageDocument(str(self.path))
        before = document.base_image
        document.flip_horizontal()
        self.assertIs(document._undo_stack[-1], before)


if __name__ == "__main__":
    unittest.main()
