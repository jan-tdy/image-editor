import os
import tempfile
import unittest
from pathlib import Path

from image_editor.core.rename_ops import (
    RenamePlan,
    RenameResult,
    apply_case,
    apply_find_replace,
    find_conflicts,
    preview_names,
)


class RenameOpsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name) / "Album"
        self.folder.mkdir()
        self.first = self.folder / "Summer Photo.JPG"
        self.second = self.folder / "portrait.png"
        self.first.write_bytes(b"first")
        self.second.write_bytes(b"second")
        os.utime(self.first, (946684800, 946684800))

    def test_case_modes(self):
        expected = {
            "keep": "mIxED words",
            "lower": "mixed words",
            "upper": "MIXED WORDS",
            "title": "Mixed Words",
            "capitalize": "Mixed words",
        }
        for mode, value in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(apply_case("mIxED words", mode), value)

    def test_plain_and_regex_replacement(self):
        self.assertEqual(apply_find_replace("photo-photo", "photo", "img", False), "img-img")
        self.assertEqual(apply_find_replace("a12b34", r"\d+", "#", True), "a#b#")

    def test_invalid_regex_has_a_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Invalid regular expression"):
            apply_find_replace("name", "[", "", True)

    def test_preview_expands_tokens_and_sequence_settings(self):
        plan = RenamePlan(
            pattern="{parent}_{name}_{n}_{date}{ext}",
            start=7,
            step=2,
            digits=4,
            case="lower",
            find=" ",
            replace="-",
        )
        results = preview_names([str(self.first), str(self.second)], plan)
        self.assertEqual(results[0].new_name, "Album_summer-photo_0007_20000101.JPG")
        self.assertTrue(results[1].new_name.startswith("Album_portrait_0009_"))
        self.assertTrue(results[1].new_name.endswith(".png"))
        self.assertIsNone(results[0].error)

    def test_preview_appends_original_extension_when_pattern_has_none(self):
        result = preview_names([str(self.second)], RenamePlan(pattern="renamed"))[0]
        self.assertEqual(result.new_name, "renamed.png")

    def test_negative_sequence_numbers_are_clamped_to_zero(self):
        result = preview_names([str(self.second)], RenamePlan(pattern="{n}", start=-3, digits=3))[0]
        self.assertEqual(result.new_name, "000.png")

    def test_preview_reports_invalid_pattern_empty_name_and_regex_per_file(self):
        cases = [
            (RenamePlan(pattern="{missing}"), "Invalid pattern"),
            (RenamePlan(pattern="   "), "empty name"),
            (RenamePlan(pattern="{name}", find="[", use_regex=True), "Invalid regular expression"),
        ]
        for plan, message in cases:
            with self.subTest(message=message):
                result = preview_names([str(self.first)], plan)[0]
                self.assertIn(message, result.error)
                self.assertEqual(result.new_name, self.first.name)

    def test_find_conflicts_detects_duplicate_targets(self):
        results = [
            RenameResult(str(self.first), "same.jpg"),
            RenameResult(str(self.second), "same.jpg"),
        ]
        target = str(self.folder / "same.jpg")
        self.assertEqual(find_conflicts(results), {target: [str(self.first), str(self.second)]})

    def test_find_conflicts_detects_external_file_but_allows_batch_source(self):
        external = self.folder / "occupied.jpg"
        external.write_bytes(b"occupied")
        collision = RenameResult(str(self.first), external.name)
        self.assertIn(str(external), find_conflicts([collision]))

        swap_target = RenameResult(str(self.first), self.second.name)
        batch_peer = RenameResult(str(self.second), self.first.name)
        self.assertEqual(find_conflicts([swap_target, batch_peer]), {})

    def test_find_conflicts_ignores_invalid_previews(self):
        result = RenameResult(str(self.first), "occupied.jpg", error="bad pattern")
        self.assertEqual(find_conflicts([result]), {})


if __name__ == "__main__":
    unittest.main()
