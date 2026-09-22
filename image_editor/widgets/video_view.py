"""Video playback widget with basic transport controls.

QtMultimedia (and its native backend, e.g. ffmpeg/gstreamer plugins) isn't
guaranteed to be present on every system, so the import is best-effort: when
it's missing, ``MULTIMEDIA_AVAILABLE`` is False and the app should hide
video support instead of crashing.
"""
from __future__ import annotations

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget

    MULTIMEDIA_AVAILABLE = True
except Exception:  # pragma: no cover - depends on system codecs/plugins
    MULTIMEDIA_AVAILABLE = False


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


if MULTIMEDIA_AVAILABLE:

    class VideoView(QWidget):
        playbackError = pyqtSignal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_output)
            self.video_widget = QVideoWidget(self)
            self.player.setVideoOutput(self.video_widget)

            self.play_button = QPushButton("▶")
            self.play_button.setFixedWidth(36)
            self.position_slider = QSlider(Qt.Orientation.Horizontal)
            self.position_slider.setRange(0, 0)
            self.time_label = QLabel("0:00 / 0:00")
            self.volume_slider = QSlider(Qt.Orientation.Horizontal)
            self.volume_slider.setFixedWidth(90)
            self.volume_slider.setRange(0, 100)
            self.volume_slider.setValue(80)
            self.audio_output.setVolume(0.8)

            controls = QHBoxLayout()
            controls.addWidget(self.play_button)
            controls.addWidget(self.position_slider, stretch=1)
            controls.addWidget(self.time_label)
            controls.addWidget(QLabel("🔊"))
            controls.addWidget(self.volume_slider)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(self.video_widget, stretch=1)
            layout.addLayout(controls)

            self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            self.play_button.clicked.connect(self.toggle_play)
            self.position_slider.sliderMoved.connect(self._seek)
            self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))
            self.player.positionChanged.connect(self._on_position_changed)
            self.player.durationChanged.connect(self._on_duration_changed)
            self.player.playbackStateChanged.connect(self._on_state_changed)
            self.player.errorOccurred.connect(
                lambda _err, msg: self.playbackError.emit(msg or "Playback error")
            )

        def load(self, path: str, autoplay: bool = True) -> None:
            self.player.setSource(QUrl.fromLocalFile(path))
            if autoplay:
                self.player.play()

        def stop_and_release(self) -> None:
            self.player.stop()
            # setSource() takes a QUrl, not None - a null QUrl is Qt's own
            # way to discard the current source and release its I/O.
            self.player.setSource(QUrl())

        def toggle_play(self) -> None:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()

        def _seek(self, position: int) -> None:
            self.player.setPosition(position)

        def _on_position_changed(self, position: int) -> None:
            if not self.position_slider.isSliderDown():
                self.position_slider.setValue(position)
            self.time_label.setText(f"{_format_ms(position)} / {_format_ms(self.player.duration())}")

        def _on_duration_changed(self, duration: int) -> None:
            self.position_slider.setRange(0, duration)

        def _on_state_changed(self, state) -> None:
            playing = state == QMediaPlayer.PlaybackState.PlayingState
            self.play_button.setText("⏸" if playing else "▶")

else:  # pragma: no cover - fallback stub shown when multimedia is unavailable

    class VideoView(QWidget):  # type: ignore[no-redef]
        playbackError = pyqtSignal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            label = QLabel(
                "Video playback isn't available on this system\n"
                "(PyQt6 multimedia backend/codecs not found)."
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label)

        def load(self, path: str, autoplay: bool = True) -> None:
            pass

        def stop_and_release(self) -> None:
            pass

        def toggle_play(self) -> None:
            pass
