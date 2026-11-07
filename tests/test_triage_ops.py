import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from image_editor.core import triage_ops as ops


class TriageSessionTests(unittest.TestCase):
    def test_defer_goes_to_end_and_back_returns(self):
        s = ops.TriageSession(["a", "b", "c"])
        self.assertEqual(s.current, "a")
        s.defer()
        self.assertEqual((s.current, list(s.queue)), ("b", ["c", "a"]))
        s.decide(ops.KEEP)  # b
        s.decide(ops.TRASH)  # c
        self.assertEqual(s.current, "a")
        s.decide(ops.FAVOURITE)
        self.assertTrue(s.finished)
        s.resume()
        self.assertEqual(s.current, "a")
        s.back()
        self.assertEqual(s.current, "c")
        self.assertEqual(s.decisions["c"], ops.TRASH)

    def test_back_to_deferred_photo_removes_it_from_queue_end(self):
        s = ops.TriageSession(["a", "b", "c"])
        s.defer()          # a deferred, current b
        s.back()           # view a again
        self.assertEqual(s.current, "a")
        self.assertEqual(list(s.queue), ["b", "c"])
        s.decide(ops.KEEP)
        self.assertEqual(s.current, "b")

    def test_back_then_forward_shows_every_photo(self):
        s = ops.TriageSession(["a", "b", "c"])
        s.decide(ops.KEEP)
        s.decide(ops.KEEP)
        s.back()
        s.back()
        self.assertEqual(s.current, "a")
        seen = []
        while not s.finished:
            seen.append(s.current)
            s.decide(ops.KEEP)
        self.assertEqual(seen, ["a", "b", "c"])

    def test_defer_last_photo_is_noop(self):
        s = ops.TriageSession(["a"])
        s.defer()
        self.assertEqual(s.current, "a")
        self.assertEqual(s.remaining(), 1)

    def test_normalize_name(self):
        self.assertEqual(ops.normalize_new_name("/x/a.jpg", "b"), "b.jpg")
        self.assertEqual(ops.normalize_new_name("/x/a.jpg", "b.png"), "b.png")
        self.assertIsNone(ops.normalize_new_name("/x/a.jpg", "  "))
        self.assertIsNone(ops.normalize_new_name("/x/a.jpg", "../b"))


class TriagePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name, "src")
        self.fav = Path(self.tmp.name, "fav")
        self.src.mkdir()
        self.paths = []
        for n in ("a.png", "b.png", "c.png", "d.png"):
            p = self.src / n
            Image.new("RGB", (4, 4)).save(p)
            self.paths.append(str(p))

    def test_collect_orders(self):
        (self.src / "img10.png").write_bytes((self.src / "a.png").read_bytes())
        (self.src / "img2.png").write_bytes((self.src / "a.png").read_bytes())
        names = [os.path.basename(p) for p in ops.collect_photos(str(self.src))]
        self.assertEqual(names.index("img2.png") < names.index("img10.png"), True)
        rev = [os.path.basename(p) for p in ops.collect_photos(str(self.src), descending=True)]
        self.assertEqual(rev, names[::-1])
        self.assertEqual(
            sorted(ops.collect_photos(str(self.src), ops.ORDER_RANDOM, seed=1)), sorted(ops.collect_photos(str(self.src)))
        )
        self.assertEqual(len(ops.collect_photos(str(self.src), ops.ORDER_DATE)), 6)

    def test_execute(self):
        s = ops.TriageSession(self.paths)
        s.set_rename(self.paths[0], "renamed")
        s.decide(ops.KEEP)            # a -> renamed.png in place
        s.set_rename(self.paths[1], "fav1")
        s.decide(ops.FAVOURITE)       # b -> fav/fav1.png
        s.decide(ops.TRASH)           # c
        s.defer() if False else None  # d stays undecided
        plan = ops.build_plan(s, str(self.fav))
        trashed = []
        res = ops.execute_plan(plan, trashed.append)
        self.assertEqual(res.errors, [])
        self.assertTrue((self.src / "renamed.png").exists())
        self.assertFalse((self.src / "a.png").exists())
        self.assertTrue((self.fav / "fav1.png").exists())
        self.assertEqual(trashed, [self.paths[2]])
        self.assertTrue((self.src / "d.png").exists())

    def test_favourite_name_conflict_gets_suffix(self):
        self.fav.mkdir()
        (self.fav / "a.png").write_bytes(b"x")
        s = ops.TriageSession(self.paths)
        s.decide(ops.FAVOURITE)
        plan = ops.build_plan(s, str(self.fav))
        self.assertEqual(os.path.basename(plan[0].dst), "a (1).png")

    def test_trash_without_backend_reports_error(self):
        s = ops.TriageSession(self.paths)
        s.decide(ops.TRASH)
        res = ops.execute_plan(ops.build_plan(s, str(self.fav)), None)
        self.assertEqual(res.done, 0)
        self.assertEqual(len(res.errors), 1)
        self.assertTrue((self.src / "a.png").exists())


if __name__ == "__main__":
    unittest.main()
