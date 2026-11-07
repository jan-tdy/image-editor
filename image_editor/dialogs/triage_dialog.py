"""Photo Triage: quickly sort a folder into keep / favourite / trash, then
apply every decision as one reviewed batch."""
from __future__ import annotations

import html
import os
from datetime import datetime

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..constants import APP_NAME, APP_ORG
from ..core import triage_ops as ops
from ..core.convert import pil_to_qpixmap
from ..core.image_ops import load_with_orientation

try:
    from send2trash import send2trash
except Exception:  # pragma: no cover - optional dependency
    send2trash = None

ORDER_LABELS = {
    "Name (natural)": ops.ORDER_NAME,
    "Date taken (EXIF / modified)": ops.ORDER_DATE,
    "Random": ops.ORDER_RANDOM,
}
ACTION_TEXT = {ops.KEEP: "Keep", ops.FAVOURITE: "Favourite", ops.TRASH: "Trash"}
ACTION_COLOR = {ops.KEEP: "#3a7d44", ops.FAVOURITE: "#c28a00", ops.TRASH: "#b3392f"}


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


class TriageSetupDialog(QDialog):
    """Pick the source folder, favourites folder and the order of display."""

    def __init__(self, parent=None, settings: QSettings | None = None):
        super().__init__(parent)
        self.setWindowTitle("Photo Triage")
        self.setMinimumWidth(520)
        self.settings = settings or QSettings(APP_ORG, APP_NAME)

        self.source_edit = QLineEdit(self.settings.value("triage/source", "", type=str))
        self.fav_edit = QLineEdit(self.settings.value("triage/favourite", "", type=str))
        self.order_combo = QComboBox()
        self.order_combo.addItems(list(ORDER_LABELS))
        saved = self.settings.value("triage/order", "", type=str)
        for i, value in enumerate(ORDER_LABELS.values()):
            if value == saved:
                self.order_combo.setCurrentIndex(i)
        self.desc_check = QCheckBox("Descending (newest / last first)")
        self.desc_check.setChecked(self.settings.value("triage/descending", False, type=bool))
        self.order_combo.currentIndexChanged.connect(self._sync_order)

        form = QFormLayout()
        form.addRow("Photos folder:", self._row(self.source_edit))
        form.addRow("Favourites folder:", self._row(self.fav_edit))
        form.addRow("Show in order:", self.order_combo)
        form.addRow("", self.desc_check)

        self.hint = QLabel(
            "Keep leaves a photo where it is, Favourite moves it to the favourites folder, "
            "Trash sends it to the system trash. Nothing changes until you confirm the final summary."
        )
        self.hint.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.start_button = buttons.addButton("Start", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addWidget(buttons)
        self._sync_order()

    def _row(self, edit: QLineEdit) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse...")
        button.clicked.connect(lambda: self._browse(edit))
        h.addWidget(edit, 1)
        h.addWidget(button)
        return row

    def _browse(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text() or os.path.expanduser("~"))
        if folder:
            edit.setText(folder)

    def _sync_order(self) -> None:
        self.desc_check.setEnabled(self.order() != ops.ORDER_RANDOM)

    def order(self) -> str:
        return ORDER_LABELS[self.order_combo.currentText()]

    def source_dir(self) -> str:
        return self.source_edit.text().strip()

    def favourite_dir(self) -> str:
        return self.fav_edit.text().strip()

    def _accept(self) -> None:
        source, fav = self.source_dir(), self.favourite_dir()
        if not os.path.isdir(source):
            QMessageBox.warning(self, "Photo Triage", "Choose an existing photos folder.")
            return
        if not fav:
            QMessageBox.warning(self, "Photo Triage", "Choose a favourites folder.")
            return
        if os.path.abspath(fav) == os.path.abspath(source):
            QMessageBox.warning(self, "Photo Triage", "The favourites folder must differ from the photos folder.")
            return
        self.settings.setValue("triage/source", source)
        self.settings.setValue("triage/favourite", fav)
        self.settings.setValue("triage/order", self.order())
        self.settings.setValue("triage/descending", self.desc_check.isChecked())
        self.accept()


class _PhotoLabel(QLabel):
    """Shows a pixmap scaled (smoothly) to whatever room is available."""

    def __init__(self):
        super().__init__()
        self._pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def set_photo(self, pixmap: QPixmap | None, message: str = "") -> None:
        self._pixmap = pixmap
        if pixmap is None:
            super().setPixmap(QPixmap())
            self.setText(message)
        else:
            self.setText("")
            self._rescale()

    def _rescale(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        scaled = self._pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        super().setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()


class TriageSummaryDialog(QDialog):
    """Final overview shown before anything is changed on disk."""

    def __init__(self, parent, session: ops.TriageSession, plan: list[ops.PlannedAction], fav_dir: str):
        super().__init__(parent)
        self.setWindowTitle("Photo Triage - summary")
        self.resize(820, 520)
        counts = session.counts()
        undecided = len(session.all_paths) - sum(counts.values())
        text = (
            f"<b>{counts[ops.KEEP]}</b> keep &nbsp; <b>{counts[ops.FAVOURITE]}</b> favourite "
            f"&nbsp; <b>{counts[ops.TRASH]}</b> trash"
        )
        if undecided:
            text += f" &nbsp; <b>{undecided}</b> undecided (left untouched)"
        header = QLabel(text)

        changes = [p for p in plan if p.action != ops.KEEP or p.dst]
        self.table = QTableWidget(len(changes), 4)
        self.table.setHorizontalHeaderLabels(["Photo", "Action", "New name", "Destination"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, item in enumerate(changes):
            dest = {ops.TRASH: "System trash", ops.FAVOURITE: item.dst}.get(item.action, item.dst or "")
            values = [os.path.basename(item.src), ACTION_TEXT[item.action], os.path.basename(item.dst or "") if item.new_name else "", dest or ""]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.resizeColumnsToContents()

        note = QLabel(f"Favourites go to: {fav_dir}")
        if send2trash is None:
            note.setText(note.text() + "\nsend2trash is not installed - trashed photos cannot be deleted.")

        buttons = QDialogButtonBox()
        self.execute_button = buttons.addButton("Apply all", QDialogButtonBox.ButtonRole.AcceptRole)
        self.execute_button.setEnabled(bool(changes))
        buttons.addButton("Back to review", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addWidget(self.table, 1)
        layout.addWidget(note)
        layout.addWidget(buttons)


class TriageReviewDialog(QDialog):
    """Photo in the centre, info at the side, rename on top, actions below."""

    def __init__(self, parent, session: ops.TriageSession, favourite_dir: str):
        super().__init__(parent)
        self.setWindowTitle("Photo Triage")
        self.resize(1100, 760)
        self.session = session
        self.favourite_dir = favourite_dir
        self.executed: ops.ExecuteResult | None = None
        self._cache: dict[str, QPixmap] = {}

        # top: rename
        self.name_edit = QLineEdit()
        self.name_edit.returnPressed.connect(self.apply_rename)
        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self.apply_rename)
        top = QHBoxLayout()
        top.addWidget(QLabel("Name:"))
        top.addWidget(self.name_edit, 1)
        top.addWidget(self.rename_button)

        # centre: photo + info
        self.photo = _PhotoLabel()
        self.photo.setStyleSheet("background: #1e1e1e; color: #ddd;")
        self.info = QLabel()
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.info.setMinimumWidth(230)
        self.info.setMaximumWidth(280)
        centre = QHBoxLayout()
        centre.addWidget(self.photo, 1)
        centre.addWidget(self.info)

        # bottom: back | keep favourite trash | next
        self.back_button = QPushButton("◀  Back")
        self.next_button = QPushButton("Next  ▶")
        self.next_button.setToolTip("Decide later - moves this photo to the end of the queue")
        self.keep_button = self._action_button(ops.KEEP, "Keep  (K)")
        self.fav_button = self._action_button(ops.FAVOURITE, "★ Favourite  (F)")
        self.trash_button = self._action_button(ops.TRASH, "Trash  (T)")
        self.finish_button = QPushButton("Finish...")
        self.finish_button.setToolTip("Review the summary and apply everything")
        self.back_button.clicked.connect(self.go_back)
        self.next_button.clicked.connect(self.go_next)
        self.keep_button.clicked.connect(lambda: self.decide(ops.KEEP))
        self.fav_button.clicked.connect(lambda: self.decide(ops.FAVOURITE))
        self.trash_button.clicked.connect(lambda: self.decide(ops.TRASH))
        self.finish_button.clicked.connect(self.finish)
        for b in (self.back_button, self.next_button):
            b.setMinimumHeight(48)
        bottom = QHBoxLayout()
        bottom.addWidget(self.back_button)
        bottom.addStretch(1)
        bottom.addWidget(self.keep_button)
        bottom.addWidget(self.fav_button)
        bottom.addWidget(self.trash_button)
        bottom.addStretch(1)
        bottom.addWidget(self.next_button)
        extra = QHBoxLayout()
        extra.addStretch(1)
        extra.addWidget(self.finish_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(centre, 1)
        layout.addLayout(bottom)
        layout.addLayout(extra)
        self.refresh()

    def _action_button(self, action: str, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumSize(150, 56)
        button.setStyleSheet(
            f"QPushButton {{ font-weight: bold; font-size: 15px; color: white; "
            f"background: {ACTION_COLOR[action]}; border-radius: 6px; }}"
            f"QPushButton:disabled {{ background: #666; }}"
        )
        return button

    # -- actions -------------------------------------------------------
    def apply_rename(self) -> None:
        path = self.session.current
        if path is None:
            return
        if not self.session.set_rename(path, self.name_edit.text()):
            QMessageBox.warning(self, "Rename", "Enter a valid file name (no folders, not empty).")
            return
        self.refresh()

    def decide(self, action: str) -> None:
        self.apply_pending_rename_text()
        self.session.decide(action)
        self._after_move()

    def go_next(self) -> None:
        self.apply_pending_rename_text()
        self.session.defer()
        self._after_move()

    def go_back(self) -> None:
        self.apply_pending_rename_text()
        self.session.back()
        self.refresh()

    def apply_pending_rename_text(self) -> None:
        """Typed-but-not-confirmed name edits are not lost when moving on."""
        path = self.session.current
        if path is not None and self.name_edit.isModified():
            self.session.set_rename(path, self.name_edit.text())

    def _after_move(self) -> None:
        if self.session.finished:
            self.refresh()
            self.finish()
        else:
            self.refresh()

    def finish(self) -> bool:
        plan = ops.build_plan(self.session, self.favourite_dir)
        dialog = TriageSummaryDialog(self, self.session, plan, self.favourite_dir)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            if self.session.finished:
                self.session.resume()
                self.refresh()
            return False
        self.executed = ops.execute_plan(plan, send2trash)
        text = f"{self.executed.done} change(s) applied."
        if self.executed.errors:
            text += "\n\nProblems:\n" + "\n".join(self.executed.errors[:20])
            QMessageBox.warning(self, "Photo Triage", text)
        else:
            QMessageBox.information(self, "Photo Triage", text)
        self.accept()
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if isinstance(self.focusWidget(), QLineEdit):
            return super().keyPressEvent(event)
        key = event.key()
        if key == Qt.Key.Key_K:
            self.decide(ops.KEEP)
        elif key == Qt.Key.Key_F:
            self.decide(ops.FAVOURITE)
        elif key in (Qt.Key.Key_T, Qt.Key.Key_Delete):
            self.decide(ops.TRASH)
        elif key == Qt.Key.Key_Right:
            self.go_next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Backspace):
            self.go_back()
        else:
            super().keyPressEvent(event)

    def reject(self) -> None:
        decided = len(self.session.decisions)
        if decided and self.executed is None:
            answer = QMessageBox.question(
                self, "Photo Triage", f"Discard {decided} unapplied decision(s) and close?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().reject()

    # -- display -------------------------------------------------------
    def _pixmap_for(self, path: str) -> QPixmap | None:
        if path in self._cache:
            return self._cache[path]
        try:
            pix = pil_to_qpixmap(load_with_orientation(path))
        except Exception:
            return None
        if len(self._cache) > 6:
            self._cache.pop(next(iter(self._cache)))
        self._cache[path] = pix
        return pix

    def refresh(self) -> None:
        s = self.session
        path = s.current
        has = path is not None
        for b in (self.keep_button, self.fav_button, self.trash_button, self.next_button, self.rename_button):
            b.setEnabled(has)
        self.name_edit.setEnabled(has)
        self.back_button.setEnabled(s.can_go_back())
        if not has:
            self.photo.set_photo(None, "All photos reviewed.")
            self.info.setText("")
            self.name_edit.setText("")
            return
        self.name_edit.setText(s.display_name(path))
        self.name_edit.setModified(False)
        pix = self._pixmap_for(path)
        self.photo.set_photo(pix, "" if pix else "Could not load this image.")
        self.info.setText(self._info_html(path))
        # Keep keyboard shortcuts (K/F/T/arrows) working after each photo.
        self.photo.setFocus()

    def _info_html(self, path: str) -> str:
        s = self.session
        rows: list[tuple[str, str]] = [("File", os.path.basename(path))]
        if path in s.renames:
            rows.append(("Renamed to", s.renames[path]))
        pix = self._cache.get(path)
        if pix is not None:
            rows.append(("Size", f"{pix.width()} × {pix.height()} px"))
        try:
            st = os.stat(path)
            rows.append(("File size", _human_size(st.st_size)))
            rows.append(("Modified", datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")))
        except OSError:
            pass
        try:
            from PIL import Image

            with Image.open(path) as img:
                exif = img.getexif()
            model = exif.get(0x0110)
            if model:
                rows.append(("Camera", str(model).strip()))
        except Exception:
            pass
        rows.append(("Folder", os.path.dirname(path)))
        decision = s.decisions.get(path)
        status = (
            f"<span style='color:{ACTION_COLOR[decision]}'><b>{ACTION_TEXT[decision]}</b></span>"
            if decision
            else "undecided"
        )
        rows.append(("Decision", status))
        counts = s.counts()
        done = len(s.decisions)
        rows.append(("Progress", f"{done} / {len(s.all_paths)} decided, {s.remaining()} left"))
        rows.append(
            ("Totals", f"keep {counts[ops.KEEP]}, fav {counts[ops.FAVOURITE]}, trash {counts[ops.TRASH]}")
        )
        safe = {"Decision", "Progress", "Totals"}
        body = "".join(
            f"<p style='margin:0 0 8px 0'><small>{k}</small><br>{v if k in safe else html.escape(v)}</p>"
            for k, v in rows
        )
        return body


def run_photo_triage(parent=None, settings: QSettings | None = None) -> bool:
    """Run the whole flow; returns True if any file operations were applied."""
    setup = TriageSetupDialog(parent, settings)
    if setup.exec() != QDialog.DialogCode.Accepted:
        return False
    paths = ops.collect_photos(setup.source_dir(), setup.order(), setup.desc_check.isChecked())
    if not paths:
        QMessageBox.information(parent, "Photo Triage", "No images found in that folder.")
        return False
    review = TriageReviewDialog(parent, ops.TriageSession(paths), setup.favourite_dir())
    review.exec()
    return review.executed is not None and review.executed.done > 0
