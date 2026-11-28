"""Shared controls for onion-skin / blink comparison against a reference image.

Used by both the main viewer (reference = the previous/next file in the
folder) and the Photo Triage review window (reference = the previously
reviewed photo). Onion skin overlays the reference at a fixed opacity;
Blink mode instead flips between the current and reference image on a
timer - the classic astronomical "blink comparator" technique for spotting
what changed between two frames. The two are mutually exclusive.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

DEFAULT_OPACITY_PERCENT = 50
DEFAULT_BLINK_INTERVAL_MS = 500
BLINK_INTERVAL_RANGE = (100, 2000)

PREV = "prev"
NEXT = "next"


class ComparePanel(QWidget):
    onionToggled = pyqtSignal(bool)
    opacityChanged = pyqtSignal(float)  # 0..1
    blinkToggled = pyqtSignal(bool)
    intervalChanged = pyqtSignal(int)  # ms
    directionChanged = pyqtSignal(str)  # PREV | NEXT

    def __init__(self, parent=None, show_direction: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.direction_combo: QComboBox | None = None
        if show_direction:
            self.direction_combo = QComboBox()
            self.direction_combo.addItem("◀ Previous image", PREV)
            self.direction_combo.addItem("Next image ▶", NEXT)
            self.direction_combo.currentIndexChanged.connect(
                lambda _i: self.directionChanged.emit(self.direction_combo.currentData())
            )
            row = QHBoxLayout()
            row.addWidget(QLabel("Compare to:"))
            row.addWidget(self.direction_combo, 1)
            layout.addLayout(row)

        self.onion_check = QCheckBox("Onion skin")
        self.onion_check.setToolTip("Overlay the reference image at partial opacity to spot differences.")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(1, 99)
        self.opacity_slider.setValue(DEFAULT_OPACITY_PERCENT)
        self.opacity_label = QLabel(f"{DEFAULT_OPACITY_PERCENT}%")
        self.opacity_label.setFixedWidth(36)

        onion_row = QHBoxLayout()
        onion_row.addWidget(QLabel("Opacity:"))
        onion_row.addWidget(self.opacity_slider)
        onion_row.addWidget(self.opacity_label)
        layout.addWidget(self.onion_check)
        layout.addLayout(onion_row)

        self.blink_check = QCheckBox("Blink mode")
        self.blink_check.setToolTip(
            "Flip between the current and reference image on a timer - a classic way to "
            "spot what changed between two frames."
        )
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(*BLINK_INTERVAL_RANGE)
        self.interval_spin.setSingleStep(50)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setValue(DEFAULT_BLINK_INTERVAL_MS)

        blink_row = QHBoxLayout()
        blink_row.addWidget(QLabel("Interval:"))
        blink_row.addWidget(self.interval_spin)
        layout.addWidget(self.blink_check)
        layout.addLayout(blink_row)
        layout.addStretch(1)

        self.onion_check.toggled.connect(self._on_onion_toggled)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.blink_check.toggled.connect(self._on_blink_toggled)
        self.interval_spin.valueChanged.connect(self.intervalChanged)

        self._sync_enabled()

    # -- internal handlers --------------------------------------------------
    def _on_onion_toggled(self, checked: bool) -> None:
        if checked and self.blink_check.isChecked():
            self.blink_check.setChecked(False)
        self._sync_enabled()
        self.onionToggled.emit(checked)

    def _on_blink_toggled(self, checked: bool) -> None:
        if checked and self.onion_check.isChecked():
            self.onion_check.setChecked(False)
        self._sync_enabled()
        self.blinkToggled.emit(checked)

    def _on_opacity_changed(self, value: int) -> None:
        self.opacity_label.setText(f"{value}%")
        self.opacityChanged.emit(value / 100)

    def _sync_enabled(self) -> None:
        self.opacity_slider.setEnabled(self.onion_check.isChecked())
        self.interval_spin.setEnabled(self.blink_check.isChecked())

    # -- external access ------------------------------------------------
    def set_onion_checked(self, checked: bool) -> None:
        self.onion_check.setChecked(checked)

    def set_blink_checked(self, checked: bool) -> None:
        self.blink_check.setChecked(checked)

    def opacity(self) -> float:
        return self.opacity_slider.value() / 100

    def interval_ms(self) -> int:
        return self.interval_spin.value()

    def direction(self) -> str:
        return self.direction_combo.currentData() if self.direction_combo else PREV
