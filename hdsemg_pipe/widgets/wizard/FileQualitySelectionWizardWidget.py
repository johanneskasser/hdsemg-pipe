"""
File Quality Selection Wizard Widget

Pipeline step for reviewing per-file signal quality and selecting
which files to include in further analysis.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStyleFactory, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.file_grouping import get_group_key, shorten_group_labels
from hdsemg_pipe.actions.tracking_error_metrics import (
    DEFAULT_THRESHOLDS, METRIC_NAMES, METRIC_NRMSE,
    TIER_ORDER, compute_metric,
)
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import BorderRadius, Colors, Fonts, Spacing, Styles
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.widgets.dialogs.TrackingErrorThresholdsDialog import (
    TrackingErrorThresholdsDialog,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_label_color(
    score: Optional[float],
    thresholds: Optional[Dict[str, float]] = None,
) -> Tuple[str, str]:
    """Map a 0–100 quality score to (label, hex_color).

    Parameters
    ----------
    score:
        Quality score in [0, 100] or None.
    thresholds:
        Optional dict mapping tier name → minimum score boundary.  When omitted
        the NRMSE defaults (90/80/70/60) are used for backwards compatibility.
    """
    if score is None:
        return "N/A", Colors.GRAY_400
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS[METRIC_NRMSE]
    if score >= thresholds.get("excellent", 90):
        return "Excellent", Colors.GREEN_500
    if score >= thresholds.get("good", 80):
        return "Good", Colors.BLUE_500
    if score >= thresholds.get("ok", 70):
        return "OK", Colors.YELLOW_500
    if score >= thresholds.get("troubled", 60):
        return "Troubled", Colors.ORANGE_500
    return "Bad", Colors.RED_500


def _rms_to_label_color(rms: Optional[float]) -> Tuple[str, str]:
    """Map mean RMS (µV) to (label, hex_color)."""
    if rms is None or np.isnan(rms):
        return "N/A", Colors.GRAY_400
    if rms <= 5:
        return "Excellent", Colors.GREEN_500
    if rms <= 10:
        return "Good", Colors.BLUE_500
    if rms <= 15:
        return "OK", Colors.YELLOW_500
    if rms <= 20:
        return "Troubled", Colors.ORANGE_500
    return "Bad", Colors.RED_500



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

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #dc2626; font-size: 11px;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

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
        from pathlib import Path as _Path
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

        from PyQt5.QtGui import QColor
        rows = []
        for fp in self._filepaths[:60]:
            name = os.path.basename(fp)
            key = get_group_key(name, regex if regex else None)
            rows.append((_Path(fp).stem, key))

        self._preview_table.setRowCount(len(rows))
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
# _FileListItem
# ---------------------------------------------------------------------------

class _FileListItem(QWidget):
    """A row in the file list: status dot + checkbox + filename label."""

    clicked = pyqtSignal(str)          # emits file_path on row click
    selection_changed = pyqtSignal(str, bool)  # emits (file_path, is_checked)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._is_active = False
        self._setup_ui()
        self._apply_style(active=False)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(Spacing.SM)

        # Coloured status dot
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet(
            f"color: {Colors.GRAY_300}; font-size: 12px;"
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._dot)

        # Include/exclude checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(True)
        self._checkbox.stateChanged.connect(self._on_state_changed)
        layout.addWidget(self._checkbox)

        # Filename label – full path as tooltip, elided display text
        filename = os.path.basename(self._file_path)
        self._name_label = QLabel(filename)
        self._name_label.setToolTip(self._file_path)
        self._name_label.setWordWrap(False)
        self._name_label.setMinimumWidth(0)
        self._name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_SM};"
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._name_label, 1)

    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        self.clicked.emit(self._file_path)
        super().mousePressEvent(event)

    def _on_state_changed(self, state):
        self.selection_changed.emit(self._file_path, state == Qt.Checked)

    # ------------------------------------------------------------------

    def set_quality_color(self, color: str):
        self._dot.setStyleSheet(
            f"color: {color}; font-size: 12px;"
            f"background: transparent; border: none;"
        )

    def set_selected(self, active: bool):
        """Highlight item when it is the currently viewed file."""
        self._is_active = active
        self._apply_style(active)

    def _apply_style(self, active: bool):
        bg = Colors.BLUE_100 if active else "transparent"
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-radius: {BorderRadius.SM};
            }}
            QWidget:hover {{
                background-color: {"#bfdbfe" if active else Colors.BG_SECONDARY};
            }}
        """)

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool):
        self._checkbox.blockSignals(True)
        self._checkbox.setChecked(checked)
        self._checkbox.blockSignals(False)
        self.selection_changed.emit(self._file_path, checked)


# ---------------------------------------------------------------------------
# _GroupHeader
# ---------------------------------------------------------------------------

class _GroupHeader(QWidget):
    """Section header row shown above each file group.

    Displays a short group label on the left and a coloured ``selected/total``
    counter on the right.
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.BG_TERTIARY};
                border-radius: {BorderRadius.SM};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(Spacing.XS)

        lbl = QLabel(label.upper())
        lbl.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_XS};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
                letter-spacing: 0.5px;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(lbl, 1)

        self._counter = QLabel("")
        self._counter.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._counter.setStyleSheet(
            f"color:{Colors.TEXT_MUTED};font-size:{Fonts.SIZE_XS};"
            f"font-weight:{Fonts.WEIGHT_MEDIUM};background:transparent;border:none;"
        )
        layout.addWidget(self._counter)

    def update_counter(self, selected: int, total: int):
        self._counter.setText(f"{selected}/{total}")
        if selected == 0:
            color = Colors.RED_500
        elif selected == total:
            color = Colors.GREEN_500
        else:
            color = Colors.ORANGE_500
        self._counter.setStyleSheet(
            f"color:{color};font-size:{Fonts.SIZE_XS};"
            f"font-weight:{Fonts.WEIGHT_SEMIBOLD};background:transparent;border:none;"
        )


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class FileQualitySelectionWizardWidget(WizardStepWidget):
    """Wizard step 5 – per-file quality review and include/exclude selection."""

    def __init__(self):
        # Instance variables must be set before super().__init__ calls create_buttons()
        self._file_items: Dict[str, _FileListItem] = {}
        self._signal_cache: Dict[str, Tuple] = {}
        self._rms_cache: Dict[str, Optional[List[dict]]] = {}
        self._score_cache: Dict[str, Optional[float]] = {}
        self._current_file: Optional[str] = None
        self._rms_df: Optional[pd.DataFrame] = None
        # Grouping state
        self._grouped_mode: bool = True
        self._last_grouped_mode: Optional[bool] = None
        self._group_file_map: Dict[str, List[str]] = {}   # group_key → [file_paths]
        self._group_headers: Dict[str, _GroupHeader] = {}  # group_key → header widget
        self._custom_group_regex: Optional[str] = None
        self._all_mat_files: List[str] = []
        # Tracking-error metric (persisted in config)
        self._active_metric: str = config.get(Settings.TRACKING_ERROR_METRIC, METRIC_NRMSE)

        super().__init__(
            step_index=5,
            step_name="File Quality Selection",
            description=(
                "Review signal quality for each file. "
                "Uncheck files you want to exclude from further analysis."
            )
        )

        # Build the main split content area after super().__init__() has set up the card
        self._setup_main_content()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_main_content(self):
        """Insert a horizontal splitter into the content card."""
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.BORDER_MUTED};
                border-radius: 2px;
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.GRAY_300};
            }}
        """)
        splitter.setMinimumHeight(440)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 710])

        # Insert before button_container (which is the last item in content_layout)
        idx = self.content_layout.indexOf(self.button_container)
        self.content_layout.insertWidget(idx, splitter)
        self._splitter = splitter

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        # Header row: "FILES" label + grouping toggle
        hdr_row = QWidget()
        hdr_row.setStyleSheet("background:transparent;")
        hdr_layout = QHBoxLayout(hdr_row)
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(Spacing.SM)

        hdr = QLabel("FILES")
        hdr.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_XS};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
                letter-spacing: 0.6px;
                background: transparent;
                border: none;
            }}
        """)
        hdr_layout.addWidget(hdr, 1)

        self._toggle_group_btn = QPushButton("Group")
        self._toggle_group_btn.setCheckable(True)
        self._toggle_group_btn.setChecked(True)
        self._toggle_group_btn.setFixedHeight(20)
        self._toggle_group_btn.setStyleSheet(self._group_btn_style(True))
        self._toggle_group_btn.toggled.connect(self._on_toggle_grouping)
        hdr_layout.addWidget(self._toggle_group_btn)

        layout.addWidget(hdr_row)

        self._custom_grouping_btn = QPushButton("⚙ Custom Grouping")
        self._custom_grouping_btn.setFixedHeight(22)
        self._custom_grouping_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_SECONDARY};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: 2px {Spacing.SM}px;
                font-size: 11px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {Colors.BLUE_50};
                color: {Colors.BLUE_700};
                border-color: {Colors.BLUE_100};
            }}
        """)
        self._custom_grouping_btn.clicked.connect(self._open_custom_grouping_dialog)
        layout.addWidget(self._custom_grouping_btn)

        # Scrollable file list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_MUTED};
                border-radius: {BorderRadius.MD};
            }}
            QScrollBar:vertical {{
                background-color: {Colors.BG_SECONDARY};
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Colors.GRAY_300};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self._list_container = QWidget()
        self._list_container.setStyleSheet(
            f"background-color: {Colors.BG_SECONDARY};"
        )
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(
            Spacing.XS, Spacing.XS, Spacing.XS, Spacing.XS
        )
        self._list_layout.setSpacing(1)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, 1)

        # Select All / Deselect All
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(Spacing.SM)

        btn_all = QPushButton("Select All")
        btn_all.setStyleSheet(Styles.button_secondary())
        btn_all.setFixedHeight(28)
        btn_all.clicked.connect(self._select_all)

        btn_none = QPushButton("Deselect All")
        btn_none.setStyleSheet(Styles.button_secondary())
        btn_none.setFixedHeight(28)
        btn_none.clicked.connect(self._deselect_all)

        btn_layout.addWidget(btn_all)
        btn_layout.addWidget(btn_none)
        layout.addWidget(btn_row)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(Spacing.MD, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        # Matplotlib figure
        self._figure = Figure(figsize=(8, 3.5), facecolor=Colors.BG_PRIMARY)
        self._figure.subplots_adjust(left=0.08, right=0.97, top=0.93, bottom=0.15)
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setMinimumHeight(180)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._ax = self._figure.add_subplot(111)
        self._draw_placeholder()
        layout.addWidget(self._canvas, 1)

        # Warning strip (hidden unless signals are missing)
        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.ORANGE_700};
                font-size: {Fonts.SIZE_SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
                background-color: {Colors.ORANGE_50};
                border: 1px solid {Colors.ORANGE_500};
                border-radius: {BorderRadius.SM};
            }}
        """)
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        # Stats row — flat labels, no card borders
        _ts = (f"color:{Colors.TEXT_MUTED};font-size:{Fonts.SIZE_XS};"
               f"font-weight:{Fonts.WEIGHT_MEDIUM};letter-spacing:0.5px;"
               f"background:transparent;border:none;")
        _vs = (f"color:{Colors.TEXT_PRIMARY};font-size:{Fonts.SIZE_LG};"
               f"font-weight:{Fonts.WEIGHT_SEMIBOLD};background:transparent;border:none;")
        _qs = f"color:{Colors.TEXT_MUTED};font-size:{Fonts.SIZE_XS};background:transparent;border:none;"

        stats_row = QWidget()
        stats_row.setStyleSheet("background:transparent;")
        stats_layout = QHBoxLayout(stats_row)
        stats_layout.setContentsMargins(0, Spacing.XS, 0, 0)
        stats_layout.setSpacing(0)

        dev_col = QWidget()
        dev_col.setStyleSheet("background:transparent;")
        dev_cv = QVBoxLayout(dev_col)
        dev_cv.setContentsMargins(0, 0, 0, 0)
        dev_cv.setSpacing(2)

        # Deviation header row: label + metric combo + gear button
        dev_hdr_row = QWidget()
        dev_hdr_row.setStyleSheet("background:transparent;")
        dev_hdr_layout = QHBoxLayout(dev_hdr_row)
        dev_hdr_layout.setContentsMargins(0, 0, 0, 0)
        dev_hdr_layout.setSpacing(Spacing.XS)

        dev_hdr_layout.addWidget(QLabel("TRACKING DEVIATION", styleSheet=_ts))

        self._metric_combo = QComboBox()
        # Force Fusion style so the popup list respects Qt stylesheets on macOS
        # (native macOS rendering ignores QAbstractItemView stylesheet rules).
        fusion = QStyleFactory.create("Fusion")
        if fusion:
            self._metric_combo.setStyle(fusion)
        self._metric_combo.addItems(METRIC_NAMES)
        self._metric_combo.setCurrentText(self._active_metric)
        self._metric_combo.setFixedHeight(18)
        self._metric_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._metric_combo.view().setMinimumWidth(200)
        self._metric_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Colors.BG_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_MUTED};
                border-radius: {BorderRadius.SM};
                font-size: {Fonts.SIZE_XS};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                padding: 1px 4px;
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
        """)
        # Style the popup list view directly — macOS native style ignores
        # QAbstractItemView rules nested inside the parent QComboBox stylesheet.
        self._metric_combo.view().setStyleSheet(f"""
            QAbstractItemView {{
                background-color: {Colors.BG_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.BLUE_100};
                selection-color: {Colors.TEXT_PRIMARY};
                outline: none;
                font-size: {Fonts.SIZE_SM};
            }}
            QAbstractItemView::item {{
                color: {Colors.TEXT_PRIMARY};
                background-color: {Colors.BG_PRIMARY};
                padding: 4px 8px;
                min-height: 22px;
            }}
            QAbstractItemView::item:selected,
            QAbstractItemView::item:hover {{
                background-color: {Colors.BLUE_100};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        self._metric_combo.currentTextChanged.connect(self._on_metric_changed)
        dev_hdr_layout.addWidget(self._metric_combo)

        self._thresholds_btn = QToolButton()
        self._thresholds_btn.setText("⚙")
        self._thresholds_btn.setFixedSize(18, 18)
        self._thresholds_btn.setToolTip("Configure quality thresholds…")
        self._thresholds_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED};
                border: none;
                font-size: 11px;
                padding: 0px;
            }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._thresholds_btn.clicked.connect(self._on_open_thresholds_dialog)
        dev_hdr_layout.addWidget(self._thresholds_btn)
        dev_hdr_layout.addStretch()

        dev_cv.addWidget(dev_hdr_row)

        self._dev_value_lbl = QLabel("—")
        self._dev_value_lbl.setStyleSheet(_vs)
        self._dev_quality_lbl = QLabel("")
        self._dev_quality_lbl.setStyleSheet(_qs)
        dev_cv.addWidget(self._dev_value_lbl)
        dev_cv.addWidget(self._dev_quality_lbl)
        stats_layout.addWidget(dev_col)
        stats_layout.addSpacing(Spacing.LG)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color:{Colors.BORDER_MUTED};border:none;")
        stats_layout.addWidget(sep)
        stats_layout.addSpacing(Spacing.LG)

        rms_col = QWidget()
        rms_col.setStyleSheet("background:transparent;")
        rms_cv = QVBoxLayout(rms_col)
        rms_cv.setContentsMargins(0, 0, 0, 0)
        rms_cv.setSpacing(2)
        rms_cv.addWidget(QLabel("RMS NOISE QUALITY", styleSheet=_ts))
        self._rms_grids_container = QWidget()
        self._rms_grids_container.setStyleSheet("background:transparent;")
        self._rms_grids_vbox = QVBoxLayout(self._rms_grids_container)
        self._rms_grids_vbox.setContentsMargins(0, 3, 0, 0)
        self._rms_grids_vbox.setSpacing(2)
        placeholder = QLabel("—")
        placeholder.setStyleSheet(
            f"color:{Colors.TEXT_PRIMARY};font-size:{Fonts.SIZE_LG};"
            f"font-weight:{Fonts.WEIGHT_SEMIBOLD};background:transparent;border:none;"
        )
        self._rms_grids_vbox.addWidget(placeholder)
        rms_cv.addWidget(self._rms_grids_container)
        stats_layout.addWidget(rms_col)
        stats_layout.addStretch()

        layout.addWidget(stats_row)

        # Filename display
        self._filename_display = QLabel("")
        self._filename_display.setWordWrap(True)
        self._filename_display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._filename_display.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Fonts.SIZE_XS};
                font-style: italic;
            }}
        """)
        layout.addWidget(self._filename_display)

        return panel

    def _draw_placeholder(self, message="Select a file from the list."):
        self._ax.clear()
        self._ax.set_facecolor(Colors.BG_SECONDARY)
        self._ax.text(
            0.5, 0.5, message,
            transform=self._ax.transAxes,
            ha='center', va='center',
            color=Colors.GRAY_400, fontsize=10, style='italic'
        )
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        for sp in self._ax.spines.values():
            sp.set_edgecolor(Colors.BORDER_MUTED)
        self._canvas.draw_idle()

    # ------------------------------------------------------------------
    # WizardStepWidget interface
    # ------------------------------------------------------------------

    def create_buttons(self):
        self._btn_skip = QPushButton("Skip")
        self._btn_skip.setStyleSheet(Styles.button_secondary())
        self._btn_skip.clicked.connect(self._on_skip)
        self.buttons.append(self._btn_skip)

        self._btn_confirm = QPushButton("Confirm Selection")
        self._btn_confirm.setStyleSheet(Styles.button_primary())
        self._btn_confirm.clicked.connect(self._on_confirm)
        self.buttons.append(self._btn_confirm)

    def check(self):
        if config.get(Settings.WORKFOLDER_PATH) is None:
            self.warn("Workfolder path is not set. Please configure it in Settings.")
            self.setActionButtonsEnabled(False)
            return

        step4_done = (global_state.is_widget_completed("step4")
                      or global_state.is_widget_skipped("step4"))
        if not step4_done:
            self.additional_information_label.setText(
                "Complete or skip the RMS Quality Analysis step first."
            )
            self.setActionButtonsEnabled(False)
            return

        self.clear_status()
        self.setActionButtonsEnabled(True)
        self._populate_file_list()
        self._load_rms_csv()
        # Always refresh displayed file after CSV reload (also handles initial auto-select)
        if self._current_file and self._current_file in self._file_items:
            self._on_file_selected(self._current_file)
        elif self._file_items:
            self._on_file_selected(next(iter(self._file_items)))
        self._update_confirm_button()

    # ------------------------------------------------------------------
    # File list population
    # ------------------------------------------------------------------

    def _populate_file_list(self):
        """Read all .mat files from disk and (re)populate the list."""
        cleaned_path = global_state.get_line_noise_cleaned_path()
        try:
            all_files = sorted([
                os.path.join(cleaned_path, f)
                for f in os.listdir(cleaned_path)
                if f.endswith(".mat") and not f.startswith(".")
            ])
        except OSError as e:
            logger.warning(f"Could not list line_noise_cleaned folder: {e}")
            return

        if not all_files:
            self.additional_information_label.setText(
                "No .mat files found in line_noise_cleaned folder."
            )
            return

        self._all_mat_files = all_files

        # Rebuild if files changed OR grouping mode changed
        mode_changed = self._grouped_mode != self._last_grouped_mode
        if set(self._file_items.keys()) == set(all_files) and not mode_changed:
            return

        self._last_grouped_mode = self._grouped_mode

        # Clear existing items (preserve the trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._file_items.clear()
        self._group_headers.clear()
        self._group_file_map.clear()
        self._current_file = None

        saved_selection = self._load_saved_selection()

        if self._grouped_mode:
            self._populate_grouped(all_files, saved_selection)
        else:
            self._populate_flat(all_files, saved_selection)

        # Auto-select happens in check() after _load_rms_csv() so RMS data is available

    def _populate_flat(self, all_files: List[str], saved_selection):
        for fp in all_files:
            item = _FileListItem(fp, self._list_container)
            if saved_selection is not None:
                item.set_checked(fp in saved_selection)
            item.clicked.connect(self._on_file_selected)
            item.selection_changed.connect(self._on_selection_changed)
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)
            self._file_items[fp] = item

    def _populate_grouped(self, all_files: List[str], saved_selection):
        # Build groups preserving file order
        groups: Dict[str, List[str]] = {}
        for fp in all_files:
            key = get_group_key(os.path.basename(fp), self._custom_group_regex)
            groups.setdefault(key, []).append(fp)
        self._group_file_map = groups

        labels = shorten_group_labels(list(groups.keys()))

        for key, files in groups.items():
            header = _GroupHeader(labels.get(key, key), self._list_container)
            self._list_layout.insertWidget(self._list_layout.count() - 1, header)
            self._group_headers[key] = header

            for fp in files:
                item = _FileListItem(fp, self._list_container)
                if saved_selection is not None:
                    item.set_checked(fp in saved_selection)
                item.clicked.connect(self._on_file_selected)
                item.selection_changed.connect(self._on_selection_changed)
                self._list_layout.insertWidget(self._list_layout.count() - 1, item)
                self._file_items[fp] = item

            # Initialize counters
            total = len(files)
            selected = sum(1 for fp in files if self._file_items[fp].is_checked())
            header.update_counter(selected, total)

    @staticmethod
    def _group_btn_style(active: bool) -> str:
        if active:
            return (f"QPushButton {{background-color:{Colors.BLUE_500};color:white;"
                    f"border:none;border-radius:{BorderRadius.SM};"
                    f"font-size:{Fonts.SIZE_XS};font-weight:{Fonts.WEIGHT_MEDIUM};"
                    f"padding:2px 8px;}}"
                    f"QPushButton:hover {{background-color:{Colors.BLUE_600};}}")
        return (f"QPushButton {{background-color:{Colors.BG_TERTIARY};"
                f"color:{Colors.TEXT_MUTED};"
                f"border:1px solid {Colors.BORDER_MUTED};border-radius:{BorderRadius.SM};"
                f"font-size:{Fonts.SIZE_XS};font-weight:{Fonts.WEIGHT_MEDIUM};"
                f"padding:2px 8px;}}"
                f"QPushButton:hover {{background-color:{Colors.BG_SECONDARY};}}")

    def _on_toggle_grouping(self, checked: bool):
        self._grouped_mode = checked
        self._toggle_group_btn.setStyleSheet(self._group_btn_style(checked))
        self._populate_file_list()
        # Re-select current or first file
        if self._current_file and self._current_file in self._file_items:
            self._on_file_selected(self._current_file)
        elif self._file_items:
            self._on_file_selected(next(iter(self._file_items)))

    def _open_custom_grouping_dialog(self):
        dialog = _CustomGroupingDialog(
            self._all_mat_files,
            current_regex=self._custom_group_regex,
            parent=self,
        )
        if dialog.exec_() == QDialog.Accepted:
            regex = dialog.get_regex()
            self._custom_group_regex = regex if regex else None
            if self._custom_group_regex:
                label = (f"⚙ Custom: {self._custom_group_regex[:24]}…"
                         if len(self._custom_group_regex) > 24
                         else f"⚙ Custom: {self._custom_group_regex}")
                self._custom_grouping_btn.setText(label)
                self._custom_grouping_btn.setStyleSheet(
                    self._custom_grouping_btn.styleSheet()
                    .replace(Colors.BG_SECONDARY, Colors.BLUE_50)
                    .replace(Colors.TEXT_SECONDARY, Colors.BLUE_700)
                )
            else:
                self._custom_grouping_btn.setText("⚙ Custom Grouping")
            if self._all_mat_files:
                # Force full rebuild by resetting last_grouped_mode
                self._last_grouped_mode = None
                self._populate_file_list()
                if self._current_file and self._current_file in self._file_items:
                    self._on_file_selected(self._current_file)
                elif self._file_items:
                    self._on_file_selected(next(iter(self._file_items)))

    # ------------------------------------------------------------------
    # RMS data
    # ------------------------------------------------------------------

    def _load_rms_csv(self):
        self._rms_df = None
        self._rms_cache.clear()  # Invalidate cache so stale Nones don't persist
        try:
            csv_path = os.path.join(
                global_state.get_analysis_path(), "rms_analysis_report.csv"
            )
            if os.path.exists(csv_path):
                self._rms_df = pd.read_csv(csv_path)
                logger.debug(
                    "Loaded RMS report CSV (%d rows, files: %s)",
                    len(self._rms_df),
                    self._rms_df["file_name"].unique().tolist() if "file_name" in self._rms_df.columns else "?",
                )
            else:
                logger.debug("RMS report CSV not found at %s", csv_path)
        except Exception as e:
            logger.warning(f"Could not load RMS CSV: {e}")

    def _get_rms_for_file(self, file_path: str) -> Optional[List[dict]]:
        """Return per-grid RMS data, or None if unavailable.

        Each dict: grid_key, label, mean_rms, std_rms, quality_label, color.
        """
        if file_path in self._rms_cache:
            return self._rms_cache[file_path]
        if self._rms_df is None:
            return None
        filename = os.path.basename(file_path)
        rows = self._rms_df[self._rms_df["file_name"] == filename]
        if rows.empty:
            stem = os.path.splitext(filename)[0]
            rows = self._rms_df[
                self._rms_df["file_name"].str.startswith(stem + ".")
                | (self._rms_df["file_name"] == stem)
            ]
        if rows.empty:
            logger.debug("RMS CSV: no rows matched for %s", filename)
            self._rms_cache[file_path] = None
            return None

        grids = []
        for grid_key, gdf in rows.groupby("grid_key", sort=False):
            mean_val = float(gdf["rms_uv"].mean())
            std_val = float(gdf["rms_uv"].std(ddof=1)) if len(gdf) > 1 else 0.0
            qlabel, qcolor = _rms_to_label_color(mean_val)

            # Build human-readable label from new columns if present, else use grid_key
            if "rows" in gdf.columns and "cols" in gdf.columns and "ied_mm" in gdf.columns:
                r = gdf["rows"].iloc[0]
                c = gdf["cols"].iloc[0]
                ied = gdf["ied_mm"].iloc[0]
                muscle = gdf["muscle"].iloc[0] if "muscle" in gdf.columns else None
                muscle_str = f" {muscle}" if muscle and str(muscle) not in ("", "nan") else ""
                label = f"{r}×{c} ({ied} mm){muscle_str}"
            else:
                label = str(grid_key)

            grids.append({
                "grid_key": grid_key,
                "label": label,
                "mean_rms": mean_val,
                "std_rms": std_val,
                "quality_label": qlabel,
                "color": qcolor,
            })

        self._rms_cache[file_path] = grids if grids else None
        return self._rms_cache[file_path]

    # ------------------------------------------------------------------
    # Signal loading
    # ------------------------------------------------------------------

    def _load_signals(self, file_path: str) -> Tuple:
        """Return (required, performed, n_grids, warnings, fsamp).

        required / performed are np.ndarray or None.
        """
        if file_path in self._signal_cache:
            return self._signal_cache[file_path]

        try:
            from hdsemg_shared.fileio.file_io import EMGFile
            emg = EMGFile.load(file_path)
        except Exception as e:
            result = (None, None, 0, [f"Failed to load file: {str(e)[:100]}"], 2048.0)
            self._signal_cache[file_path] = result
            return result

        if not hasattr(emg, 'grids') or not emg.grids:
            result = (None, None, 0, ["No grid information found in file."], 2048.0)
            self._signal_cache[file_path] = result
            return result

        n_grids = len(emg.grids)
        grid = emg.grids[0]
        warnings = []

        if n_grids > 1:
            warnings.append(f"Multi-grid file — showing grid 1 of {n_grids}.")

        fsamp = float(
            getattr(emg, 'fsamp', None)
            or getattr(emg, 'FSAMP', None)
            or 2048.0
        )

        required = None
        performed = None

        # requested_path_idx / performed_path_idx are direct column indices
        # into emgfile.data (same convention as crop_roi.py).
        req_idx = getattr(grid, 'requested_path_idx', None)
        if req_idx is not None:
            try:
                required = np.array(emg.data[:, req_idx], dtype=float)
            except Exception as e:
                warnings.append(f"Could not read required path: {e}")
        else:
            warnings.append("No required path signal defined.")

        perf_idx = getattr(grid, 'performed_path_idx', None)
        if perf_idx is not None:
            try:
                performed = np.array(emg.data[:, perf_idx], dtype=float)
            except Exception as e:
                warnings.append(f"Could not read performed path: {e}")
        else:
            warnings.append("No performed path signal defined.")

        result = (required, performed, n_grids, warnings, fsamp)
        self._signal_cache[file_path] = result
        return result

    # ------------------------------------------------------------------
    # File selection handler
    # ------------------------------------------------------------------

    def _on_file_selected(self, file_path: str):
        # Update highlight
        if self._current_file and self._current_file in self._file_items:
            self._file_items[self._current_file].set_selected(False)
        self._current_file = file_path
        if file_path in self._file_items:
            self._file_items[file_path].set_selected(True)

        # Full filename below the cards (scrollable via text selection)
        self._filename_display.setText(os.path.basename(file_path))
        self._filename_display.setToolTip(file_path)

        # Load signals
        required, performed, _n, warnings, fsamp = self._load_signals(file_path)

        # Warning strip
        if warnings:
            self._warning_label.setText("  •  ".join(warnings))
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

        # Plot
        self._update_plot(required, performed, fsamp)

        # Deviation score
        score: Optional[float] = None
        if required is not None and performed is not None:
            score = compute_metric(self._active_metric, required, performed)
        self._score_cache[file_path] = score

        thresholds = self._get_active_thresholds()

        # RMS — per-grid data
        rms_grids = self._get_rms_for_file(file_path)
        rms_mean = float(np.mean([g["mean_rms"] for g in rms_grids])) if rms_grids else None

        # Update status dot colour in the list (prefer deviation score if available)
        if score is not None:
            dot_color = _score_to_label_color(score, thresholds)[1]
        elif rms_mean is not None and not np.isnan(rms_mean):
            dot_color = _rms_to_label_color(rms_mean)[1]
        else:
            dot_color = Colors.GRAY_300
        if file_path in self._file_items:
            self._file_items[file_path].set_quality_color(dot_color)

        # Deviation stat
        if score is not None:
            slabel, scolor = _score_to_label_color(score, thresholds)
            self._update_stat(self._dev_value_lbl, self._dev_quality_lbl,
                              f"{score:.1f} %", slabel, scolor)
        else:
            self._reset_stat(self._dev_value_lbl, self._dev_quality_lbl)

        # RMS stat — per-grid breakdown
        self._refresh_rms_display(rms_grids)

    # ------------------------------------------------------------------
    # Metric / threshold helpers and slots
    # ------------------------------------------------------------------

    def _get_active_thresholds(self) -> Dict[str, float]:
        """Return the tier thresholds for the currently active metric."""
        all_thresholds = config.get(Settings.TRACKING_ERROR_THRESHOLDS, {})
        if isinstance(all_thresholds, dict) and self._active_metric in all_thresholds:
            stored = all_thresholds[self._active_metric]
            defaults = DEFAULT_THRESHOLDS.get(self._active_metric, {})
            return {tier: stored.get(tier, defaults.get(tier, 60.0)) for tier in TIER_ORDER}
        return dict(DEFAULT_THRESHOLDS.get(self._active_metric, {}))

    def _on_metric_changed(self, metric_name: str):
        """Switch active metric, persist to config, invalidate score cache, repaint."""
        self._active_metric = metric_name
        config.set(Settings.TRACKING_ERROR_METRIC, metric_name)
        # Scores depend on the metric — invalidate so they are recomputed on next view
        self._score_cache.clear()
        # Repaint all quality dots that are already loaded by re-visiting current file
        if self._current_file:
            self._on_file_selected(self._current_file)

    def _on_open_thresholds_dialog(self):
        """Open the thresholds dialog for the active metric and repaint on close."""
        dlg = TrackingErrorThresholdsDialog(self._active_metric, parent=self)
        dlg.exec_()
        # Regardless of accept/reject, thresholds may have changed (reset on "Reset")
        if self._current_file:
            self._on_file_selected(self._current_file)

    # ------------------------------------------------------------------
    # Stat label helpers
    # ------------------------------------------------------------------

    def _update_stat(self, value_lbl: QLabel, quality_lbl: QLabel,
                     value_text: str, quality_label: str, color: str):
        value_lbl.setText(value_text)
        value_lbl.setStyleSheet(
            f"color:{color};font-size:{Fonts.SIZE_LG};"
            f"font-weight:{Fonts.WEIGHT_SEMIBOLD};background:transparent;border:none;"
        )
        quality_lbl.setText(quality_label)
        quality_lbl.setStyleSheet(
            f"color:{color};font-size:{Fonts.SIZE_XS};background:transparent;border:none;"
        )

    def _reset_stat(self, value_lbl: QLabel, quality_lbl: QLabel):
        value_lbl.setText("—")
        value_lbl.setStyleSheet(
            f"color:{Colors.TEXT_PRIMARY};font-size:{Fonts.SIZE_LG};"
            f"font-weight:{Fonts.WEIGHT_SEMIBOLD};background:transparent;border:none;"
        )
        quality_lbl.setText("")
        quality_lbl.setStyleSheet(
            f"color:{Colors.TEXT_MUTED};font-size:{Fonts.SIZE_XS};background:transparent;border:none;"
        )

    def _refresh_rms_display(self, grids: Optional[List[dict]]):
        """Rebuild the per-grid RMS row list — one compact line per grid."""
        layout = self._rms_grids_vbox

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not grids:
            placeholder = QLabel("—")
            placeholder.setStyleSheet(
                f"color:{Colors.TEXT_PRIMARY};font-size:{Fonts.SIZE_LG};"
                f"font-weight:{Fonts.WEIGHT_SEMIBOLD};background:transparent;border:none;"
            )
            layout.addWidget(placeholder)
            return

        for g in grids:
            std_str = f"±{g['std_rms']:.1f} " if g["std_rms"] > 0 else ""
            c = g["color"]
            lbl = g["label"]
            mean = g["mean_rms"]
            qlabel = g["quality_label"]
            row = QLabel(
                f"<span style='color:{c}'>●</span>"
                f"&nbsp;<span style='color:{Colors.TEXT_MUTED}'>{lbl}</span>"
                f"&nbsp;&nbsp;<span style='color:{c};font-weight:600'>"
                f"{mean:.1f}&nbsp;{std_str}µV</span>"
                f"&nbsp;<span style='color:{c}'>· {qlabel}</span>"
            )
            row.setTextFormat(Qt.RichText)
            row.setStyleSheet(
                f"font-size:{Fonts.SIZE_XS};background:transparent;border:none;"
            )
            layout.addWidget(row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------

    def _update_plot(
        self,
        required: Optional[np.ndarray],
        performed: Optional[np.ndarray],
        fsamp: float,
    ):
        self._ax.clear()
        self._ax.set_facecolor(Colors.BG_SECONDARY)

        if required is None and performed is None:
            self._draw_placeholder("No path signals available for this file.")
            return

        def _norm(sig: np.ndarray) -> np.ndarray:
            rng = sig.max() - sig.min()
            return (sig - sig.min()) / rng if rng > 1e-10 else sig - sig.min()

        if required is not None:
            t = np.arange(len(required)) / fsamp
            self._ax.plot(
                t, _norm(required),
                color=Colors.BLUE_600, linewidth=1.5, linestyle='--',
                alpha=0.9, label='Required Path', zorder=3,
            )

        if performed is not None:
            t = np.arange(len(performed)) / fsamp
            self._ax.plot(
                t, _norm(performed),
                color=Colors.ORANGE_500, linewidth=1.5, linestyle='-',
                alpha=0.9, label='Performed Path', zorder=2,
            )

        self._ax.set_xlabel("Time (s)", fontsize=9, color=Colors.TEXT_SECONDARY)
        self._ax.set_ylabel("Norm. Amplitude", fontsize=9, color=Colors.TEXT_SECONDARY)
        self._ax.legend(loc='upper right', fontsize=8, framealpha=0.85)
        self._ax.grid(True, alpha=0.22, linestyle='--', color=Colors.GRAY_300)
        self._ax.tick_params(labelsize=8, colors=Colors.TEXT_SECONDARY)
        for sp in self._ax.spines.values():
            sp.set_edgecolor(Colors.BORDER_MUTED)

        self._figure.tight_layout(pad=0.8)
        self._canvas.draw_idle()

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _on_selection_changed(self, file_path: str, _is_selected: bool):
        self._update_confirm_button()
        if self._grouped_mode:
            key = get_group_key(os.path.basename(file_path), self._custom_group_regex)
            if key in self._group_headers and key in self._group_file_map:
                files = self._group_file_map[key]
                total = len(files)
                selected = sum(
                    1 for fp in files
                    if fp in self._file_items and self._file_items[fp].is_checked()
                )
                self._group_headers[key].update_counter(selected, total)

    def _update_confirm_button(self):
        total = len(self._file_items)
        selected = sum(1 for it in self._file_items.values() if it.is_checked())
        self._btn_confirm.setText(
            f"Confirm Selection ({selected}/{total} files)"
        )

    def _select_all(self):
        for item in self._file_items.values():
            item.set_checked(True)
        self._update_confirm_button()

    def _deselect_all(self):
        for item in self._file_items.values():
            item.set_checked(False)
        self._update_confirm_button()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_saved_selection(self) -> Optional[set]:
        try:
            sel_path = os.path.join(
                global_state.get_analysis_path(), "file_quality_selection.json"
            )
            if os.path.exists(sel_path):
                with open(sel_path, 'r') as f:
                    data = json.load(f)
                return set(data.get("selected", []))
        except Exception as e:
            logger.warning(f"Could not load saved selection: {e}")
        return None

    def _save_selection(self, selected: list, all_files: list):
        try:
            sel_data = {
                "selected": selected,
                "excluded": [fp for fp in all_files if fp not in selected],
            }
            sel_path = os.path.join(
                global_state.get_analysis_path(), "file_quality_selection.json"
            )
            with open(sel_path, 'w') as f:
                json.dump(sel_data, f, indent=2)
            logger.info(
                f"Saved file selection: {len(selected)}/{len(all_files)} files selected."
            )
        except Exception as e:
            logger.warning(f"Could not save file selection: {e}")

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def _on_skip(self):
        logger.debug("Skipping File Quality Selection step.")
        super().skip_step("File quality review skipped — all files included.")

    def _on_confirm(self):
        selected = [fp for fp, it in self._file_items.items() if it.is_checked()]
        all_files = list(self._file_items.keys())

        if not selected:
            self.warn("Please select at least one file to proceed.")
            return

        global_state.line_noise_cleaned_files = selected
        self._save_selection(selected, all_files)

        excluded = len(all_files) - len(selected)
        msg = f"Selection confirmed: {len(selected)}/{len(all_files)} files included."
        if excluded:
            msg += f" ({excluded} excluded.)"
        self.success(msg)
        self.complete_step()
