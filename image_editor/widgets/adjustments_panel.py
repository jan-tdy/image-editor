"""Dock panel with live sliders for brightness/contrast/saturation/RGB."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

SLIDER_RANGE = (-100, 100)


class AdjustSlider(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(*SLIDER_RANGE)
        self.slider.setValue(0)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(50)

        self.value_label = QLabel("0")
        self.value_label.setFixedWidth(32)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        row = QVBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        header = QLabel(label)
        row.addWidget(header)

        slider_row = QHBoxLayout()
        slider_row.addWidget(self.slider)
        slider_row.addWidget(self.value_label)
        row.addLayout(slider_row)

        self.slider.valueChanged.connect(self._on_change)

    def _on_change(self, value: int) -> None:
        self.value_label.setText(str(value))
        self.valueChanged.emit(float(value))

    def set_value(self, value: float) -> None:
        block = self.slider.blockSignals(True)
        self.slider.setValue(int(value))
        self.value_label.setText(str(int(value)))
        self.slider.blockSignals(block)

    def value(self) -> float:
        return float(self.slider.value())


class AdjustmentsPanel(QWidget):
    """Emits ``adjustmentChanged(name, value)`` live, and ``applyRequested`` /
    ``resetRequested`` / ``cancelRequested`` for the explicit commit actions.
    """

    adjustmentChanged = pyqtSignal(str, float)
    applyRequested = pyqtSignal()
    resetRequested = pyqtSignal()
    cancelRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.sliders: dict[str, AdjustSlider] = {}
        for key, label in (
            ("brightness", "Brightness"),
            ("contrast", "Contrast"),
            ("saturation", "Saturation"),
            ("red", "Red"),
            ("green", "Green"),
            ("blue", "Blue"),
        ):
            slider = AdjustSlider(label)
            slider.valueChanged.connect(lambda v, k=key: self.adjustmentChanged.emit(k, v))
            self.sliders[key] = slider
            layout.addWidget(slider)

        layout.addStretch(1)

        buttons = QDialogButtonBox()
        self.apply_button = QPushButton("Apply")
        self.reset_button = QPushButton("Reset")
        self.cancel_button = QPushButton("Cancel")
        buttons.addButton(self.apply_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.reset_button, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

        self.apply_button.clicked.connect(self.applyRequested)
        self.reset_button.clicked.connect(self._on_reset)
        self.cancel_button.clicked.connect(self.cancelRequested)

    def _on_reset(self) -> None:
        for slider in self.sliders.values():
            slider.set_value(0)
        self.resetRequested.emit()

    def set_values(self, **values: float) -> None:
        for key, value in values.items():
            if key in self.sliders:
                self.sliders[key].set_value(value)

    def values(self) -> dict[str, float]:
        return {key: slider.value() for key, slider in self.sliders.items()}
