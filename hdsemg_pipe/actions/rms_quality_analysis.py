"""
RMS Quality Analysis Dialog

Interactive dialog for analyzing RMS noise quality across multiple EMG files.
Allows users to select a time region from the performed path signal and
calculates RMS noise statistics for all channels.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np
import json
from datetime import datetime

from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar
)
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
import matplotlib.pyplot as plt

from hdsemg_shared.fileio.file_io import EMGFile, Grid
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, BorderRadius, Fonts, Styles
from hdsemg_pipe.state.global_state import global_state


# Quality thresholds in microvolts (matching existing RMS plot code)
QUALITY_THRESHOLDS = {
    'excellent': 5,
    'good': 10,
    'ok': 15,
    'troubled': 20,
}

QUALITY_COLORS = {
    'excellent': '#22c55e',  # green
    'good': '#93c5fd',       # lightblue
    'ok': '#f97316',         # orange
    'troubled': '#d946ef',   # magenta
    'bad': '#ef4444',        # red
}

QUALITY_LABELS = {
    'excellent': '≤5 µV: excellent',
    'good': '5–10 µV: good',
    'ok': '10–15 µV: ok',
    'troubled': '15–20 µV: troubled',
    'bad': '>20 µV: bad',
}


@dataclass
class GridData:
    """Helper to pair an EMGFile with one of its Grids."""
    emgfile: EMGFile
    grid: Grid
    file_path: str


@dataclass
class ChannelRMSResult:
    """RMS result for a single channel."""
    file_name: str
    grid_key: str
    channel_idx: int
    rms_uv: float
    quality: str


@dataclass
class FileRMSResult:
    """Aggregated RMS results for a single file."""
    file_name: str
    grid_key: str
    mean_rms: float
    std_rms: float
    min_rms: float
    max_rms: float
    channel_results: List[ChannelRMSResult] = field(default_factory=list)
    quality_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def quality(self) -> str:
        """Overall quality based on mean RMS."""
        return classify_quality(self.mean_rms)


@dataclass
class AnalysisResults:
    """Complete analysis results across all files."""
    file_results: List[FileRMSResult]
    grand_mean: float
    grand_std: float
    overall_min: float
    overall_max: float
    total_channels: int
    quality_counts: Dict[str, int]
    region_start_s: float
    region_end_s: float
    sampling_frequency: float


def classify_quality(rms_uv: float) -> str:
    """Classify RMS value into quality category."""
    if rms_uv <= QUALITY_THRESHOLDS['excellent']:
        return 'excellent'
    elif rms_uv <= QUALITY_THRESHOLDS['good']:
        return 'good'
    elif rms_uv <= QUALITY_THRESHOLDS['ok']:
        return 'ok'
    elif rms_uv <= QUALITY_THRESHOLDS['troubled']:
        return 'troubled'
    else:
        return 'bad'


def calculate_rms(signal: np.ndarray) -> float:
    """Calculate Root Mean Square of a signal."""
    return np.sqrt(np.mean(signal ** 2))


class RMSQualityDialog(QtWidgets.QDialog):
    """Dialog for interactive RMS quality analysis."""

    def __init__(self, file_paths: List[str], parent=None):
        super().__init__(parent)
        logger.info("Initializing RMS Quality Analysis Dialog for %d files", len(file_paths))

        self.file_paths = file_paths
        self.original_file_paths = self._get_original_file_paths()
        self.grid_items: List[GridData] = []
        self.performed_path_map: Dict[str, np.ndarray] = {}
        self.analysis_results: Optional[AnalysisResults] = None

        # Selection state
        self.selected_region: Optional[Tuple[float, float]] = None
        self.span_selector = None
        self.threshold_lines = []
        self.first_click_pos = None

        # Display options
        self.use_original_files = False
        self.show_filenames = True

        self.load_files()
        self.init_ui()

    def _get_original_file_paths(self) -> List[str]:
        """Get corresponding original file paths."""
        try:
            original_path = global_state.get_original_files_path()
            if os.path.exists(original_path):
                # Get all .mat files from original_files folder
                return [os.path.join(original_path, f) for f in os.listdir(original_path)
                        if f.endswith('.mat')]
        except Exception as e:
            logger.warning("Could not get original files path: %s", e)
        return []

    def load_files(self):
        """Load each file via EMGFile and collect its Grids."""
        # Clear existing data
        self.grid_items.clear()
        self.performed_path_map.clear()

        # Select which file paths to use
        paths_to_load = self.original_file_paths if self.use_original_files else self.file_paths

        for fp in paths_to_load:
            try:
                logger.info("Loading file: %s", fp)
                emg = EMGFile.load(fp)
                for grid in emg.grids:
                    self.grid_items.append(GridData(emgfile=emg, grid=grid, file_path=fp))
                logger.debug("→ %d grids from %s", len(emg.grids), Path(fp).name)
            except Exception as e:
                logger.error("Failed to load %s: %s", fp, e, exc_info=True)
                QtWidgets.QMessageBox.warning(self, "Loading Error", f"Failed to load {fp}:\n{e}")

        logger.info("Total grids loaded: %d", len(self.grid_items))
        self._build_performed_path_map()

    def _build_performed_path_map(self):
        """Extract performed path signals from all grids."""
        for gd in self.grid_items:
            uid = gd.grid.grid_uid
            emg = gd.emgfile
            grid = gd.grid

            # Try to get performed path signal
            if (grid.performed_path_idx is not None
                and grid.ref_indices
                and grid.performed_path_idx < len(grid.ref_indices)):
                ref_col_idx = grid.ref_indices[grid.performed_path_idx]
                signal = emg.data[:, ref_col_idx]
                logger.debug("Using performed_path_idx for %s", gd.emgfile.file_name)
            elif grid.ref_indices:
                # Fallback to first reference signal
                signal = emg.data[:, grid.ref_indices[0]]
                logger.debug("No performed_path_idx, using first ref for %s", gd.emgfile.file_name)
            else:
                # No reference signals - skip
                logger.warning("No reference signals in %s, grid %s", gd.emgfile.file_name, grid.grid_key)
                continue

            self.performed_path_map[uid] = signal

    def init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("RMS Quality Analysis")
        self.resize(1600, 900)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_SECONDARY};
            }}
        """)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        main_layout.setSpacing(Spacing.LG)

        # Header
        header = QtWidgets.QLabel("RMS Quality Analysis")
        header.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_XXL};
                font-weight: {Fonts.WEIGHT_BOLD};
            }}
        """)

        instruction = QtWidgets.QLabel(
            "🖱️ Drag to select a quiet region for RMS analysis  •  "
            "📊 Results will show signal quality across all files"
        )
        instruction.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
            }}
        """)
        instruction.setWordWrap(True)

        main_layout.addWidget(header)
        main_layout.addWidget(instruction)

        # Options panel
        self._create_options_panel(main_layout)

        # Main content: plot on left, results on right
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(Spacing.LG)

        # Left: Selection plot
        self._create_selection_panel(content_layout)

        # Right: Results panel
        self._create_results_panel(content_layout)

        main_layout.addLayout(content_layout)

        # Bottom: Action buttons
        self._create_action_buttons(main_layout)

        # Initialize plot
        self.update_selection_plot()

    def _create_options_panel(self, parent_layout):
        """Create options panel with checkboxes for file source and display options."""
        options_frame = QtWidgets.QFrame()
        options_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.SM}px;
            }}
        """)

        options_layout = QtWidgets.QHBoxLayout(options_frame)
        options_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        options_layout.setSpacing(Spacing.XL)

        # File source selection
        source_label = QtWidgets.QLabel("Data Source:")
        source_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
        """)
        options_layout.addWidget(source_label)

        self.cb_use_original = QtWidgets.QCheckBox("Use original files (before line noise removal)")
        self.cb_use_original.setChecked(False)
        self.cb_use_original.setEnabled(len(self.original_file_paths) > 0)
        self.cb_use_original.stateChanged.connect(self._on_source_changed)
        self.cb_use_original.setStyleSheet(f"""
            QCheckBox {{
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        if not self.original_file_paths:
            self.cb_use_original.setToolTip("No original files available")
        options_layout.addWidget(self.cb_use_original)

        options_layout.addSpacing(Spacing.XL)

        # Display options
        display_label = QtWidgets.QLabel("Display:")
        display_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
        """)
        options_layout.addWidget(display_label)

        self.cb_show_filenames = QtWidgets.QCheckBox("Show filenames in chart")
        self.cb_show_filenames.setChecked(True)
        self.cb_show_filenames.stateChanged.connect(self._on_display_changed)
        self.cb_show_filenames.setStyleSheet(f"""
            QCheckBox {{
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        options_layout.addWidget(self.cb_show_filenames)

        options_layout.addStretch()

        # File count info
        self.file_count_label = QtWidgets.QLabel(f"Files: {len(self.file_paths)}")
        self.file_count_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
            }}
        """)
        options_layout.addWidget(self.file_count_label)

        parent_layout.addWidget(options_frame)

    def _on_source_changed(self, state):
        """Handle data source checkbox change."""
        self.use_original_files = (state == QtCore.Qt.Checked)
        self.load_files()
        self.reset_selection()

        # Update file count label
        count = len(self.original_file_paths) if self.use_original_files else len(self.file_paths)
        source = "original" if self.use_original_files else "cleaned"
        self.file_count_label.setText(f"Files: {count} ({source})")

        logger.info("Switched to %s files", source)

    def _on_display_changed(self, state):
        """Handle display option checkbox change."""
        self.show_filenames = (state == QtCore.Qt.Checked)
        if self.analysis_results:
            self._update_results_display()

    def _create_selection_panel(self, parent_layout):
        """Create the signal selection panel with matplotlib plot."""
        panel = QtWidgets.QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.LG};
            }}
        """)

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)

        # Section title
        title = QtWidgets.QLabel("Step 1: Select Analysis Region")
        title.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
            }}
        """)
        layout.addWidget(title)

        # Matplotlib figure
        self.selection_figure = Figure(figsize=(10, 4), facecolor=Colors.BG_PRIMARY)
        self.selection_canvas = FigureCanvas(self.selection_figure)
        self.selection_ax = self.selection_figure.add_subplot(111)
        self.selection_ax.set_facecolor(Colors.BG_PRIMARY)

        # Navigation toolbar
        self.toolbar = NavigationToolbar(self.selection_canvas, self)
        self.toolbar.setStyleSheet(f"""
            QToolBar {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px;
            }}
        """)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.selection_canvas)

        # ROI info display with editable spinboxes
        info_layout = QtWidgets.QHBoxLayout()

        spinbox_style = f"""
            QDoubleSpinBox {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_SM};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                background-color: {Colors.GRAY_100};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
                min-width: 80px;
            }}
            QDoubleSpinBox:focus {{
                border: 1px solid {Colors.BLUE_600};
            }}
        """

        label_style = f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
            }}
        """

        # Start time input
        start_label = QtWidgets.QLabel("Start:")
        start_label.setStyleSheet(label_style)
        info_layout.addWidget(start_label)

        self.roi_start_spin = QtWidgets.QDoubleSpinBox()
        self.roi_start_spin.setDecimals(3)
        self.roi_start_spin.setSuffix(" s")
        self.roi_start_spin.setRange(0, 10000)
        self.roi_start_spin.setSingleStep(0.1)
        self.roi_start_spin.setStyleSheet(spinbox_style)
        self.roi_start_spin.valueChanged.connect(self._on_time_input_changed)
        info_layout.addWidget(self.roi_start_spin)

        info_layout.addSpacing(Spacing.MD)

        # End time input
        end_label = QtWidgets.QLabel("End:")
        end_label.setStyleSheet(label_style)
        info_layout.addWidget(end_label)

        self.roi_end_spin = QtWidgets.QDoubleSpinBox()
        self.roi_end_spin.setDecimals(3)
        self.roi_end_spin.setSuffix(" s")
        self.roi_end_spin.setRange(0, 10000)
        self.roi_end_spin.setSingleStep(0.1)
        self.roi_end_spin.setStyleSheet(spinbox_style)
        self.roi_end_spin.valueChanged.connect(self._on_time_input_changed)
        info_layout.addWidget(self.roi_end_spin)

        info_layout.addSpacing(Spacing.MD)

        # Duration label (read-only)
        self.roi_duration_label = QtWidgets.QLabel("Duration: --")
        self.roi_duration_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_SM};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                background-color: {Colors.GRAY_100};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
            }}
        """)
        info_layout.addWidget(self.roi_duration_label)

        info_layout.addStretch()

        # Calculate button
        self.btn_calculate = QtWidgets.QPushButton("Calculate RMS")
        self.btn_calculate.setStyleSheet(Styles.button_primary())
        self.btn_calculate.clicked.connect(self.calculate_rms_for_selection)
        self.btn_calculate.setEnabled(False)
        info_layout.addWidget(self.btn_calculate)

        layout.addLayout(info_layout)

        parent_layout.addWidget(panel, stretch=2)

    def _create_results_panel(self, parent_layout):
        """Create the results display panel."""
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(500)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)

        panel = QtWidgets.QWidget()
        panel.setStyleSheet("background-color: transparent;")

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(0, 0, Spacing.SM, 0)

        # Section title
        title = QtWidgets.QLabel("Step 2: Analysis Results")
        title.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
            }}
        """)
        layout.addWidget(title)

        # Results figure
        self.results_figure = Figure(figsize=(6, 8), facecolor=Colors.BG_PRIMARY)
        self.results_canvas = FigureCanvas(self.results_figure)
        layout.addWidget(self.results_canvas)

        # Summary text
        self.summary_label = QtWidgets.QLabel("Select a region and click 'Calculate RMS' to see results.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
            }}
        """)
        layout.addWidget(self.summary_label)

        layout.addStretch()

        scroll.setWidget(panel)
        parent_layout.addWidget(scroll, stretch=1)

    def _create_action_buttons(self, parent_layout):
        """Create action buttons at the bottom."""
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        btn_reset = QtWidgets.QPushButton("Reset Selection")
        btn_reset.setStyleSheet(Styles.button_secondary())
        btn_reset.clicked.connect(self.reset_selection)
        btn_layout.addWidget(btn_reset)

        self.btn_save = QtWidgets.QPushButton("Save Results && Close")
        self.btn_save.setStyleSheet(Styles.button_primary())
        self.btn_save.clicked.connect(self.save_and_close)
        self.btn_save.setEnabled(False)
        btn_layout.addWidget(self.btn_save)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.setStyleSheet(Styles.button_secondary())
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        parent_layout.addLayout(btn_layout)

    def update_selection_plot(self):
        """Update the selection plot with overlaid performed paths."""
        self.selection_ax.clear()
        self.selection_ax.set_facecolor(Colors.BG_PRIMARY)

        if not self.performed_path_map:
            self.selection_ax.text(0.5, 0.5, "No performed path signals found",
                                   ha='center', va='center', transform=self.selection_ax.transAxes)
            self.selection_canvas.draw_idle()
            return

        # Get sampling frequency from first grid
        sf = self.grid_items[0].emgfile.sampling_frequency if self.grid_items else 2048

        # Plot all performed paths (normalized)
        for gd in self.grid_items:
            uid = gd.grid.grid_uid
            if uid not in self.performed_path_map:
                continue

            signal = self.performed_path_map[uid].copy()
            n_samples = len(signal)
            time_vector = np.arange(n_samples) / sf

            # Normalize to [0, 1] for visualization
            signal_min, signal_max = signal.min(), signal.max()
            if signal_max != signal_min:
                signal = (signal - signal_min) / (signal_max - signal_min)

            label = f"{Path(gd.file_path).name} ({gd.grid.grid_key})"
            self.selection_ax.plot(time_vector, signal, alpha=0.6, linewidth=0.8, label=label)

        # Academic-style formatting
        self.selection_ax.set_xlabel("Time (s)", fontsize=11, fontfamily='sans-serif')
        self.selection_ax.set_ylabel("Normalized Amplitude (a.u.)", fontsize=11, fontfamily='sans-serif')
        self.selection_ax.set_title("Performed Path Signals", fontsize=12, fontweight='bold', fontfamily='sans-serif')
        self.selection_ax.grid(True, alpha=0.3, linestyle='--', color='gray')
        self.selection_ax.tick_params(labelsize=10)

        # Legend
        if len(self.grid_items) <= 8:
            self.selection_ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
        else:
            self.selection_ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=7, framealpha=0.9)
            self.selection_figure.subplots_adjust(right=0.75)

        # Setup span selector
        self.span_selector = SpanSelector(
            self.selection_ax,
            self._on_span_select,
            'horizontal',
            useblit=True,
            props=dict(alpha=0.3, facecolor=Colors.BLUE_500),
            interactive=True,
            drag_from_anywhere=True
        )

        # Connect click event
        self.selection_canvas.mpl_connect('button_press_event', self._on_click)

        self.selection_figure.tight_layout()
        self.selection_canvas.draw_idle()

    def _on_span_select(self, xmin, xmax):
        """Handle span selection (drag mode)."""
        self.first_click_pos = None
        self.selected_region = (xmin, xmax)
        self._update_roi_display()
        self._draw_selection_lines()
        self.btn_calculate.setEnabled(True)
        logger.debug("Region selected: %.3f - %.3f s", xmin, xmax)

    def _on_click(self, event):
        """Handle click events for two-click selection."""
        if event.inaxes != self.selection_ax or event.button != 1:
            return
        if self.toolbar.mode != '':
            return

        x_pos = event.xdata

        if self.first_click_pos is None:
            self.first_click_pos = x_pos
            self._draw_selection_lines()
        else:
            second_pos = x_pos
            start = min(self.first_click_pos, second_pos)
            end = max(self.first_click_pos, second_pos)
            self.selected_region = (start, end)
            self.first_click_pos = None

            # Update SpanSelector to show the selection
            if self.span_selector is not None:
                self.span_selector.extents = (start, end)

            self._update_roi_display()
            self._draw_selection_lines()
            self.btn_calculate.setEnabled(True)

    def _update_roi_display(self):
        """Update the ROI info spinboxes."""
        if self.selected_region:
            start, end = self.selected_region
            duration = end - start

            # Block signals to avoid recursion when updating from code
            self.roi_start_spin.blockSignals(True)
            self.roi_end_spin.blockSignals(True)

            self.roi_start_spin.setValue(start)
            self.roi_end_spin.setValue(end)
            self.roi_duration_label.setText(f"Duration: {duration:.3f} s")

            self.roi_start_spin.blockSignals(False)
            self.roi_end_spin.blockSignals(False)

    def _on_time_input_changed(self):
        """Handle manual time input changes."""
        start = self.roi_start_spin.value()
        end = self.roi_end_spin.value()

        # Validate: end must be after start
        if end <= start:
            return

        # Update selected region
        self.selected_region = (start, end)

        # Update duration label
        duration = end - start
        self.roi_duration_label.setText(f"Duration: {duration:.3f} s")

        # Update the SpanSelector to match the new values
        if self.span_selector is not None:
            self.span_selector.extents = (start, end)

        # Update visualization (removes extra lines, redraws canvas)
        self._draw_selection_lines()
        self.btn_calculate.setEnabled(True)

    def _draw_selection_lines(self):
        """Draw selection visualization.

        Only draws lines for first-click indicator (two-click mode).
        The SpanSelector handles the region visualization.
        """
        for line in self.threshold_lines:
            try:
                line.remove()
            except:
                pass
        self.threshold_lines.clear()

        # Only draw a line for the first click in two-click mode
        if self.first_click_pos is not None:
            line = self.selection_ax.axvline(self.first_click_pos, color=Colors.BLUE_600,
                                             linestyle='--', linewidth=2)
            self.threshold_lines.append(line)

        self.selection_canvas.draw_idle()

    def reset_selection(self):
        """Reset the selection."""
        self.selected_region = None
        self.first_click_pos = None
        self.analysis_results = None

        for line in self.threshold_lines:
            try:
                line.remove()
            except:
                pass
        self.threshold_lines.clear()

        # Reset SpanSelector
        if self.span_selector is not None:
            self.span_selector.extents = (0, 0)

        # Reset spinboxes
        self.roi_start_spin.blockSignals(True)
        self.roi_end_spin.blockSignals(True)
        self.roi_start_spin.setValue(0)
        self.roi_end_spin.setValue(0)
        self.roi_start_spin.blockSignals(False)
        self.roi_end_spin.blockSignals(False)
        self.roi_duration_label.setText("Duration: --")

        self.btn_calculate.setEnabled(False)
        self.btn_save.setEnabled(False)

        self.update_selection_plot()
        self.results_figure.clear()
        self.results_canvas.draw_idle()

        self.summary_label.setText("Select a region and click 'Calculate RMS' to see results.")
        logger.info("Selection reset")

    def calculate_rms_for_selection(self):
        """Calculate RMS for all channels in the selected region."""
        if not self.selected_region:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a region first.")
            return

        start_s, end_s = self.selected_region
        sf = self.grid_items[0].emgfile.sampling_frequency if self.grid_items else 2048

        start_idx = int(start_s * sf)
        end_idx = int(end_s * sf)

        file_results = []
        all_channel_results = []
        total_quality_counts = {k: 0 for k in QUALITY_COLORS.keys()}

        # Process each grid
        processed_files = set()
        for gd in self.grid_items:
            emg = gd.emgfile
            grid = gd.grid
            file_name = emg.file_name

            # Skip if we've already processed this file's grid
            file_grid_key = f"{file_name}_{grid.grid_uid}"
            if file_grid_key in processed_files:
                continue
            processed_files.add(file_grid_key)

            # Get EMG channel data only (exclude reference signals)
            emg_indices = grid.emg_indices
            ref_indices = set(grid.ref_indices) if grid.ref_indices else set()

            if not emg_indices:
                logger.warning("No EMG indices for grid %s in %s", grid.grid_key, file_name)
                continue

            # Filter out any reference indices from EMG indices (safety check)
            emg_only_indices = [idx for idx in emg_indices if idx not in ref_indices]
            logger.debug("Grid %s: %d EMG channels (excluded %d ref channels)",
                        grid.grid_key, len(emg_only_indices), len(emg_indices) - len(emg_only_indices))

            # Clamp indices to valid range
            n_samples = emg.data.shape[0]
            si = max(0, min(start_idx, n_samples - 1))
            ei = max(si + 1, min(end_idx, n_samples))

            channel_results = []
            rms_values = []

            for ch_idx, data_idx in enumerate(emg_only_indices):
                if data_idx >= emg.data.shape[1]:
                    continue

                # Extract region and calculate RMS
                region_data = emg.data[si:ei, data_idx]
                rms_raw = calculate_rms(region_data)

                # Convert to microvolts
                # The OTB4 file loader applies: conv = ADC_Range / (2^ADC_Nbits) * 1000 / Gain
                # The "* 1000" means data is stored in millivolts (mV).
                # To convert mV to µV: multiply by 1000
                # Example: 0.011 mV * 1000 = 11 µV (matches OTBiolab reference)
                rms_uv = rms_raw * 1000.0

                quality = classify_quality(rms_uv)

                result = ChannelRMSResult(
                    file_name=file_name,
                    grid_key=grid.grid_key,
                    channel_idx=ch_idx,
                    rms_uv=rms_uv,
                    quality=quality
                )
                channel_results.append(result)
                all_channel_results.append(result)
                rms_values.append(rms_uv)
                total_quality_counts[quality] += 1

            if rms_values:
                # Aggregate results for this file
                quality_counts = {k: 0 for k in QUALITY_COLORS.keys()}
                for cr in channel_results:
                    quality_counts[cr.quality] += 1

                file_result = FileRMSResult(
                    file_name=file_name,
                    grid_key=grid.grid_key,
                    mean_rms=np.mean(rms_values),
                    std_rms=np.std(rms_values),
                    min_rms=np.min(rms_values),
                    max_rms=np.max(rms_values),
                    channel_results=channel_results,
                    quality_counts=quality_counts
                )
                file_results.append(file_result)

        if not file_results:
            QtWidgets.QMessageBox.warning(self, "No Data", "No valid channel data found.")
            return

        # Calculate grand statistics
        all_rms = [cr.rms_uv for cr in all_channel_results]

        self.analysis_results = AnalysisResults(
            file_results=file_results,
            grand_mean=np.mean(all_rms),
            grand_std=np.std(all_rms),
            overall_min=np.min(all_rms),
            overall_max=np.max(all_rms),
            total_channels=len(all_channel_results),
            quality_counts=total_quality_counts,
            region_start_s=start_s,
            region_end_s=end_s,
            sampling_frequency=sf
        )

        self._update_results_display()
        self.btn_save.setEnabled(True)
        logger.info("RMS analysis complete: mean=%.2f µV, std=%.2f µV",
                    self.analysis_results.grand_mean, self.analysis_results.grand_std)

    def _update_results_display(self):
        """Update the results visualization."""
        if not self.analysis_results:
            return

        results = self.analysis_results
        self.results_figure.clear()

        # Create subplots
        gs = self.results_figure.add_gridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.4)

        # Panel A: Bar chart of mean RMS per file with error bars
        ax1 = self.results_figure.add_subplot(gs[0])
        self._plot_file_rms_bars(ax1, results)

        # Panel B: Overall statistics
        ax2 = self.results_figure.add_subplot(gs[1])
        self._plot_overall_stats(ax2, results)

        # Panel C: Quality distribution pie chart
        ax3 = self.results_figure.add_subplot(gs[2])
        self._plot_quality_pie(ax3, results)

        self.results_figure.tight_layout()
        self.results_canvas.draw_idle()

        # Update summary text
        self._update_summary_text(results)

    def _plot_file_rms_bars(self, ax, results: AnalysisResults, show_names: bool = None):
        """Plot bar chart of mean RMS per file with academic formatting."""
        if show_names is None:
            show_names = self.show_filenames

        means = [fr.mean_rms for fr in results.file_results]
        stds = [fr.std_rms for fr in results.file_results]
        colors = [QUALITY_COLORS[fr.quality] for fr in results.file_results]

        x = np.arange(len(results.file_results))
        bars = ax.bar(x, means, yerr=stds, color=colors, edgecolor='black',
                      linewidth=0.5, capsize=3, error_kw={'elinewidth': 1})

        # Add quality threshold lines
        for thresh_name, thresh_value in QUALITY_THRESHOLDS.items():
            ax.axhline(y=thresh_value, color=QUALITY_COLORS[thresh_name],
                       linestyle='--', alpha=0.7, linewidth=1)

        ax.set_xticks(x)
        if show_names:
            file_names = [fr.file_name[:15] + '...' if len(fr.file_name) > 18 else fr.file_name
                          for fr in results.file_results]
            ax.set_xticklabels(file_names, rotation=45, ha='right', fontsize=8)
            ax.set_xlabel("")
        else:
            # Show index numbers instead
            ax.set_xticklabels([str(i + 1) for i in range(len(results.file_results))], fontsize=8)
            ax.set_xlabel("Grid #", fontsize=10, fontfamily='sans-serif')

        ax.set_ylabel("RMS Noise (µV)", fontsize=10, fontfamily='sans-serif')
        ax.set_title("RMS Noise Quality per Recording", fontsize=11, fontweight='bold', fontfamily='sans-serif')
        ax.set_ylim(0, max(means) * 1.3 if means else 30)
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')
        ax.tick_params(labelsize=9)

    def _plot_overall_stats(self, ax, results: AnalysisResults):
        """Plot overall statistics with error bar."""
        ax.bar([0], [results.grand_mean], yerr=[results.grand_std],
               color=QUALITY_COLORS[classify_quality(results.grand_mean)],
               edgecolor='black', linewidth=0.5, capsize=5, width=0.5)

        # Add threshold lines
        for thresh_name, thresh_value in QUALITY_THRESHOLDS.items():
            ax.axhline(y=thresh_value, color=QUALITY_COLORS[thresh_name],
                       linestyle='--', alpha=0.7, linewidth=1)

        ax.set_xticks([0])
        ax.set_xticklabels(['All Recordings'], fontsize=10)
        ax.set_ylabel("RMS Noise (µV)", fontsize=10, fontfamily='sans-serif')
        ax.set_title(f"Overall: {results.grand_mean:.2f} ± {results.grand_std:.2f} µV",
                     fontsize=11, fontweight='bold', fontfamily='sans-serif')
        ax.set_ylim(0, max(results.grand_mean + results.grand_std * 2, 25))
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')

    def _plot_quality_pie(self, ax, results: AnalysisResults):
        """Plot quality distribution pie chart."""
        # Filter out zero counts
        pie_data = {k: v for k, v in results.quality_counts.items() if v > 0}

        if pie_data:
            wedges, texts, autotexts = ax.pie(
                pie_data.values(),
                labels=[QUALITY_LABELS.get(k, k) for k in pie_data.keys()],
                colors=[QUALITY_COLORS[k] for k in pie_data.keys()],
                autopct='%1.1f%%',
                startangle=90,
                textprops={'fontsize': 8}
            )
            ax.set_title("Quality Distribution", fontsize=11, fontweight='bold', fontfamily='sans-serif')
        else:
            ax.text(0.5, 0.5, "No data", ha='center', va='center')

    def _update_summary_text(self, results: AnalysisResults):
        """Update the summary text label."""
        summary = f"""
<b>Analysis Summary</b><br>
<br>
<b>Region:</b> {results.region_start_s:.3f} - {results.region_end_s:.3f} s<br>
<b>Files analyzed:</b> {len(results.file_results)}<br>
<b>Total channels:</b> {results.total_channels}<br>
<br>
<b>RMS Statistics (µV):</b><br>
• Mean: {results.grand_mean:.2f}<br>
• Std: {results.grand_std:.2f}<br>
• Min: {results.overall_min:.2f}<br>
• Max: {results.overall_max:.2f}<br>
<br>
<b>Quality Breakdown:</b><br>
• Excellent (≤5): {results.quality_counts['excellent']}<br>
• Good (≤10): {results.quality_counts['good']}<br>
• OK (≤15): {results.quality_counts['ok']}<br>
• Troubled (≤20): {results.quality_counts['troubled']}<br>
• Bad (>20): {results.quality_counts['bad']}
"""
        self.summary_label.setText(summary)

    def save_and_close(self):
        """Save results to analysis folder and close dialog."""
        if not self.analysis_results:
            self.reject()
            return

        try:
            # Create analysis folder
            analysis_path = global_state.get_analysis_path()
            os.makedirs(analysis_path, exist_ok=True)

            # Save summary figure
            self._save_summary_figure(analysis_path)

            # Save per-channel figure
            self._save_per_channel_figure(analysis_path)

            # Save CSV report
            self._save_csv_report(analysis_path)

            # Save text summary
            self._save_text_summary(analysis_path)

            # Save channel selection JSON
            self._save_channel_selection_json()

            logger.info("Analysis results saved to %s", analysis_path)
            QtWidgets.QMessageBox.information(
                self, "Results Saved",
                f"Analysis results saved to:\n{analysis_path}"
            )
            self.accept()

        except Exception as e:
            logger.error("Failed to save results: %s", e, exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Save Error", f"Failed to save results:\n{e}")

    def _save_channel_selection_json(self):
        """Save channel selection data to JSON files."""
        results = self.analysis_results
        if not results:
            return

        try:
            # Get cropped signal path and create it if it doesn't exist
            cropped_signal_path = global_state.get_cropped_signal_path()
            os.makedirs(cropped_signal_path, exist_ok=True)
            logger.info(f"Ensured channel selection directory exists at: {cropped_signal_path}")

            # Group results by file name
            file_channel_results = {}
            for fr in results.file_results:
                if fr.file_name not in file_channel_results:
                    file_channel_results[fr.file_name] = []
                file_channel_results[fr.file_name].extend(fr.channel_results)

            for file_name, channel_results in file_channel_results.items():
                grids_data = {}
                for cr in channel_results:
                    if cr.grid_key not in grids_data:
                        grids_data[cr.grid_key] = {}
                    
                    grids_data[cr.grid_key][str(cr.channel_idx)] = {
                        "rms_label": cr.quality,
                        "rms_quality": f"{cr.rms_uv:.2f} µV"
                    }

                json_data = {"grids": grids_data}

                # Construct output path
                base_name = Path(file_name).stem
                json_file_name = f"{base_name}_rms.json"
                output_path = os.path.join(cropped_signal_path, json_file_name)

                # Save JSON file
                with open(output_path, 'w') as f:
                    json.dump(json_data, f, indent=4)
                
                logger.info(f"Saved channel selection JSON for {file_name} to {output_path}")

        except Exception as e:
            logger.error("Failed to save channel selection JSON: %s", e, exc_info=True)
            # Optionally, show a non-critical error message to the user
            QtWidgets.QMessageBox.warning(self, "JSON Save Warning", f"Could not save channel selection file for some items:\n{e}")


    def _save_summary_figure(self, output_path: str):
        """Save academic-style summary figure."""
        results = self.analysis_results

        fig = Figure(figsize=(12, 10), dpi=300)
        gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1], hspace=0.3, wspace=0.3)

        # Panel A: Bar chart with error bars
        ax1 = fig.add_subplot(gs[0, :])
        means = [fr.mean_rms for fr in results.file_results]
        stds = [fr.std_rms for fr in results.file_results]
        colors = [QUALITY_COLORS[fr.quality] for fr in results.file_results]

        x = np.arange(len(results.file_results))
        ax1.bar(x, means, yerr=stds, color=colors, edgecolor='black',
                linewidth=0.5, capsize=3, error_kw={'elinewidth': 1})

        for thresh_name, thresh_value in QUALITY_THRESHOLDS.items():
            ax1.axhline(y=thresh_value, color=QUALITY_COLORS[thresh_name],
                        linestyle='--', alpha=0.7, linewidth=1, label=QUALITY_LABELS[thresh_name])

        ax1.set_xticks(x)
        if self.show_filenames:
            file_names = [fr.file_name for fr in results.file_results]
            display_names = [fn[:20] + '...' if len(fn) > 23 else fn for fn in file_names]
            ax1.set_xticklabels(display_names, rotation=45, ha='right', fontsize=9)
            ax1.set_xlabel("Recording", fontsize=11, fontfamily='sans-serif')
        else:
            ax1.set_xticklabels([str(i + 1) for i in range(len(results.file_results))], fontsize=9)
            ax1.set_xlabel("Recording #", fontsize=11, fontfamily='sans-serif')

        ax1.set_ylabel("RMS Noise (µV)", fontsize=11, fontfamily='sans-serif')
        ax1.set_title("A) RMS Noise Quality per Recording", fontsize=12, fontweight='bold',
                      fontfamily='sans-serif', loc='left')
        ax1.legend(loc='upper right', fontsize=8, framealpha=0.9)
        ax1.grid(True, alpha=0.3, linestyle='--', axis='y')

        # Panel B: Overall statistics
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.bar([0], [results.grand_mean], yerr=[results.grand_std],
                color=QUALITY_COLORS[classify_quality(results.grand_mean)],
                edgecolor='black', linewidth=0.5, capsize=5, width=0.4)

        for thresh_name, thresh_value in QUALITY_THRESHOLDS.items():
            ax2.axhline(y=thresh_value, color=QUALITY_COLORS[thresh_name],
                        linestyle='--', alpha=0.5, linewidth=1)

        ax2.set_xticks([0])
        ax2.set_xticklabels(['All Recordings'], fontsize=10)
        ax2.set_ylabel("RMS Noise (µV)", fontsize=11, fontfamily='sans-serif')
        ax2.set_title(f"B) Grand Mean: {results.grand_mean:.2f} ± {results.grand_std:.2f} µV",
                      fontsize=12, fontweight='bold', fontfamily='sans-serif', loc='left')
        ax2.grid(True, alpha=0.3, linestyle='--', axis='y')

        # Panel C: Quality pie chart
        ax3 = fig.add_subplot(gs[1, 1])
        pie_data = {k: v for k, v in results.quality_counts.items() if v > 0}
        if pie_data:
            ax3.pie(
                pie_data.values(),
                labels=[QUALITY_LABELS.get(k, k) for k in pie_data.keys()],
                colors=[QUALITY_COLORS[k] for k in pie_data.keys()],
                autopct='%1.1f%%',
                startangle=90,
                textprops={'fontsize': 9}
            )
        ax3.set_title("C) Quality Distribution", fontsize=12, fontweight='bold',
                      fontfamily='sans-serif', loc='left')

        fig.tight_layout()
        fig.savefig(os.path.join(output_path, "rms_quality_summary.png"), dpi=300, bbox_inches='tight')
        plt.close(fig)

    def _save_per_channel_figure(self, output_path: str):
        """Save per-channel RMS heatmap figure."""
        results = self.analysis_results

        # Collect all channel data
        all_files = []
        max_channels = 0
        for fr in results.file_results:
            all_files.append(fr)
            max_channels = max(max_channels, len(fr.channel_results))

        if not all_files or max_channels == 0:
            return

        # Create data matrix
        data_matrix = np.full((len(all_files), max_channels), np.nan)
        for i, fr in enumerate(all_files):
            for cr in fr.channel_results:
                if cr.channel_idx < max_channels:
                    data_matrix[i, cr.channel_idx] = cr.rms_uv

        fig = Figure(figsize=(14, max(6, len(all_files) * 0.3)), dpi=300)
        ax = fig.add_subplot(111)

        # Create heatmap
        im = ax.imshow(data_matrix, aspect='auto', cmap='RdYlGn_r',
                       vmin=0, vmax=max(25, np.nanmax(data_matrix)))

        # Labels
        ax.set_yticks(np.arange(len(all_files)))
        ax.set_yticklabels([fr.file_name for fr in all_files], fontsize=8)
        ax.set_xlabel("Channel Index", fontsize=11, fontfamily='sans-serif')
        ax.set_ylabel("Recording", fontsize=11, fontfamily='sans-serif')
        ax.set_title("RMS Noise per Channel (µV)", fontsize=12, fontweight='bold', fontfamily='sans-serif')

        # Colorbar
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("RMS (µV)", fontsize=10)

        fig.tight_layout()
        fig.savefig(os.path.join(output_path, "rms_quality_per_channel.png"), dpi=300, bbox_inches='tight')
        plt.close(fig)

    def _save_csv_report(self, output_path: str):
        """Save detailed CSV report."""
        results = self.analysis_results

        csv_path = os.path.join(output_path, "rms_analysis_report.csv")
        with open(csv_path, 'w') as f:
            f.write("file_name,grid_key,channel_idx,rms_uv,quality,region_start_s,region_end_s\n")
            for fr in results.file_results:
                for cr in fr.channel_results:
                    f.write(f"{cr.file_name},{cr.grid_key},{cr.channel_idx},{cr.rms_uv:.4f},"
                            f"{cr.quality},{results.region_start_s:.4f},{results.region_end_s:.4f}\n")

        logger.info("CSV report saved to %s", csv_path)

    def _save_text_summary(self, output_path: str):
        """Save text summary."""
        results = self.analysis_results
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        txt_path = os.path.join(output_path, "rms_analysis_summary.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("RMS QUALITY ANALYSIS SUMMARY\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Analysis Date: {timestamp}\n")
            f.write(f"Selected Region: {results.region_start_s:.4f} - {results.region_end_s:.4f} s\n")
            f.write(f"Sampling Frequency: {results.sampling_frequency:.1f} Hz\n\n")

            f.write("-" * 40 + "\n")
            f.write("OVERALL STATISTICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Files analyzed: {len(results.file_results)}\n")
            f.write(f"Total channels: {results.total_channels}\n\n")
            f.write(f"Grand Mean RMS: {results.grand_mean:.2f} µV\n")
            f.write(f"Grand Std RMS:  {results.grand_std:.2f} µV\n")
            f.write(f"Min RMS:        {results.overall_min:.2f} µV\n")
            f.write(f"Max RMS:        {results.overall_max:.2f} µV\n\n")

            f.write("-" * 40 + "\n")
            f.write("QUALITY BREAKDOWN\n")
            f.write("-" * 40 + "\n")
            f.write(f"Excellent (≤5 µV):   {results.quality_counts['excellent']}\n")
            f.write(f"Good (5-10 µV):      {results.quality_counts['good']}\n")
            f.write(f"OK (10-15 µV):       {results.quality_counts['ok']}\n")
            f.write(f"Troubled (15-20 µV): {results.quality_counts['troubled']}\n")
            f.write(f"Bad (>20 µV):        {results.quality_counts['bad']}\n\n")

            f.write("-" * 40 + "\n")
            f.write("PER-FILE SUMMARY\n")
            f.write("-" * 40 + "\n")
            for fr in results.file_results:
                f.write(f"\n{fr.file_name} ({fr.grid_key}):\n")
                f.write(f"  Mean RMS: {fr.mean_rms:.2f} ± {fr.std_rms:.2f} µV\n")
                f.write(f"  Min/Max:  {fr.min_rms:.2f} / {fr.max_rms:.2f} µV\n")
                f.write(f"  Quality:  {fr.quality}\n")
                f.write(f"  Channels: {len(fr.channel_results)}\n")

            f.write("\n" + "=" * 60 + "\n")

        logger.info("Text summary saved to %s", txt_path)
