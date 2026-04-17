# hdsemg_pipe/widgets/wizard/MUQualityReviewWizardWidget.py
"""Step 9 — MU Quality Review.

Left panel: file list grouped by recording session (>=1 per group required).
Right panel: threshold bar + horizontal split of plot canvas (~65%) and MU
             reliability table (~35%) + footer counter + Proceed button.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFontMetrics, QPainter
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False

try:
    import openhdemg.library as emg
    _OPENHDEMG_AVAILABLE = True
except ImportError:
    _OPENHDEMG_AVAILABLE = False

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.decomposition_file import DecompositionFile, ReliabilityThresholds
from hdsemg_pipe.actions.file_grouping import get_group_key, shorten_group_labels
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import BorderRadius, Colors, Spacing, Styles
from hdsemg_pipe.ui_elements.toast import toast_manager
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class _ReliabilityWorker(QThread):
    finished = pyqtSignal(object)   # pd.DataFrame
    error = pyqtSignal(str)

    def __init__(self, dec_file: DecompositionFile, thresholds: ReliabilityThresholds):
        super().__init__()
        self._dec_file = dec_file
        self._thresholds = thresholds

    def run(self):
        try:
            df = self._dec_file.compute_reliability(self._thresholds)
            self.finished.emit(df)
        except Exception as exc:
            self.error.emit(str(exc))


class _STAWorker(QThread):
    finished = pyqtSignal(object)   # sta result dict or None
    error = pyqtSignal(str)

    _GRID_CODES = ["GR08MM1305", "GR04MM1305", "GR10MM0808"]

    def __init__(self, emgfile: dict):
        super().__init__()
        self._emgfile = emgfile

    def run(self):
        if not _OPENHDEMG_AVAILABLE:
            self.finished.emit(None)
            return
        try:
            ef = self._emgfile
            sorted_rawemg = None
            for code in self._GRID_CODES:
                try:
                    sorted_rawemg = emg.sort_rawemg(
                        ef, code=code, orientation=0, dividebycolumn=True
                    )
                    break
                except Exception:
                    continue
            if sorted_rawemg is None:
                self.finished.emit(None)
                return
            sta_result = emg.sta(ef, sorted_rawemg)
            self.finished.emit(sta_result)
        except Exception as exc:
            logger.warning("_STAWorker: STA failed: %s", exc)
            self.finished.emit(None)


class _ProceedWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(int)   # emits n_written
    error = pyqtSignal(str)

    def __init__(
        self,
        kept_files: List[str],
        thresholds: ReliabilityThresholds,
        overrides: Dict[str, Dict[str, str]],
        source_dir: Path,
        dest_dir: Path,
        manifest_path: Path,
    ):
        super().__init__()
        self._kept_files = kept_files
        self._thresholds = thresholds
        self._overrides = overrides
        self._source_dir = source_dir
        self._dest_dir = dest_dir
        self._manifest_path = manifest_path

    def run(self):
        try:
            self._dest_dir.mkdir(parents=True, exist_ok=True)
            total = len(self._kept_files)
            n_written = 0

            for i, filename in enumerate(self._kept_files):
                self.progress.emit(i + 1, total)
                src_json = self._source_dir / filename
                if not src_json.exists():
                    logger.warning("Source file not found: %s", src_json)
                    continue

                # --- Determine which MU indices to keep from JSON analysis ---
                dec_json = DecompositionFile.load(src_json)
                file_overrides_raw = self._overrides.get(filename, {})
                file_overrides = {
                    (0, int(k)): v for k, v in file_overrides_raw.items()
                }

                # Compute reliability to find which MUs survive
                rel_df = dec_json.compute_reliability(self._thresholds)
                keep_mu_indices: set = set()
                for _, row in rel_df.iterrows():
                    mu = int(row["mu_index"])
                    key = (0, mu)
                    decision = file_overrides.get(key, "Auto")
                    if decision == "Keep":
                        keep_mu_indices.add(mu)
                    elif decision == "Filter":
                        pass  # explicitly filtered
                    elif bool(row["is_reliable"]):
                        keep_mu_indices.add(mu)

                stem = src_json.stem
                out_stem = stem if stem.endswith("_covisi_filtered") else stem + "_covisi_filtered"

                # --- 1. Filter and save JSON ---
                filtered_json = dec_json.filter_mus_by_reliability(self._thresholds, file_overrides)
                out_json = self._dest_dir / (out_stem + ".json")
                filtered_json.save(out_json)
                n_written += 1

                # --- 2. Filter sibling PKL (same stem, .pkl extension) ---
                # PKL files lack IPTS, so SIL/PNR cannot be recomputed from them.
                # Apply the same keep_mu_indices derived from the JSON analysis above.
                src_pkl = self._source_dir / (stem + ".pkl")
                if src_pkl.exists():
                    try:
                        dec_pkl = DecompositionFile.load(src_pkl)
                        dec_pkl._pkl_keep_indices = {0: keep_mu_indices}
                        out_pkl = self._dest_dir / (out_stem + ".pkl")
                        dec_pkl.save(out_pkl)
                        n_written += 1
                    except Exception as exc:
                        logger.warning("PKL filter failed for %s: %s", src_pkl.name, exc)

                # --- 3. Filter sibling MAT (same stem + _muedit.mat) ---
                src_mat = self._source_dir / (stem + "_muedit.mat")
                if src_mat.exists():
                    try:
                        dec_mat = DecompositionFile.load(src_mat)
                        out_mat = self._dest_dir / (out_stem + "_muedit.mat")
                        dec_mat._filter_mat_pulsetrain_by_indices(keep_mu_indices, out_mat)
                        n_written += 1
                    except Exception as exc:
                        logger.warning("MAT filter failed for %s: %s", src_mat.name, exc)

            # Write manifest
            manifest = {
                "version": 1,
                "thresholds": self._thresholds.to_dict(),
                "kept_files": self._kept_files,
                "mu_overrides": self._overrides,
            }
            self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._manifest_path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)

            self.finished.emit(n_written)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Custom grouping dialog
# ---------------------------------------------------------------------------

class _CustomGroupingDialog(QDialog):
    """Dialog for applying a custom regex-based file grouping pattern."""

    _PRESETS = [
        ("Default (strip grid dims)", ""),
        ("Subject + Block (e.g. 2_Pyr_1)", r"^(\d+(?:_[A-Za-z]+)+_\d+)"),
        ("First 2 underscore parts", r"^((?:[^_]+_){1}[^_]+)"),
        ("First 3 underscore parts", r"^((?:[^_]+_){2}[^_]+)"),
    ]

    def __init__(self, filepaths: List[str], current_regex: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._filepaths = filepaths
        self._regex = current_regex or ""
        self.setWindowTitle("Custom File Grouping")
        self.resize(720, 520)
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel(
            "<b>Custom Grouping by Regex</b><br>"
            "<span style='color:#666; font-size:12px;'>"
            "Enter a Python regex to extract the group key from each filename stem "
            "(without extension). Use a <b>capture group</b> <code>(...)</code> to "
            "define exactly which part becomes the key; without one the whole match is used."
            "</span>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Presets
        preset_label = QLabel("Presets:")
        preset_label.setStyleSheet("color: #555; font-size: 11px; font-weight: bold;")
        layout.addWidget(preset_label)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for name, pattern in self._PRESETS:
            btn = QPushButton(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.BG_SECONDARY};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: {BorderRadius.SM};
                    padding: 4px 10px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BLUE_50};
                    border-color: {Colors.BLUE_500};
                }}
            """)
            btn.clicked.connect(lambda _, p=pattern: self._apply_preset(p))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        # Regex input row
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: 8px;
            }}
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 4, 8, 4)

        regex_label = QLabel("Regex:")
        regex_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: bold; min-width: 48px;")
        input_layout.addWidget(regex_label)

        self._regex_input = QLineEdit(self._regex)
        self._regex_input.setPlaceholderText(
            r"e.g.  ^(\d+_Pyr_\d+)   or leave empty to use the default logic"
        )
        self._regex_input.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: 4px 8px;
                font-family: monospace;
                font-size: 12px;
                background-color: white;
            }}
            QLineEdit:focus {{
                border-color: {Colors.BLUE_500};
            }}
        """)
        self._regex_input.textChanged.connect(self._on_regex_changed)
        input_layout.addWidget(self._regex_input, 1)
        layout.addWidget(input_frame)

        # Validation error label
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #dc2626; font-size: 11px;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        # Preview table
        preview_label = QLabel("Preview — how files are grouped with current pattern:")
        preview_label.setStyleSheet("color: #555; font-size: 11px; font-weight: bold;")
        layout.addWidget(preview_label)

        self._preview_table = QTableWidget()
        self._preview_table.setColumnCount(2)
        self._preview_table.setHorizontalHeaderLabels(["Filename stem", "Group key"])
        self._preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._preview_table.setSelectionMode(QTableWidget.NoSelection)
        self._preview_table.setAlternatingRowColors(True)
        self._preview_table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_SECONDARY};
                padding: 4px 8px;
                border: none;
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
                font-weight: bold;
                color: {Colors.TEXT_SECONDARY};
            }}
        """)
        layout.addWidget(self._preview_table, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(Styles.button_secondary())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._apply_btn = QPushButton("Apply Grouping")
        self._apply_btn.setStyleSheet(Styles.button_primary())
        self._apply_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._apply_btn)
        layout.addLayout(btn_row)

    def _apply_preset(self, pattern: str):
        self._regex_input.setText(pattern)

    def _on_regex_changed(self, text: str):
        self._regex = text
        self._update_preview()

    def _update_preview(self):
        regex = self._regex.strip()
        if regex:
            try:
                re.compile(regex)
                self._error_label.setVisible(False)
                self._apply_btn.setEnabled(True)
            except re.error as exc:
                self._error_label.setText(f"Invalid regex: {exc}")
                self._error_label.setVisible(True)
                self._apply_btn.setEnabled(False)
                self._preview_table.setRowCount(0)
                return

        rows = []
        for fp in self._filepaths[:60]:
            name = os.path.basename(fp)
            key = get_group_key(name, regex if regex else None)
            rows.append((Path(fp).stem, key))

        self._preview_table.setRowCount(len(rows))
        # Colour rows by group to make grouping visually obvious
        group_colors: Dict[str, str] = {}
        palette = ["#eff6ff", "#f0fdf4", "#fff7ed", "#fdf4ff", "#fefce8"]
        for i, (stem, key) in enumerate(rows):
            if key not in group_colors:
                group_colors[key] = palette[len(group_colors) % len(palette)]
            bg = QColor(group_colors[key])
            for col, text in enumerate([stem, key]):
                cell = QTableWidgetItem(text)
                cell.setBackground(bg)
                self._preview_table.setItem(i, col, cell)

    def _on_accept(self):
        regex = self._regex.strip()
        if regex:
            try:
                re.compile(regex)
            except re.error as exc:
                self._error_label.setText(f"Invalid regex: {exc}")
                self._error_label.setVisible(True)
                return
        self._regex = regex
        self.accept()

    def get_regex(self) -> str:
        """Return the accepted regex (empty string → use default logic)."""
        return self._regex


# ---------------------------------------------------------------------------
# File list items
# ---------------------------------------------------------------------------

_LIST_ROW_HEIGHT = 26  # Shared fixed height for group headers and file items


class _ElidedLabel(QLabel):
    """QLabel that shows '…' when text is wider than the widget."""

    def paintEvent(self, event):
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self.text(), Qt.ElideRight, self.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        painter.drawText(self.contentsRect(), Qt.AlignLeft | Qt.AlignVCenter, elided)


class _GroupHeader(QWidget):
    """Group label + select-all checkbox. Pills live in the synchronized _GroupHeaderPills column."""

    group_toggled = pyqtSignal(str, bool)  # group_key, check_all

    def __init__(self, label: str, group_key: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_LIST_ROW_HEIGHT)
        self._group_key = group_key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, 0, Spacing.SM, 0)
        layout.setSpacing(4)

        self.checkbox = QCheckBox()
        self.checkbox.setTristate(True)
        self.checkbox.setCheckState(Qt.Checked)
        self.checkbox.clicked.connect(self._on_clicked)
        layout.addWidget(self.checkbox)

        lbl = _ElidedLabel(label)
        lbl.setStyleSheet(
            f"font-weight: bold; color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lbl.setMinimumWidth(0)
        layout.addWidget(lbl)

    def _on_clicked(self):
        # Tristate cycles Unchecked→PartiallyChecked on first click from unchecked;
        # normalize partial → checked so the user only gets all-or-nothing toggling.
        if self.checkbox.checkState() == Qt.PartiallyChecked:
            self.checkbox.blockSignals(True)
            self.checkbox.setCheckState(Qt.Checked)
            self.checkbox.blockSignals(False)
        self.group_toggled.emit(self._group_key, self.checkbox.isChecked())

    def update_check_state(self, n_checked: int, n_total: int):
        self.checkbox.blockSignals(True)
        if n_checked == 0:
            self.checkbox.setCheckState(Qt.Unchecked)
        elif n_checked == n_total:
            self.checkbox.setCheckState(Qt.Checked)
        else:
            self.checkbox.setCheckState(Qt.PartiallyChecked)
        self.checkbox.blockSignals(False)


class _GroupHeaderPills(QWidget):
    """The MU-count and file-count pills, always visible in the pinned pills column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_LIST_ROW_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, Spacing.SM, 0)
        layout.setSpacing(4)

        self._mu_pill = QLabel("…")
        self._mu_pill.setStyleSheet(self._pill_style(Colors.GRAY_400))
        layout.addWidget(self._mu_pill)

        self._file_pill = QLabel("…")
        self._file_pill.setStyleSheet(self._pill_style(Colors.GRAY_400))
        layout.addWidget(self._file_pill)

    @staticmethod
    def _pill_style(bg_color: str) -> str:
        return (
            f"background-color: {bg_color}; color: white; font-size: 10px; "
            f"font-weight: bold; border-radius: 7px; padding: 1px 6px;"
        )

    def set_file_counter(self, selected: int, total: int):
        color = Colors.GREEN_600 if selected >= 1 else Colors.RED_600
        self._file_pill.setStyleSheet(self._pill_style(color))
        self._file_pill.setText(f"{selected}/{total}")

    def set_mu_counter(self, reliable: int, total: int):
        color = Colors.GREEN_600 if reliable >= 1 else Colors.GRAY_400
        self._mu_pill.setStyleSheet(self._pill_style(color))
        self._mu_pill.setText(f"{reliable} MU" if total > 0 else "–")

    def set_counter(self, selected: int, total: int):
        self.set_file_counter(selected, total)


class _FileListItem(QWidget):
    toggled = pyqtSignal(str, bool)
    selected = pyqtSignal(str)

    def __init__(self, filepath: str, label: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_LIST_ROW_HEIGHT)
        self.filepath = filepath
        self._is_selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, 0, Spacing.SM, 0)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(
            lambda checked: self.toggled.emit(filepath, checked)
        )
        layout.addWidget(self.checkbox)

        self.name_label = QLabel(label)
        self.name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(self.name_label)
        layout.addStretch()

        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self.selected.emit(self.filepath)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        bg = Colors.BLUE_100 if selected else "transparent"
        self.setStyleSheet(f"background-color: {bg}; border-radius: 4px;")



# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class MUQualityReviewWizardWidget(WizardStepWidget):
    """Step 9 — MU Quality Review."""

    def __init__(self, parent=None):
        super().__init__(
            step_index=9,
            step_name="MU Quality Review",
            description=(
                "Review and filter motor units based on SIL, PNR, and CoVISI "
                "reliability metrics. Select files to forward, inspect plots, "
                "and override per-MU decisions before proceeding."
            ),
            parent=parent,
        )

        # Tighten the WizardStepWidget chrome for this full-screen step
        self.main_layout.setContentsMargins(
            Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM
        )
        self.main_layout.setSpacing(Spacing.XS)
        self.content_card.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.LG};
            }}
        """)
        self.content_layout.setContentsMargins(
            Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM
        )
        self.content_layout.setSpacing(Spacing.XS)
        self.button_container.setVisible(False)

        self._thresholds = ReliabilityThresholds()
        self._reliability_cache: Dict[str, object] = {}
        self._emgfile_cache: Dict[str, Optional[dict]] = {}
        self._overrides: Dict[str, Dict[str, str]] = {}
        self._checked: Dict[str, bool] = {}
        self._groups: Dict[str, List[str]] = {}
        self._items: Dict[str, _FileListItem] = {}
        self._group_headers: Dict[str, _GroupHeaderPills] = {}
        self._group_header_widgets: Dict[str, _GroupHeader] = {}
        self._current_file: Optional[str] = None
        self._sta_cache: Dict[str, object] = {}
        self._worker: Optional[QThread] = None
        self._bg_workers: List[QThread] = []   # keeps preload workers alive
        self._custom_group_regex: Optional[str] = None
        self._all_filepaths: List[str] = []
        # Debounce timer for override-warning dialog
        self._override_warn_timer = QTimer(self)
        self._override_warn_timer.setSingleShot(True)
        self._override_warn_timer.timeout.connect(self._check_overrides_after_threshold_change)
        self._override_warned_for_count: int = 0  # avoids re-showing for same overrides

        self._build_ui()

    # -- WizardStepWidget interface --------------------------------------------

    def create_buttons(self):
        # Buttons are managed inside _build_ui; nothing to add to the base footer.
        pass

    # -- UI construction -------------------------------------------------------

    def _build_ui(self):
        container = QFrame()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QHBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        outer_splitter = QSplitter(Qt.Horizontal)
        root.addWidget(outer_splitter)

        # ---- Left panel: file list + always-visible pills column ----
        left = QWidget()
        left.setMinimumWidth(160)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(Spacing.SM, Spacing.SM, 0, Spacing.SM)
        left_layout.setSpacing(0)

        # File-names scroll area: horizontal scroll enabled for long names
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._file_list_widget = QWidget()
        self._file_list_layout = QVBoxLayout(self._file_list_widget)
        self._file_list_layout.setContentsMargins(0, 0, 0, 0)
        self._file_list_layout.setSpacing(2)
        self._file_list_layout.addStretch()
        scroll.setWidget(self._file_list_widget)

        # Pills column: fixed width, V-scroll synced with file list, no H-scroll
        self._pills_col_widget = QWidget()
        self._pills_col_layout = QVBoxLayout(self._pills_col_widget)
        self._pills_col_layout.setContentsMargins(0, 0, 0, 0)
        self._pills_col_layout.setSpacing(2)
        self._pills_col_layout.addStretch()

        self._pills_col_scroll = QScrollArea()
        self._pills_col_scroll.setWidget(self._pills_col_widget)
        self._pills_col_scroll.setWidgetResizable(True)
        self._pills_col_scroll.setFrameShape(QFrame.NoFrame)
        self._pills_col_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._pills_col_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._pills_col_scroll.setFixedWidth(90)

        # Bidirectional V-scroll sync (Qt skips signal if value unchanged → no loop)
        scroll.verticalScrollBar().valueChanged.connect(
            self._pills_col_scroll.verticalScrollBar().setValue
        )
        self._pills_col_scroll.verticalScrollBar().valueChanged.connect(
            scroll.verticalScrollBar().setValue
        )

        list_area = QWidget()
        list_area_layout = QHBoxLayout(list_area)
        list_area_layout.setContentsMargins(0, 0, 0, 0)
        list_area_layout.setSpacing(0)
        list_area_layout.addWidget(scroll)
        list_area_layout.addWidget(self._pills_col_scroll)
        left_layout.addWidget(list_area)

        self._grouping_btn = QPushButton("⚙ Custom Grouping")
        self._grouping_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_SECONDARY};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
                font-size: 11px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {Colors.BLUE_50};
                color: {Colors.BLUE_700};
                border-color: {Colors.BLUE_100};
            }}
        """)
        self._grouping_btn.clicked.connect(self._open_custom_grouping_dialog)
        left_layout.addWidget(self._grouping_btn)

        outer_splitter.addWidget(left)

        # ---- Right panel ----
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        right_layout.setSpacing(Spacing.SM)

        # Threshold bar
        threshold_bar = QFrame()
        threshold_bar.setStyleSheet(Styles.card())
        tb_layout = QHBoxLayout(threshold_bar)
        tb_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

        self._sil_check = QCheckBox("SIL >=")
        self._sil_check.setChecked(True)
        self._sil_spin = QDoubleSpinBox()
        self._sil_spin.setRange(0.0, 1.0)
        self._sil_spin.setSingleStep(0.05)
        self._sil_spin.setDecimals(3)
        self._sil_spin.setValue(0.9)

        self._pnr_check = QCheckBox("PNR >=")
        self._pnr_check.setChecked(True)
        self._pnr_spin = QDoubleSpinBox()
        self._pnr_spin.setRange(0.0, 100.0)
        self._pnr_spin.setSingleStep(1.0)
        self._pnr_spin.setDecimals(1)
        self._pnr_spin.setValue(30.0)
        self._pnr_spin.setSuffix(" dB")

        self._covisi_check = QCheckBox("CoVISI <=")
        self._covisi_check.setChecked(True)
        self._covisi_spin = QDoubleSpinBox()
        self._covisi_spin.setRange(0.0, 100.0)
        self._covisi_spin.setSingleStep(1.0)
        self._covisi_spin.setDecimals(1)
        self._covisi_spin.setValue(30.0)
        self._covisi_spin.setSuffix(" %")

        for w in [
            self._sil_check, self._sil_spin,
            self._pnr_check, self._pnr_spin,
            self._covisi_check, self._covisi_spin,
        ]:
            tb_layout.addWidget(w)
        tb_layout.addStretch()
        right_layout.addWidget(threshold_bar)

        # Content splitter: plot | table
        content_splitter = QSplitter(Qt.Horizontal)

        # Plot panel
        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(Spacing.XS)

        self._plot_dropdown = QComboBox()
        self._plot_dropdown.addItems(
            ["Discharge Rate (IDR)", "Discharge Times", "MUAPs"]
        )
        plot_layout.addWidget(self._plot_dropdown)

        self._canvas_container = QWidget()
        self._canvas_layout = QVBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)

        if _MATPLOTLIB_AVAILABLE:
            self._figure = Figure(figsize=(8, 5), tight_layout=True)
            self._canvas = FigureCanvasQTAgg(self._figure)
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._canvas_layout.addWidget(self._canvas)
        else:
            self._canvas_layout.addWidget(QLabel("matplotlib unavailable"))

        plot_layout.addWidget(self._canvas_container)
        content_splitter.addWidget(plot_panel)

        # MU table panel
        table_panel = QWidget()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._mu_table = QTableWidget()
        self._mu_table.setColumnCount(7)
        self._mu_table.setHorizontalHeaderLabels(
            ["#", "SIL", "PNR (dB)", "CoVISI (%)", "DR (pps)", "Spikes", "Decision"]
        )
        self._mu_table.horizontalHeader().setStretchLastSection(True)
        self._mu_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._mu_table.setSelectionMode(QTableWidget.NoSelection)
        self._mu_table.setToolTip("Click Decision cell to toggle Keep / Filter override")
        self._mu_table.cellClicked.connect(self._on_table_cell_clicked)
        table_layout.addWidget(self._mu_table)
        content_splitter.addWidget(table_panel)

        content_splitter.setSizes([650, 350])
        right_layout.addWidget(content_splitter, stretch=1)

        # Footer
        self._footer_label = QLabel()
        self._footer_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        right_layout.addWidget(self._footer_label)

        # Proceed button
        self._proceed_btn = QPushButton("Proceed")
        self._proceed_btn.setStyleSheet(Styles.button_primary())
        self._proceed_btn.setEnabled(False)
        self._proceed_btn.clicked.connect(self._on_proceed)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._proceed_btn)
        right_layout.addLayout(btn_row)

        outer_splitter.addWidget(right)
        outer_splitter.setSizes([240, 760])

        # Connect threshold controls
        for w in [self._sil_check, self._pnr_check, self._covisi_check]:
            w.toggled.connect(self._on_threshold_changed)
        for w in [self._sil_spin, self._pnr_spin, self._covisi_spin]:
            w.valueChanged.connect(self._on_threshold_changed)

        self._plot_dropdown.currentIndexChanged.connect(self._on_plot_type_changed)

        self.content_layout.addWidget(container)

    # -- WizardStepWidget hook -------------------------------------------------

    def check(self):
        """Populate file list from decomposition_auto folder."""
        if not global_state.is_widget_completed("step8"):
            return
        source_dir = Path(global_state.get_decomposition_path())
        if not source_dir.exists():
            return
        _EXCLUDED_PREFIXES = ("algorithm_params", "decomposition_mapping",
                              "multigrid_groupings", "status_test")
        files = sorted(
            str(p) for p in source_dir.iterdir()
            if p.suffix.lower() == ".json"
            and not any(p.name.startswith(ex) for ex in _EXCLUDED_PREFIXES)
        )
        if files:
            self._populate_file_list(files)

    # -- Public API ------------------------------------------------------------

    def restore_from_manifest(self, manifest: dict):
        """Restore widget state from a previously saved manifest."""
        thresholds_data = manifest.get("thresholds", {})
        self._thresholds = ReliabilityThresholds.from_dict(thresholds_data)

        for w in [
            self._sil_check, self._sil_spin, self._pnr_check,
            self._pnr_spin, self._covisi_check, self._covisi_spin,
        ]:
            w.blockSignals(True)
        self._sil_check.setChecked(self._thresholds.sil_enabled)
        self._sil_spin.setValue(self._thresholds.sil_min)
        self._pnr_check.setChecked(self._thresholds.pnr_enabled)
        self._pnr_spin.setValue(self._thresholds.pnr_min)
        self._covisi_check.setChecked(self._thresholds.covisi_enabled)
        self._covisi_spin.setValue(self._thresholds.covisi_max)
        for w in [
            self._sil_check, self._sil_spin, self._pnr_check,
            self._pnr_spin, self._covisi_check, self._covisi_spin,
        ]:
            w.blockSignals(False)

        self._overrides = manifest.get("mu_overrides", {})
        kept_files = set(manifest.get("kept_files", []))

        for filepath, item in self._items.items():
            basename = Path(filepath).name
            should_check = basename in kept_files
            item.checkbox.blockSignals(True)
            item.checkbox.setChecked(should_check)
            item.checkbox.blockSignals(False)
            self._checked[filepath] = should_check

        self._update_group_headers()
        self._update_proceed_button()

    # -- Private helpers -------------------------------------------------------

    def _populate_file_list(self, filepaths: List[str]):
        self._all_filepaths = filepaths
        # Clear both layouts (keep the stretch item at the end of each)
        for layout in (self._file_list_layout, self._pills_col_layout):
            while layout.count() > 1:
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        self._items.clear()
        self._group_headers.clear()
        self._group_header_widgets.clear()
        self._groups.clear()
        self._checked.clear()

        for fp in filepaths:
            key = get_group_key(os.path.basename(fp), self._custom_group_regex)
            self._groups.setdefault(key, []).append(fp)

        labels = shorten_group_labels(list(self._groups.keys()))

        insert_pos = 0
        for key, fps in self._groups.items():
            # File-names column: group label + select-all checkbox
            header_widget = _GroupHeader(labels.get(key, key), group_key=key)
            header_widget.group_toggled.connect(self._on_group_toggled)
            self._group_header_widgets[key] = header_widget
            self._file_list_layout.insertWidget(insert_pos, header_widget)

            # Pills column: always-visible pills for this group
            pills = _GroupHeaderPills()
            self._group_headers[key] = pills
            self._pills_col_layout.insertWidget(insert_pos, pills)

            insert_pos += 1
            for fp in fps:
                item = _FileListItem(fp, Path(fp).name)
                item.toggled.connect(self._on_file_toggled)
                item.selected.connect(self._on_file_selected)
                self._items[fp] = item
                self._checked[fp] = True
                self._file_list_layout.insertWidget(insert_pos, item)

                # Spacer in pills column matching each file item row
                spacer = QWidget()
                spacer.setFixedHeight(_LIST_ROW_HEIGHT)
                self._pills_col_layout.insertWidget(insert_pos, spacer)

                insert_pos += 1

        self._update_group_headers()
        self._update_proceed_button()

        if filepaths:
            self._on_file_selected(filepaths[0])
        self._preload_all_reliability()

    def _preload_all_reliability(self):
        """Launch background reliability workers for every file not yet cached.

        This populates the group-header MU counters without requiring the user
        to manually click through each file first.
        """
        self._bg_workers.clear()
        for fp in self._all_filepaths:
            if fp in self._reliability_cache:
                continue
            try:
                dec = DecompositionFile.load(Path(fp))
            except Exception as exc:
                logger.warning("Preload: could not load %s: %s", fp, exc)
                continue
            if fp not in self._emgfile_cache:
                self._emgfile_cache[fp] = dec.get_emgfile_for_plotting()
            worker = _ReliabilityWorker(dec, self._thresholds)
            worker.finished.connect(
                lambda df, p=fp: self._on_reliability_loaded(p, df)
            )
            worker.error.connect(
                lambda err: logger.warning("Preload reliability error: %s", err)
            )
            self._bg_workers.append(worker)
            worker.start()

    def _on_file_toggled(self, filepath: str, checked: bool):
        self._checked[filepath] = checked
        self._update_group_headers()
        self._update_proceed_button()
        self._update_footer()

    def _on_group_toggled(self, group_key: str, check_all: bool):
        fps = self._groups.get(group_key, [])
        for fp in fps:
            self._checked[fp] = check_all
            item = self._items.get(fp)
            if item:
                item.checkbox.blockSignals(True)
                item.checkbox.setChecked(check_all)
                item.checkbox.blockSignals(False)
        self._update_group_headers()
        self._update_proceed_button()
        self._update_footer()

    def _on_file_selected(self, filepath: str):
        if self._current_file:
            old = self._items.get(self._current_file)
            if old:
                old.set_selected(False)
        self._current_file = filepath
        item = self._items.get(filepath)
        if item:
            item.set_selected(True)
        self._load_file_data(filepath)

    def _load_file_data(self, filepath: str):
        if filepath in self._reliability_cache:
            self._refresh_mu_table(filepath)
            self._refresh_plot(filepath)
            return
        try:
            dec = DecompositionFile.load(Path(filepath))
        except Exception as exc:
            logger.warning("Could not load %s: %s", filepath, exc)
            return
        self._emgfile_cache[filepath] = dec.get_emgfile_for_plotting()
        worker = _ReliabilityWorker(dec, self._thresholds)
        worker.finished.connect(
            lambda df, fp=filepath: self._on_reliability_loaded(fp, df)
        )
        worker.error.connect(
            lambda err: logger.warning("Reliability worker error: %s", err)
        )
        self._worker = worker
        worker.start()

    def _on_reliability_loaded(self, filepath: str, df):
        self._reliability_cache[filepath] = df
        if filepath == self._current_file:
            self._refresh_mu_table(filepath)
            self._refresh_plot(filepath)
        self._update_group_headers()
        self._update_footer()

    def _refresh_mu_table(self, filepath: str):
        import math
        df = self._reliability_cache.get(filepath)
        if df is None or len(df) == 0:
            self._mu_table.setRowCount(0)
            return

        file_overrides = self._overrides.get(filepath, {})
        thresholds = self._build_thresholds()

        green = QColor(Colors.GREEN_100)
        red = QColor(Colors.RED_100)
        neutral = QColor(Colors.BG_PRIMARY)

        def _metric_item(val, fmt, passes):
            """Cell coloured green/red based on whether this metric passes."""
            if isinstance(val, float) and math.isnan(val):
                item = QTableWidgetItem("N/A")
                item.setBackground(red)
            else:
                item = QTableWidgetItem(fmt.format(val))
                item.setBackground(green if passes else red)
            return item

        def _neutral_item(val, fmt):
            if isinstance(val, float) and math.isnan(val):
                item = QTableWidgetItem("N/A")
            else:
                item = QTableWidgetItem(fmt.format(val))
            item.setBackground(neutral)
            return item

        self._mu_table.setRowCount(len(df))
        for row_idx, (_, row) in enumerate(df.iterrows()):
            mu = int(row["mu_index"])
            sil = float(row["sil"])
            pnr = float(row["pnr"])
            covisi = float(row["covisi"])
            override = file_overrides.get(str(mu), "Auto")  # "Auto"|"Keep"|"Filter"

            # Per-metric pass/fail
            sil_ok = (not math.isnan(sil)) and sil >= thresholds.sil_min if thresholds.sil_enabled else True
            pnr_ok = (not math.isnan(pnr)) and pnr >= thresholds.pnr_min if thresholds.pnr_enabled else True
            cov_ok = (not math.isnan(covisi)) and covisi <= thresholds.covisi_max if thresholds.covisi_enabled else True

            # Overall decision
            auto_keep = sil_ok and pnr_ok and cov_ok
            if override == "Keep":
                final_keep = True
            elif override == "Filter":
                final_keep = False
            else:
                final_keep = auto_keep

            # MU # cell — coloured by final decision
            mu_item = QTableWidgetItem(str(mu))
            mu_item.setBackground(green if final_keep else red)
            self._mu_table.setItem(row_idx, 0, mu_item)

            self._mu_table.setItem(row_idx, 1, _metric_item(sil, "{:.3f}", sil_ok))
            self._mu_table.setItem(row_idx, 2, _metric_item(pnr, "{:.1f}", pnr_ok))
            self._mu_table.setItem(row_idx, 3, _metric_item(covisi, "{:.1f}", cov_ok))
            self._mu_table.setItem(row_idx, 4, _neutral_item(float(row["dr_mean"]), "{:.1f}"))
            self._mu_table.setItem(row_idx, 5, _neutral_item(float(row["n_spikes"]), "{:.0f}"))

            # Decision cell: show effective decision + * if user has overridden
            is_overridden = override != "Auto"
            label = ("Keep" if final_keep else "Filter") + (" *" if is_overridden else "")
            decision_item = QTableWidgetItem(label)
            decision_item.setBackground(green if final_keep else red)
            self._mu_table.setItem(row_idx, 6, decision_item)

    def _on_table_cell_clicked(self, row: int, col: int):
        """Click on the Decision column cycles override: Auto → Keep → Filter → Auto.
        Clicking any row updates the MUAPs plot to show that MU."""
        if self._current_file is None:
            return
        # Refresh MUAPs plot for newly selected row
        if self._plot_dropdown.currentText() == "MUAPs":
            sta = self._sta_cache.get(self._current_file)
            if sta is not None:
                self._draw_muaps(sta)
        if col != 6:
            return
        df = self._reliability_cache.get(self._current_file)
        if df is None or row >= len(df):
            return
        mu = int(df.iloc[row]["mu_index"])
        current = self._overrides.get(self._current_file, {}).get(str(mu), "Auto")
        next_override = {"Auto": "Keep", "Keep": "Filter", "Filter": "Auto"}[current]
        if next_override == "Auto":
            # Remove override (back to auto)
            overrides = self._overrides.get(self._current_file, {})
            overrides.pop(str(mu), None)
        else:
            self._overrides.setdefault(self._current_file, {})[str(mu)] = next_override
        self._override_warned_for_count = 0  # allow re-warning on next threshold change
        self._refresh_mu_table(self._current_file)
        self._update_group_headers()
        self._update_footer()

    def _refresh_plot(self, filepath: str):
        if not _MATPLOTLIB_AVAILABLE or not _OPENHDEMG_AVAILABLE:
            return
        emgfile = self._emgfile_cache.get(filepath)
        plot_type = self._plot_dropdown.currentText()
        if plot_type == "MUAPs":
            if emgfile is None:
                # emgfile not ready yet; clear stale canvas
                self._figure.clear()
                ax = self._figure.add_subplot(111)
                ax.text(0.5, 0.5, "Loading…", ha="center", va="center",
                        transform=ax.transAxes, fontsize=10, color="gray")
                ax.axis("off")
                self._canvas.draw()
                return
            self._load_muaps_plot(filepath, emgfile)
            return
        if emgfile is None:
            return
        # openhdemg's get_unique_fig_name() iterates plt.get_fignums() and calls
        # canvas.manager.get_window_title() on each.  After we embed a figure via
        # FigureCanvasQTAgg the Qt canvas has manager=None, which causes a crash on
        # the next openhdemg plot call.  Purge all pyplot-registered figures first.
        plt.close('all')
        try:
            if plot_type == "Discharge Rate (IDR)":
                fig = emg.plot_idr(emgfile, munumber="all", showimmediately=False)
            else:
                raw = emgfile.get("RAW_SIGNAL")
                has_raw = (
                    raw is not None
                    and hasattr(raw, "shape")
                    and raw.shape[0] > 0
                )
                fig = emg.plot_mupulses(
                    emgfile,
                    linewidths=0.8,
                    addrefsig=has_raw,
                    showimmediately=False,
                )
            self._replace_canvas_figure(fig)
        except Exception as exc:
            self._figure.clear()
            ax = self._figure.add_subplot(111)
            ax.text(
                0.5, 0.5, f"Plot error:\n{exc}",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=9, color="red",
            )
            self._canvas.draw()

    def _replace_canvas_figure(self, fig):
        """Swap out the embedded canvas for openhdemg's returned figure."""
        if fig is None:
            return
        # Remove the old canvas from the layout
        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Embed openhdemg's figure directly — preserves scatter/collection artists
        self._figure = fig
        self._canvas = FigureCanvasQTAgg(fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas_layout.addWidget(self._canvas)
        self._canvas.draw()

    def _load_muaps_plot(self, filepath: str, emgfile: dict):
        if filepath in self._sta_cache:
            self._draw_muaps(self._sta_cache[filepath])
            return
        # Clear stale canvas and show computing indicator while STA runs
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.text(0.5, 0.5, "Computing MUAPs…", ha="center", va="center",
                transform=ax.transAxes, fontsize=10, color="gray")
        ax.axis("off")
        self._canvas.draw()
        worker = _STAWorker(emgfile)
        worker.finished.connect(
            lambda sta, fp=filepath: self._on_sta_done(fp, sta)
        )
        worker.error.connect(
            lambda err: logger.warning("STA worker error: %s", err)
        )
        self._worker = worker
        worker.start()

    def _on_sta_done(self, filepath: str, sta_result):
        self._sta_cache[filepath] = sta_result
        if filepath == self._current_file:
            self._draw_muaps(sta_result)

    def _draw_muaps(self, sta_result):
        if sta_result is None or not _OPENHDEMG_AVAILABLE:
            self._figure.clear()
            ax = self._figure.add_subplot(111)
            ax.text(
                0.5, 0.5, "MUAPs unavailable",
                ha="center", va="center", transform=ax.transAxes,
            )
            self._canvas.draw()
            return
        # sta_result is {mu_index: DataFrame, ...}; plot_muaps needs a single MU entry
        selected_row = self._mu_table.currentRow()
        mu_index = 0
        if self._current_file is not None:
            df = self._reliability_cache.get(self._current_file)
            if df is not None and selected_row >= 0 and selected_row < len(df):
                mu_index = int(df.iloc[selected_row]["mu_index"])
        # Fall back to first available key if mu_index not present
        if mu_index not in sta_result:
            mu_index = next(iter(sta_result), None)
        if mu_index is None:
            self._figure.clear()
            ax = self._figure.add_subplot(111)
            ax.text(0.5, 0.5, "MUAPs unavailable", ha="center", va="center", transform=ax.transAxes)
            self._canvas.draw()
            return
        plt.close('all')
        try:
            fig = emg.plot_muaps(
                sta_result[mu_index],
                title=f"MUAPs — MU {mu_index}",
                showimmediately=False,
            )
            self._replace_canvas_figure(fig)
        except Exception as exc:
            self._figure.clear()
            ax = self._figure.add_subplot(111)
            ax.text(
                0.5, 0.5, f"MUAPs error:\n{exc}",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=9, color="red",
            )
            self._canvas.draw()

    def _on_plot_type_changed(self):
        if self._current_file:
            self._refresh_plot(self._current_file)

    def _on_threshold_changed(self):
        self._thresholds = self._build_thresholds()
        # The reliability cache stores raw SIL/PNR/CoVISI values that are
        # threshold-independent.  All display helpers (_refresh_mu_table,
        # _update_group_headers, _update_footer) already apply self._thresholds
        # live to those raw values, so we only need to repaint — no cache
        # invalidation, no worker launch, no disk I/O.
        self._update_group_headers()
        if self._current_file:
            if self._current_file in self._reliability_cache:
                self._refresh_mu_table(self._current_file)
            else:
                # File not yet loaded — trigger initial load (first visit only)
                self._load_file_data(self._current_file)
        self._update_footer()
        # Debounced check: warn about active manual overrides once the user
        # stops adjusting sliders (600 ms of silence).
        total_overrides = sum(len(v) for v in self._overrides.values())
        if total_overrides > 0 and total_overrides != self._override_warned_for_count:
            self._override_warn_timer.start(600)

    def _check_overrides_after_threshold_change(self):
        """Show a one-time dialog when thresholds change while manual overrides exist."""
        total_overrides = sum(len(v) for v in self._overrides.values())
        if total_overrides == 0:
            return
        # Don't re-warn for the exact same count we already warned about
        if total_overrides == self._override_warned_for_count:
            return
        self._override_warned_for_count = total_overrides

        msg = QMessageBox(self)
        msg.setWindowTitle("Manual MU Overrides Active")
        msg.setIcon(QMessageBox.Information)
        msg.setText(
            f"<b>{total_overrides} MU decision(s)</b> have been set manually (marked with *).<br><br>"
            "Changing thresholds updates the <i>automatic</i> decisions, but "
            "your manual overrides are <b>kept as-is</b>.<br><br>"
            "What would you like to do?"
        )
        keep_btn = msg.addButton("Keep manual decisions", QMessageBox.AcceptRole)
        reset_btn = msg.addButton("Reset all to Auto", QMessageBox.ResetRole)
        msg.setDefaultButton(keep_btn)
        msg.exec_()

        if msg.clickedButton() == reset_btn:
            self._overrides.clear()
            self._override_warned_for_count = 0
            if self._current_file:
                self._refresh_mu_table(self._current_file)
            self._update_group_headers()
            self._update_footer()

    def _build_thresholds(self) -> ReliabilityThresholds:
        return ReliabilityThresholds(
            sil_min=self._sil_spin.value(),
            pnr_min=self._pnr_spin.value(),
            covisi_max=self._covisi_spin.value(),
            sil_enabled=self._sil_check.isChecked(),
            pnr_enabled=self._pnr_check.isChecked(),
            covisi_enabled=self._covisi_check.isChecked(),
        )

    def _update_group_headers(self):
        thresholds = self._build_thresholds()
        for key, fps in self._groups.items():
            header = self._group_headers.get(key)
            if not header:
                continue
            checked_fps = [fp for fp in fps if self._checked.get(fp, True)]

            # File pill — always up to date
            header.set_file_counter(len(checked_fps), len(fps))

            # Group header checkbox — reflects current selection state
            hw = self._group_header_widgets.get(key)
            if hw:
                hw.update_check_state(len(checked_fps), len(fps))

            # MU pill — use whatever files have data; show partial count as data loads
            total_reliable = 0
            total_mus = 0
            for fp in checked_fps:
                df = self._reliability_cache.get(fp)
                if df is None:
                    continue
                file_overrides = self._overrides.get(fp, {})
                for _, row in df.iterrows():
                    mu = int(row["mu_index"])
                    total_mus += 1
                    decision = file_overrides.get(str(mu), "Auto")
                    sil = float(row["sil"])
                    pnr = float(row["pnr"])
                    covisi = float(row["covisi"])
                    is_rel = thresholds.is_reliable(sil, pnr, covisi)
                    if decision == "Keep" or (decision == "Auto" and is_rel):
                        total_reliable += 1
            header.set_mu_counter(total_reliable, total_mus)

    def _update_proceed_button(self):
        any_checked = any(
            self._checked.get(fp, True)
            for fps in self._groups.values()
            for fp in fps
        )
        self._proceed_btn.setEnabled(any_checked and bool(self._groups))

    def _update_footer(self):
        import math
        total_mus = 0
        filtered_mus = 0
        thresholds = self._build_thresholds()
        for fp, checked in self._checked.items():
            if not checked:
                continue
            df = self._reliability_cache.get(fp)
            if df is None:
                continue
            file_overrides = self._overrides.get(fp, {})
            for _, row in df.iterrows():
                mu = int(row["mu_index"])
                total_mus += 1
                decision = file_overrides.get(str(mu), "Auto")
                sil = float(row["sil"])
                pnr = float(row["pnr"])
                covisi = float(row["covisi"])
                is_reliable = thresholds.is_reliable(sil, pnr, covisi)
                if decision == "Filter" or (decision == "Auto" and not is_reliable):
                    filtered_mus += 1
        self._footer_label.setText(
            f"{filtered_mus} of {total_mus} total MUs filtered"
        )

    def _open_custom_grouping_dialog(self):
        dialog = _CustomGroupingDialog(
            self._all_filepaths,
            current_regex=self._custom_group_regex,
            parent=self,
        )
        if dialog.exec_() == QDialog.Accepted:
            regex = dialog.get_regex()
            self._custom_group_regex = regex if regex else None
            # Update button label to indicate an active custom pattern
            if self._custom_group_regex:
                self._grouping_btn.setText(f"⚙ Custom: {self._custom_group_regex[:24]}…"
                                           if len(self._custom_group_regex) > 24
                                           else f"⚙ Custom: {self._custom_group_regex}")
                self._grouping_btn.setStyleSheet(self._grouping_btn.styleSheet().replace(
                    Colors.BG_SECONDARY, Colors.BLUE_50
                ).replace(Colors.TEXT_SECONDARY, Colors.BLUE_700))
            else:
                self._grouping_btn.setText("⚙ Custom Grouping")
            if self._all_filepaths:
                self._populate_file_list(self._all_filepaths)

    def _on_proceed(self):
        unvisited = [
            fp for fp in self._checked
            if self._checked[fp] and fp not in self._reliability_cache
        ]
        if unvisited:
            reply = QMessageBox.question(
                self,
                "Unvisited files",
                f"{len(unvisited)} file(s) have not been reviewed.\n"
                "They will be processed with Auto decisions using current thresholds.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        kept_files = [
            Path(fp).name
            for fp, checked in self._checked.items()
            if checked
        ]
        source_dir = Path(global_state.get_decomposition_path())
        dest_dir = Path(global_state.get_decomposition_covisi_filtered_path())
        manifest_path = Path(global_state.get_analysis_path()) / "mu_quality_selection.json"

        self._proceed_btn.setEnabled(False)
        worker = _ProceedWorker(
            kept_files=kept_files,
            thresholds=self._build_thresholds(),
            overrides=self._overrides,
            source_dir=source_dir,
            dest_dir=dest_dir,
            manifest_path=manifest_path,
        )
        worker.finished.connect(self._on_proceed_done)
        worker.error.connect(self._on_proceed_error)
        worker.progress.connect(
            lambda cur, tot: self._proceed_btn.setText(f"Processing {cur}/{tot}…")
        )
        self._worker = worker
        worker.start()

    def _on_proceed_done(self, n_written: int):
        self._proceed_btn.setEnabled(True)
        self._proceed_btn.setText("Proceed")
        toast_manager.show_toast(f"Done — {n_written} file(s) written to covisi_filtered/", "success")
        self.complete_step()  # marks complete, emits stepCompleted → triggers auto-navigation

    def _on_proceed_error(self, error: str):
        self._proceed_btn.setEnabled(True)
        self._proceed_btn.setText("Proceed")
        toast_manager.show_toast(f"Proceed failed: {error}", "error", duration=8000)
