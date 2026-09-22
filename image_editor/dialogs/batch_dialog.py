"""Batch rename / convert / resize / adjust dialog."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from ..core.rename_ops import RenamePlan, RenameResult, find_conflicts, preview_names
from ..widgets.adjustments_panel import AdjustSlider
from ..workers.batch_worker import BatchFileJob, BatchSettings, BatchWorker, undo_batch

FORMAT_CHOICES = {
    "Keep original": None,
    "JPEG": ".jpg",
    "PNG": ".png",
    "BMP": ".bmp",
    "TIFF": ".tiff",
    "WEBP": ".webp",
}

CASE_CHOICES = {
    "Keep as-is": "keep",
    "lowercase": "lower",
    "UPPERCASE": "upper",
    "Title Case": "title",
    "Capitalize first": "capitalize",
}

ROTATE_CHOICES = {"No rotation": 0, "90° clockwise": 90, "180°": 180, "90° counter-clockwise": 270}


class BatchDialog(QDialog):
    def __init__(self, parent=None, initial_paths: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Batch Rename & Edit")
        self.resize(980, 640)
        self._worker: BatchWorker | None = None
        self._last_log = None

        self._build_ui()
        if initial_paths:
            self.add_paths(initial_paths)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        # -- left: file table + add/remove controls --------------------------
        left = QVBoxLayout()
        file_buttons = QHBoxLayout()
        btn_add_files = QPushButton("Add Files...")
        btn_add_folder = QPushButton("Add Folder...")
        btn_remove = QPushButton("Remove Selected")
        btn_select_all = QPushButton("Select All")
        btn_select_none = QPushButton("Select None")
        for b in (btn_add_files, btn_add_folder, btn_remove, btn_select_all, btn_select_none):
            file_buttons.addWidget(b)
        left.addLayout(file_buttons)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["", "Original Name", "New Name / Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        left.addWidget(self.table, stretch=1)

        self.progress_bar = QProgressBar()
        self.status_label = QLabel("")
        left.addWidget(self.progress_bar)
        left.addWidget(self.status_label)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(120)
        left.addWidget(self.log_view)

        run_row = QHBoxLayout()
        self.btn_run = QPushButton("Run Batch")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_undo = QPushButton("Undo Last Run")
        self.btn_close = QPushButton("Close")
        self.btn_cancel.setEnabled(False)
        self.btn_undo.setEnabled(False)
        for b in (self.btn_run, self.btn_cancel, self.btn_undo, self.btn_close):
            run_row.addWidget(b)
        left.addLayout(run_row)

        root.addLayout(left, stretch=2)

        # -- right: options ---------------------------------------------------
        right = QVBoxLayout()
        right.addWidget(self._build_rename_group())
        right.addWidget(self._build_convert_group())
        right.addWidget(self._build_adjust_group())
        right.addWidget(self._build_output_group())
        right.addStretch(1)
        right_container = QWidget()
        right_container.setLayout(right)
        right_container.setMinimumWidth(340)
        root.addWidget(right_container, stretch=1)

        btn_add_files.clicked.connect(self._add_files_dialog)
        btn_add_folder.clicked.connect(self._add_folder_dialog)
        btn_remove.clicked.connect(self._remove_selected)
        btn_select_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_select_none.clicked.connect(lambda: self._set_all_checked(False))
        self.btn_run.clicked.connect(self._run_batch)
        self.btn_cancel.clicked.connect(self._cancel_batch)
        self.btn_undo.clicked.connect(self._undo_last_run)
        self.btn_close.clicked.connect(self.close)

    def _build_rename_group(self) -> QGroupBox:
        box = QGroupBox("Rename", checkable=True)
        box.setChecked(False)
        self.rename_group = box
        form = QFormLayout(box)

        self.pattern_edit = QLineEdit("{name}")
        form.addRow("Pattern:", self.pattern_edit)
        hint = QLabel("Tokens: {name} {ext} {n} {date} {parent} {orig}")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", hint)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 1_000_000)
        self.start_spin.setValue(1)
        self.step_spin = QSpinBox()
        self.step_spin.setRange(-1000, 1000)
        self.step_spin.setValue(1)
        self.digits_spin = QSpinBox()
        self.digits_spin.setRange(1, 8)
        self.digits_spin.setValue(3)
        num_row = QHBoxLayout()
        num_row.addWidget(QLabel("Start:"))
        num_row.addWidget(self.start_spin)
        num_row.addWidget(QLabel("Step:"))
        num_row.addWidget(self.step_spin)
        num_row.addWidget(QLabel("Digits:"))
        num_row.addWidget(self.digits_spin)
        form.addRow(num_row)

        self.case_combo = QComboBox()
        self.case_combo.addItems(CASE_CHOICES.keys())
        form.addRow("Case:", self.case_combo)

        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        find_row = QHBoxLayout()
        find_row.addWidget(self.find_edit)
        find_row.addWidget(QLabel("→"))
        find_row.addWidget(self.replace_edit)
        form.addRow("Find/Replace:", find_row)
        self.regex_check = QCheckBox("Use regular expressions")
        form.addRow("", self.regex_check)

        for widget in (self.pattern_edit, self.find_edit, self.replace_edit):
            widget.textChanged.connect(self._refresh_preview)
        for widget in (self.start_spin, self.step_spin, self.digits_spin):
            widget.valueChanged.connect(self._refresh_preview)
        self.case_combo.currentIndexChanged.connect(self._refresh_preview)
        self.regex_check.toggled.connect(self._refresh_preview)
        box.toggled.connect(self._refresh_preview)
        return box

    def _build_convert_group(self) -> QGroupBox:
        box = QGroupBox("Convert && Resize", checkable=True)
        box.setChecked(False)
        self.convert_group = box
        form = QFormLayout(box)

        self.format_combo = QComboBox()
        self.format_combo.addItems(FORMAT_CHOICES.keys())
        form.addRow("Format:", self.format_combo)

        self.resize_combo = QComboBox()
        self.resize_combo.addItems(["No resize", "Fit within (keep aspect)", "Exact size", "Scale %"])
        form.addRow("Resize:", self.resize_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 20000)
        self.width_spin.setValue(1920)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 20000)
        self.height_spin.setValue(1080)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("W:"))
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("H:"))
        size_row.addWidget(self.height_spin)
        form.addRow("Size:", size_row)

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(1, 500)
        self.scale_spin.setValue(50)
        self.scale_spin.setSuffix(" %")
        form.addRow("Scale:", self.scale_spin)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(90)
        form.addRow("JPEG quality:", self.quality_spin)

        self.format_combo.currentTextChanged.connect(self._refresh_preview)
        box.toggled.connect(self._refresh_preview)
        return box

    def _build_adjust_group(self) -> QGroupBox:
        box = QGroupBox("Adjust && Rotate", checkable=True)
        box.setChecked(False)
        self.adjust_group = box
        layout = QVBoxLayout(box)

        rotate_row = QHBoxLayout()
        self.rotate_combo = QComboBox()
        self.rotate_combo.addItems(ROTATE_CHOICES.keys())
        self.flip_h_check = QCheckBox("Flip Horizontal")
        self.flip_v_check = QCheckBox("Flip Vertical")
        rotate_row.addWidget(QLabel("Rotate:"))
        rotate_row.addWidget(self.rotate_combo)
        rotate_row.addWidget(self.flip_h_check)
        rotate_row.addWidget(self.flip_v_check)
        layout.addLayout(rotate_row)

        self.adjust_sliders: dict[str, AdjustSlider] = {}
        for key, label in (
            ("brightness", "Brightness"), ("contrast", "Contrast"), ("saturation", "Saturation"),
            ("red", "Red"), ("green", "Green"), ("blue", "Blue"),
        ):
            slider = AdjustSlider(label)
            self.adjust_sliders[key] = slider
            layout.addWidget(slider)
        return box

    def _build_output_group(self) -> QGroupBox:
        box = QGroupBox("Output")
        layout = QVBoxLayout(box)

        self.radio_overwrite = QRadioButton("Overwrite / rename original files")
        self.radio_folder = QRadioButton("Save to folder:")
        self.radio_overwrite.setChecked(True)
        group = QButtonGroup(box)
        group.addButton(self.radio_overwrite)
        group.addButton(self.radio_folder)
        layout.addWidget(self.radio_overwrite)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        btn_browse = QPushButton("Browse...")
        folder_row.addWidget(self.radio_folder)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(btn_browse)
        layout.addLayout(folder_row)

        self.backup_check = QCheckBox("Keep .bak backups when overwriting/replacing originals")
        self.backup_check.setChecked(True)
        layout.addWidget(self.backup_check)

        btn_browse.clicked.connect(self._browse_output_folder)
        self.radio_overwrite.toggled.connect(lambda checked: self.backup_check.setEnabled(True))
        return box

    # ------------------------------------------------------------------
    # File list management
    # ------------------------------------------------------------------
    def add_paths(self, paths: list[str]) -> None:
        existing = {self._row_path(r) for r in range(self.table.rowCount())}
        for path in paths:
            if path in existing:
                continue
            ext = Path(path).suffix.lower()
            if ext not in IMAGE_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)

            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, check_item)

            name_item = QTableWidgetItem(Path(path).name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, 1, name_item)

            self.table.setItem(row, 2, QTableWidgetItem(Path(path).name))
            existing.add(path)
        self._refresh_preview()

    def _row_path(self, row: int) -> str:
        item = self.table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _row_is_checked(self, row: int) -> bool:
        item = self.table.item(row, 0)
        return item is not None and item.checkState() == Qt.CheckState.Checked

    def _checked_paths(self) -> list[str]:
        return [self._row_path(r) for r in range(self.table.rowCount()) if self._row_is_checked(r)]

    def _add_files_dialog(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Files", "", f"Media Files ({exts})")
        if paths:
            self.add_paths(paths)

    def _add_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add Folder")
        if not folder:
            return
        from ..models.file_model import list_media

        self.add_paths([e.path for e in list_media(folder)])

    def _remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        self._refresh_preview()

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(state)

    def _browse_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.folder_edit.setText(folder)
            self.radio_folder.setChecked(True)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _refresh_preview(self) -> None:
        paths = [self._row_path(r) for r in range(self.table.rowCount())]
        if not paths:
            return

        if self.rename_group.isChecked():
            plan = RenamePlan(
                pattern=self.pattern_edit.text() or "{name}",
                start=self.start_spin.value(),
                step=self.step_spin.value(),
                digits=self.digits_spin.value(),
                case=CASE_CHOICES[self.case_combo.currentText()],
                find=self.find_edit.text(),
                replace=self.replace_edit.text(),
                use_regex=self.regex_check.isChecked(),
            )
            results = preview_names(paths, plan)
        else:
            results = [RenameResult(p, Path(p).name) for p in paths]

        target_ext = FORMAT_CHOICES[self.format_combo.currentText()] if self.convert_group.isChecked() else None
        if target_ext:
            adjusted = []
            for r in results:
                if r.error:
                    adjusted.append(r)
                    continue
                if Path(r.old_path).suffix.lower() in VIDEO_EXTENSIONS:
                    adjusted.append(r)  # videos are never re-encoded
                else:
                    adjusted.append(RenameResult(r.old_path, Path(r.new_name).stem + target_ext))
            results = adjusted

        conflicts = find_conflicts(results)
        conflict_sources = {src for sources in conflicts.values() for src in sources}

        for row, result in enumerate(results):
            item = self.table.item(row, 2)
            if item is None:
                continue
            if result.error:
                item.setText(f"⚠ {result.error}")
                item.setForeground(Qt.GlobalColor.red)
            elif result.old_path in conflict_sources:
                item.setText(f"⚠ conflict: {result.new_name}")
                item.setForeground(Qt.GlobalColor.red)
            else:
                item.setText(result.new_name)
                item.setForeground(Qt.GlobalColor.black)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _build_settings(self) -> BatchSettings:
        resize_mode_map = {"No resize": "none", "Fit within (keep aspect)": "fit", "Exact size": "exact", "Scale %": "scale_pct"}
        return BatchSettings(
            do_rename=self.rename_group.isChecked(),
            do_convert_resize=self.convert_group.isChecked(),
            target_format=FORMAT_CHOICES[self.format_combo.currentText()],
            resize_mode=resize_mode_map[self.resize_combo.currentText()],
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            scale_pct=self.scale_spin.value(),
            jpeg_quality=self.quality_spin.value(),
            do_adjust=self.adjust_group.isChecked(),
            brightness=self.adjust_sliders["brightness"].value(),
            contrast=self.adjust_sliders["contrast"].value(),
            saturation=self.adjust_sliders["saturation"].value(),
            red=self.adjust_sliders["red"].value(),
            green=self.adjust_sliders["green"].value(),
            blue=self.adjust_sliders["blue"].value(),
            do_rotate=self.adjust_group.isChecked() and ROTATE_CHOICES[self.rotate_combo.currentText()] != 0,
            rotate_degrees=ROTATE_CHOICES[self.rotate_combo.currentText()],
            flip_h=self.adjust_group.isChecked() and self.flip_h_check.isChecked(),
            flip_v=self.adjust_group.isChecked() and self.flip_v_check.isChecked(),
            output_mode="folder" if self.radio_folder.isChecked() else "overwrite",
            output_folder=self.folder_edit.text(),
            backup_before_overwrite=self.backup_check.isChecked(),
        )

    def _build_jobs(self, settings: BatchSettings) -> list[BatchFileJob] | None:
        paths = self._checked_paths()
        if not paths:
            QMessageBox.information(self, "Batch", "No files selected.")
            return None

        if settings.output_mode == "folder" and not settings.output_folder:
            QMessageBox.warning(self, "Batch", "Choose an output folder first.")
            return None

        new_names: dict[str, str] = {}
        if settings.do_rename:
            plan = RenamePlan(
                pattern=self.pattern_edit.text() or "{name}",
                start=self.start_spin.value(),
                step=self.step_spin.value(),
                digits=self.digits_spin.value(),
                case=CASE_CHOICES[self.case_combo.currentText()],
                find=self.find_edit.text(),
                replace=self.replace_edit.text(),
                use_regex=self.regex_check.isChecked(),
            )
            results = preview_names(paths, plan)
            errors = [r for r in results if r.error]
            if errors:
                QMessageBox.warning(self, "Batch", f"Rename pattern error: {errors[0].error}")
                return None
            conflicts = find_conflicts(results)
            if conflicts:
                names = "\n".join(list(conflicts.keys())[:8])
                QMessageBox.warning(self, "Batch", f"Naming conflicts detected, aborting:\n{names}")
                return None
            new_names = {r.old_path: r.new_name for r in results}

        jobs = []
        for path in paths:
            ext = Path(path).suffix.lower()
            jobs.append(BatchFileJob(src_path=path, is_video=(ext in VIDEO_EXTENSIONS), new_name=new_names.get(path)))
        return jobs

    def _run_batch(self) -> None:
        settings = self._build_settings()
        jobs = self._build_jobs(settings)
        if not jobs:
            return

        self.log_view.clear()
        self.progress_bar.setRange(0, len(jobs))
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_undo.setEnabled(False)

        self._worker = BatchWorker(jobs, settings, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finishedBatch.connect(self._on_finished)
        self._worker.start()

    def _cancel_batch(self) -> None:
        if self._worker is not None:
            self._worker.requestInterruption()
            self.status_label.setText("Cancelling...")

    def _on_progress(self, done: int, total: int, filename: str) -> None:
        self.progress_bar.setValue(done)
        self.status_label.setText(f"{done}/{total}: {filename}")

    def _on_finished(self, log) -> None:
        self._last_log = log
        errors = [e for e in log if e.mode == "error"]
        for entry in log:
            if entry.mode == "error":
                self.log_view.appendPlainText(f"ERROR {Path(entry.src_path).name}: {entry.error}")
            else:
                self.log_view.appendPlainText(f"OK    {Path(entry.src_path).name} -> {Path(entry.out_path).name} [{entry.mode}]")
        self.status_label.setText(f"Done: {len(log) - len(errors)} ok, {len(errors)} failed")
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_undo.setEnabled(any(e.mode != "noop" and e.mode != "error" for e in log))

    def _undo_last_run(self) -> None:
        if not self._last_log:
            return
        if QMessageBox.question(self, "Undo Batch", "Revert the changes made by the last batch run?") != QMessageBox.StandardButton.Yes:
            return
        warnings = undo_batch(self._last_log)
        self.btn_undo.setEnabled(False)
        self._last_log = None
        if warnings:
            QMessageBox.warning(self, "Undo Batch", "Undo finished with warnings:\n" + "\n".join(warnings))
        else:
            QMessageBox.information(self, "Undo Batch", "Batch changes reverted.")

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(2000)
        super().closeEvent(event)
