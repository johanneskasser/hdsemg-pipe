"""
Step 9.5: CoVISI Post-Validation (Wizard Version)

This step validates motor unit quality after MUedit manual cleaning by
comparing CoVISI values before and after editing.

Provides quality assurance checkpoint with options to:
- Accept all MUs and continue
- Filter MUs still exceeding threshold
- Return to MUedit for further cleaning
"""

import csv
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.covisi_analysis import (
    DEFAULT_COVISI_THRESHOLD,
    OPENHDEMG_AVAILABLE,
    compare_pre_post_covisi,
    compute_covisi_for_all_mus,
    compute_covisi_from_muedit_mat,
    get_covisi_quality_category,
    load_covisi_report,
    save_covisi_report,
)
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import (
    BorderRadius,
    Colors,
    Fonts,
    Spacing,
    Styles,
)
from hdsemg_pipe.actions.process_log import read_manual_cleaning_tool
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget

try:
    import openhdemg.library as emg
except ImportError:
    emg = None


class PostValidationWorker(QThread):
    """Worker thread for computing post-cleaning validation."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    result = pyqtSignal(str, dict)  # filename, comparison_report
    finished = pyqtSignal(dict)  # overall_report
    error = pyqtSignal(str)

    def __init__(self, edited_files, json_files, fsamp_dict, parent=None):
        super().__init__(parent)
        self.edited_files = edited_files
        self.json_files = json_files
        self.fsamp_dict = fsamp_dict

    def run(self):
        """Compute validation for all edited files."""
        try:
            overall_report = {
                "files_validated": 0,
                "total_mus_pre": 0,
                "total_mus_post": 0,
                "avg_improvement": [],
                "mus_exceeding_threshold": 0,
                "per_file_reports": {},
            }

            total = len(self.edited_files)
            for idx, edited_path in enumerate(self.edited_files):
                filename = os.path.basename(edited_path)
                self.progress.emit(idx, total, f"Validating {filename}...")

                try:
                    # Find corresponding original JSON
                    base_name = self._get_base_name(edited_path)
                    json_path = self._find_matching_json(base_name)

                    if not json_path:
                        logger.warning(
                            f"No matching JSON found for {filename}, skipping..."
                        )
                        continue

                    # Get sampling frequency
                    fsamp = self.fsamp_dict.get(json_path, 2048.0)

                    # Load original JSON and compute pre-cleaning CoVISI
                    emgfile = emg.emg_from_json(str(json_path))
                    pre_covisi = compute_covisi_for_all_mus(emgfile)

                    # Compute post-cleaning CoVISI from edited MAT
                    post_covisi = compute_covisi_from_muedit_mat(edited_path, fsamp)

                    # Compare
                    comparison = compare_pre_post_covisi(pre_covisi, post_covisi)
                    comparison["json_path"] = json_path
                    comparison["edited_path"] = edited_path

                    # Emit result
                    self.result.emit(filename, comparison)

                    # Aggregate
                    overall_report["files_validated"] += 1
                    overall_report["total_mus_pre"] += comparison["pre_mu_count"]
                    overall_report["total_mus_post"] += comparison["post_mu_count"]
                    overall_report["mus_exceeding_threshold"] += len(
                        comparison["mus_exceeding_threshold"]
                    )
                    if comparison["avg_improvement_percent"] is not None:
                        overall_report["avg_improvement"].append(
                            comparison["avg_improvement_percent"]
                        )
                    overall_report["per_file_reports"][filename] = comparison

                except Exception as e:
                    logger.error(f"Failed to validate {filename}: {e}")
                    overall_report["per_file_reports"][filename] = {"error": str(e)}

            # Calculate overall average improvement
            if overall_report["avg_improvement"]:
                overall_report["avg_improvement_overall"] = np.mean(
                    overall_report["avg_improvement"]
                )
            else:
                overall_report["avg_improvement_overall"] = None

            self.finished.emit(overall_report)

        except Exception as e:
            self.error.emit(f"Post-validation failed: {str(e)}")

    def _get_base_name(self, edited_path):
        """Extract base name from edited MAT file path."""
        filename = os.path.basename(edited_path)
        # Remove common suffixes: _muedit.mat_edited.mat, _covisi_filtered_muedit.mat_edited.mat
        for suffix in [
            "_muedit.mat_edited.mat",
            "_covisi_filtered_muedit.mat_edited.mat",
            "_multigrid_muedit.mat_edited.mat",
        ]:
            if filename.endswith(suffix):
                return filename[: -len(suffix)]
        return Path(filename).stem

    def _find_matching_json(self, base_name):
        """Find matching JSON file for a base name."""
        for json_path in self.json_files:
            json_filename = os.path.basename(json_path)
            # Check direct match
            if json_filename == f"{base_name}.json":
                return json_path
            # Check filtered version
            if json_filename == f"{base_name}_covisi_filtered.json":
                return json_path
        return None


class PklPostValidationWorker(QThread):
    """Worker thread for computing post-cleaning validation from PKL files."""

    progress = pyqtSignal(int, int, str)
    result = pyqtSignal(str, dict)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, edited_pkl_files, source_pkl_folder=None, parent=None):
        super().__init__(parent)
        self.edited_pkl_files = list(edited_pkl_files)
        self.source_pkl_folder = source_pkl_folder

    def run(self):
        from pathlib import Path as _Path
        from hdsemg_pipe.actions.decomposition_file import DecompositionFile

        overall_report = {
            "files_validated": 0,
            "total_mus_pre": 0,
            "total_mus_post": 0,
            "avg_improvement": [],
            "mus_exceeding_threshold": 0,
            "per_file_reports": {},
        }
        try:
            total = len(self.edited_pkl_files)
            for idx, edited_path in enumerate(self.edited_pkl_files):
                edited_path = _Path(edited_path)
                filename = edited_path.name
                self.progress.emit(idx, total, f"Validating {filename}...")
                try:
                    # Derive source PKL by stripping _edited from stem.
                    # Source files live in source_pkl_folder (upstream), not the scd_edition folder.
                    stem = edited_path.stem
                    source_stem = stem[: -len("_edited")]
                    if self.source_pkl_folder:
                        source_path = _Path(self.source_pkl_folder) / f"{source_stem}.pkl"
                    else:
                        source_path = edited_path.parent / f"{source_stem}.pkl"

                    if not source_path.exists():
                        logger.warning("Source PKL not found: %s", source_path)
                        continue

                    pre_covisi = DecompositionFile.load(source_path).compute_covisi()
                    post_covisi = DecompositionFile.load(edited_path).compute_covisi()

                    comparison = compare_pre_post_covisi(pre_covisi, post_covisi)
                    comparison["source_path"] = str(source_path)
                    comparison["edited_path"] = str(edited_path)

                    self.result.emit(filename, comparison)

                    overall_report["files_validated"] += 1
                    overall_report["total_mus_pre"] += comparison["pre_mu_count"]
                    overall_report["total_mus_post"] += comparison["post_mu_count"]
                    overall_report["mus_exceeding_threshold"] += len(
                        comparison["mus_exceeding_threshold"]
                    )
                    if comparison["avg_improvement_percent"] is not None:
                        overall_report["avg_improvement"].append(
                            comparison["avg_improvement_percent"]
                        )
                    overall_report["per_file_reports"][filename] = comparison

                except Exception as e:
                    logger.error("Failed to validate %s: %s", filename, e)
                    overall_report["per_file_reports"][filename] = {"error": str(e)}

            if overall_report["avg_improvement"]:
                overall_report["avg_improvement_overall"] = np.mean(
                    overall_report["avg_improvement"]
                )
            else:
                overall_report["avg_improvement_overall"] = None

            self.finished.emit(overall_report)

        except Exception as e:
            logger.exception("PklPostValidationWorker failed")
            self.error.emit(f"PKL post-validation failed: {str(e)}")


_RESULTS_TABLE_STYLE = f"""
    QTableWidget {{
        background-color: {Colors.BG_PRIMARY};
        alternate-background-color: {Colors.BG_SECONDARY};
        border: 1px solid {Colors.BORDER_MUTED};
        border-radius: {BorderRadius.MD};
        gridline-color: transparent;
        font-size: {Fonts.SIZE_BASE};
        color: {Colors.TEXT_PRIMARY};
    }}
    QTableWidget::item {{
        padding: 2px {Spacing.MD}px;
    }}
    QTableWidget::item:selected {{
        background-color: {Colors.BLUE_50};
        color: {Colors.TEXT_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: {Colors.BG_SECONDARY};
        color: {Colors.TEXT_SECONDARY};
        padding: 8px {Spacing.MD}px;
        border: none;
        border-bottom: 1px solid {Colors.BORDER_MUTED};
        font-weight: {Fonts.WEIGHT_SEMIBOLD};
        font-size: {Fonts.SIZE_SM};
    }}
"""


def _plain_label(text: str = "", size: str = Fonts.SIZE_BASE, color: str = Colors.TEXT_PRIMARY,
                 weight: str = Fonts.WEIGHT_NORMAL) -> QLabel:
    """QLabel without any inherited frame border/padding."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"QLabel {{ color: {color}; font-size: {size}; font-weight: {weight};"
        " border: none; padding: 0; background: transparent; }"
    )
    return lbl


class _FileNameDelegate(QStyledItemDelegate):
    """Shows file names without the repetitive processing suffix.

    Only the *displayed* text changes; the item keeps the full name (tooltip, CSV export).
    """

    _SUFFIX = re.compile(r"(_covisi_filtered)?(_muedit)?(\.mat)?(_edited)?(\.mat|\.pkl)?$")

    def displayText(self, value, locale):
        return self._SUFFIX.sub("", str(value))


def _configure_results_table(table: QTableWidget, row_height: int = 34) -> None:
    """Shared look for the inline and the expanded results table."""
    table.setStyleSheet(_RESULTS_TABLE_STYLE)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setTextElideMode(Qt.ElideLeft)  # the distinguishing part of a name is at its end
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    table.setItemDelegateForColumn(0, _FileNameDelegate(table))
    # Header alignment follows the cell alignment: MU index / status centred, numbers right
    for col in range(table.columnCount()):
        item = table.horizontalHeaderItem(col)
        if item is not None and col > 0:
            align = Qt.AlignCenter if col in (1, 7) else Qt.AlignRight | Qt.AlignVCenter
            item.setTextAlignment(align)


# Cell colours: light tint + dark text instead of saturated blocks
_GOOD = (QColor(Colors.GREEN_100), QColor(Colors.GREEN_800))
_WARN = (QColor(Colors.YELLOW_100), QColor(Colors.ORANGE_800))
_BAD = (QColor(Colors.RED_100), QColor(Colors.RED_700))


class CoVISIPostValidationWizardWidget(WizardStepWidget):
    """
    Step 9.5: CoVISI Post-Validation.

    This step:
    - Computes CoVISI for cleaned MUs from MUedit
    - Compares with pre-cleaning values
    - Shows improvement metrics
    - Warns about MUs still exceeding threshold
    - Allows filtering, accepting, or returning to MUedit
    """

    def __init__(self, parent=None):
        # Step configuration
        step_index = 12  # After MUEdit (11), before FinalResults (13)
        step_name = "CoVISI Post-Validation"
        description = (
            "Validate motor unit quality after MUedit cleaning. "
            "Compare CoVISI values before and after manual editing."
        )

        super().__init__(step_index, step_name, description, parent)
        self.use_scoped_content_card()

        self.muedit_folder = None  # where edited MAT files live
        self.json_source_folder = None  # where source JSONs live (covisi_filtered or auto)
        self.edited_files = []
        self.json_files = []
        self.edited_pkl_files = []
        self.source_pkl_folder = None  # where unedited source PKLs live (pre-edit)
        self._use_pkl = False
        self.multigrid_skipped_count = 0  # count of multigrid files skipped (not validatable)
        self.fsamp_dict = {}
        self.validation_results = {}
        self.overall_report = None
        self.validation_worker = None
        self._post_reliability_cache: dict = {}  # {filename: {mu_idx: {"sil": float, "pnr": float}}}

        # Create custom UI
        self.create_validation_ui()
        self.content_layout.addWidget(self.validation_container)

        # Perform initial check
        self.check()

    def create_validation_ui(self):
        """Create the validation UI."""
        self.validation_container = QFrame()
        self.validation_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout = QVBoxLayout(self.validation_container)
        container_layout.setSpacing(Spacing.MD)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # Status line (progress and result messages)
        self.status_label = _plain_label(
            "Waiting for MUedit cleaned files...", Fonts.SIZE_SM, Colors.TEXT_SECONDARY
        )
        self.status_label.setWordWrap(True)
        container_layout.addWidget(self.status_label)

        # Progress bar (thin)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                border: none;
                border-radius: 7px;
                text-align: center;
                background-color: {Colors.GRAY_200};
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_XS};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.BLUE_600};
                border-radius: 7px;
            }}
        """
        )
        self.progress_bar.setVisible(False)
        container_layout.addWidget(self.progress_bar)

        # Summary band: four figures that answer "did cleaning help?"
        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("summaryBand")
        self.summary_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.summary_frame.setStyleSheet(
            f"QFrame#summaryBand {{ background: {Colors.BG_SECONDARY}; border: 1px solid {Colors.BORDER_MUTED};"
            f" border-radius: {BorderRadius.LG}; }}"
        )
        summary_layout = QHBoxLayout(self.summary_frame)
        summary_layout.setContentsMargins(Spacing.XL, Spacing.MD, Spacing.XL, Spacing.MD)
        summary_layout.setSpacing(Spacing.XXXL)
        self._summary_values = {}
        for key, caption in (
            ("files", "files validated"),
            ("mus", "MUs before → after cleaning"),
            ("improvement", "average CoVISI improvement"),
            ("exceeding", "still above threshold"),
        ):
            col = QVBoxLayout()
            col.setSpacing(0)
            value = _plain_label("–", "24px", Colors.TEXT_PRIMARY, Fonts.WEIGHT_SEMIBOLD)
            col.addWidget(value)
            col.addWidget(_plain_label(caption, Fonts.SIZE_SM, Colors.TEXT_SECONDARY))
            host = QWidget()
            host.setLayout(col)
            host.setStyleSheet("background: transparent;")
            summary_layout.addWidget(host)
            self._summary_values[key] = value
        summary_layout.addStretch(1)
        self.summary_frame.setVisible(False)
        container_layout.addWidget(self.summary_frame)

        # Warning callout (MUs exceeding the threshold)
        self.warning_frame = QFrame()
        self.warning_frame.setObjectName("warningCallout")
        self.warning_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.warning_frame.setStyleSheet(
            f"QFrame#warningCallout {{ background: {Colors.ORANGE_50}; border: 1px solid {Colors.ORANGE_500};"
            f" border-radius: {BorderRadius.LG}; }}"
        )
        warning_layout = QVBoxLayout(self.warning_frame)
        warning_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        warning_layout.setSpacing(Spacing.XS)
        self.warning_label = _plain_label("", Fonts.SIZE_BASE, Colors.ORANGE_800)
        self.warning_label.setWordWrap(True)
        self.warning_label.setTextFormat(Qt.RichText)
        warning_layout.addWidget(self.warning_label)
        self.warning_frame.setVisible(False)
        container_layout.addWidget(self.warning_frame)

        # Table section: title + actions above the table
        table_section = QFrame()
        table_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_section_layout = QVBoxLayout(table_section)
        table_section_layout.setContentsMargins(0, Spacing.SM, 0, 0)
        table_section_layout.setSpacing(Spacing.SM)

        table_header_row = QHBoxLayout()
        table_header_row.setSpacing(Spacing.MD)

        self.table_header = _plain_label(
            "Pre/post comparison", Fonts.SIZE_LG, Colors.TEXT_PRIMARY, Fonts.WEIGHT_SEMIBOLD
        )
        self.table_header.setVisible(False)
        table_header_row.addWidget(self.table_header)
        table_header_row.addStretch()

        self.btn_export_csv = QPushButton("Export to CSV")
        self.btn_export_csv.setStyleSheet(Styles.button_secondary())
        self.btn_export_csv.setToolTip("Export validation results to CSV file")
        self.btn_export_csv.clicked.connect(self.export_to_csv)
        self.btn_export_csv.setEnabled(False)
        table_header_row.addWidget(self.btn_export_csv)

        self.btn_expand_table = QPushButton("Expand Table")
        self.btn_expand_table.setStyleSheet(Styles.button_secondary())
        self.btn_expand_table.setToolTip("Open table in a resizable window for easier review")
        self.btn_expand_table.clicked.connect(self.open_table_in_window)
        self.btn_expand_table.setEnabled(False)
        table_header_row.addWidget(self.btn_expand_table)

        table_section_layout.addLayout(table_header_row)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.results_table.setColumnCount(8)
        self.results_table.setHorizontalHeaderLabels(
            [
                "File",
                "MU Index",
                "SIL (post)",
                "PNR post (dB)",
                "Pre-CoVISI (%)",
                "Post-CoVISI (%)",
                "Improvement",
                "Status",
            ]
        )
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 8):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.results_table.setSortingEnabled(True)
        _configure_results_table(self.results_table)
        self.results_table.setMinimumHeight(440)
        self.results_table.setVisible(False)
        table_section_layout.addWidget(self.results_table, stretch=1)

        container_layout.addWidget(table_section, stretch=1)

    def create_buttons(self):
        """Create buttons for this step."""
        self.btn_validate = QPushButton("Run Validation")
        self.btn_validate.setStyleSheet(Styles.button_secondary())
        self.btn_validate.setToolTip("Compare CoVISI before and after MUedit cleaning")
        self.btn_validate.clicked.connect(self.start_validation)
        self.btn_validate.setEnabled(False)
        self.buttons.append(self.btn_validate)

        self.btn_accept = QPushButton("Accept All && Continue")
        self.btn_accept.setStyleSheet(Styles.button_primary())
        self.btn_accept.setToolTip("Accept all MUs and proceed to final results")
        self.btn_accept.clicked.connect(self.accept_and_continue)
        self.btn_accept.setEnabled(False)
        self.buttons.append(self.btn_accept)

        self.btn_filter = QPushButton("Filter Failing MUs")
        self.btn_filter.setStyleSheet(Styles.button_secondary())
        self.btn_filter.setToolTip(
            "Remove MUs still exceeding CoVISI threshold after cleaning"
        )
        self.btn_filter.clicked.connect(self.filter_failing_mus)
        self.btn_filter.setEnabled(False)
        self.btn_filter.setVisible(False)  # Only show if there are failing MUs
        self.buttons.append(self.btn_filter)

        self.btn_return_muedit = QPushButton("Return to MUedit")
        self.btn_return_muedit.setStyleSheet(Styles.button_secondary())
        self.btn_return_muedit.setToolTip("Go back to MUedit for further cleaning")
        self.btn_return_muedit.clicked.connect(self.return_to_muedit)
        self.btn_return_muedit.setEnabled(False)
        self.buttons.append(self.btn_return_muedit)

    def check(self):
        """Check if this step can be activated."""
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        self.muedit_folder = global_state.get_decomposition_muedit_path()
        self._update_json_source_folder()
        self._use_pkl = (read_manual_cleaning_tool() == "scd_edition")

        if not OPENHDEMG_AVAILABLE and not self._use_pkl:
            self.status_label.setText(
                "⚠️ openhdemg library not available. Validation disabled."
            )
            return False

        # Check if previous step (MUedit) is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        # Scan for edited files
        self.scan_files()

        return True

    def _update_json_source_folder(self):
        """Determine whether to read JSONs from covisi_filtered or decomposition_auto."""
        covisi_folder = global_state.get_decomposition_covisi_filtered_path()

        # Primary check: step state
        covisi_applied_by_state = (
            global_state.is_widget_completed("step9")
            and not global_state.is_widget_skipped("step9")
        )

        # Fallback check: physical folder evidence
        covisi_applied_by_folder = os.path.exists(covisi_folder) and any(
            f.endswith('_covisi_filtered.json') for f in os.listdir(covisi_folder)
        )

        if (covisi_applied_by_state or covisi_applied_by_folder) and os.path.exists(covisi_folder):
            self.json_source_folder = covisi_folder
        else:
            self.json_source_folder = global_state.get_decomposition_path()  # decomposition_auto

    def scan_files(self):
        """Scan for edited files and corresponding source files."""
        if self._use_pkl:
            self._scan_pkl_files()
            return

        if not os.path.exists(self.muedit_folder):
            self.status_label.setText("MUEdit folder not found.")
            return

        # All edited MAT files now live in decomposition_muedit/ (new design).
        # Skip multigrid files (no 1:1 JSON match; merged files can't be validated against originals).
        self.edited_files = [
            os.path.join(self.muedit_folder, f)
            for f in os.listdir(self.muedit_folder)
            if f.endswith("_edited.mat") and "_multigrid_muedit.mat" not in f
        ]

        # Count skipped multigrid files for user info
        self.multigrid_skipped_count = sum(
            1 for f in os.listdir(self.muedit_folder)
            if f.endswith("_edited.mat") and "_multigrid_muedit.mat" in f
        ) if os.path.exists(self.muedit_folder) else 0

        if self.multigrid_skipped_count > 0:
            logger.info(
                f"Skipping {self.multigrid_skipped_count} multigrid file(s) "
                "(merged files cannot be validated against original JSONs)"
            )

        # Find JSON files for pre-cleaning comparison.
        # Read from covisi_filtered/ if CoVISI was applied, else decomposition_auto/
        state_files = {
            "decomposition_mapping.json",
            "multigrid_groupings.json",
            "covisi_pre_filter_report.json",
            "covisi_post_validation_report.json",
        }

        if self.json_source_folder and os.path.exists(self.json_source_folder):
            self.json_files = [
                os.path.join(self.json_source_folder, f)
                for f in os.listdir(self.json_source_folder)
                if f.endswith(".json") and f not in state_files and not f.startswith("algorithm_params")
            ]
        else:
            self.json_files = []

        # Load sampling frequencies from JSON files
        # Optimized: Read only FSAMP field directly from JSON without loading entire EMG file
        self.fsamp_dict = {}
        for json_path in self.json_files:
            try:
                import json
                import gzip
                # Try gzip-compressed format first (standard for openhdemg JSON files)
                try:
                    with gzip.open(json_path, 'rt', encoding='utf-8') as f:
                        data = json.load(f)
                        self.fsamp_dict[json_path] = data.get("FSAMP", 2048.0)
                except (gzip.BadGzipFile, OSError):
                    # Fall back to plain text JSON if not gzip-compressed
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.fsamp_dict[json_path] = data.get("FSAMP", 2048.0)
            except Exception as e:
                logger.warning(f"Could not read FSAMP from {json_path}: {e}")
                self.fsamp_dict[json_path] = 2048.0

        if self.edited_files:
            msg = f"Found {len(self.edited_files)} edited file(s). Click 'Run Validation' to compare CoVISI values."
            if self.multigrid_skipped_count > 0:
                msg += f" ({self.multigrid_skipped_count} multigrid file(s) skipped)"
            self.status_label.setText(msg)
            self.btn_validate.setEnabled(True)
            self.btn_accept.setEnabled(True)
            self.btn_return_muedit.setEnabled(True)
        else:
            msg = "No single-grid edited files found for validation."
            if self.multigrid_skipped_count > 0:
                msg += f" ({self.multigrid_skipped_count} multigrid file(s) skipped)"
            self.status_label.setText(msg)
            self.btn_validate.setEnabled(False)
            self.btn_accept.setEnabled(False)
            self.btn_return_muedit.setEnabled(False)

    def _scan_pkl_files(self):
        """Scan for edited PKL files for scd-edition post-validation."""
        scd_edition_folder = global_state.get_decomposition_scd_edition_path()
        removed_dups = global_state.get_decomposition_removed_duplicates_path()
        covisi_filtered = global_state.get_decomposition_covisi_filtered_path()
        auto_folder = global_state.get_decomposition_path()

        # scd-edition always writes edited PKL files to the scd_edition folder.
        # Source (pre-edit) PKLs live in the upstream folder (removed_dups > covisi_filtered > auto).
        edited_dir = None
        if scd_edition_folder and os.path.isdir(scd_edition_folder) and any(
            f.endswith("_edited.pkl") for f in os.listdir(scd_edition_folder)
        ):
            edited_dir = scd_edition_folder
        elif removed_dups and os.path.isdir(removed_dups) and any(
            f.endswith("_edited.pkl") for f in os.listdir(removed_dups)
        ):
            edited_dir = removed_dups
        elif covisi_filtered and os.path.isdir(covisi_filtered) and any(
            f.endswith("_edited.pkl") for f in os.listdir(covisi_filtered)
        ):
            edited_dir = covisi_filtered

        # Determine source (unedited) PKL folder — highest priority upstream folder that exists.
        if removed_dups and os.path.isdir(removed_dups) and any(
            f.endswith("_duplicates_removed.pkl") for f in os.listdir(removed_dups)
        ):
            self.source_pkl_folder = removed_dups
        elif covisi_filtered and os.path.isdir(covisi_filtered) and any(
            f.endswith("_covisi_filtered.pkl") for f in os.listdir(covisi_filtered)
        ):
            self.source_pkl_folder = covisi_filtered
        elif auto_folder and os.path.isdir(auto_folder):
            self.source_pkl_folder = auto_folder
        else:
            self.source_pkl_folder = None

        self.edited_pkl_files = []
        if edited_dir:
            logger.info(f"Scanning for edited PKL files in {edited_dir}...")
            self.edited_pkl_files = [
                os.path.join(edited_dir, f)
                for f in os.listdir(edited_dir)
                if f.endswith("_edited.pkl")
            ]

        if self.edited_pkl_files:
            self.status_label.setText(
                f"Found {len(self.edited_pkl_files)} edited PKL file(s). "
                "Click 'Run Validation' to compare CoVISI values."
            )
            self.btn_validate.setEnabled(True)
            self.btn_accept.setEnabled(True)
            self.btn_return_muedit.setEnabled(True)
        else:
            self.status_label.setText("No edited PKL files found for validation.")
            self.btn_validate.setEnabled(False)
            self.btn_accept.setEnabled(False)
            self.btn_return_muedit.setEnabled(False)

    def start_validation(self):
        """Start the validation process."""
        if self._use_pkl:
            self._start_pkl_validation()
            return

        if not self.edited_files:
            self.warn("No edited files to validate.")
            return

        # Disable buttons
        self.btn_validate.setEnabled(False)
        self.btn_accept.setEnabled(False)
        self.btn_filter.setEnabled(False)
        self.btn_return_muedit.setEnabled(False)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.edited_files))

        # Clear previous results
        self.validation_results.clear()
        self.results_table.setRowCount(0)
        self.summary_frame.setVisible(False)
        self.warning_frame.setVisible(False)

        # Start worker
        self.validation_worker = PostValidationWorker(
            self.edited_files, self.json_files, self.fsamp_dict
        )
        self.validation_worker.progress.connect(self.on_validation_progress)
        self.validation_worker.result.connect(self.on_validation_result)
        self.validation_worker.finished.connect(self.on_validation_finished)
        self.validation_worker.error.connect(self.on_validation_error)
        self.validation_worker.start()

        logger.info(
            f"Starting post-validation for {len(self.edited_files)} file(s)..."
        )

    def _start_pkl_validation(self):
        """Start post-validation for PKL files (scd-edition path)."""
        if not self.edited_pkl_files:
            self.warn("No edited PKL files to validate.")
            return

        self.btn_validate.setEnabled(False)
        self.btn_accept.setEnabled(False)
        self.btn_filter.setEnabled(False)
        self.btn_return_muedit.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.edited_pkl_files))

        self.validation_results.clear()
        self.results_table.setRowCount(0)
        self.summary_frame.setVisible(False)
        self.warning_frame.setVisible(False)

        self.validation_worker = PklPostValidationWorker(self.edited_pkl_files, self.source_pkl_folder)
        self.validation_worker.progress.connect(self.on_validation_progress)
        self.validation_worker.result.connect(self.on_validation_result)
        self.validation_worker.finished.connect(self.on_validation_finished)
        self.validation_worker.error.connect(self.on_validation_error)
        self.validation_worker.start()

        logger.info("Starting PKL post-validation for %d file(s)...", len(self.edited_pkl_files))

    def _load_post_reliability(self, file_path: str, filename: str) -> dict:
        """Compute SIL/PNR for a post-cleaning file (cached)."""
        if filename in self._post_reliability_cache:
            return self._post_reliability_cache[filename]
        result = {}
        try:
            from hdsemg_pipe.actions.decomposition_file import (
                DecompositionFile,
                ReliabilityThresholds,
            )
            dec = DecompositionFile.load(Path(file_path))
            thresholds = ReliabilityThresholds()  # defaults for display only
            df = dec.compute_reliability(thresholds)
            for _, row in df.iterrows():
                result[int(row["mu_index"])] = {
                    "sil": float(row["sil"]),
                    "pnr": float(row["pnr"]),
                }
        except Exception as exc:
            logger.warning("Post-reliability computation failed for %s: %s", filename, exc)
        self._post_reliability_cache[filename] = result
        return result

    def on_validation_progress(self, current, total, message):
        """Handle validation progress."""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def on_validation_result(self, filename, comparison):
        """Handle validation result for one file."""
        self.validation_results[filename] = comparison

        # Show table and header
        self.table_header.setVisible(True)
        self.results_table.setVisible(True)

        # Temporarily disable sorting to add rows
        self.results_table.setSortingEnabled(False)

        for detail in comparison.get("comparison_details", []):
            table_row = self.results_table.rowCount()
            self.results_table.insertRow(table_row)

            # File name
            file_item = QTableWidgetItem(filename)
            file_item.setToolTip(filename)
            self.results_table.setItem(table_row, 0, file_item)

            # MU index - use setData for proper numeric sorting
            mu_item = QTableWidgetItem()
            mu_item.setData(Qt.DisplayRole, int(detail["mu_index"]))
            mu_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(table_row, 1, mu_item)

            # SIL and PNR (post-cleaning)
            edited_path = comparison.get("edited_path", "")
            post_rel = self._load_post_reliability(edited_path, filename)
            mu_rel = post_rel.get(int(detail["mu_index"]), {})
            sil_val = mu_rel.get("sil", float("nan"))
            pnr_val = mu_rel.get("pnr", float("nan"))

            sil_item = QTableWidgetItem()
            if not math.isnan(sil_val):
                sil_item.setData(Qt.EditRole, float(sil_val))
                sil_item.setData(Qt.DisplayRole, f"{sil_val:.3f}")
            else:
                sil_item.setText("N/A")
            sil_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(table_row, 2, sil_item)

            pnr_item = QTableWidgetItem()
            if not math.isnan(pnr_val):
                pnr_item.setData(Qt.EditRole, float(pnr_val))
                pnr_item.setData(Qt.DisplayRole, f"{pnr_val:.1f}")
            else:
                pnr_item.setText("N/A")
            pnr_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(table_row, 3, pnr_item)

            # Pre-CoVISI - use setData for proper numeric sorting
            pre_val = detail["covisi_pre"]
            pre_item = QTableWidgetItem()
            if pd.notna(pre_val):
                display_text = f"{round(pre_val, 1)}"
                pre_item.setData(Qt.EditRole, float(pre_val))
                pre_item.setData(Qt.DisplayRole, display_text)
            else:
                pre_item.setText("N/A")
            pre_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(table_row, 4, pre_item)

            # Post-CoVISI - use setData for proper numeric sorting
            post_val = detail["covisi_post"]
            post_item = QTableWidgetItem()
            if pd.notna(post_val):
                display_text = f"{round(post_val, 1)}"
                post_item.setData(Qt.EditRole, float(post_val))
                post_item.setData(Qt.DisplayRole, display_text)
            else:
                post_item.setText("N/A")
            post_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Color code post value
            if pd.notna(post_val):
                if post_val <= DEFAULT_COVISI_THRESHOLD:
                    bg, fg = _GOOD
                elif post_val <= 50.0:
                    bg, fg = _WARN
                else:
                    bg, fg = _BAD
                post_item.setBackground(bg)
                post_item.setForeground(fg)

            self.results_table.setItem(table_row, 5, post_item)

            # Improvement - use setData for proper numeric sorting
            improvement = detail["improvement_percent"]
            improvement_item = QTableWidgetItem()
            if pd.notna(improvement):
                display_text = f"{round(improvement, 1)}"
                improvement_item.setData(Qt.EditRole, float(improvement))
                improvement_item.setData(Qt.DisplayRole, display_text)
                if improvement > 0:
                    improvement_item.setForeground(QColor(Colors.GREEN_700))
                elif improvement < 0:
                    improvement_item.setForeground(QColor(Colors.RED_600))
            else:
                improvement_item.setText("N/A")
            improvement_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(table_row, 6, improvement_item)

            # Status
            if detail["exceeds_threshold"]:
                status_item = QTableWidgetItem("Exceeds")
                status_item.setForeground(QColor(Colors.RED_600))
            else:
                status_item = QTableWidgetItem("Pass")
                status_item.setForeground(QColor(Colors.GREEN_700))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(table_row, 7, status_item)

        # Re-enable sorting
        self.results_table.setSortingEnabled(True)

    def on_validation_finished(self, overall_report):
        """Handle validation completion."""
        self.progress_bar.setVisible(False)
        self.overall_report = overall_report

        # Update summary
        self.summary_frame.setVisible(True)
        failing_count = overall_report["mus_exceeding_threshold"]
        improvement = overall_report["avg_improvement_overall"]
        self._summary_values["files"].setText(str(overall_report["files_validated"]))
        self._summary_values["mus"].setText(
            f"{overall_report['total_mus_pre']} → {overall_report['total_mus_post']}"
        )
        self._summary_values["improvement"].setText("–" if improvement is None else f"{improvement:.1f}%")
        self._summary_values["exceeding"].setText(str(failing_count))
        self._summary_values["exceeding"].setStyleSheet(
            f"QLabel {{ color: {Colors.RED_600 if failing_count else Colors.GREEN_700}; font-size: 24px;"
            f" font-weight: {Fonts.WEIGHT_SEMIBOLD}; border: none; padding: 0; background: transparent; }}"
        )

        # Show warning if there are failing MUs
        if failing_count > 0:
            self.warning_frame.setVisible(True)
            self.warning_label.setText(
                f"<b>{failing_count} motor unit(s) still exceed the {DEFAULT_COVISI_THRESHOLD}% "
                f"CoVISI threshold after cleaning.</b><br>"
                "Accept All keeps them (they may be valid despite a high CoVISI), "
                "Filter Failing removes them, Return to MUedit cleans further."
            )
            self.btn_filter.setVisible(True)
            self.btn_filter.setEnabled(True)
        else:
            self.warning_frame.setVisible(False)
            self.btn_filter.setVisible(False)

        # Enable buttons
        self.btn_validate.setEnabled(True)
        self.btn_accept.setEnabled(True)
        self.btn_return_muedit.setEnabled(True)
        self.btn_export_csv.setEnabled(len(self.validation_results) > 0)
        self.btn_expand_table.setEnabled(len(self.validation_results) > 0)

        self.status_label.setText(
            f"Validation complete. {overall_report['files_validated']} file(s) analyzed."
        )

        self.success("Post-validation complete.")

    def on_validation_error(self, error_msg):
        """Handle validation error."""
        self.progress_bar.setVisible(False)
        self.btn_validate.setEnabled(True)
        self.btn_accept.setEnabled(True)
        self.btn_return_muedit.setEnabled(True)

        self.error(error_msg)
        self.status_label.setText(f"Error: {error_msg}")

    def _get_report_path(self):
        """Return the correct folder for the post-validation report depending on cleaning tool."""
        if self._use_pkl:
            folder = global_state.get_decomposition_scd_edition_path()
        else:
            folder = global_state.get_decomposition_path()
        return os.path.join(folder, "covisi_post_validation_report.json")

    def accept_and_continue(self):
        """Accept all MUs and proceed to final results."""
        # Save validation report
        report = self.overall_report or {
            "validation_skipped": True,
            "reason": "User accepted without running validation",
        }
        report["action"] = "accepted_all"

        report_path = self._get_report_path()
        save_covisi_report(report, report_path, report_type="post_validation")

        self.info("All MUs accepted. Proceeding to final results.")
        self.status_label.setText("✓ Validation complete. Proceeding to final results.")

        self.complete_step()

    def filter_failing_mus(self):
        """Filter out MUs still exceeding threshold."""
        if not self.overall_report:
            self.warn("Please run validation first.")
            return

        # TODO: Implement filtering of failing MUs from edited files
        # This would require modifying the edited MAT files or
        # creating a list of MUs to exclude during final conversion

        # For now, save the report with filtering info
        report = self.overall_report.copy()
        report["action"] = "filtered_failing"
        report["mus_to_exclude"] = []

        for filename, comparison in report.get("per_file_reports", {}).items():
            if isinstance(comparison, dict) and "comparison_details" in comparison:
                for detail in comparison["comparison_details"]:
                    if detail.get("exceeds_threshold", False):
                        report["mus_to_exclude"].append(
                            {"file": filename, "mu_index": detail["mu_index"]}
                        )

        report_path = self._get_report_path()
        save_covisi_report(report, report_path, report_type="post_validation")

        self.info(
            f"Marked {len(report['mus_to_exclude'])} MU(s) for exclusion. "
            "These will be filtered during final conversion."
        )
        self.status_label.setText(
            f"✓ {len(report['mus_to_exclude'])} MU(s) marked for filtering."
        )

        self.complete_step()

    def return_to_muedit(self):
        """Return to MUedit step for further cleaning."""
        # Go back to previous step
        self.info("Returning to MUedit for further cleaning.")

        # Signal to go back (the main window handles navigation)
        # For now, just don't complete this step
        self.status_label.setText(
            "Please clean the motor units further in MUedit, then return here."
        )

    def export_to_csv(self):
        """Export validation results to CSV file."""
        if not self.validation_results:
            self.warn("No validation results to export. Run validation first.")
            return

        # Get analysis folder path
        analysis_folder = os.path.join(global_state.workfolder, "analysis")
        if not os.path.exists(analysis_folder):
            os.makedirs(analysis_folder)
            logger.info(f"Created analysis folder: {analysis_folder}")

        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"covisi_post_validation_{timestamp}.csv"
        default_path = os.path.join(analysis_folder, default_filename)

        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Validation Results to CSV",
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
                    "SIL (post)",
                    "PNR post (dB)",
                    "Pre-CoVISI (%)",
                    "Post-CoVISI (%)",
                    "Improvement (%)",
                    "Status",
                    "Threshold (%)",
                ])

                # Write data from table
                for row_idx in range(self.results_table.rowCount()):
                    file_name = self.results_table.item(row_idx, 0).text()
                    mu_index = self.results_table.item(row_idx, 1).data(Qt.DisplayRole)

                    sil_item = self.results_table.item(row_idx, 2)
                    sil_val = sil_item.data(Qt.DisplayRole) if sil_item.data(Qt.DisplayRole) is not None else sil_item.text()

                    pnr_item = self.results_table.item(row_idx, 3)
                    pnr_val = pnr_item.data(Qt.DisplayRole) if pnr_item.data(Qt.DisplayRole) is not None else pnr_item.text()

                    # Handle potential N/A values
                    pre_item = self.results_table.item(row_idx, 4)
                    pre_val = pre_item.data(Qt.DisplayRole) if pre_item.data(Qt.DisplayRole) is not None else pre_item.text()

                    post_item = self.results_table.item(row_idx, 5)
                    post_val = post_item.data(Qt.DisplayRole) if post_item.data(Qt.DisplayRole) is not None else post_item.text()

                    improvement_item = self.results_table.item(row_idx, 6)
                    improvement_val = improvement_item.data(Qt.DisplayRole) if improvement_item.data(Qt.DisplayRole) is not None else improvement_item.text()

                    status = self.results_table.item(row_idx, 7).text()

                    writer.writerow([
                        file_name,
                        mu_index,
                        sil_val,
                        pnr_val,
                        pre_val,
                        post_val,
                        improvement_val,
                        status,
                        DEFAULT_COVISI_THRESHOLD,
                    ])

            self.success(f"Exported validation results to {os.path.basename(file_path)}")
            logger.info(f"Exported CoVISI post-validation results to: {file_path}")

        except Exception as e:
            self.error(f"Failed to export CSV: {str(e)}")
            logger.error(f"Failed to export CSV: {e}")

    def open_table_in_window(self):
        """Open the results table in a separate resizable dialog window."""
        if self.results_table.rowCount() == 0:
            self.warn("No data to display. Run validation first.")
            return

        # Create modeless dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("CoVISI Post-Validation Results")
        dialog.setModal(False)
        dialog.resize(900, 600)

        # Main layout
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setSpacing(Spacing.MD)
        dialog_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        # Header label
        header_label = QLabel("Pre/Post Comparison Results")
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
            [
                "File",
                "MU Index",
                "SIL (post)",
                "PNR post (dB)",
                "Pre-CoVISI (%)",
                "Post-CoVISI (%)",
                "Improvement",
                "Status",
            ]
        )
        expanded_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 8):
            expanded_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeToContents
            )
        expanded_table.setSortingEnabled(True)
        _configure_results_table(expanded_table)

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
        use_pkl = (read_manual_cleaning_tool() == "scd_edition")
        if use_pkl:
            folder = global_state.get_decomposition_scd_edition_path()
        else:
            folder = global_state.get_decomposition_path()
        if not folder:
            return False
        report_path = os.path.join(folder, "covisi_post_validation_report.json")
        return os.path.exists(report_path)

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.muedit_folder = global_state.get_decomposition_muedit_path()
        self._update_json_source_folder()
        self._use_pkl = (read_manual_cleaning_tool() == "scd_edition")
        self.scan_files()

        if self.is_completed():
            logger.info("CoVISI post-validation step already completed (report exists)")
