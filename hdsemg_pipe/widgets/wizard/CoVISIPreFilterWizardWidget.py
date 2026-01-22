"""
Step 8.5: CoVISI Pre-Filtering (Wizard Version)

This step allows filtering of motor units based on CoVISI (Coefficient of
Variation of Interspike Interval) before MUedit manual cleaning.

Literature standard: CoVISI < 30% indicates physiologically plausible MUs.
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.covisi_analysis import (
    COVISI_METHOD_AUTO,
    COVISI_METHOD_STEADY,
    DEFAULT_COVISI_THRESHOLD,
    OPENHDEMG_AVAILABLE,
    SteadyStateSelectionDialog,
    apply_covisi_filter_to_json,
    compute_covisi_for_all_mus,
    get_contraction_duration,
    get_covisi_quality_category,
    get_ref_signal_for_plotting,
    save_covisi_report,
)
from hdsemg_pipe.actions.decomposition_export import export_to_muedit_mat
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import (
    BorderRadius,
    Colors,
    Fonts,
    Spacing,
    Styles,
)
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget

try:
    import openhdemg.library as emg
    _OPENHDEMG_AVAILABLE = True
except ImportError:
    emg = None
    _OPENHDEMG_AVAILABLE = False


class CoVISIComputeWorker(QThread):
    """Worker thread for computing CoVISI values."""

    progress = pyqtSignal(int, int, str)  # current, total, filename
    result = pyqtSignal(str, object, float)  # filename, covisi_df or error, duration
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, json_files, method=COVISI_METHOD_AUTO,
                 start_steady=None, end_steady=None, parent=None):
        super().__init__(parent)
        self.json_files = json_files
        self.method = method
        self.start_steady = start_steady
        self.end_steady = end_steady

    def run(self):
        """Compute CoVISI for all JSON files."""
        # Check openhdemg availability at runtime
        if not _OPENHDEMG_AVAILABLE or emg is None:
            self.error.emit("openhdemg library is not available. Please install it first.")
            return

        try:
            total = len(self.json_files)
            for idx, json_path in enumerate(self.json_files):
                filename = os.path.basename(json_path)
                self.progress.emit(idx, total, filename)

                try:
                    # Load JSON file
                    emgfile = emg.emg_from_json(str(json_path))

                    # Get contraction duration for UI
                    duration = get_contraction_duration(emgfile)

                    # Compute CoVISI with specified method
                    covisi_df = compute_covisi_for_all_mus(
                        emgfile,
                        method=self.method,
                        start_steady=self.start_steady,
                        end_steady=self.end_steady,
                    )
                    self.result.emit(json_path, covisi_df, duration)

                except Exception as e:
                    logger.error(f"Failed to compute CoVISI for {filename}: {e}")
                    self.result.emit(json_path, str(e), 0.0)

            self.finished.emit()

        except Exception as e:
            self.error.emit(f"CoVISI computation failed: {str(e)}")


class CoVISIFilterWorker(QThread):
    """Worker thread for filtering motor units by CoVISI."""

    progress = pyqtSignal(int, int, str)  # current, total, filename
    finished = pyqtSignal(dict)  # overall stats
    error = pyqtSignal(str)

    def __init__(self, json_files, threshold, output_folder, parent=None):
        super().__init__(parent)
        self.json_files = json_files
        self.threshold = threshold
        self.output_folder = output_folder

    def run(self):
        """Apply CoVISI filtering and export to MUedit."""
        try:
            overall_stats = {
                "files_processed": 0,
                "total_mus_original": 0,
                "total_mus_filtered": 0,
                "total_mus_removed": 0,
                "per_file_stats": {},
            }

            total = len(self.json_files)
            for idx, json_path in enumerate(self.json_files):
                filename = os.path.basename(json_path)
                self.progress.emit(idx, total, f"Filtering {filename}...")

                try:
                    # Generate output path for filtered JSON
                    base_name = Path(json_path).stem
                    filtered_json_path = os.path.join(
                        self.output_folder, f"{base_name}_covisi_filtered.json"
                    )

                    # Apply CoVISI filter
                    stats = apply_covisi_filter_to_json(
                        json_path,
                        filtered_json_path,
                        threshold=self.threshold,
                    )

                    # Export filtered JSON to MUedit format
                    self.progress.emit(
                        idx, total, f"Exporting {filename} to MUedit..."
                    )
                    muedit_path = export_to_muedit_mat(filtered_json_path)

                    # Aggregate stats
                    overall_stats["files_processed"] += 1
                    overall_stats["total_mus_original"] += stats["original_mu_count"]
                    overall_stats["total_mus_filtered"] += stats["filtered_mu_count"]
                    overall_stats["total_mus_removed"] += stats["removed_count"]
                    overall_stats["per_file_stats"][filename] = stats

                except Exception as e:
                    logger.error(f"Failed to filter {filename}: {e}")
                    overall_stats["per_file_stats"][filename] = {"error": str(e)}

            self.finished.emit(overall_stats)

        except Exception as e:
            self.error.emit(f"CoVISI filtering failed: {str(e)}")


class CoVISIPreFilterWizardWidget(WizardStepWidget):
    """
    Step 8.5: CoVISI Pre-Filtering.

    This step:
    - Computes CoVISI for all motor units in decomposition results
    - Displays CoVISI values with quality categories
    - Allows threshold adjustment (default 30%)
    - Filters MUs exceeding threshold (optional - can skip)
    - Re-exports filtered files to MUedit format
    """

    def __init__(self, parent=None):
        # Step configuration
        step_index = 9  # After MultiGrid (8), before MUEdit (10)
        step_name = "CoVISI Pre-Filtering"
        description = (
            "Filter motor units based on CoVISI (Coefficient of Variation of "
            "Interspike Interval). MUs with CoVISI > 30% are typically "
            "non-physiological. Filtering is optional."
        )

        super().__init__(step_index, step_name, description, parent)

        self.expected_folder = None
        self.json_files = []
        self.covisi_data = {}  # filename -> covisi_df
        self.threshold = DEFAULT_COVISI_THRESHOLD
        self.compute_worker = None
        self.filter_worker = None
        self.filtering_applied = False

        # Method selection
        self.analysis_method = COVISI_METHOD_AUTO
        self.start_steady = None
        self.end_steady = None
        self.contraction_duration = 0.0  # Will be set when files are loaded

        # Create custom UI
        self.create_covisi_ui()
        self.content_layout.addWidget(self.covisi_container)

        # Perform initial check
        self.check()

    def create_covisi_ui(self):
        """Create the CoVISI analysis UI."""
        self.covisi_container = QFrame()
        self.covisi_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout = QVBoxLayout(self.covisi_container)
        container_layout.setSpacing(Spacing.MD)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # Status label
        self.status_label = QLabel("Waiting for decomposition results...")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
                padding: {Spacing.SM}px;
                background-color: {Colors.BG_TERTIARY};
                border-radius: {BorderRadius.SM};
            }}
        """
        )
        container_layout.addWidget(self.status_label)

        # Settings row with two groups
        settings_row = QHBoxLayout()
        settings_row.setSpacing(Spacing.LG)

        # Method selection group
        method_group = QGroupBox("Analysis Method")
        method_group.setStyleSheet(
            f"""
            QGroupBox {{
                background-color: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
                padding-top: {Spacing.XL}px;
                font-weight: {Fonts.WEIGHT_MEDIUM};
                font-size: {Fonts.SIZE_BASE};
                color: {Colors.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
            }}
        """
        )
        method_layout = QVBoxLayout(method_group)
        method_layout.setSpacing(Spacing.SM)

        # Radio buttons for method selection
        self.method_button_group = QButtonGroup(self)

        self.radio_auto = QRadioButton("Auto (Rec/Derec)")
        self.radio_auto.setToolTip(
            "Automatic mode: Uses recruitment and derecruitment phases.\n"
            "Fast and requires no user input.\n"
            "Best for quick analysis or contractions without steady-state."
        )
        self.radio_auto.setChecked(True)
        self.radio_auto.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_BASE};")
        self.method_button_group.addButton(self.radio_auto, 0)
        method_layout.addWidget(self.radio_auto)

        self.radio_steady = QRadioButton("Manual (Steady-State)")
        self.radio_steady.setToolTip(
            "Manual mode: Analyze CoVISI during the steady-state plateau.\n"
            "More accurate for trapezoidal contractions.\n"
            "Requires specifying start and end times."
        )
        self.radio_steady.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_BASE};")
        self.method_button_group.addButton(self.radio_steady, 1)
        method_layout.addWidget(self.radio_steady)

        # Steady-state time inputs (initially hidden)
        self.steady_state_widget = QWidget()
        steady_layout = QHBoxLayout(self.steady_state_widget)
        steady_layout.setContentsMargins(Spacing.LG, Spacing.SM, 0, 0)
        steady_layout.setSpacing(Spacing.MD)

        start_label = QLabel("Start:")
        start_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
        steady_layout.addWidget(start_label)

        self.start_steady_spinbox = QDoubleSpinBox()
        self.start_steady_spinbox.setRange(0.0, 999.0)
        self.start_steady_spinbox.setValue(0.0)
        self.start_steady_spinbox.setSingleStep(0.5)
        self.start_steady_spinbox.setDecimals(1)
        self.start_steady_spinbox.setSuffix(" s")
        self.start_steady_spinbox.setToolTip("Start time of steady-state phase (seconds)")
        self.start_steady_spinbox.setStyleSheet(
            f"""
            QDoubleSpinBox {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
                min-width: 80px;
                font-size: {Fonts.SIZE_SM};
            }}
        """
        )
        steady_layout.addWidget(self.start_steady_spinbox)

        end_label = QLabel("End:")
        end_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};")
        steady_layout.addWidget(end_label)

        self.end_steady_spinbox = QDoubleSpinBox()
        self.end_steady_spinbox.setRange(0.0, 999.0)
        self.end_steady_spinbox.setValue(10.0)
        self.end_steady_spinbox.setSingleStep(0.5)
        self.end_steady_spinbox.setDecimals(1)
        self.end_steady_spinbox.setSuffix(" s")
        self.end_steady_spinbox.setToolTip("End time of steady-state phase (seconds)")
        self.end_steady_spinbox.setStyleSheet(
            f"""
            QDoubleSpinBox {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
                min-width: 80px;
                font-size: {Fonts.SIZE_SM};
            }}
        """
        )
        steady_layout.addWidget(self.end_steady_spinbox)

        # Duration hint label
        self.duration_label = QLabel("")
        self.duration_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM};")
        steady_layout.addWidget(self.duration_label)

        steady_layout.addSpacing(Spacing.MD)

        # Button to open visual selection dialog
        self.btn_select_from_signal = QPushButton("Select from Signal...")
        self.btn_select_from_signal.setToolTip(
            "Open a dialog to visually select the steady-state region\n"
            "from the reference signal (force/torque)"
        )
        self.btn_select_from_signal.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.BLUE_600};
                color: white;
                border: none;
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.MD}px;
                font-size: {Fonts.SIZE_SM};
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background-color: {Colors.BLUE_700};
            }}
            QPushButton:disabled {{
                background-color: {Colors.GRAY_400};
            }}
        """
        )
        self.btn_select_from_signal.clicked.connect(self.open_steady_state_dialog)
        steady_layout.addWidget(self.btn_select_from_signal)

        steady_layout.addStretch()
        self.steady_state_widget.setVisible(False)
        method_layout.addWidget(self.steady_state_widget)

        # Connect method selection signals
        self.method_button_group.buttonClicked.connect(self.on_method_changed)

        settings_row.addWidget(method_group)

        # Threshold control group
        threshold_group = QGroupBox("Filter Threshold")
        threshold_group.setStyleSheet(
            f"""
            QGroupBox {{
                background-color: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
                padding-top: {Spacing.XL}px;
                font-weight: {Fonts.WEIGHT_MEDIUM};
                font-size: {Fonts.SIZE_BASE};
                color: {Colors.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
            }}
        """
        )
        threshold_group_layout = QVBoxLayout(threshold_group)
        threshold_group_layout.setSpacing(Spacing.SM)

        threshold_row = QHBoxLayout()
        threshold_row.setSpacing(Spacing.MD)

        threshold_label = QLabel("CoVISI Threshold:")
        threshold_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_BASE};"
        )
        threshold_row.addWidget(threshold_label)

        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setRange(5.0, 100.0)
        self.threshold_spinbox.setValue(DEFAULT_COVISI_THRESHOLD)
        self.threshold_spinbox.setSingleStep(5.0)
        self.threshold_spinbox.setDecimals(1)
        self.threshold_spinbox.setSuffix(" %")
        self.threshold_spinbox.setToolTip(
            "Motor units with CoVISI above this threshold will be filtered.\n"
            "Literature standard: 30%"
        )
        self.threshold_spinbox.valueChanged.connect(self.on_threshold_changed)
        self.threshold_spinbox.setStyleSheet(
            f"""
            QDoubleSpinBox {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.SM}px {Spacing.MD}px;
                color: {Colors.TEXT_PRIMARY};
                min-width: 100px;
                font-size: {Fonts.SIZE_BASE};
            }}
        """
        )
        threshold_row.addWidget(self.threshold_spinbox)
        threshold_row.addStretch()

        threshold_group_layout.addLayout(threshold_row)

        # Preview label
        self.preview_label = QLabel("")
        self.preview_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM};"
        )
        threshold_group_layout.addWidget(self.preview_label)

        settings_row.addWidget(threshold_group)
        settings_row.addStretch()

        # Export buttons
        export_buttons = QVBoxLayout()
        export_buttons.setSpacing(Spacing.SM)

        self.btn_export_csv = QPushButton("Export to CSV")
        self.btn_export_csv.setStyleSheet(Styles.button_secondary())
        self.btn_export_csv.setToolTip("Export CoVISI analysis results to CSV file")
        self.btn_export_csv.clicked.connect(self.export_to_csv)
        self.btn_export_csv.setEnabled(False)
        export_buttons.addWidget(self.btn_export_csv)

        self.btn_expand_table = QPushButton("Expand Table")
        self.btn_expand_table.setStyleSheet(Styles.button_secondary())
        self.btn_expand_table.setToolTip("Open table in a resizable window for easier review")
        self.btn_expand_table.clicked.connect(self.open_table_in_window)
        self.btn_expand_table.setEnabled(False)
        export_buttons.addWidget(self.btn_expand_table)

        export_buttons.addStretch()
        settings_row.addLayout(export_buttons)

        container_layout.addLayout(settings_row)

        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                text-align: center;
                height: 24px;
                background-color: {Colors.BG_SECONDARY};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.BLUE_600};
                border-radius: {BorderRadius.SM};
            }}
        """
        )
        self.progress_bar.setVisible(False)
        container_layout.addWidget(self.progress_bar)

        # Results table - make it expandable
        table_container = QFrame()
        table_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(Spacing.XS)

        # Table header label
        self.table_header = QLabel("Motor Unit Quality Analysis")
        self.table_header.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                padding: {Spacing.XS}px 0;
            }}
        """
        )
        self.table_header.setVisible(False)
        table_layout.addWidget(self.table_header)

        self.results_table = QTableWidget()
        self.results_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(
            ["File", "MU Index", "CoVISI (%)", "Quality", "Status"]
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)
        self.results_table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {Colors.BG_PRIMARY};
                alternate-background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                gridline-color: {Colors.BORDER_DEFAULT};
                font-size: {Fonts.SIZE_BASE};
            }}
            QTableWidget::item {{
                padding: {Spacing.SM}px {Spacing.MD}px;
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_TERTIARY};
                color: {Colors.TEXT_PRIMARY};
                padding: {Spacing.MD}px;
                border: none;
                border-bottom: 2px solid {Colors.BORDER_DEFAULT};
                font-weight: {Fonts.WEIGHT_BOLD};
                font-size: {Fonts.SIZE_BASE};
            }}
        """
        )
        self.results_table.setMinimumHeight(300)
        self.results_table.setVisible(False)
        table_layout.addWidget(self.results_table, stretch=1)

        container_layout.addWidget(table_container, stretch=1)

    def create_buttons(self):
        """Create buttons for this step."""
        self.btn_compute = QPushButton("Analyze CoVISI")
        self.btn_compute.setStyleSheet(Styles.button_secondary())
        self.btn_compute.setToolTip("Compute CoVISI values for all motor units")
        self.btn_compute.clicked.connect(self.start_compute)
        self.btn_compute.setEnabled(False)
        self.buttons.append(self.btn_compute)

        self.btn_apply_filter = QPushButton("Apply Filter")
        self.btn_apply_filter.setStyleSheet(Styles.button_primary())
        self.btn_apply_filter.setToolTip(
            "Filter out MUs with CoVISI above threshold and export to MUedit"
        )
        self.btn_apply_filter.clicked.connect(self.start_filter)
        self.btn_apply_filter.setEnabled(False)
        self.buttons.append(self.btn_apply_filter)

        self.btn_skip = QPushButton("Skip Filtering")
        self.btn_skip.setStyleSheet(Styles.button_secondary())
        self.btn_skip.setToolTip(
            "Skip CoVISI filtering and proceed with all MUs to MUedit"
        )
        self.btn_skip.clicked.connect(self.skip_filtering)
        self.btn_skip.setEnabled(False)
        self.buttons.append(self.btn_skip)

    def check(self):
        """Check if this step can be activated."""
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        self.expected_folder = global_state.get_decomposition_path()

        if not OPENHDEMG_AVAILABLE:
            self.status_label.setText(
                "⚠️ openhdemg library not available. CoVISI analysis disabled."
            )
            return False

        # Check if previous step is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        # Scan for JSON files
        self.scan_json_files()

        return True

    def scan_json_files(self):
        """Scan for JSON files in decomposition folder."""
        if not os.path.exists(self.expected_folder):
            self.status_label.setText("Decomposition folder not found.")
            return

        # State files to exclude
        state_files = {
            "decomposition_mapping.json",
            "multigrid_groupings.json",
            "covisi_pre_filter_report.json",
        }

        # Find JSON files (exclude state files and already-filtered files)
        self.json_files = [
            os.path.join(self.expected_folder, f)
            for f in os.listdir(self.expected_folder)
            if f.endswith(".json")
            and f not in state_files
            and "_covisi_filtered" not in f
        ]

        if self.json_files:
            self.status_label.setText(
                f"Found {len(self.json_files)} decomposition file(s). "
                "Click 'Analyze CoVISI' to compute quality metrics."
            )
            self.btn_compute.setEnabled(True)
            self.btn_skip.setEnabled(True)
        else:
            self.status_label.setText("No decomposition files found.")
            self.btn_compute.setEnabled(False)
            self.btn_skip.setEnabled(False)

    def start_compute(self):
        """Start computing CoVISI values."""
        if not self.json_files:
            self.warn("No JSON files to analyze.")
            return

        # Validate steady-state parameters if using manual method
        if self.analysis_method == COVISI_METHOD_STEADY:
            self.start_steady = self.start_steady_spinbox.value()
            self.end_steady = self.end_steady_spinbox.value()

            if self.start_steady >= self.end_steady:
                self.error("Start time must be less than end time for steady-state analysis.")
                return

            if self.end_steady - self.start_steady < 1.0:
                self.warn("Steady-state duration is very short (< 1s). Results may be unreliable.")

        # Disable buttons
        self.btn_compute.setEnabled(False)
        self.btn_apply_filter.setEnabled(False)
        self.btn_skip.setEnabled(False)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.json_files))

        # Clear previous data
        self.covisi_data.clear()
        self.results_table.setRowCount(0)

        # Start worker with method parameters
        self.compute_worker = CoVISIComputeWorker(
            self.json_files,
            method=self.analysis_method,
            start_steady=self.start_steady if self.analysis_method == COVISI_METHOD_STEADY else None,
            end_steady=self.end_steady if self.analysis_method == COVISI_METHOD_STEADY else None,
        )
        self.compute_worker.progress.connect(self.on_compute_progress)
        self.compute_worker.result.connect(self.on_compute_result)
        self.compute_worker.finished.connect(self.on_compute_finished)
        self.compute_worker.error.connect(self.on_compute_error)
        self.compute_worker.start()

        method_str = "steady-state" if self.analysis_method == COVISI_METHOD_STEADY else "auto (rec/derec)"
        logger.info(f"Starting CoVISI computation ({method_str}) for {len(self.json_files)} file(s)...")

    def on_compute_progress(self, current, total, filename):
        """Handle computation progress."""
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Computing CoVISI for {filename}...")

    def on_compute_result(self, json_path, result, duration):
        """Handle computation result for one file."""
        filename = os.path.basename(json_path)

        if isinstance(result, str):
            # Error occurred
            logger.error(f"CoVISI computation error for {filename}: {result}")
            return

        # Store result
        self.covisi_data[json_path] = result

        # Update duration info (use the first file's duration as reference)
        if duration > 0 and self.contraction_duration == 0:
            self.contraction_duration = duration
            self.duration_label.setText(f"(Duration: {duration:.1f}s)")
            # Set reasonable default steady-state values if not yet set
            if self.end_steady_spinbox.value() == 10.0:
                # Suggest middle 60% of contraction as steady-state
                suggested_start = duration * 0.2
                suggested_end = duration * 0.8
                self.start_steady_spinbox.setValue(round(suggested_start, 1))
                self.end_steady_spinbox.setValue(round(suggested_end, 1))

        # Add to table
        self.table_header.setVisible(True)
        self.results_table.setVisible(True)

        # Temporarily disable sorting to add rows
        self.results_table.setSortingEnabled(False)

        for _, row in result.iterrows():
            table_row = self.results_table.rowCount()
            self.results_table.insertRow(table_row)

            # File name
            file_item = QTableWidgetItem(filename)
            self.results_table.setItem(table_row, 0, file_item)

            # MU index - use setData for proper numeric sorting
            mu_item = QTableWidgetItem()
            mu_item.setData(Qt.DisplayRole, int(row["mu_index"]))
            mu_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(table_row, 1, mu_item)

            # CoVISI value - use setData for proper numeric sorting
            covisi_val = row["covisi_all"]
            display_text = f"{round(covisi_val, 2)}"
            covisi_item = QTableWidgetItem()
            covisi_item.setData(Qt.EditRole, float(covisi_val))
            covisi_item.setData(Qt.DisplayRole, display_text)
            covisi_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Color code by threshold
            if covisi_val <= self.threshold:
                covisi_item.setBackground(Qt.darkGreen)
                covisi_item.setForeground(Qt.white)
            elif covisi_val <= 50.0:
                # Marginal - yellow/orange
                covisi_item.setBackground(Qt.darkYellow)
                covisi_item.setForeground(Qt.black)
            else:
                covisi_item.setBackground(Qt.darkRed)
                covisi_item.setForeground(Qt.white)

            self.results_table.setItem(table_row, 2, covisi_item)

            # Quality category
            quality = get_covisi_quality_category(covisi_val)
            quality_item = QTableWidgetItem(quality.capitalize())
            quality_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(table_row, 3, quality_item)

            # Status (will be filtered or kept)
            status = "Keep" if covisi_val <= self.threshold else "Filter"
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(table_row, 4, status_item)

        # Re-enable sorting
        self.results_table.setSortingEnabled(True)

    def on_compute_finished(self):
        """Handle computation completion."""
        self.progress_bar.setVisible(False)

        # Update preview
        self.update_filter_preview()

        # Enable buttons
        self.btn_compute.setEnabled(True)
        self.btn_apply_filter.setEnabled(len(self.covisi_data) > 0)
        self.btn_skip.setEnabled(True)
        self.btn_export_csv.setEnabled(len(self.covisi_data) > 0)
        self.btn_expand_table.setEnabled(len(self.covisi_data) > 0)

        total_mus = sum(len(df) for df in self.covisi_data.values())
        method_str = "steady-state" if self.analysis_method == COVISI_METHOD_STEADY else "rec/derec"

        status_text = (
            f"CoVISI analysis complete ({method_str}). "
            f"Found {total_mus} motor units in {len(self.covisi_data)} file(s)."
        )
        if self.analysis_method == COVISI_METHOD_STEADY:
            status_text += f" Steady-state: {self.start_steady:.1f}s - {self.end_steady:.1f}s"

        self.status_label.setText(status_text)
        self.success(f"CoVISI analysis complete for {len(self.covisi_data)} file(s).")

    def on_compute_error(self, error_msg):
        """Handle computation error."""
        self.progress_bar.setVisible(False)
        self.btn_compute.setEnabled(True)
        self.btn_skip.setEnabled(True)

        self.error(error_msg)
        self.status_label.setText(f"Error: {error_msg}")

    def on_method_changed(self, button):
        """Handle analysis method change."""
        if button == self.radio_auto:
            self.analysis_method = COVISI_METHOD_AUTO
            self.steady_state_widget.setVisible(False)
            logger.info("Switched to Auto (Rec/Derec) analysis method")
        else:
            self.analysis_method = COVISI_METHOD_STEADY
            self.steady_state_widget.setVisible(True)
            # Update duration hint if we have files loaded
            if self.contraction_duration > 0:
                self.duration_label.setText(f"(Duration: {self.contraction_duration:.1f}s)")
            logger.info("Switched to Manual (Steady-State) analysis method")

    def open_steady_state_dialog(self):
        """Open the visual steady-state selection dialog."""
        # Find MUedit MAT files in decomposition folder
        mat_files = []
        if self.expected_folder and os.path.exists(self.expected_folder):
            for f in os.listdir(self.expected_folder):
                if f.endswith("_muedit.mat") and "_edited" not in f:
                    mat_files.append(os.path.join(self.expected_folder, f))

        if not mat_files:
            self.warn(
                "No MUedit MAT files found. Please ensure Multi-Grid Configuration "
                "(Step 8) has been completed to export MAT files."
            )
            return

        # Open the selection dialog
        dialog = SteadyStateSelectionDialog(mat_files, self)
        result = dialog.exec_()

        if result == dialog.Accepted:
            start, end = dialog.get_selection()
            if start is not None and end is not None:
                # Update spinboxes with selected values
                self.start_steady_spinbox.setValue(start)
                self.end_steady_spinbox.setValue(end)
                self.start_steady = start
                self.end_steady = end

                # Update duration label
                duration = end - start
                self.duration_label.setText(f"Selected: {start:.1f}s - {end:.1f}s ({duration:.1f}s)")

                self.success(f"Steady-state region selected: {start:.1f}s - {end:.1f}s")
                logger.info(f"Steady-state selection from dialog: {start:.2f}s - {end:.2f}s")

    def on_threshold_changed(self, value):
        """Handle threshold change."""
        self.threshold = value
        self.update_filter_preview()
        self.update_table_colors()

    def update_filter_preview(self):
        """Update the filter preview label."""
        if not self.covisi_data:
            self.preview_label.setText("")
            return

        total_mus = 0
        to_filter = 0

        for df in self.covisi_data.values():
            total_mus += len(df)
            to_filter += (df["covisi_all"] > self.threshold).sum()

        to_keep = total_mus - to_filter
        self.preview_label.setText(
            f"Preview: {to_filter} of {total_mus} MUs will be filtered "
            f"({to_keep} kept)"
        )

    def update_table_colors(self):
        """Update table colors based on current threshold."""
        for row in range(self.results_table.rowCount()):
            covisi_item = self.results_table.item(row, 2)
            if covisi_item:
                try:
                    covisi_val = float(covisi_item.text())
                    if covisi_val <= self.threshold:
                        covisi_item.setBackground(Qt.darkGreen)
                        self.results_table.item(row, 4).setText("Keep")
                    else:
                        covisi_item.setBackground(Qt.darkRed)
                        self.results_table.item(row, 4).setText("Filter")
                except ValueError:
                    pass

    def start_filter(self):
        """Start the filtering process."""
        if not self.covisi_data:
            self.warn("Please run CoVISI analysis first.")
            return

        # Disable buttons
        self.btn_compute.setEnabled(False)
        self.btn_apply_filter.setEnabled(False)
        self.btn_skip.setEnabled(False)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.json_files))

        # Start worker
        self.filter_worker = CoVISIFilterWorker(
            self.json_files, self.threshold, self.expected_folder
        )
        self.filter_worker.progress.connect(self.on_filter_progress)
        self.filter_worker.finished.connect(self.on_filter_finished)
        self.filter_worker.error.connect(self.on_filter_error)
        self.filter_worker.start()

        logger.info(
            f"Starting CoVISI filtering with threshold {self.threshold}%..."
        )

    def on_filter_progress(self, current, total, message):
        """Handle filtering progress."""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def on_filter_finished(self, stats):
        """Handle filtering completion."""
        self.progress_bar.setVisible(False)
        self.filtering_applied = True

        # Save report
        report_path = os.path.join(
            self.expected_folder, "covisi_pre_filter_report.json"
        )
        save_covisi_report(stats, report_path, report_type="pre_filter")

        # Show summary
        removed = stats["total_mus_removed"]
        original = stats["total_mus_original"]
        filtered = stats["total_mus_filtered"]

        self.success(
            f"CoVISI filtering complete. Removed {removed} of {original} MUs "
            f"({filtered} remaining)."
        )
        self.status_label.setText(
            f"✓ Filtering complete: {filtered} MUs kept, {removed} removed"
        )

        # Mark step as completed
        self.complete_step()

    def on_filter_error(self, error_msg):
        """Handle filtering error."""
        self.progress_bar.setVisible(False)
        self.btn_compute.setEnabled(True)
        self.btn_apply_filter.setEnabled(len(self.covisi_data) > 0)
        self.btn_skip.setEnabled(True)

        self.error(error_msg)
        self.status_label.setText(f"Error: {error_msg}")

    def skip_filtering(self):
        """Skip CoVISI filtering and proceed with all MUs."""
        # Save a report indicating filtering was skipped
        report = {
            "filtering_skipped": True,
            "threshold_available": self.threshold,
            "files_count": len(self.json_files),
            "reason": "User chose to skip pre-filtering",
            "analysis_method": self.analysis_method,
        }

        # Include steady-state parameters if used
        if self.analysis_method == COVISI_METHOD_STEADY:
            report["start_steady"] = self.start_steady
            report["end_steady"] = self.end_steady

        if self.covisi_data:
            # Include CoVISI values even though filtering was skipped
            report["covisi_values"] = {}
            for json_path, df in self.covisi_data.items():
                filename = os.path.basename(json_path)
                report["covisi_values"][filename] = dict(
                    zip(df["mu_index"].astype(int), df["covisi_all"])
                )

        report_path = os.path.join(
            self.expected_folder, "covisi_pre_filter_report.json"
        )
        save_covisi_report(report, report_path, report_type="pre_filter")

        self.info("CoVISI filtering skipped. Proceeding with all MUs.")
        self.status_label.setText("✓ Filtering skipped. All MUs will be processed.")

        # Mark step as completed
        self.complete_step()

    def export_to_csv(self):
        """Export CoVISI analysis results to CSV file."""
        if not self.covisi_data:
            self.warn("No data to export. Run CoVISI analysis first.")
            return

        # Get analysis folder path
        analysis_folder = os.path.join(global_state.workfolder, "analysis")
        if not os.path.exists(analysis_folder):
            os.makedirs(analysis_folder)
            logger.info(f"Created analysis folder: {analysis_folder}")

        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"covisi_pre_filter_analysis_{timestamp}.csv"
        default_path = os.path.join(analysis_folder, default_filename)

        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CoVISI Analysis to CSV",
            default_path,
            "CSV Files (*.csv);;All Files (*)",
        )

        if not file_path:
            return  # User cancelled

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow([
                    "File",
                    "MU Index",
                    "CoVISI (%)",
                    "Quality",
                    "Status",
                    "Threshold (%)",
                ])

                # Write data from table
                for row_idx in range(self.results_table.rowCount()):
                    file_name = self.results_table.item(row_idx, 0).text()
                    mu_index = self.results_table.item(row_idx, 1).data(Qt.DisplayRole)
                    covisi_val = self.results_table.item(row_idx, 2).data(Qt.DisplayRole)
                    quality = self.results_table.item(row_idx, 3).text()
                    status = self.results_table.item(row_idx, 4).text()

                    writer.writerow([
                        file_name,
                        mu_index,
                        covisi_val,
                        quality,
                        status,
                        self.threshold,
                    ])

            self.success(f"Exported CoVISI analysis to {os.path.basename(file_path)}")
            logger.info(f"Exported CoVISI pre-filter analysis to: {file_path}")

        except Exception as e:
            self.error(f"Failed to export CSV: {str(e)}")
            logger.error(f"Failed to export CSV: {e}")

    def open_table_in_window(self):
        """Open the results table in a separate resizable dialog window."""
        if self.results_table.rowCount() == 0:
            self.warn("No data to display. Run CoVISI analysis first.")
            return

        # Create modeless dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("CoVISI Pre-Filter Analysis")
        dialog.setModal(False)
        dialog.resize(900, 600)

        # Main layout
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setSpacing(Spacing.MD)
        dialog_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        # Header label
        header_label = QLabel("Motor Unit Quality Analysis (Pre-Filter)")
        header_label.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_XL};
                font-weight: {Fonts.WEIGHT_BOLD};
                padding-bottom: {Spacing.SM}px;
            }}
        """
        )
        dialog_layout.addWidget(header_label)

        # Create expanded table
        expanded_table = QTableWidget()
        expanded_table.setColumnCount(self.results_table.columnCount())
        expanded_table.setHorizontalHeaderLabels(
            ["File", "MU Index", "CoVISI (%)", "Quality", "Status"]
        )
        expanded_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            expanded_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeToContents
            )
        expanded_table.setAlternatingRowColors(True)
        expanded_table.setSortingEnabled(True)
        expanded_table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {Colors.BG_PRIMARY};
                alternate-background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                gridline-color: {Colors.BORDER_DEFAULT};
                font-size: {Fonts.SIZE_BASE};
            }}
            QTableWidget::item {{
                padding: {Spacing.SM}px {Spacing.MD}px;
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_TERTIARY};
                color: {Colors.TEXT_PRIMARY};
                padding: {Spacing.MD}px;
                border: none;
                border-bottom: 2px solid {Colors.BORDER_DEFAULT};
                font-weight: {Fonts.WEIGHT_BOLD};
                font-size: {Fonts.SIZE_BASE};
            }}
        """
        )

        # Copy data from original table
        expanded_table.setRowCount(self.results_table.rowCount())
        for row in range(self.results_table.rowCount()):
            for col in range(self.results_table.columnCount()):
                original_item = self.results_table.item(row, col)
                if original_item:
                    new_item = QTableWidgetItem()
                    # Copy both text and data for proper sorting
                    new_item.setText(original_item.text())
                    data = original_item.data(Qt.DisplayRole)
                    if data is not None:
                        new_item.setData(Qt.DisplayRole, data)
                    new_item.setTextAlignment(original_item.textAlignment())
                    new_item.setBackground(original_item.background())
                    new_item.setForeground(original_item.foreground())
                    expanded_table.setItem(row, col, new_item)

        dialog_layout.addWidget(expanded_table, stretch=1)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.setStyleSheet(Styles.button_secondary())
        close_button.clicked.connect(dialog.close)
        button_layout.addWidget(close_button)

        dialog_layout.addLayout(button_layout)

        # Show dialog
        dialog.show()

    def is_completed(self):
        """Check if this step is completed."""
        # Check if report exists (either filtering applied or skipped)
        report_path = os.path.join(
            self.expected_folder, "covisi_pre_filter_report.json"
        )
        return os.path.exists(report_path)

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.expected_folder = global_state.get_decomposition_path()
        self.scan_json_files()

        # Check if already completed
        if self.is_completed():
            logger.info("CoVISI pre-filter step already completed (report exists)")
