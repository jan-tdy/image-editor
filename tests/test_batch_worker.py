import tempfile
import unittest
from pathlib import Path

from PIL import Image

from image_editor.workers.batch_worker import (
    BatchFileJob,
    BatchLogEntry,
    BatchSettings,
    _apply_pixel_ops,
    _resolve_out_path,
    process_one,
    undo_batch,
)


class BatchWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name)

    def make_image(self, name="source.png", size=(4, 2), color=(80, 40, 20, 255)):
        path = self.folder / name
        Image.new("RGBA", size, color).save(path)
        return path

    def test_needs_pixel_ops_covers_each_pixel_setting(self):
        self.assertFalse(BatchSettings().needs_pixel_ops())
        for kwargs in (
            {"do_convert_resize": True},
            {"do_adjust": True},
            {"do_rotate": True},
            {"flip_h": True},
            {"flip_v": True},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertTrue(BatchSettings(**kwargs).needs_pixel_ops())

    def test_output_path_applies_rename_format_and_output_folder(self):
        source = self.make_image()
        output = self.folder / "output"
        settings = BatchSettings(
            do_rename=True,
            do_convert_resize=True,
            target_format=".jpg",
            output_mode="folder",
            output_folder=str(output),
        )
        path = _resolve_out_path(BatchFileJob(str(source), new_name="renamed"), settings)
        self.assertEqual(path, output / "renamed.jpg")

    def test_video_output_path_never_changes_format(self):
        source = self.folder / "clip.mp4"
        source.write_bytes(b"video")
        settings = BatchSettings(do_convert_resize=True, target_format=".png")
        self.assertEqual(_resolve_out_path(BatchFileJob(str(source), is_video=True), settings), source)

    def test_pixel_ops_rotate_and_resize_in_declared_order(self):
        image = Image.new("RGB", (4, 2), "red")
        settings = BatchSettings(
            do_rotate=True,
            rotate_degrees=90,
            do_convert_resize=True,
            resize_mode="exact",
            width=3,
            height=5,
        )
        self.assertEqual(_apply_pixel_ops(image, settings).size, (3, 5))

    def test_scale_percent_is_clamped_to_at_least_one_percent_and_pixel(self):
        image = Image.new("RGB", (4, 2), "red")
        settings = BatchSettings(do_convert_resize=True, resize_mode="scale_pct", scale_pct=0)
        self.assertEqual(_apply_pixel_ops(image, settings).size, (1, 1))

    def test_noop_does_not_rewrite_source(self):
        source = self.make_image()
        before = source.read_bytes()
        entry = process_one(BatchFileJob(str(source)), BatchSettings())
        self.assertEqual(entry.mode, "noop")
        self.assertEqual(source.read_bytes(), before)

    def test_in_place_rename_moves_source_and_is_undoable(self):
        source = self.make_image()
        target = self.folder / "renamed.png"
        settings = BatchSettings(do_rename=True)
        entry = process_one(BatchFileJob(str(source), new_name=target.name), settings)
        self.assertEqual(entry.mode, "renamed")
        self.assertFalse(source.exists())
        self.assertTrue(target.exists())
        self.assertEqual(undo_batch([entry]), [])
        self.assertTrue(source.exists())
        self.assertFalse(target.exists())

    def test_rename_refuses_to_replace_existing_file(self):
        source = self.make_image()
        target = self.make_image("occupied.png", color=(1, 2, 3, 255))
        occupied = target.read_bytes()
        entry = process_one(
            BatchFileJob(str(source), new_name=target.name),
            BatchSettings(do_rename=True),
        )
        self.assertEqual(entry.mode, "error")
        self.assertIn("already exists", entry.error)
        self.assertTrue(source.exists())
        self.assertEqual(target.read_bytes(), occupied)

    def test_folder_mode_converts_and_resizes_without_touching_source(self):
        source = self.make_image()
        before = source.read_bytes()
        output = self.folder / "output"
        settings = BatchSettings(
            do_convert_resize=True,
            target_format=".jpg",
            resize_mode="exact",
            width=2,
            height=3,
            output_mode="folder",
            output_folder=str(output),
        )
        entry = process_one(BatchFileJob(str(source)), settings)
        self.assertEqual(entry.mode, "copied")
        self.assertEqual(source.read_bytes(), before)
        with Image.open(entry.out_path) as result:
            self.assertEqual(result.size, (2, 3))
            self.assertEqual(result.mode, "RGB")

    def test_overwrite_backup_and_undo_restore_exact_original_bytes(self):
        source = self.make_image()
        original = source.read_bytes()
        settings = BatchSettings(do_adjust=True, brightness=50, backup_before_overwrite=True)
        entry = process_one(BatchFileJob(str(source)), settings)
        self.assertEqual(entry.mode, "overwritten")
        self.assertIsNotNone(entry.backup_path)
        self.assertNotEqual(source.read_bytes(), original)

        self.assertEqual(undo_batch([entry]), [])
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(Path(entry.backup_path).exists())

    def test_renamed_edit_with_backup_is_fully_undoable(self):
        source = self.make_image()
        original = source.read_bytes()
        settings = BatchSettings(do_rename=True, flip_h=True, backup_before_overwrite=True)
        entry = process_one(BatchFileJob(str(source), new_name="edited.png"), settings)
        self.assertEqual(entry.mode, "renamed_and_edited")
        self.assertFalse(source.exists())
        self.assertTrue(Path(entry.out_path).exists())

        self.assertEqual(undo_batch([entry]), [])
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(Path(entry.out_path).exists())

    def test_destructive_edit_without_backup_reports_undo_warning(self):
        source = self.make_image()
        settings = BatchSettings(do_adjust=True, brightness=10, backup_before_overwrite=False)
        entry = process_one(BatchFileJob(str(source)), settings)
        warnings = undo_batch([entry])
        self.assertEqual(len(warnings), 1)
        self.assertIn("no backup available", warnings[0])

    def test_video_is_copied_verbatim_and_pixel_operations_are_ignored(self):
        source = self.folder / "clip.mp4"
        source.write_bytes(b"not-real-video-but-verbatim")
        output = self.folder / "output"
        output.mkdir()
        settings = BatchSettings(
            do_rename=True,
            do_adjust=True,
            brightness=100,
            output_mode="folder",
            output_folder=str(output),
        )
        entry = process_one(BatchFileJob(str(source), is_video=True, new_name="copy.mp4"), settings)
        self.assertEqual(entry.mode, "copied")
        self.assertEqual(Path(entry.out_path).read_bytes(), source.read_bytes())

    def test_undo_copy_removes_only_the_generated_output(self):
        source = self.make_image()
        output = self.folder / "output"
        output.mkdir()
        settings = BatchSettings(output_mode="folder", output_folder=str(output))
        entry = process_one(BatchFileJob(str(source)), settings)
        self.assertTrue(Path(entry.out_path).exists())
        self.assertEqual(undo_batch([entry]), [])
        self.assertTrue(source.exists())
        self.assertFalse(Path(entry.out_path).exists())

    def test_missing_source_returns_per_file_error_without_raising(self):
        missing = self.folder / "missing.png"
        entry = process_one(BatchFileJob(str(missing)), BatchSettings())
        self.assertIn("no longer exists", entry.error)
        self.assertEqual(entry.src_path, str(missing))

    def test_undo_without_backup_warns_for_renamed_edit(self):
        source = self.folder / "original.png"
        output = self.folder / "edited.png"
        output.write_bytes(b"edited")
        entry = BatchLogEntry(str(source), str(output), mode="renamed_and_edited")
        warnings = undo_batch([entry])
        self.assertFalse(output.exists())
        self.assertEqual(len(warnings), 1)
        self.assertIn("original could not be restored", warnings[0])


if __name__ == "__main__":
    unittest.main()
