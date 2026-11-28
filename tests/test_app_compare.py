import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication

from image_editor.app import MainWindow
from image_editor.models.file_model import MediaEntry
from image_editor.widgets.compare_panel import NEXT, PREV

_app = QApplication.instance() or QApplication([])


class NeighborEntryTests(unittest.TestCase):
    def _navigator(self, index):
        entries = [MediaEntry(f"/tmp/{n}.jpg", is_video=False) for n in ("a", "b", "c")]
        return SimpleNamespace(entries=entries, index=index)

    def test_previous_direction(self):
        window = SimpleNamespace(navigator=self._navigator(1), compare_direction=PREV)
        entry = MainWindow._neighbor_entry(window)
        self.assertEqual(entry.path, "/tmp/a.jpg")

    def test_next_direction(self):
        window = SimpleNamespace(navigator=self._navigator(1), compare_direction=NEXT)
        entry = MainWindow._neighbor_entry(window)
        self.assertEqual(entry.path, "/tmp/c.jpg")

    def test_no_previous_at_start(self):
        window = SimpleNamespace(navigator=self._navigator(0), compare_direction=PREV)
        self.assertIsNone(MainWindow._neighbor_entry(window))

    def test_no_next_at_end(self):
        window = SimpleNamespace(navigator=self._navigator(2), compare_direction=NEXT)
        self.assertIsNone(MainWindow._neighbor_entry(window))

    def test_no_entries_at_all(self):
        window = SimpleNamespace(navigator=SimpleNamespace(entries=[], index=-1), compare_direction=PREV)
        self.assertIsNone(MainWindow._neighbor_entry(window))


class BlinkTimerStateTests(unittest.TestCase):
    def _window(self, compare_mode, document, interval_ms=500):
        timer = Mock()
        timer.isActive.return_value = False
        compare_panel = Mock()
        compare_panel.interval_ms.return_value = interval_ms
        return SimpleNamespace(
            compare_mode=compare_mode, document=document, blink_timer=timer, compare_panel=compare_panel
        )

    def test_starts_timer_in_blink_mode_with_a_document(self):
        window = self._window("blink", object())
        MainWindow._update_blink_timer_state(window)
        window.blink_timer.start.assert_called_once_with(500)
        window.blink_timer.stop.assert_not_called()

    def test_does_not_start_timer_when_off(self):
        window = self._window("off", object())
        MainWindow._update_blink_timer_state(window)
        window.blink_timer.start.assert_not_called()

    def test_does_not_start_timer_without_a_document(self):
        window = self._window("blink", None)
        MainWindow._update_blink_timer_state(window)
        window.blink_timer.start.assert_not_called()

    def test_stops_running_timer_when_mode_leaves_blink(self):
        window = self._window("onion", object())
        window.blink_timer.isActive.return_value = True
        MainWindow._update_blink_timer_state(window)
        window.blink_timer.stop.assert_called_once_with()


class OnionBlinkToggleTests(unittest.TestCase):
    def _window(self, compare_mode="off"):
        return SimpleNamespace(
            compare_mode=compare_mode,
            act_onion_skin=Mock(),
            act_blink_mode=Mock(),
            image_view=Mock(),
            compare_panel=Mock(opacity=Mock(return_value=0.5), interval_ms=Mock(return_value=500)),
            blink_timer=Mock(isActive=Mock(return_value=False)),
            _blink_showing_reference=False,
            _refresh_compare_reference=Mock(),
            _update_blink_timer_state=Mock(),
        )

    def test_enabling_onion_sets_mode_and_refreshes(self):
        window = self._window()
        MainWindow._on_onion_toggled(window, True)
        self.assertEqual(window.compare_mode, "onion")
        window.act_onion_skin.setChecked.assert_called_once_with(True)
        window._refresh_compare_reference.assert_called_once_with()
        window._update_blink_timer_state.assert_called_once_with()

    def test_disabling_onion_turns_mode_off_and_hides_overlay(self):
        window = self._window(compare_mode="onion")
        MainWindow._on_onion_toggled(window, False)
        self.assertEqual(window.compare_mode, "off")
        window.image_view.set_compare_visible.assert_called_once_with(False)

    def test_disabling_onion_while_blink_is_active_leaves_blink_alone(self):
        # Mutual exclusion is handled by ComparePanel itself before this
        # fires, so compare_mode here is already "blink" by the time the
        # (now False) onion signal arrives.
        window = self._window(compare_mode="blink")
        MainWindow._on_onion_toggled(window, False)
        self.assertEqual(window.compare_mode, "blink")
        window.image_view.set_compare_visible.assert_not_called()

    def test_enabling_blink_resets_the_flip_state(self):
        window = self._window()
        window._blink_showing_reference = True
        MainWindow._on_blink_toggled(window, True)
        self.assertEqual(window.compare_mode, "blink")
        self.assertFalse(window._blink_showing_reference)
        window._refresh_compare_reference.assert_called_once_with()

    def test_disabling_blink_turns_mode_off(self):
        window = self._window(compare_mode="blink")
        MainWindow._on_blink_toggled(window, False)
        self.assertEqual(window.compare_mode, "off")
        window.image_view.set_compare_visible.assert_called_once_with(False)


class BlinkTickTests(unittest.TestCase):
    def test_flips_the_overlay_each_tick(self):
        window = SimpleNamespace(_blink_showing_reference=False, image_view=Mock())
        MainWindow._blink_tick(window)
        self.assertTrue(window._blink_showing_reference)
        window.image_view.set_compare_visible.assert_called_once_with(True)
        MainWindow._blink_tick(window)
        self.assertFalse(window._blink_showing_reference)
        window.image_view.set_compare_visible.assert_called_with(False)


class RefreshCompareReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = []
        for n in ("a.png", "b.png"):
            p = Path(self.tmp.name, n)
            Image.new("RGB", (20, 10), (10, 20, 30)).save(p)
            self.paths.append(str(p))

    def _window(self, index, compare_mode="off"):
        entries = [MediaEntry(p, is_video=False) for p in self.paths]
        window = SimpleNamespace(
            is_video=False,
            document=object(),
            navigator=SimpleNamespace(entries=entries, index=index),
            compare_direction=PREV,
            compare_mode=compare_mode,
            compare_panel=Mock(opacity=Mock(return_value=0.5)),
            image_view=Mock(),
            _blink_showing_reference=False,
        )
        window._neighbor_entry = lambda: MainWindow._neighbor_entry(window)
        return window

    def test_loads_the_previous_file_as_the_reference(self):
        window = self._window(index=1)
        MainWindow._refresh_compare_reference(window)
        window.image_view.set_compare_pixmap.assert_called_once()
        pixmap = window.image_view.set_compare_pixmap.call_args[0][0]
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())

    def test_no_reference_when_there_is_no_neighbour(self):
        window = self._window(index=0)
        MainWindow._refresh_compare_reference(window)
        window.image_view.set_compare_pixmap.assert_called_once_with(None)

    def test_onion_mode_shows_the_overlay_at_the_panel_opacity(self):
        window = self._window(index=1, compare_mode="onion")
        MainWindow._refresh_compare_reference(window)
        window.image_view.set_compare_opacity.assert_called_once_with(0.5)
        window.image_view.set_compare_visible.assert_called_once_with(True)

    def test_blink_mode_shows_full_opacity_and_respects_flip_state(self):
        window = self._window(index=1, compare_mode="blink")
        window._blink_showing_reference = True
        MainWindow._refresh_compare_reference(window)
        window.image_view.set_compare_opacity.assert_called_once_with(1.0)
        window.image_view.set_compare_visible.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
