import tempfile
import unittest
from pathlib import Path

from image_editor.models.file_model import FolderNavigator, list_media


class FileModelTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.folder = Path(self.tempdir.name)

    def touch(self, name):
        path = self.folder / name
        path.write_bytes(b"data")
        return path

    def test_list_media_filters_files_and_naturally_sorts_names(self):
        self.touch("image10.png")
        video = self.touch("Image2.MP4")
        image = self.touch("image1.jpg")
        self.touch("notes.txt")
        (self.folder / "fake3.png").mkdir()

        entries = list_media(str(self.folder))

        self.assertEqual([entry.name for entry in entries], ["image1.jpg", "Image2.MP4", "image10.png"])
        self.assertFalse(entries[0].is_video)
        self.assertEqual(entries[0].path, str(image))
        self.assertTrue(entries[1].is_video)
        self.assertEqual(entries[1].path, str(video))

    def test_list_media_returns_empty_for_missing_folder(self):
        self.assertEqual(list_media(str(self.folder / "missing")), [])

    def test_set_folder_selects_requested_path(self):
        first = self.touch("1.png")
        second = self.touch("2.png")
        navigator = FolderNavigator()
        navigator.set_folder(str(self.folder), select_path=str(second))
        self.assertEqual(navigator.current().path, str(second))
        self.assertTrue(navigator.has_prev())
        self.assertFalse(navigator.has_next())

    def test_missing_initial_selection_falls_back_to_first_entry(self):
        first = self.touch("1.png")
        self.touch("2.png")
        navigator = FolderNavigator()
        navigator.set_folder(str(self.folder), select_path=str(self.folder / "missing.png"))
        self.assertEqual(navigator.current().path, str(first))
        self.assertEqual(navigator.index, 0)

    def test_navigation_stops_at_boundaries(self):
        first = self.touch("1.png")
        second = self.touch("2.png")
        navigator = FolderNavigator()
        navigator.set_folder(str(self.folder))
        self.assertIsNone(navigator.prev())
        self.assertEqual(navigator.next().path, str(second))
        self.assertIsNone(navigator.next())
        self.assertEqual(navigator.prev().path, str(first))

    def test_refresh_retains_current_path_when_it_still_exists(self):
        self.touch("1.png")
        second = self.touch("2.png")
        navigator = FolderNavigator()
        navigator.set_folder(str(self.folder), str(second))
        self.touch("0.png")
        navigator.refresh()
        self.assertEqual(navigator.current().path, str(second))

    def test_refresh_clamps_index_when_current_file_is_removed(self):
        self.touch("1.png")
        second = self.touch("2.png")
        third = self.touch("3.png")
        navigator = FolderNavigator()
        navigator.set_folder(str(self.folder), str(third))
        third.unlink()
        navigator.refresh()
        self.assertEqual(navigator.current().path, str(second))
        self.assertEqual(navigator.index, 1)

    def test_refresh_empty_folder_resets_index(self):
        only = self.touch("only.png")
        navigator = FolderNavigator()
        navigator.set_folder(str(self.folder))
        only.unlink()
        navigator.refresh()
        self.assertEqual(navigator.entries, [])
        self.assertEqual(navigator.index, -1)
        self.assertIsNone(navigator.current())


if __name__ == "__main__":
    unittest.main()
