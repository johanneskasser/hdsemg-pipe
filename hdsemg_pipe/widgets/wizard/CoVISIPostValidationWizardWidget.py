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
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from PyQt5.QtCore import QThread, pyqtSignal, Qt
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
        step_index = 11  # After MUEdit (10), before FinalResults (12)
        step_name = "CoVISI Post-Validation"
        description = (
            "Validate motor unit quality after MUedit cleaning. "
            "Compare CoVISI values before and after manual editing."
        )

        super().__init__(step_index, step_name, description, parent)

        self.expected_folder = None
        self.edited_files = []
        self.json_files = []
        self.fsamp_dict = {}
        self.validation_results = {}
        self.overall_report = None
        self.validation_worker = None

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

        # Status label
        self.status_label = QLabel("Waiting for MUedit cleaned files...")
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

        # Summary and warning row
        info_row = QHBoxLayout()
        info_row.setSpacing(Spacing.MD)

        # Summary panel
        self.summary_frame = QFrame()
        self.summary_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.summary_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
            }}
        """
        )
        summary_layout = QVBoxLayout(self.summary_frame)
        summary_layout.setSpacing(Spacing.SM)

        self.summary_title = QLabel("Validation Summary")
        self.summary_title.setStyleSheet(
            f"font-weight: {Fonts.WEIGHT_BOLD}; font-size: {Fonts.SIZE_LG}; color: {Colors.TEXT_PRIMARY};"
        )
        summary_layout.addWidget(self.summary_title)

        self.summary_content = QLabel("")
        self.summary_content.setWordWrap(True)
        self.summary_content.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_BASE};")
        summary_layout.addWidget(self.summary_content)

        self.summary_frame.setVisible(False)
        info_row.addWidget(self.summary_frame)

        # Warning panel (for MUs exceeding threshold)
        self.warning_frame = QFrame()
        self.warning_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.warning_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: #FEF3C7;
                border: 1px solid #F59E0B;
                border-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
            }}
        """
        )
        warning_layout = QVBoxLayout(self.warning_frame)
        warning_layout.setSpacing(Spacing.SM)

        warning_title = QLabel("Warning")
        warning_title.setStyleSheet(f"font-weight: {Fonts.WEIGHT_BOLD}; font-size: {Fonts.SIZE_LG}; color: #92400E;")
        warning_layout.addWidget(warning_title)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(f"color: #92400E; font-size: {Fonts.SIZE_BASE};")
        warning_layout.addWidget(self.warning_label)

        self.warning_frame.setVisible(False)
        info_row.addWidget(self.warning_frame)

        container_layout.addLayout(info_row)

        # Progress bar
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

        # Table section with header and export button
        table_section = QFrame()
        table_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_section_layout = QVBoxLayout(table_section)
        table_section_layout.setContentsMargins(0, 0, 0, 0)
        table_section_layout.setSpacing(Spacing.SM)

        # Table header row
        table_header_row = QHBoxLayout()
        table_header_row.setSpacing(Spacing.MD)

        self.table_header = QLabel("Pre/Post Comparison Results")
        self.table_header.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
        """
        )
        self.table_header.setVisible(False)
        table_header_row.addWidget(self.table_header)

        table_header_row.addStretch()

        # Export button
        self.btn_export_csv = QPushButton("Export to CSV")
        self.btn_export_csv.setStyleSheet(Styles.button_secondary())
        self.btn_export_csv.setToolTip("Export validation results to CSV file")
        self.btn_export_csv.clicked.connect(self.export_to_csv)
        self.btn_export_csv.setEnabled(False)
        table_header_row.addWidget(self.btn_export_csv)

        table_section_layout.addLayout(table_header_row)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(
            [
                "File",
                "MU Index",
                "Pre-CoVISI (%)",
                "Post-CoVISI (%)",
                "Improvement",
                "Status",
            ]
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        for col in range(1, 6):
            self.results_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeToContents
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

        self.btn_accept = QPushButton("Accept All & Continue")
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

        self.expected_folder = global_state.get_decomposition_path()

        if not OPENHDEMG_AVAILABLE:
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

    def scan_files(self):
        """Scan for edited MAT files and corresponding JSON files."""
        if not os.path.exists(self.expected_folder):
            self.status_label.setText("Decomposition folder not found.")
            return

        # Find edited MAT files
        self.edited_files = [
            os.path.join(self.expected_folder, f)
            for f in os.listdir(self.expected_folder)
            if f.endswith("_edited.mat")
        ]

        # Find JSON files (for pre-cleaning comparison)
        state_files = {
            "decomposition_mapping.json",
            "multigrid_groupings.json",
            "covisi_pre_filter_report.json",
            "covisi_post_validation_report.json",
        }

        self.json_files = [
            os.path.join(self.expected_folder, f)
            for f in os.listdir(self.expected_folder)
            if f.endswith(".json") and f not in state_files
        ]

        # Load sampling frequencies from JSON files
        self.fsamp_dict = {}
        for json_path in self.json_files:
            try:
                emgfile = emg.emg_from_json(str(json_path))
                self.fsamp_dict[json_path] = emgfile.get("FSAMP", 2048.0)
            except Exception as e:
                logger.warning(f"Could not read FSAMP from {json_path}: {e}")
                self.fsamp_dict[json_path] = 2048.0

        if self.edited_files:
            self.status_label.setText(
                f"Found {len(self.edited_files)} edited file(s). "
                "Click 'Run Validation' to compare CoVISI values."
            )
            self.btn_validate.setEnabled(True)
            self.btn_accept.setEnabled(True)
            self.btn_return_muedit.setEnabled(True)
        else:
            self.status_label.setText("No edited MUedit files found.")
            self.btn_validate.setEnabled(False)
            self.btn_accept.setEnabled(False)
            self.btn_return_muedit.setEnabled(False)

    def start_validation(self):
        """Start the validation process."""
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
            self.results_table.setItem(table_row, 0, file_item)

            # MU index - use setData for proper numeric sorting
            mu_item = QTableWidgetItem()
            mu_item.setData(Qt.DisplayRole, int(detail["mu_index"]))
            mu_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(table_row, 1, mu_item)

            # Pre-CoVISI - use setData for proper numeric sorting
            pre_val = detail["covisi_pre"]
            pre_item = QTableWidgetItem()
            if pd.notna(pre_val):
                pre_item.setData(Qt.DisplayRole, round(pre_val, 1))
            else:
                pre_item.setText("N/A")
            pre_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(table_row, 2, pre_item)

            # Post-CoVISI - use setData for proper numeric sorting
            post_val = detail["covisi_post"]
            post_item = QTableWidgetItem()
            if pd.notna(post_val):
                post_item.setData(Qt.DisplayRole, round(post_val, 1))
            else:
                post_item.setText("N/A")
            post_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Color code post value
            if pd.notna(post_val):
                if post_val <= DEFAULT_COVISI_THRESHOLD:
                    post_item.setBackground(Qt.darkGreen)
                    post_item.setForeground(Qt.white)
                elif post_val <= 50.0:
                    post_item.setBackground(Qt.darkYellow)
                    post_item.setForeground(Qt.black)
                else:
                    post_item.setBackground(Qt.darkRed)
                    post_item.setForeground(Qt.white)

            self.results_table.setItem(table_row, 3, post_item)

            # Improvement - use setData for proper numeric sorting
            improvement = detail["improvement_percent"]
            improvement_item = QTableWidgetItem()
            if pd.notna(improvement):
                improvement_item.setData(Qt.DisplayRole, round(improvement, 1))
                if improvement > 0:
                    improvement_item.setForeground(Qt.darkGreen)
                elif improvement < 0:
                    improvement_item.setForeground(Qt.red)
            else:
                improvement_item.setText("N/A")
            improvement_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(table_row, 4, improvement_item)

            # Status
            if detail["exceeds_threshold"]:
                status_item = QTableWidgetItem("Exceeds")
                status_item.setForeground(Qt.red)
            else:
                status_item = QTableWidgetItem("Pass")
                status_item.setForeground(Qt.darkGreen)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(table_row, 5, status_item)

        # Re-enable sorting
        self.results_table.setSortingEnabled(True)

    def on_validation_finished(self, overall_report):
        """Handle validation completion."""
        self.progress_bar.setVisible(False)
        self.overall_report = overall_report

        # Update summary
        self.summary_frame.setVisible(True)
        summary_lines = [
            f"Files validated: {overall_report['files_validated']}",
            f"Total MUs (pre-cleaning): {overall_report['total_mus_pre']}",
            f"Total MUs (post-cleaning): {overall_report['total_mus_post']}",
        ]

        if overall_report["avg_improvement_overall"] is not None:
            summary_lines.append(
                f"Average CoVISI improvement: {overall_report['avg_improvement_overall']:.1f}%"
            )

        self.summary_content.setText("\n".join(summary_lines))

        # Show warning if there are failing MUs
        failing_count = overall_report["mus_exceeding_threshold"]
        if failing_count > 0:
            self.warning_frame.setVisible(True)
            self.warning_label.setText(
                f"{failing_count} motor unit(s) still exceed the {DEFAULT_COVISI_THRESHOLD}% "
                f"CoVISI threshold after cleaning.\n\n"
                "Options:\n"
                "• Accept All: Keep these MUs (may be valid despite high CoVISI)\n"
                "• Filter Failing: Remove MUs exceeding threshold\n"
                "• Return to MUedit: Clean further in MUedit"
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

    def accept_and_continue(self):
        """Accept all MUs and proceed to final results."""
        # Save validation report
        report = self.overall_report or {
            "validation_skipped": True,
            "reason": "User accepted without running validation",
        }
        report["action"] = "accepted_all"

        report_path = os.path.join(
            self.expected_folder, "covisi_post_validation_report.json"
        )
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

        report_path = os.path.join(
            self.expected_folder, "covisi_post_validation_report.json"
        )
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

                    # Handle potential N/A values
                    pre_item = self.results_table.item(row_idx, 2)
                    pre_val = pre_item.data(Qt.DisplayRole) if pre_item.data(Qt.DisplayRole) is not None else pre_item.text()

                    post_item = self.results_table.item(row_idx, 3)
                    post_val = post_item.data(Qt.DisplayRole) if post_item.data(Qt.DisplayRole) is not None else post_item.text()

                    improvement_item = self.results_table.item(row_idx, 4)
                    improvement_val = improvement_item.data(Qt.DisplayRole) if improvement_item.data(Qt.DisplayRole) is not None else improvement_item.text()

                    status = self.results_table.item(row_idx, 5).text()

                    writer.writerow([
                        file_name,
                        mu_index,
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

    def is_completed(self):
        """Check if this step is completed."""
        report_path = os.path.join(
            self.expected_folder, "covisi_post_validation_report.json"
        )
        return os.path.exists(report_path)

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.expected_folder = global_state.get_decomposition_path()
        self.scan_files()

        if self.is_completed():
            logger.info("CoVISI post-validation step already completed (report exists)")
