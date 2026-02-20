"""
Step 10: Remove Duplicate MUs (Within/Between Grids)

This step detects and removes duplicate motor units within and between grids using
a Python implementation of MUEdit's remduplicatesbgrids algorithm.

Users can review duplicates visually and decide which MUs to remove.
This step is optional and skippable.
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.widgets.GridGroupingDialog import GridGroupingDialog
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts
from hdsemg_pipe.actions.duplicate_detection import (
    detect_duplicates_in_group,
    remove_duplicates_from_emgfiles,
    save_cleaned_jsons,
    get_discharge_times,
)
from hdsemg_pipe.actions.decomposition_export import create_emgfile_groups

try:
    import openhdemg.library as emg
    OPENHDEMG_AVAILABLE = True
except ImportError:
    emg = None
    OPENHDEMG_AVAILABLE = False
    logger.warning("openhdemg not available - duplicate detection will not work")


# ============================================================================
# WORKER THREAD
# ============================================================================

class DuplicateDetectionWorker(QThread):
    """Worker thread for duplicate detection."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(dict)  # detection_results
    error = pyqtSignal(str)

    def __init__(self, groups, maxlag, jitter, tol, fsamp=None, parent=None):
        super().__init__(parent)
        self.groups = groups  # Output from create_emgfile_groups
        self.maxlag = maxlag
        self.jitter = jitter
        self.tol = tol
        self.fsamp = fsamp

    def run(self):
        """Run duplicate detection on all groups."""
        if not OPENHDEMG_AVAILABLE or emg is None:
            self.error.emit("openhdemg library is not available. Please install it first.")
            return

        try:
            all_results = {
                'groups': [],
                'total_duplicate_groups': 0,
                'total_mus_to_remove': 0,
                'total_files': 0
            }

            for idx, group_info in enumerate(self.groups):
                group_name = group_info['name']
                json_paths = group_info['files']

                self.progress.emit(
                    idx, len(self.groups),
                    f"Detecting duplicates in {group_name}..."
                )

                # Load JSON files
                emgfile_list = []
                for json_path in json_paths:
                    try:
                        emgfile = emg.emg_from_json(str(json_path))
                        emgfile_list.append(emgfile)
                    except Exception as e:
                        logger.error(f"Failed to load {json_path}: {e}")
                        continue

                if len(emgfile_list) == 0:
                    logger.warning(f"Group '{group_name}': No files loaded, skipping")
                    continue

                # Run detection
                detection_result = detect_duplicates_in_group(
                    emgfile_list,
                    maxlag=self.maxlag,
                    jitter=self.jitter,
                    tol=self.tol,
                    fsamp=self.fsamp
                )

                # Store results with file paths (for later use)
                group_result = {
                    'group_name': group_name,
                    'json_paths': [str(p) for p in json_paths],
                    'detection': detection_result,
                    'emgfiles': emgfile_list  # Keep loaded for later
                }
                all_results['groups'].append(group_result)
                all_results['total_files'] += len(json_paths)

                # Update counts
                n_dup_groups = len(detection_result['duplicate_groups'])
                all_results['total_duplicate_groups'] += n_dup_groups

                # Count MUs to remove (all duplicates except survivors)
                for dup_group in detection_result['duplicate_groups']:
                    all_results['total_mus_to_remove'] += (
                        len(dup_group['mus']) - 1
                    )

            self.finished.emit(all_results)

        except Exception as e:
            logger.exception("Detection worker failed")
            self.error.emit(f"Detection failed: {str(e)}")


# ============================================================================
# VIEW DUPLICATE DIALOG
# ============================================================================

class ViewDuplicateDialog(QDialog):
    """Dialog to view duplicate MU comparison with spike train plots."""

    def __init__(self, group_result, dup_group_idx, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate MU Comparison")
        self.resize(1000, 700)

        self.group_result = group_result
        self.dup_group = group_result['detection']['duplicate_groups'][dup_group_idx]

        self.init_ui()

    def init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Header with overlap info
        mus_str = ", ".join([f"File{f}_MU{m}" for f, m in self.dup_group['mus']])
        survivor_str = f"File{self.dup_group['survivor'][0]}_MU{self.dup_group['survivor'][1]}"

        header = QLabel(
            f"<b>Duplicate Group:</b> {mus_str}<br>"
            f"<b>Survivor:</b> {survivor_str} (lowest CoV ISI)"
        )
        header.setStyleSheet(Styles.label_heading(size="lg"))
        header.setWordWrap(True)
        layout.addWidget(header)

        # CoV ISI table
        cov_group = QGroupBox("CoV ISI Values")
        cov_layout = QVBoxLayout(cov_group)

        cov_str = "<table style='border-collapse: collapse;'>"
        cov_str += "<tr><th style='padding: 5px; border: 1px solid #ccc;'>MU</th>"
        cov_str += "<th style='padding: 5px; border: 1px solid #ccc;'>CoV ISI (%)</th></tr>"
        for (f, m), cov_val in self.dup_group['cov_isi_values'].items():
            is_survivor = (f, m) == self.dup_group['survivor']
            style = "background-color: #d4edda;" if is_survivor else ""
            cov_str += f"<tr style='{style}'>"
            cov_str += f"<td style='padding: 5px; border: 1px solid #ccc;'>File{f}_MU{m}</td>"
            cov_str += f"<td style='padding: 5px; border: 1px solid #ccc;'>{cov_val:.2f}</td>"
            cov_str += "</tr>"
        cov_str += "</table>"

        cov_label = QLabel(cov_str)
        cov_label.setTextFormat(Qt.RichText)
        cov_layout.addWidget(cov_label)
        layout.addWidget(cov_group)

        # Spike train plots
        plot_group = QGroupBox("Spike Trains")
        plot_layout = QVBoxLayout(plot_group)

        # Default view: matplotlib spike trains
        self.create_spike_train_plots(plot_layout)

        layout.addWidget(plot_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(Styles.button_secondary())
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def create_spike_train_plots(self, parent_layout):
        """Create spike train raster plots using matplotlib."""
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        except ImportError:
            parent_layout.addWidget(QLabel("Matplotlib not available for plotting"))
            return

        fig = Figure(figsize=(10, 6))
        emgfiles = self.group_result['emgfiles']

        n_mus = len(self.dup_group['mus'])

        for idx, (file_idx, mu_idx) in enumerate(self.dup_group['mus']):
            ax = fig.add_subplot(n_mus, 1, idx + 1)

            # Get discharge times
            emgfile = emgfiles[file_idx]
            discharge_times = get_discharge_times(emgfile, mu_idx)

            # Plot as event plot (raster)
            ax.eventplot(discharge_times, colors='blue', linewidths=1.0)
            ax.set_ylabel(f"File{file_idx}_MU{mu_idx}", fontsize=10)
            ax.set_xlim([0, max([get_discharge_times(emgfiles[f], m).max()
                                  for f, m in self.dup_group['mus']]) + 1])

            # Highlight survivor
            if (file_idx, mu_idx) == self.dup_group['survivor']:
                ax.set_ylabel(f"File{file_idx}_MU{mu_idx} ★", fontsize=10, color='green')
                ax.spines['left'].set_color('green')
                ax.spines['left'].set_linewidth(2)

            if idx == n_mus - 1:
                ax.set_xlabel("Time (s)")
            else:
                ax.set_xticklabels([])

        fig.tight_layout()
        canvas = FigureCanvasQTAgg(fig)
        parent_layout.addWidget(canvas)


class JSONExportWorker(QThread):
    """Worker thread for exporting cleaned JSONs to MUEdit MAT format."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(int, int, list, list)  # success_count, skipped_count, output_paths, skipped_files
    error = pyqtSignal(str)

    def __init__(self, json_files, output_folder, parent=None):
        super().__init__(parent)
        self.json_files = json_files
        self.output_folder = output_folder

    def run(self):
        """Export JSON files to MAT format."""
        try:
            from hdsemg_pipe.actions.decomposition_export import export_to_muedit_mat

            os.makedirs(self.output_folder, exist_ok=True)

            success_count = 0
            skipped_count = 0
            failed_count = 0
            output_paths = []
            skipped_files = []   # Files skipped because they have 0 MUs
            failed_files = []    # Files that failed due to an error

            total = len(self.json_files)
            for idx, json_path in enumerate(self.json_files):
                filename = os.path.basename(json_path)
                self.progress.emit(idx, total, f"Exporting {filename}...")

                try:
                    output_path = export_to_muedit_mat(
                        json_load_filepath=json_path,
                        ngrid=None,
                        output_dir=self.output_folder
                    )

                    if output_path is None:
                        # export_to_muedit_mat returns None when file has 0 MUs
                        skipped_count += 1
                        skipped_files.append(filename)
                        logger.info(f"Skipped MAT export for {filename} (0 MUs)")
                    else:
                        output_paths.append(output_path)
                        success_count += 1
                        logger.info(f"Exported {filename} -> {output_path}")

                except Exception as e:
                    failed_count += 1
                    failed_files.append(filename)
                    logger.error(f"Failed to export {filename}: {e}")
                    logger.exception(f"Full error for {filename}")
                    continue

            logger.info(
                f"MAT export summary: {total} JSON files processed → "
                f"{success_count} exported, "
                f"{skipped_count} skipped (0 MUs), "
                f"{failed_count} failed"
            )
            if skipped_files:
                logger.info(f"Skipped (0 MUs): {', '.join(skipped_files)}")
            if failed_files:
                logger.warning(f"Failed exports: {', '.join(failed_files)}")

            self.finished.emit(success_count, skipped_count, output_paths, skipped_files)

        except Exception as e:
            logger.exception("Export worker failed")
            self.error.emit(f"Export failed: {str(e)}")


# ============================================================================
# MAIN WIDGET
# ============================================================================

class RemoveDuplicateMUsWizardWidget(WizardStepWidget):
    """
    Step 10: Remove Duplicate MUs (Within/Between Grids)

    This step:
    - Groups JSON files (by file+muscle)
    - Detects duplicates using Python algorithm
    - Shows duplicates in UI for user review
    - Lets user confirm/modify removals
    - Saves cleaned JSONs to decomposition_removed_duplicates/
    - Can be skipped
    """

    def __init__(self, parent=None):
        step_index = 10
        step_name = "Remove Duplicate MUs"
        description = "Detect and remove duplicate motor units within and between grids (optional)"

        self.json_files = []
        self.grid_groupings = {}  # {group_name: [file1, file2, ...]}
        self.detection_results = None
        self.detection_worker = None
        self.export_worker = None
        self.saved_json_paths = []  # Paths to cleaned JSONs (for export)

        super().__init__(step_index, step_name, description, parent)

        self.init_ui()
        self.check()

    def create_buttons(self):
        """Create action buttons for this step."""
        # Configure grouping button
        self.btn_configure = QPushButton("Configure Grouping")
        self.btn_configure.setStyleSheet(Styles.button_secondary())
        self.btn_configure.clicked.connect(self.open_grouping_dialog)
        self.btn_configure.setEnabled(False)
        self.buttons.append(self.btn_configure)

        # Detect duplicates button
        self.btn_detect = QPushButton("Detect Duplicates")
        self.btn_detect.setStyleSheet(Styles.button_primary())
        self.btn_detect.clicked.connect(self.start_detection)
        self.btn_detect.setEnabled(False)
        self.buttons.append(self.btn_detect)

        # Apply removals button
        self.btn_apply = QPushButton("Apply Removals and Save")
        self.btn_apply.setStyleSheet(Styles.button_primary())
        self.btn_apply.clicked.connect(self.apply_removals)
        self.btn_apply.setEnabled(False)
        self.buttons.append(self.btn_apply)

        # Skip button
        self.btn_skip = QPushButton("Skip This Step")
        self.btn_skip.setStyleSheet(Styles.button_secondary())
        self.btn_skip.setToolTip(
            "Skip duplicate detection and proceed to next step.\n"
            "All files will be exported to MUEdit as-is."
        )
        self.btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(self.btn_skip)

    def init_ui(self):
        """Initialize UI components."""
        # Status panel
        self.status_group = self.create_status_panel()
        self.content_layout.addWidget(self.status_group)

        # Parameters panel
        self.params_group = self.create_parameter_panel()
        self.content_layout.addWidget(self.params_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(Styles.progress_bar())
        self.progress_bar.setVisible(False)
        self.content_layout.addWidget(self.progress_bar)

        # Results panel
        self.results_group = self.create_results_panel()
        self.content_layout.addWidget(self.results_group)

    def create_status_panel(self):
        """Create status information panel."""
        group = QGroupBox("Status")
        group.setStyleSheet(Styles.groupbox())
        layout = QVBoxLayout(group)

        self.lbl_files_found = QLabel("No files found")
        layout.addWidget(self.lbl_files_found)

        self.lbl_grouping_strategy = QLabel("Grouping: File + Muscle (default)")
        layout.addWidget(self.lbl_grouping_strategy)

        return group

    def create_parameter_panel(self):
        """Create parameter configuration panel."""
        group = QGroupBox("Detection Parameters")
        group.setStyleSheet(Styles.groupbox())

        # Use compact single-row layout
        row = QHBoxLayout(group)
        row.setSpacing(Spacing.MD)
        row.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)

        # Jitter
        row.addWidget(QLabel("Jitter:"))
        self.jitter_spin = QDoubleSpinBox()
        self.jitter_spin.setRange(0.01, 0.2)
        self.jitter_spin.setValue(0.05)
        self.jitter_spin.setSuffix(" s")
        self.jitter_spin.setDecimals(3)
        self.jitter_spin.setFixedWidth(80)
        self.jitter_spin.setToolTip("Time tolerance for spike matching (default: 0.05s = 50ms)")
        row.addWidget(self.jitter_spin)

        # MaxLag
        row.addWidget(QLabel("Max lag:"))
        self.maxlag_spin = QSpinBox()
        self.maxlag_spin.setRange(64, 2048)
        self.maxlag_spin.setValue(512)
        self.maxlag_spin.setSuffix(" samp")
        self.maxlag_spin.setFixedWidth(100)
        self.maxlag_spin.setToolTip("Maximum time shift for cross-correlation (default: 512)")
        row.addWidget(self.maxlag_spin)

        # Overlap threshold
        row.addWidget(QLabel("Overlap:"))
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(0.5, 1.0)
        self.tol_spin.setValue(0.8)
        self.tol_spin.setSingleStep(0.05)
        self.tol_spin.setDecimals(2)
        self.tol_spin.setFixedWidth(60)
        self.tol_spin.setToolTip("Overlap threshold for duplicate detection (default: 0.8 = 80%)")
        row.addWidget(self.tol_spin)

        # Fsamp
        row.addWidget(QLabel("Fsamp:"))
        self.lbl_fsamp = QLabel("Auto")
        self.lbl_fsamp.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-style: italic;")
        self.lbl_fsamp.setMinimumWidth(80)
        row.addWidget(self.lbl_fsamp)

        row.addStretch()

        return group

    def create_results_panel(self):
        """Create results display panel."""
        group = QGroupBox("Detection Results")
        group.setStyleSheet(Styles.groupbox())
        group.setVisible(False)  # Hidden until detection runs
        layout = QVBoxLayout(group)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "Group", "MUs in Duplicate", "Overlap %", "Survivor", "Action", "View"
        ])
        self.results_table.horizontalHeader().setStretchLastSection(False)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.results_table)

        # Summary label
        self.lbl_summary = QLabel("")
        layout.addWidget(self.lbl_summary)

        return group

    def check(self):
        """Check if step can be activated."""
        # Don't show errors on initial load (no workfolder set)
        if not global_state.workfolder:
            return False

        if not OPENHDEMG_AVAILABLE:
            self.error("openhdemg library is required for duplicate detection")
            return False

        # Check if previous step completed
        if not global_state.is_widget_completed("step9"):
            # CoVISI not completed - check if we have files in decomposition_auto
            if not global_state.is_widget_completed("step8"):
                self.error("Please complete decomposition step first")
                return False

        self.scan_json_files()
        return True

    def scan_json_files(self):
        """Scan for JSON files to process."""
        # Priority order:
        # 1. decomposition_covisi_filtered/ (if step 9 completed and not skipped)
        # 2. decomposition_auto/ (fallback)

        try:
            covisi_folder = global_state.get_decomposition_covisi_filtered_path()
            auto_folder = global_state.get_decomposition_path()
        except (ValueError, AttributeError):
            # Workfolder not set
            return

        source_folder = None

        # Check step 9 (CoVISI)
        if (global_state.is_widget_completed("step9") and
            covisi_folder and os.path.exists(covisi_folder)):
            # Check if actually skipped (skip marker exists)
            skip_marker = os.path.join(covisi_folder, '.skip_marker.json')
            if not os.path.exists(skip_marker):
                source_folder = covisi_folder
                logger.info("Using CoVISI-filtered files for duplicate detection")

        # Fallback to auto folder
        if source_folder is None:
            source_folder = auto_folder
            logger.info("Using decomposition_auto files for duplicate detection")

        # Scan for JSON files
        if not source_folder or not os.path.exists(source_folder):
            # Don't show error on initial load
            if global_state.workfolder:
                self.error(f"Source folder not found: {source_folder}")
            return

        state_files = {
            'decomposition_mapping.json',
            'multigrid_groupings.json',
            'covisi_pre_filter_report.json',
            'duplicate_detection_params.json',
            'duplicate_detection_report.json'
        }

        self.json_files = [
            os.path.join(source_folder, f)
            for f in os.listdir(source_folder)
            if f.endswith('.json') and f not in state_files and not f.startswith('algorithm_params')
        ]

        self.lbl_files_found.setText(f"Found {len(self.json_files)} JSON files in {Path(source_folder).name}/")

        if len(self.json_files) > 0:
            self.btn_configure.setEnabled(True)
            self.btn_detect.setEnabled(True)

            # Auto-detect fsamp from first file
            try:
                emgfile = emg.emg_from_json(self.json_files[0])
                fsamp = emgfile.get('FSAMP', 2048.0)
                self.lbl_fsamp.setText(f"{fsamp} Hz")
            except Exception as e:
                logger.warning(f"Could not auto-detect fsamp: {e}")

    def open_grouping_dialog(self):
        """Open grouping configuration dialog."""
        if len(self.json_files) == 0:
            self.error("No JSON files found")
            return

        # Use existing GridGroupingDialog
        dialog = GridGroupingDialog(
            self.json_files,
            current_groupings=self.grid_groupings,
            parent=self
        )

        if dialog.exec_() == QDialog.Accepted:
            self.grid_groupings = dialog.get_groupings()
            self.info(f"Configured {len(self.grid_groupings)} groups")
            logger.info(f"Groups configured: {list(self.grid_groupings.keys())}")

    def start_detection(self):
        """Start duplicate detection."""
        if len(self.json_files) == 0:
            self.error("No JSON files to process")
            return

        # Create groups
        try:
            groups = []

            # If manual groupings configured, use those
            if self.grid_groupings:
                for group_name, file_basenames in self.grid_groupings.items():
                    # Resolve basenames to full paths
                    group_files = []
                    for basename in file_basenames:
                        matching = [f for f in self.json_files if Path(f).name == basename]
                        if matching:
                            group_files.extend(matching)

                    if len(group_files) > 0:
                        groups.append({'name': group_name, 'files': group_files})
            else:
                # Auto-group by muscle name (simple strategy)
                muscle_groups = {}
                for json_file in self.json_files:
                    # Extract muscle name from filename (simplified)
                    # Pattern: ..._{muscle}.json or ..._{muscle}_covisi_filtered.json
                    stem = Path(json_file).stem
                    # Remove common suffixes
                    for suffix in ['_covisi_filtered', '_duplicates_removed']:
                        if stem.endswith(suffix):
                            stem = stem[:-len(suffix)]

                    # Extract muscle name (last part before extensions)
                    parts = stem.split('_')
                    if len(parts) >= 2:
                        muscle = parts[-1]  # Last part is typically muscle name
                        if muscle not in muscle_groups:
                            muscle_groups[muscle] = []
                        muscle_groups[muscle].append(json_file)

                # Create groups from muscle groupings
                for muscle, files in muscle_groups.items():
                    if len(files) > 0:
                        groups.append({'name': muscle, 'files': files})

            logger.info(f"Created {len(groups)} groups for detection ({len([g for g in groups if len(g['files']) >= 2])} multi-file groups)")

            # Start worker
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)

            self.btn_detect.setEnabled(False)
            self.btn_configure.setEnabled(False)

            self.detection_worker = DuplicateDetectionWorker(
                groups,
                maxlag=self.maxlag_spin.value(),
                jitter=self.jitter_spin.value(),
                tol=self.tol_spin.value(),
                fsamp=None  # Auto-detect
            )

            self.detection_worker.progress.connect(self.on_detection_progress)
            self.detection_worker.finished.connect(self.on_detection_finished)
            self.detection_worker.error.connect(self.on_detection_error)
            self.detection_worker.start()

        except Exception as e:
            logger.exception("Failed to start detection")
            self.error(f"Failed to start detection: {str(e)}")

    def on_detection_progress(self, current, total, message):
        """Handle detection progress updates."""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)

        self.info(message)

    def on_detection_finished(self, results):
        """Handle detection completion."""
        self.progress_bar.setVisible(False)
        self.btn_detect.setEnabled(True)
        self.btn_configure.setEnabled(True)

        self.detection_results = results

        # Check if any duplicates were found
        if results['total_duplicate_groups'] > 0:
            # Display results for user review
            self.display_results(results)
            self.btn_apply.setEnabled(True)
            self.success(f"Found {results['total_duplicate_groups']} duplicate groups")
        else:
            # No duplicates found - automatically copy files and complete step
            self.info("No duplicates found - all MUs are unique. Auto-completing step...")
            self.auto_complete_no_duplicates(results)

    def auto_complete_no_duplicates(self, results):
        """Automatically complete step when no duplicates are found."""
        try:
            output_folder = global_state.get_decomposition_removed_duplicates_path()
            os.makedirs(output_folder, exist_ok=True)

            # Copy all source files to output folder
            self.saved_json_paths = []
            processed_files = set()

            for group_result in results['groups']:
                for json_path in group_result['json_paths']:
                    # Copy file to output folder (no suffix change since no duplicates removed)
                    output_path = os.path.join(output_folder, Path(json_path).name)
                    shutil.copy2(json_path, output_path)
                    self.saved_json_paths.append(output_path)
                    processed_files.add(json_path)
                    logger.info(f"Copied {Path(json_path).name} (no duplicates found)")

            # Copy any files that were NOT in groups
            for json_path in self.json_files:
                if json_path not in processed_files:
                    output_path = os.path.join(output_folder, Path(json_path).name)
                    shutil.copy2(json_path, output_path)
                    self.saved_json_paths.append(output_path)
                    logger.info(f"Copied {Path(json_path).name} (not in any group)")

            # Save detection report
            self.save_detection_report(output_folder)

            logger.info(f"Copied {len(self.saved_json_paths)} files (no duplicates + ungrouped)")

            # Export to MAT format for MUEdit
            self.start_export_to_muedit()

        except Exception as e:
            logger.exception("Failed to auto-complete step")
            self.error(f"Failed to auto-complete: {str(e)}")

    def on_detection_error(self, error_msg):
        """Handle detection error."""
        self.progress_bar.setVisible(False)
        self.btn_detect.setEnabled(True)
        self.btn_configure.setEnabled(True)

        self.error(error_msg)

    def display_results(self, results):
        """Display detection results in table."""
        self.results_group.setVisible(True)
        self.results_table.setRowCount(0)

        row = 0
        for group_result in results['groups']:
            for dup_group_idx, dup_group in enumerate(group_result['detection']['duplicate_groups']):
                self.results_table.insertRow(row)

                # Column 0: Group name
                self.results_table.setItem(row, 0, QTableWidgetItem(group_result['group_name']))

                # Column 1: MUs in duplicate
                mus_str = ", ".join([f"F{f}M{m}" for f, m in dup_group['mus']])
                self.results_table.setItem(row, 1, QTableWidgetItem(mus_str))

                # Column 2: Average overlap
                avg_overlap = sum(sum(row_scores) for row_scores in dup_group['overlap_scores']) / \
                              (len(dup_group['mus']) ** 2)
                self.results_table.setItem(row, 2, QTableWidgetItem(f"{avg_overlap*100:.1f}%"))

                # Column 3: Survivor
                survivor_str = f"F{dup_group['survivor'][0]}M{dup_group['survivor'][1]}"
                self.results_table.setItem(row, 3, QTableWidgetItem(survivor_str))

                # Column 4: Checkbox (remove or keep both)
                chk_remove = QCheckBox("Remove")
                chk_remove.setChecked(True)  # Default: remove duplicates
                chk_remove.setToolTip("Uncheck to keep all MUs in this group")
                self.results_table.setCellWidget(row, 4, chk_remove)

                # Column 5: View button
                btn_view = QPushButton("View")
                btn_view.setStyleSheet(Styles.button_secondary())
                btn_view.clicked.connect(
                    lambda checked, gr=group_result, idx=dup_group_idx: self.view_duplicate(gr, idx)
                )
                self.results_table.setCellWidget(row, 5, btn_view)

                row += 1

        # Update summary
        self.lbl_summary.setText(
            f"Summary: {results['total_duplicate_groups']} duplicate groups found in {results['total_files']} files. "
            f"Action: Remove {results['total_mus_to_remove']} MUs (checked rows), keep survivors."
        )

    def view_duplicate(self, group_result, dup_group_idx):
        """Open dialog to view duplicate comparison."""
        dialog = ViewDuplicateDialog(group_result, dup_group_idx, parent=self)
        dialog.exec_()

    def apply_removals(self):
        """Apply duplicate removals, save cleaned files, and export to MAT."""
        if self.detection_results is None:
            self.error("No detection results available")
            return

        try:
            output_folder = global_state.get_decomposition_removed_duplicates_path()
            os.makedirs(output_folder, exist_ok=True)

            # Collect removals based on checkboxes
            self.saved_json_paths = []
            processed_files = set()  # Track which files were processed

            for group_result in self.detection_results['groups']:
                # Filter duplicate groups based on checkboxes
                groups_to_remove = []

                row = 0
                for dup_group_idx, dup_group in enumerate(group_result['detection']['duplicate_groups']):
                    # Check if removal is enabled
                    chk_remove = self.results_table.cellWidget(row, 4)
                    if isinstance(chk_remove, QCheckBox) and chk_remove.isChecked():
                        groups_to_remove.append(dup_group)
                    row += 1

                # Apply removals
                cleaned_emgfiles = remove_duplicates_from_emgfiles(
                    group_result['emgfiles'],
                    groups_to_remove
                )

                # Save cleaned JSONs
                original_paths = group_result['json_paths']
                output_paths = save_cleaned_jsons(
                    cleaned_emgfiles,
                    original_paths,
                    output_folder,
                    suffix='_duplicates_removed'
                )

                self.saved_json_paths.extend(output_paths)
                # Track processed files
                for path in original_paths:
                    processed_files.add(path)

            # Copy any files that were NOT in groups (to ensure ALL files are exported)
            for json_path in self.json_files:
                if json_path not in processed_files:
                    output_path = os.path.join(output_folder, Path(json_path).name)
                    shutil.copy2(json_path, output_path)
                    self.saved_json_paths.append(output_path)
                    logger.info(f"Copied {Path(json_path).name} (not in any group)")

            # Save report
            self.save_detection_report(output_folder)

            logger.info(f"Saved {len(self.saved_json_paths)} JSON files (cleaned + ungrouped)")

            # Now export to MAT format for MUEdit
            self.start_export_to_muedit()

        except Exception as e:
            logger.exception("Failed to apply removals")
            self.error(f"Failed to apply removals: {str(e)}")

    def start_export_to_muedit(self):
        """Export cleaned JSONs to MUEdit MAT format."""
        muedit_folder = global_state.get_decomposition_muedit_path()
        os.makedirs(muedit_folder, exist_ok=True)

        logger.info(f"Starting MAT export of {len(self.saved_json_paths)} JSON files to MUEdit format...")

        # Update UI
        self.lbl_summary.setText(f"Exporting {len(self.saved_json_paths)} JSON files to MUEdit MAT format...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Disable buttons during export
        self.btn_apply.setEnabled(False)
        self.btn_detect.setEnabled(False)
        self.btn_configure.setEnabled(False)

        # Start export worker
        self.export_worker = JSONExportWorker(self.saved_json_paths, muedit_folder)
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()

    def on_export_progress(self, current, total, message):
        """Handle export progress updates."""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)
        self.lbl_summary.setText(message)

    def on_export_finished(self, success_count, skipped_count, output_paths, skipped_files):
        """Handle export completion."""
        self.progress_bar.setVisible(False)

        total_json = len(self.saved_json_paths)
        failed_count = total_json - success_count - skipped_count

        # Build a detailed breakdown for the summary label
        parts = [f"{total_json} JSON files processed"]
        parts.append(f"{success_count} MAT files exported")
        if skipped_count > 0:
            parts.append(f"{skipped_count} skipped (0 MUs — no motor units to export)")
        if failed_count > 0:
            parts.append(f"{failed_count} failed (see log)")

        summary_text = " · ".join(parts)
        self.lbl_summary.setText(summary_text)

        if skipped_count > 0:
            logger.info(
                f"Note: {skipped_count} JSON file(s) were not converted to MAT because they "
                f"contain 0 motor units. This is expected when all MUs were removed by "
                f"CoVISI filtering or duplicate removal. "
                f"Affected files: {', '.join(skipped_files)}"
            )

        # Mark step as completed
        global_state.complete_widget(f"step{self.step_index}")

        self.success(
            f"Saved {total_json} cleaned JSON files · "
            f"Exported {success_count} MAT files for MUEdit"
            + (f" · {skipped_count} skipped (0 MUs)" if skipped_count > 0 else "")
        )
        self.complete_step()

    def on_export_error(self, error_msg):
        """Handle export errors."""
        self.progress_bar.setVisible(False)
        self.lbl_summary.setText("Export failed")
        self.error(f"Export to MUEdit failed: {error_msg}")

        # Re-enable buttons
        self.btn_apply.setEnabled(True)
        self.btn_detect.setEnabled(True)
        self.btn_configure.setEnabled(True)

    def save_detection_report(self, output_folder):
        """Save detection report to JSON."""
        report_path = os.path.join(output_folder, 'duplicate_detection_report.json')

        report = {
            'timestamp': datetime.now().isoformat(),
            'parameters': {
                'jitter': self.jitter_spin.value(),
                'maxlag': self.maxlag_spin.value(),
                'tol': self.tol_spin.value(),
                'grouping_strategy': 'file_and_muscle'
            },
            'summary': {
                'total_files': self.detection_results['total_files'],
                'total_duplicate_groups': self.detection_results['total_duplicate_groups'],
                'total_mus_removed': self.detection_results['total_mus_to_remove']
            }
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Saved detection report: {report_path}")

    def skip_step(self):
        """Skip duplicate detection step - copy files and export to MAT."""
        try:
            output_folder = global_state.get_decomposition_removed_duplicates_path()
            os.makedirs(output_folder, exist_ok=True)

            # Save skip marker
            skip_marker_path = os.path.join(output_folder, '.skip_marker.json')
            with open(skip_marker_path, 'w') as f:
                json.dump({'skipped': True, 'reason': 'User skipped duplicate detection'}, f)

            # Copy all source files to output folder
            self.saved_json_paths = []
            for json_path in self.json_files:
                output_path = os.path.join(output_folder, Path(json_path).name)
                shutil.copy2(json_path, output_path)
                self.saved_json_paths.append(output_path)
                logger.info(f"Copied {Path(json_path).name} (step skipped)")

            logger.info(f"Copied {len(self.saved_json_paths)} files (duplicate detection skipped)")

            # Export to MAT format for MUEdit
            self.start_export_to_muedit()

        except Exception as e:
            logger.exception("Failed to skip step")
            self.error(f"Failed to skip step: {str(e)}")
