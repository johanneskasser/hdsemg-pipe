# hdsemg_pipe/widgets/standalone/output_options_dialog.py
"""Dialog for selecting output options when filtering MUs in standalone mode."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, Optional, Set

from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt

from hdsemg_pipe.ui_elements.theme import BorderRadius, Colors, Spacing, Styles


@dataclass
class FilterOutputConfig:
    """Describes where filtered output should be written."""

    mode: str  # "in_place" | "archive" | "custom"
    source_dir: Path
    output_dir: Path
    backup_dir: Optional[Path]
    # Which sibling types to include alongside JSON ("pkl", "mat")
    process_siblings: FrozenSet[str] = field(default_factory=frozenset)


class OutputOptionsDialog(QDialog):
    """Presents three output strategies for the standalone MU quality filter."""

    def __init__(
        self,
        source_dir: Path,
        detected_siblings: Set[str],
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._source_dir = source_dir
        self._detected_siblings = detected_siblings  # e.g. {"pkl", "mat"}
        self._backup_dir: Optional[Path] = None
        self._output_dir: Optional[Path] = None

        self.setWindowTitle("Filter Output Options")
        self.setMinimumWidth(560)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        # Header
        header = QLabel(
            "<b>Choose how filtered files should be written</b><br>"
            f"<span style='color:{Colors.TEXT_SECONDARY}; font-size:12px;'>"
            f"Source folder: {self._source_dir}</span>"
        )
        header.setWordWrap(True)
        root.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {Colors.BORDER_DEFAULT};")
        root.addWidget(sep)

        # Radio group — output mode
        self._radio_group = QButtonGroup(self)

        self._rb_inplace = QRadioButton(
            "Replace in-place — overwrite original files, remove discarded MUs"
        )
        self._rb_archive = QRadioButton(
            "Archive originals — move originals to _originals/ subfolder, "
            "write filtered files in source folder"
        )
        self._rb_custom = QRadioButton("Custom — choose backup and output locations")

        self._rb_archive.setChecked(True)  # sensible default

        for i, rb in enumerate([self._rb_inplace, self._rb_archive, self._rb_custom]):
            rb.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
            self._radio_group.addButton(rb, i)
            root.addWidget(rb)

        self._radio_group.buttonClicked.connect(self._on_mode_changed)

        # Custom options (shown only when rb_custom is selected)
        self._custom_frame = QFrame()
        self._custom_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
            }}
        """)
        custom_layout = QVBoxLayout(self._custom_frame)
        custom_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        custom_layout.setSpacing(Spacing.XS)

        # Backup row (optional)
        backup_row = QHBoxLayout()
        backup_label = QLabel("Backup location (optional):")
        backup_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px; border: none;")
        backup_row.addWidget(backup_label)
        backup_row.addStretch()
        self._backup_path_label = QLabel("— none —")
        self._backup_path_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; font-style: italic; border: none;"
        )
        backup_row.addWidget(self._backup_path_label)
        backup_btn = QPushButton("Browse…")
        backup_btn.setStyleSheet(Styles.button_secondary())
        backup_btn.clicked.connect(self._pick_backup_dir)
        backup_row.addWidget(backup_btn)
        custom_layout.addLayout(backup_row)

        # Output row (required)
        output_row = QHBoxLayout()
        output_label = QLabel("Output location *:")
        output_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px; border: none;")
        output_row.addWidget(output_label)
        output_row.addStretch()
        self._output_path_label = QLabel("— not set —")
        self._output_path_label.setStyleSheet(
            f"color: {Colors.RED_600}; font-size: 11px; font-style: italic; border: none;"
        )
        output_row.addWidget(self._output_path_label)
        output_btn = QPushButton("Browse…")
        output_btn.setStyleSheet(Styles.button_secondary())
        output_btn.clicked.connect(self._pick_output_dir)
        output_row.addWidget(output_btn)
        custom_layout.addLayout(output_row)

        self._custom_frame.setVisible(False)
        root.addWidget(self._custom_frame)

        # In-place warning
        self._inplace_warning = QLabel(
            "Warning: Original files will be permanently overwritten. "
            "Files for unchecked recordings will be deleted. This cannot be undone."
        )
        self._inplace_warning.setWordWrap(True)
        self._inplace_warning.setStyleSheet(
            f"color: {Colors.RED_600}; font-size: 12px; "
            f"background-color: #fff1f2; border: 1px solid #fecdd3; "
            f"border-radius: {BorderRadius.SM}; padding: 8px;"
        )
        self._inplace_warning.setVisible(False)
        root.addWidget(self._inplace_warning)

        # Sibling file-type section (only when siblings are detected)
        self._cb_pkl: Optional[QCheckBox] = None
        self._cb_mat: Optional[QCheckBox] = None

        if self._detected_siblings:
            sib_sep = QFrame()
            sib_sep.setFrameShape(QFrame.HLine)
            sib_sep.setStyleSheet(f"color: {Colors.BORDER_DEFAULT};")
            root.addWidget(sib_sep)

            sib_header = QLabel(
                "<b>Sibling file types</b> — also apply MU filtering to:"
            )
            sib_header.setWordWrap(True)
            sib_header.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
            root.addWidget(sib_header)

            sib_note = QLabel(
                "Detected alongside the JSON files in the source folder. "
                "Uncheck to leave those files untouched."
            )
            sib_note.setWordWrap(True)
            sib_note.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
            )
            root.addWidget(sib_note)

            sib_row = QHBoxLayout()
            sib_row.setSpacing(Spacing.LG)

            if "pkl" in self._detected_siblings:
                self._cb_pkl = QCheckBox(".pkl (binary decomposition)")
                self._cb_pkl.setChecked(True)
                self._cb_pkl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
                sib_row.addWidget(self._cb_pkl)

            if "mat" in self._detected_siblings:
                self._cb_mat = QCheckBox("_muedit.mat (MATLAB)")
                self._cb_mat.setChecked(True)
                self._cb_mat.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
                sib_row.addWidget(self._cb_mat)

            sib_row.addStretch()
            root.addLayout(sib_row)

        root.addStretch()

        # Button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(Styles.button_secondary())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._run_btn = QPushButton("Run Filter")
        self._run_btn.setStyleSheet(Styles.button_primary())
        self._run_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._run_btn)

        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _on_mode_changed(self) -> None:
        mode = self._current_mode()
        self._custom_frame.setVisible(mode == "custom")
        self._inplace_warning.setVisible(mode == "in_place")
        self._update_run_btn()

    def _current_mode(self) -> str:
        if self._rb_inplace.isChecked():
            return "in_place"
        if self._rb_custom.isChecked():
            return "custom"
        return "archive"

    def _pick_backup_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select backup folder", str(self._source_dir)
        )
        if path:
            self._backup_dir = Path(path)
            self._backup_path_label.setText(str(self._backup_dir))
            self._backup_path_label.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; border: none;"
            )
        self._update_run_btn()

    def _pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select output folder", str(self._source_dir)
        )
        if path:
            self._output_dir = Path(path)
            self._output_path_label.setText(str(self._output_dir))
            self._output_path_label.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; border: none;"
            )
        self._update_run_btn()

    def _update_run_btn(self) -> None:
        if self._current_mode() == "custom":
            self._run_btn.setEnabled(self._output_dir is not None)
        else:
            self._run_btn.setEnabled(True)

    def _on_accept(self) -> None:
        self.accept()

    def _selected_siblings(self) -> FrozenSet[str]:
        result: Set[str] = set()
        if self._cb_pkl is not None and self._cb_pkl.isChecked():
            result.add("pkl")
        if self._cb_mat is not None and self._cb_mat.isChecked():
            result.add("mat")
        return frozenset(result)

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def get_config(self) -> FilterOutputConfig:
        """Return the selected output configuration. Call after exec_() == Accepted."""
        mode = self._current_mode()
        siblings = self._selected_siblings()
        if mode == "in_place":
            return FilterOutputConfig(
                mode="in_place",
                source_dir=self._source_dir,
                output_dir=self._source_dir,
                backup_dir=None,
                process_siblings=siblings,
            )
        if mode == "archive":
            return FilterOutputConfig(
                mode="archive",
                source_dir=self._source_dir,
                output_dir=self._source_dir,
                backup_dir=self._source_dir / "_originals",
                process_siblings=siblings,
            )
        # custom
        return FilterOutputConfig(
            mode="custom",
            source_dir=self._source_dir,
            output_dir=self._output_dir,
            backup_dir=self._backup_dir,
            process_siblings=siblings,
        )
