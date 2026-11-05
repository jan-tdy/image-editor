import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageCms
from PIL.ExifTags import Base

from image_editor.workers.batch_journal import (
    JOURNAL_PREFIX,
    journal_directory,
    read_journal,
    undo_journal,
    write_journal,
)
from image_editor.workers.batch_worker import (
    BatchFileJob,
    BatchLogEntry,
    BatchSettings,
    process_one,
)


class BatchJournalTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name)

    def make_png(self, name, color=(80, 40, 20)):
        path = self.folder / name
        Image.new("RGB", (4, 4), color).save(path)
        return path

    def test_round_trip_preserves_entries(self):
        log = [
            BatchLogEntry("/a/x.png", "/a/x.png", mode="overwritten", backup_path="/a/x.png.bak"),
            BatchLogEntry("/a/y.png", "/out/y.jpg", mode="copied"),
            BatchLogEntry("/a/z.png", "", mode="error", error="boom"),
        ]
        path = write_journal(log, self.folder)
        self.assertTrue(path.name.startswith(JOURNAL_PREFIX))
        self.assertEqual(read_journal(path), log)

    def test_journal_is_hidden_and_versioned(self):
        path = write_journal([BatchLogEntry("/a/x.png", "/a/x.png", mode="copied")], self.folder)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertTrue(path.name.startswith("."))
        self.assertEqual(list(self.folder.glob("*.tmp")), [])

    def test_read_rejects_foreign_or_broken_files(self):
        bad_version = self.folder / "v.json"
        bad_version.write_text(json.dumps({"version": 99, "entries": []}), encoding="utf-8")
        broken = self.folder / "b.json"
        broken.write_text("{not json", encoding="utf-8")
        malformed = self.folder / "m.json"
        malformed.write_text(json.dumps({"version": 1, "entries": [{"src_path": 5}]}), encoding="utf-8")
        for path in (bad_version, broken, malformed):
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                read_journal(path)

    def test_journal_directory_prefers_output_folder(self):
        jobs = [BatchFileJob(str(self.folder / "a" / "x.png"))]
        settings = BatchSettings(output_mode="folder", output_folder=str(self.folder / "out"))
        self.assertEqual(journal_directory(jobs, settings), self.folder / "out")

    def test_journal_directory_uses_common_parent_for_overwrite(self):
        jobs = [
            BatchFileJob(str(self.folder / "a" / "x.png")),
            BatchFileJob(str(self.folder / "a" / "y.png")),
        ]
        self.assertEqual(journal_directory(jobs, BatchSettings()), self.folder / "a")
        mixed = jobs + [BatchFileJob(str(self.folder / "b" / "z.png"))]
        self.assertEqual(journal_directory(mixed, BatchSettings()), self.folder)

    def test_undo_journal_restores_overwritten_original_and_removes_journal(self):
        source = self.make_png("photo.png")
        original_bytes = source.read_bytes()
        settings = BatchSettings(do_adjust=True, brightness=40, backup_before_overwrite=True)
        entry = process_one(BatchFileJob(str(source)), settings)
        self.assertEqual(entry.mode, "overwritten")
        self.assertNotEqual(source.read_bytes(), original_bytes)

        journal = write_journal([entry], self.folder)
        self.assertEqual(undo_journal(journal), [])

        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertFalse(Path(entry.backup_path).exists())
        self.assertFalse(journal.exists())

    def test_undo_journal_keeps_journal_when_a_step_cannot_be_reverted(self):
        source = self.make_png("photo.png")
        entry = BatchLogEntry(str(source), str(source), mode="overwritten", backup_path=None)
        journal = write_journal([entry], self.folder)
        warnings = undo_journal(journal)
        self.assertEqual(len(warnings), 1)
        self.assertTrue(journal.exists())

    def test_reencoded_batch_output_keeps_metadata_unless_disabled(self):
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        exif = Image.Exif()
        exif[Base.Make] = "TestCam"
        source = self.folder / "photo.jpg"
        Image.new("RGB", (10, 6), (5, 5, 5)).save(source, exif=exif.tobytes(), icc_profile=profile)
        out_dir = self.folder / "out"

        kept = process_one(
            BatchFileJob(str(source)),
            BatchSettings(output_mode="folder", output_folder=str(out_dir), do_adjust=True, brightness=5),
        )
        kept_img = Image.open(kept.out_path)
        self.assertEqual(kept_img.getexif().get(Base.Make), "TestCam")
        self.assertTrue(kept_img.info.get("icc_profile"))

        stripped = process_one(
            BatchFileJob(str(source)),
            BatchSettings(
                output_mode="folder", output_folder=str(out_dir / "bare"),
                do_adjust=True, brightness=5, keep_metadata=False,
            ),
        )
        bare_img = Image.open(stripped.out_path)
        self.assertIsNone(bare_img.getexif().get(Base.Make))
        self.assertFalse(bare_img.info.get("icc_profile"))


if __name__ == "__main__":
    unittest.main()
