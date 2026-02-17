"""
File Quality Selection Wizard Widget

Pipeline step for reviewing per-file signal quality and selecting
which files to include in further analysis.
"""

import json
import os
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import BorderRadius, Colors, Fonts, Spacing, Styles
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_label_color(score: Optional[float]) -> Tuple[str, str]:
    """Map NRMSE score (0–100 %) to (label, hex_color)."""
    if score is None:
        return "N/A", Colors.GRAY_400
    if score >= 90:
        return "Excellent", Colors.GREEN_500
    if score >= 80:
        return "Good", Colors.BLUE_500
    if score >= 70:
        return "OK", Colors.YELLOW_500
    if score >= 60:
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


def _compute_nrmse_score(required: np.ndarray, performed: np.ndarray) -> Optional[float]:
    """Compute 0–100 % tracking quality score (100 = perfect match).

    Uses Normalized RMSE: score = max(0, (1 - RMSE / range(required)) * 100).
    """
    min_len = min(len(required), len(performed))
    req = required[:min_len].astype(float)
    perf = performed[:min_len].astype(float)
    req_range = req.max() - req.min()
    if req_range < 1e-10:
        return None
    rmse = np.sqrt(np.mean((req - perf) ** 2))
    return max(0.0, (1.0 - rmse / req_range) * 100.0)


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
        filename = os.path.basename(file_path)
        self._name_label = QLabel(filename)
        self._name_label.setToolTip(file_path)
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
        bg = Colors.BLUE_50 if active else "transparent"
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-radius: {BorderRadius.SM};
            }}
            QWidget:hover {{
                background-color: {"#dbeafe" if active else Colors.BG_SECONDARY};
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
# _MetadataCard
# ---------------------------------------------------------------------------

class _MetadataCard(QFrame):
    """Small info card: title + coloured dot + value + quality label."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_MUTED};
                border-radius: {BorderRadius.MD};
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(Spacing.XS)

        # Section title
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_XS};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                letter-spacing: 0.4px;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(title_lbl)

        # Value row
        value_row = QWidget()
        value_row.setStyleSheet("background: transparent; border: none;")
        value_layout = QHBoxLayout(value_row)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(Spacing.XS)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {Colors.GRAY_300}; font-size: 16px; background: transparent; border: none;"
        )
        value_layout.addWidget(self._dot)

        self._value = QLabel("—")
        self._value.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
                background: transparent;
                border: none;
            }}
        """)
        value_layout.addWidget(self._value)
        value_layout.addStretch()
        layout.addWidget(value_row)

        # Quality word
        self._quality = QLabel("")
        self._quality.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Fonts.SIZE_XS};
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(self._quality)

    def update_card(self, value_text: str, quality_label: str, color: str):
        self._dot.setStyleSheet(
            f"color: {color}; font-size: 16px; background: transparent; border: none;"
        )
        self._value.setText(value_text)
        self._quality.setText(quality_label)
        self._quality.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: {Fonts.SIZE_XS};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                background: transparent;
                border: none;
            }}
        """)

    def reset_card(self):
        self._dot.setStyleSheet(
            f"color: {Colors.GRAY_300}; font-size: 16px; background: transparent; border: none;"
        )
        self._value.setText("—")
        self._quality.setText("")
        self._quality.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Fonts.SIZE_XS};
                background: transparent;
                border: none;
            }}
        """)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class FileQualitySelectionWizardWidget(WizardStepWidget):
    """Wizard step 5 – per-file quality review and include/exclude selection."""

    def __init__(self):
        # Instance variables must be set before super().__init__ calls create_buttons()
        self._file_items: Dict[str, _FileListItem] = {}
        self._signal_cache: Dict[str, Tuple] = {}
        self._rms_cache: Dict[str, Optional[float]] = {}
        self._score_cache: Dict[str, Optional[float]] = {}
        self._current_file: Optional[str] = None
        self._rms_df: Optional[pd.DataFrame] = None

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

        # Header
        hdr = QLabel("FILES")
        hdr.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_XS};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
                letter-spacing: 0.6px;
            }}
        """)
        layout.addWidget(hdr)

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

        # Metadata cards row
        meta_row = QWidget()
        meta_layout = QHBoxLayout(meta_row)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(Spacing.MD)
        self._deviation_card = _MetadataCard("Tracking Deviation (NRMSE)")
        self._rms_card = _MetadataCard("RMS Noise Quality")
        meta_layout.addWidget(self._deviation_card)
        meta_layout.addWidget(self._rms_card)
        layout.addWidget(meta_row)

        # Filename display
        self._filename_display = QLabel("Select a file from the list to inspect.")
        self._filename_display.setWordWrap(True)
        self._filename_display.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self._filename_display.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
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

        if not global_state.line_noise_cleaned_files:
            self.additional_information_label.setText(
                "Complete the RMS Quality Analysis step first."
            )
            self.setActionButtonsEnabled(False)
            return

        self.clear_status()
        self.setActionButtonsEnabled(True)
        self._populate_file_list()
        self._load_rms_csv()
        self._update_confirm_button()

    # ------------------------------------------------------------------
    # File list population
    # ------------------------------------------------------------------

    def _populate_file_list(self):
        """Read all .mat files from disk and populate the list."""
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

        # Skip repopulation if files haven't changed
        if set(self._file_items.keys()) == set(all_files):
            return

        # Remove existing items (preserve the trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._file_items.clear()

        # Load previously saved selection
        saved_selection = self._load_saved_selection()

        for fp in all_files:
            list_item = _FileListItem(fp, self._list_container)
            if saved_selection is not None:
                list_item.set_checked(fp in saved_selection)
            list_item.clicked.connect(self._on_file_selected)
            list_item.selection_changed.connect(self._on_selection_changed)
            # Insert before the trailing stretch
            self._list_layout.insertWidget(self._list_layout.count() - 1, list_item)
            self._file_items[fp] = list_item

        # Automatically show first file
        if all_files:
            self._on_file_selected(all_files[0])

    # ------------------------------------------------------------------
    # RMS data
    # ------------------------------------------------------------------

    def _load_rms_csv(self):
        self._rms_df = None
        try:
            csv_path = os.path.join(
                global_state.get_analysis_path(), "rms_analysis_report.csv"
            )
            if os.path.exists(csv_path):
                self._rms_df = pd.read_csv(csv_path)
                logger.debug("Loaded RMS report CSV.")
        except Exception as e:
            logger.warning(f"Could not load RMS CSV: {e}")

    def _get_rms_for_file(self, file_path: str) -> Optional[float]:
        if file_path in self._rms_cache:
            return self._rms_cache[file_path]
        if self._rms_df is None:
            self._rms_cache[file_path] = None
            return None
        filename = os.path.basename(file_path)
        rows = self._rms_df[self._rms_df["file_name"] == filename]
        if rows.empty:
            self._rms_cache[file_path] = None
            return None
        val = float(rows["rms_uv"].mean())
        self._rms_cache[file_path] = val
        return val

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

        ref_indices = getattr(grid, 'ref_indices', None) or []

        req_idx = getattr(grid, 'requested_path_idx', None)
        if req_idx is not None and ref_indices and req_idx < len(ref_indices):
            try:
                col = ref_indices[req_idx]
                required = np.array(emg.data[:, col], dtype=float)
            except Exception as e:
                warnings.append(f"Could not read required path: {e}")
        else:
            warnings.append("No required path signal defined.")

        perf_idx = getattr(grid, 'performed_path_idx', None)
        if perf_idx is not None and ref_indices and perf_idx < len(ref_indices):
            try:
                col = ref_indices[perf_idx]
                performed = np.array(emg.data[:, col], dtype=float)
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
            score = _compute_nrmse_score(required, performed)
        self._score_cache[file_path] = score

        # RMS
        rms = self._get_rms_for_file(file_path)

        # Update status dot colour in the list (prefer deviation score if available)
        if score is not None:
            dot_color = _score_to_label_color(score)[1]
        elif rms is not None and not np.isnan(rms):
            dot_color = _rms_to_label_color(rms)[1]
        else:
            dot_color = Colors.GRAY_300
        if file_path in self._file_items:
            self._file_items[file_path].set_quality_color(dot_color)

        # Deviation card
        if score is not None:
            slabel, scolor = _score_to_label_color(score)
            self._deviation_card.update_card(f"{score:.1f} %", slabel, scolor)
        else:
            self._deviation_card.reset_card()

        # RMS card
        if rms is not None and not np.isnan(rms):
            rlabel, rcolor = _rms_to_label_color(rms)
            self._rms_card.update_card(f"{rms:.1f} µV", rlabel, rcolor)
        else:
            self._rms_card.reset_card()

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

    def _on_selection_changed(self, _file_path: str, _is_selected: bool):
        self._update_confirm_button()

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
