"""
Step 7: Multi-Grid Configuration (Wizard Version)

This step allows configuration of multi-grid groups and exports
decomposition results to MUEdit format.
"""
import os
import json
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QPushButton, QLabel, QVBoxLayout, QFrame, QProgressBar, QDialog

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.enum.FolderNames import FolderNames
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.widgets.GridGroupingDialog import GridGroupingDialog
from hdsemg_pipe.actions.decomposition_export import (
    export_to_muedit_mat, export_multi_grid_to_muedit
)
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts


class MUEditExportWorker(QThread):
    """Worker thread for exporting files to MUEdit format."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(int, int, list)  # success_count, error_count, error_messages
    error = pyqtSignal(str)

    def __init__(self, json_files, grid_groupings, muedit_folder,
                 covisi_filtered_folder=None, auto_folder=None, parent=None):
        super().__init__(parent)
        self.json_files = json_files
        self.grid_groupings = grid_groupings
        self.muedit_folder = muedit_folder
        self.covisi_filtered_folder = covisi_filtered_folder  # decomposition_covisi_filtered/ or None
        self.auto_folder = auto_folder  # decomposition_auto/

    def _resolve_group_member_path(self, filename):
        """Resolve the actual JSON path for a group member filename.

        Group member filenames are stored as original names (e.g. file.json).
        When CoVISI was applied, the actual files are in covisi_filtered_folder
        as file_covisi_filtered.json.
        """
        stem = Path(filename).stem
        # Try covisi-filtered version first
        if self.covisi_filtered_folder:
            covisi_path = os.path.join(self.covisi_filtered_folder, stem + "_covisi_filtered.json")
            if os.path.exists(covisi_path):
                return covisi_path
        # Fall back to original in auto folder
        if self.auto_folder:
            auto_path = os.path.join(self.auto_folder, filename)
            if os.path.exists(auto_path):
                return auto_path
        # Last resort: search in json_files list
        matching = [f for f in self.json_files if os.path.basename(f) == filename]
        return matching[0] if matching else None

    def run(self):
        """Run the export process in background. All outputs go to decomposition_muedit/."""
        try:
            success_count = 0
            error_count = 0
            error_messages = []

            total_files = len(self.json_files)

            # Track which original filenames are in groups
            files_in_groups = set()
            for group_files in self.grid_groupings.values():
                files_in_groups.update(group_files)

            current = 0

            # First, export multi-grid groups
            for group_name, group_file_names in self.grid_groupings.items():
                try:
                    group_file_paths = []
                    for filename in group_file_names:
                        resolved = self._resolve_group_member_path(filename)
                        if resolved:
                            group_file_paths.append(resolved)
                        else:
                            logger.warning(f"Could not resolve path for group member '{filename}'")

                    if len(group_file_paths) < 2:
                        logger.warning(f"Group '{group_name}' has less than 2 resolved files, skipping...")
                        for filename in group_file_names:
                            files_in_groups.discard(filename)
                        continue

                    self.progress.emit(current, total_files, f"Exporting multi-grid group '{group_name}'...")

                    os.makedirs(self.muedit_folder, exist_ok=True)
                    muedit_file = export_multi_grid_to_muedit(
                        group_file_paths, group_name, output_dir=self.muedit_folder
                    )

                    if muedit_file:
                        success_count += len(group_file_paths)
                        logger.info(f"Successfully exported multi-grid: {os.path.basename(muedit_file)}")

                    current += len(group_file_paths)

                except Exception as e:
                    error_count += len(group_file_names)
                    error_msg = f"Failed to export multi-grid group '{group_name}': {str(e)}"
                    error_messages.append(error_msg)
                    logger.error(error_msg)

            # Then, export remaining single-grid files (those not in any group)
            # Single-grid files are determined by whether their original filename is in files_in_groups
            single_grid_files = [
                f for f in self.json_files
                if Path(f).stem.replace("_covisi_filtered", "") + ".json" not in files_in_groups
                and os.path.basename(f) not in files_in_groups
            ]

            for json_file in single_grid_files:
                try:
                    self.progress.emit(current, total_files, f"Exporting {os.path.basename(json_file)}...")

                    os.makedirs(self.muedit_folder, exist_ok=True)
                    muedit_file = export_to_muedit_mat(json_file, output_dir=self.muedit_folder)
                    if muedit_file:
                        success_count += 1
                        logger.info(f"Successfully exported: {os.path.basename(muedit_file)}")

                    current += 1

                except Exception as e:
                    error_count += 1
                    error_msg = f"Failed to export {os.path.basename(json_file)}: {str(e)}"
                    error_messages.append(error_msg)
                    logger.error(error_msg)
                    current += 1

            self.finished.emit(success_count, error_count, error_messages)

        except Exception as e:
            self.error.emit(f"Export worker failed: {str(e)}")


class MultiGridConfigWizardWidget(WizardStepWidget):
    """
    Step 7: Configure multi-grid groups and export to MUEdit.

    This step:
    - Shows all JSON decomposition files
    - Allows configuration of multi-grid groups
    - Exports files to MUEdit format (automatically in background)
    - Completes when all exports are done
    """

    def __init__(self, parent=None):
        # Hardcoded step configuration
        step_index = 10
        step_name = "Multi-Grid Configuration"
        description = "Configure multi-grid groups for MUEdit's duplicate detection (optional). Export files to MUEdit format."

        super().__init__(step_index, step_name, description, parent)

        self.expected_folder = None  # always decomposition_auto/ (for groupings JSON)
        self.source_folder = None    # where JSONs are read from (covisi_filtered or auto)
        self.json_files = []
        self.grid_groupings = {}
        self.export_worker = None

        # Create status UI
        self.create_status_ui()
        self.content_layout.addWidget(self.status_container)

        # Perform initial check
        self.check()

    def create_status_ui(self):
        """Create compact status UI."""
        self.status_container = QFrame()
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setSpacing(Spacing.SM)
        status_layout.setContentsMargins(0, 0, 0, 0)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
                padding: {Spacing.SM}px;
            }}
        """)
        status_layout.addWidget(self.status_label)

        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
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
        """)
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

    def create_buttons(self):
        """Create buttons for this step."""
        self.btn_configure_groups = QPushButton("Configure Multi-Grid Groups")
        self.btn_configure_groups.setStyleSheet(Styles.button_secondary())
        self.btn_configure_groups.setToolTip(
            "Configure multi-grid groups (manual or auto-grouping)\n"
            "• Auto-group by muscle only\n"
            "• Auto-group by file + muscle\n"
            "• Or manually drag files into groups"
        )
        self.btn_configure_groups.clicked.connect(self.open_grid_grouping_dialog)
        self.btn_configure_groups.setEnabled(False)
        self.buttons.append(self.btn_configure_groups)

        self.btn_export = QPushButton("Export to MUEdit")
        self.btn_export.setStyleSheet(Styles.button_primary())
        self.btn_export.setToolTip("Export files to MUEdit format")
        self.btn_export.clicked.connect(self.start_export)
        self.btn_export.setEnabled(False)
        self.buttons.append(self.btn_export)

    def check(self):
        """Check if this step can be activated."""
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        self.expected_folder = global_state.get_decomposition_path()  # decomposition_auto/
        self._update_source_folder()

        # Always scan for JSON files to show status, even if step is not yet activated
        self.scan_json_files()

        # Check if previous step is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        return True

    def _update_source_folder(self):
        """Determine whether to read JSONs from covisi_filtered or decomposition_auto."""
        covisi_folder = global_state.get_decomposition_covisi_filtered_path()

        # Primary check: step state
        covisi_applied_by_state = (
            global_state.is_widget_completed("step9")
            and not global_state.is_widget_skipped("step9")
        )

        # Fallback check: physical folder evidence.
        # Handles backwards-compat workfolders where step9 wasn't recorded in the
        # process log (e.g. CoVISI was run before process-log support or the log
        # entry was lost during a reconstruction cycle).
        covisi_applied_by_folder = os.path.exists(covisi_folder) and any(
            f.endswith('_covisi_filtered.json') for f in os.listdir(covisi_folder)
        )

        if (covisi_applied_by_state or covisi_applied_by_folder) and os.path.exists(covisi_folder):
            self.source_folder = covisi_folder
        else:
            self.source_folder = self.expected_folder

    def scan_json_files(self):
        """Scan for JSON files in source folder (covisi_filtered if available, else decomp_auto)."""
        folder = self.source_folder or self.expected_folder
        if not folder or not os.path.exists(folder):
            return

        # State persistence files that should be excluded from export
        state_files = {'decomposition_mapping.json', 'multigrid_groupings.json', 'covisi_pre_filter_report.json'}

        self.json_files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.endswith('.json') and f not in state_files and not f.startswith('algorithm_params')
        ]

        # Update UI
        if len(self.json_files) >= 2:
            self.btn_configure_groups.setEnabled(True)
            self.status_label.setText(f"Found {len(self.json_files)} JSON file(s). Multi-grid grouping available.")
        elif len(self.json_files) == 1:
            self.btn_configure_groups.setEnabled(False)
            self.status_label.setText("Found 1 JSON file. Will export as single grid.")
        else:
            self.btn_configure_groups.setEnabled(False)
            self.status_label.setText("No JSON files found.")

        self.btn_export.setEnabled(len(self.json_files) > 0)

    def open_grid_grouping_dialog(self):
        """Open dialog to configure multi-grid groups."""
        if len(self.json_files) < 2:
            self.warn("Multi-grid grouping requires at least 2 files.")
            return

        dialog = GridGroupingDialog(self.json_files, self.grid_groupings, self)
        if dialog.exec_() == QDialog.Accepted:
            self.grid_groupings = dialog.get_groupings()

            if self.grid_groupings:
                group_count = len(self.grid_groupings)
                total_grids = sum(len(grids) for grids in self.grid_groupings.values())
                self.success(f"Configured {group_count} multi-grid group(s) with {total_grids} grid(s).")
                logger.info(f"Grid groupings: {self.grid_groupings}")
            else:
                logger.info("No multi-grid groups configured. All files will be exported as single grids.")

    def start_export(self):
        """Start the export process in background."""
        if not self.json_files:
            self.warn("No JSON files to export.")
            return

        # Disable buttons during export
        self.btn_configure_groups.setEnabled(False)
        self.btn_export.setEnabled(False)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.json_files))

        # Start worker — all outputs go to decomposition_muedit/
        muedit_folder = global_state.get_decomposition_muedit_path()
        covisi_filtered_folder = global_state.get_decomposition_covisi_filtered_path()
        self.export_worker = MUEditExportWorker(
            self.json_files, self.grid_groupings,
            muedit_folder=muedit_folder,
            covisi_filtered_folder=covisi_filtered_folder if os.path.exists(covisi_filtered_folder) else None,
            auto_folder=self.expected_folder,
        )
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()

        logger.info(f"Starting export of {len(self.json_files)} file(s) to MUEdit format...")

    def on_export_progress(self, current, _total, message):
        """Handle export progress updates."""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def on_export_finished(self, success_count, _error_count, error_messages):
        """Handle export completion."""
        self.progress_bar.setVisible(False)

        # Re-enable buttons
        self.btn_configure_groups.setEnabled(len(self.json_files) >= 2)
        self.btn_export.setEnabled(True)

        # Filter out errors related to state files and algorithm_params (these are already filtered in scan now, but handle legacy errors)
        state_files = {'decomposition_mapping.json', 'multigrid_groupings.json'}
        non_state_errors = [
            msg for msg in error_messages
            if not any(state_file in msg for state_file in state_files)
            and 'algorithm_params' not in msg
        ]
        actual_error_count = len(non_state_errors)

        # Show summary
        if success_count > 0 and actual_error_count == 0:
            multi_grid_count = len(self.grid_groupings)
            summary = f"Successfully exported {success_count} file(s) to MUEdit format."
            if multi_grid_count > 0:
                summary += f"\n• {multi_grid_count} multi-grid group(s)"
            else:
                summary += "\n• All files exported as single grids"

            self.success(summary)
            self.status_label.setText(f"✓ Export complete: {success_count} file(s) exported")

            # ALWAYS save state to JSON (even if empty) for state reconstruction
            self.save_groupings_to_json()

            # Mark step as completed
            self.complete_step()

        elif success_count > 0 and actual_error_count > 0:
            # Some files failed — warn but still complete the step.
            # Failed exports cannot be retried automatically; the user must proceed.
            self.warn(
                f"Export finished with {actual_error_count} error(s) "
                f"({success_count} succeeded):\n" + "\n".join(non_state_errors)
            )
            self.save_groupings_to_json()
            self.complete_step()
        else:
            self.error(f"Export failed:\n" + "\n".join(error_messages))

    def on_export_error(self, error_msg):
        """Handle export worker error."""
        self.progress_bar.setVisible(False)
        self.btn_configure_groups.setEnabled(len(self.json_files) >= 2)
        self.btn_export.setEnabled(True)

        self.error(f"Export failed: {error_msg}")

    def is_completed(self):
        """Check if this step is completed.

        All MAT files are now in decomposition_muedit/:
        - Groups: {group_name}_multigrid_muedit.mat
        - Singles: {stem}_muedit.mat (stem may include _covisi_filtered)
        """
        if not self.json_files:
            return False

        muedit_folder = global_state.get_decomposition_muedit_path()
        if not os.path.exists(muedit_folder):
            return False

        # Collect original filenames in groups
        files_in_groups = set()
        for group_files in self.grid_groupings.values():
            files_in_groups.update(group_files)

        # Check multi-grid group MAT files exist
        for group_name in self.grid_groupings.keys():
            safe_group_name = "".join(c for c in group_name if c.isalnum() or c in (' ', '_', '-')).strip()
            safe_group_name = safe_group_name.replace(' ', '_')
            expected_path = os.path.join(muedit_folder, f"{safe_group_name}_multigrid_muedit.mat")
            if not os.path.exists(expected_path):
                return False

        # Check single-grid MAT files in decomposition_muedit/
        for json_file in self.json_files:
            json_basename = os.path.basename(json_file)
            # Determine the original filename (strip _covisi_filtered suffix if present)
            original_basename = json_basename.replace("_covisi_filtered.json", ".json")

            if original_basename in files_in_groups:
                continue  # covered by multigrid group check above

            # Expected MAT: {stem}_muedit.mat in multigrid folder
            stem = Path(json_file).stem
            expected_mat = os.path.join(muedit_folder, f"{stem}_muedit.mat")
            if not os.path.exists(expected_mat):
                return False

        return True

    def save_groupings_to_json(self):
        """Save the multi-grid groupings to a JSON file for state persistence."""
        decomp_auto_folder = os.path.join(global_state.workfolder, FolderNames.DECOMPOSITION_AUTO.value)

        # Ensure folder exists
        if not os.path.exists(decomp_auto_folder):
            os.makedirs(decomp_auto_folder)
            logger.info(f"Created decomposition_auto folder: {decomp_auto_folder}")

        groupings_file = os.path.join(decomp_auto_folder, "multigrid_groupings.json")

        try:
            with open(groupings_file, 'w') as f:
                json.dump(self.grid_groupings, f, indent=2)
            logger.info(f"Saved multi-grid groupings to {groupings_file}: {self.grid_groupings}")
        except Exception as e:
            logger.error(f"Failed to save multi-grid groupings: {e}")
            self.error(f"Failed to save groupings: {e}")

    def load_groupings_from_json(self):
        """Load the multi-grid groupings from JSON file for state reconstruction."""
        decomp_auto_folder = os.path.join(global_state.workfolder, FolderNames.DECOMPOSITION_AUTO.value)
        groupings_file = os.path.join(decomp_auto_folder, "multigrid_groupings.json")

        if os.path.exists(groupings_file):
            try:
                with open(groupings_file, 'r') as f:
                    self.grid_groupings = json.load(f)
                logger.info(f"Loaded multi-grid groupings from {groupings_file}: {self.grid_groupings}")
                return True
            except Exception as e:
                logger.error(f"Failed to load multi-grid groupings: {e}")
                return False

        return False

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.expected_folder = global_state.get_decomposition_path()
        self._update_source_folder()

        # Scan for JSON files
        self.scan_json_files()

        # Load groupings from JSON for state reconstruction
        if self.load_groupings_from_json():
            logger.info(f"State reconstructed from JSON: groupings loaded")

        logger.info(f"File checking initialized for folder: {self.source_folder}")
