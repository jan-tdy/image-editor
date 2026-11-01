"""Transport bar (play/pause, frame scrubber) shown below the image view
while an animated GIF is open."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget


class GifTransportBar(QWidget):
    playToggled = pyqtSignal(bool)  # True = play requested, False = pause
    frameChanged = pyqtSignal(int)  # user scrubbed to this frame index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.play_button = QPushButton("⏸")
        self.play_button.setFixedWidth(36)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_label = QLabel("Frame 1/1")
        self.frame_label.setMinimumWidth(90)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(self.play_button)
        layout.addWidget(self.frame_slider, stretch=1)
        layout.addWidget(self.frame_label)

        self.play_button.clicked.connect(self._toggle_clicked)
        self.frame_slider.valueChanged.connect(self._slider_moved)

        self._playing = True
        self._updating = False

    def configure(self, frame_count: int) -> None:
        self._updating = True
        self.frame_slider.setRange(0, max(0, frame_count - 1))
        self._updating = False

    def set_frame(self, index: int, frame_count: int) -> None:
        self._updating = True
        self.frame_slider.setValue(index)
        self._updating = False
        self.frame_label.setText(f"Frame {index + 1}/{frame_count}")

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.play_button.setText("⏸" if playing else "▶")

    def _toggle_clicked(self) -> None:
        self.set_playing(not self._playing)
        self.playToggled.emit(self._playing)

    def _slider_moved(self, value: int) -> None:
        if self._updating:
            return
        self.frameChanged.emit(value)
