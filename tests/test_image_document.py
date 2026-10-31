import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageSequence

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


class AnimatedGifDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "anim.gif"
        frames = [
            Image.new("RGB", (4, 2), (255, 0, 0)),
            Image.new("RGB", (4, 2), (0, 255, 0)),
            Image.new("RGB", (4, 2), (0, 0, 255)),
        ]
        # Durations must be multiples of 10ms: the GIF format stores timing
        # in centiseconds, so anything finer gets silently rounded on save.
        frames[0].save(
            self.path,
            save_all=True,
            append_images=frames[1:],
            duration=[50, 70, 100],
            loop=0,
        )

    def test_load_reads_every_frame_with_its_duration(self):
        document = ImageDocument(str(self.path))
        self.assertTrue(document.is_animated)
        self.assertEqual(document.frame_count, 3)
        self.assertEqual(document.frame_durations, [50, 70, 100])
        self.assertEqual(document.current_frame_index, 0)
        self.assertEqual(document.base_image.getpixel((0, 0))[:3], (255, 0, 0))

    def test_set_current_frame_switches_the_displayed_frame(self):
        document = ImageDocument(str(self.path))
        document.set_current_frame(1)
        self.assertEqual(document.current_frame_index, 1)
        self.assertEqual(document.base_image.getpixel((0, 0))[:3], (0, 255, 0))

    def test_set_current_frame_clamps_out_of_range_indices(self):
        document = ImageDocument(str(self.path))
        document.set_current_frame(99)
        self.assertEqual(document.current_frame_index, 2)
        document.set_current_frame(-5)
        self.assertEqual(document.current_frame_index, 0)

    def test_rotate_applies_to_every_frame_and_is_undoable(self):
        document = ImageDocument(str(self.path))
        document.rotate90()
        self.assertEqual(document.size, (2, 4))
        for frame in document.frames:
            self.assertEqual(frame.size, (2, 4))

        self.assertTrue(document.undo())
        self.assertEqual(document.size, (4, 2))
        for frame in document.frames:
            self.assertEqual(frame.size, (4, 2))

    def test_commit_adjustments_bakes_into_every_frame(self):
        document = ImageDocument(str(self.path))
        originals = [frame.copy() for frame in document.frames]
        document.set_adjustments(brightness=-100)
        self.assertTrue(document.commit_adjustments())
        # Every frame should be darkened, not just the one that happened to
        # be on screen when the adjustment was committed.
        for frame, original in zip(document.frames, originals):
            self.assertNotEqual(list(frame.getdata()), list(original.getdata()))

    def test_save_as_gif_round_trips_frames_and_durations(self):
        document = ImageDocument(str(self.path))
        document.rotate90()
        out_path = Path(self.tempdir.name) / "out.gif"

        document.save(str(out_path))

        with Image.open(out_path) as saved:
            self.assertTrue(saved.is_animated)
            self.assertEqual(saved.n_frames, 3)
            durations = []
            for frame in ImageSequence.Iterator(saved):
                durations.append(frame.info.get("duration"))
            self.assertEqual(durations, [50, 70, 100])
        self.assertFalse(document.dirty)

    def test_save_as_png_exports_only_the_current_frame(self):
        document = ImageDocument(str(self.path))
        document.set_current_frame(1)
        out_path = Path(self.tempdir.name) / "frame.png"

        document.save(str(out_path))

        with Image.open(out_path) as saved:
            self.assertFalse(getattr(saved, "is_animated", False))
            self.assertEqual(saved.convert("RGB").getpixel((0, 0)), (0, 255, 0))

    def test_revert_to_original_restores_all_frames(self):
        document = ImageDocument(str(self.path))
        document.rotate90()
        document.revert_to_original()
        self.assertEqual(document.size, (4, 2))
        self.assertEqual(document.frame_count, 3)
        self.assertEqual(document.base_image.getpixel((0, 0))[:3], (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
