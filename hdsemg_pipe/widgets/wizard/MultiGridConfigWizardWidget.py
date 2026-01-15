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
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.widgets.GridGroupingDialog import GridGroupingDialog
from hdsemg_pipe.actions.decomposition_export import (
    export_to_muedit_mat, export_multi_grid_to_muedit, is_muedit_file_exists
)
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts


class MUEditExportWorker(QThread):
    """Worker thread for exporting files to MUEdit format."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(int, int, list)  # success_count, error_count, error_messages
    error = pyqtSignal(str)

    def __init__(self, json_files, grid_groupings, parent=None):
        super().__init__(parent)
        self.json_files = json_files
        self.grid_groupings = grid_groupings

    def run(self):
        """Run the export process in background."""
        try:
            success_count = 0
            error_count = 0
            error_messages = []

            total_files = len(self.json_files)

            # Track which files are in groups
            files_in_groups = set()
            for group_files in self.grid_groupings.values():
                files_in_groups.update(group_files)

            current = 0

            # First, export multi-grid groups
            for group_name, group_file_names in self.grid_groupings.items():
                try:
                    # Get full paths
                    group_file_paths = []
                    for filename in group_file_names:
                        matching_files = [f for f in self.json_files if os.path.basename(f) == filename]
                        if matching_files:
                            group_file_paths.append(matching_files[0])

                    if len(group_file_paths) < 2:
                        logger.warning(f"Group '{group_name}' has less than 2 files, skipping...")
                        for filename in group_file_names:
                            files_in_groups.discard(filename)
                        continue

                    self.progress.emit(current, total_files, f"Exporting multi-grid group '{group_name}'...")

                    muedit_file = export_multi_grid_to_muedit(group_file_paths, group_name)

                    if muedit_file:
                        success_count += len(group_file_paths)
                        logger.info(f"Successfully exported multi-grid: {os.path.basename(muedit_file)}")

                    current += len(group_file_paths)

                except Exception as e:
                    error_count += len(group_file_names)
                    error_msg = f"Failed to export multi-grid group '{group_name}': {str(e)}"
                    error_messages.append(error_msg)
                    logger.error(error_msg)

            # Then, export remaining single-grid files
            single_grid_files = [f for f in self.json_files if os.path.basename(f) not in files_in_groups]

            for json_file in single_grid_files:
                try:
                    # Check if already exists
                    if is_muedit_file_exists(json_file):
                        logger.info(f"MUEdit file already exists for {os.path.basename(json_file)}, skipping...")
                        current += 1
                        continue

                    self.progress.emit(current, total_files, f"Exporting {os.path.basename(json_file)}...")

                    muedit_file = export_to_muedit_mat(json_file)
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
        step_index = 8
        step_name = "Multi-Grid Configuration"
        description = "Configure multi-grid groups for MUEdit's duplicate detection (optional). Export files to MUEdit format."

        super().__init__(step_index, step_name, description, parent)

        self.expected_folder = None
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
        self.btn_configure_groups.setToolTip("Group grids from the same muscle (optional)")
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

        self.expected_folder = global_state.get_decomposition_path()

        # Always scan for JSON files to show status, even if step is not yet activated
        self.scan_json_files()

        # Check if previous step is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        return True

    def scan_json_files(self):
        """Scan for JSON files in decomposition folder."""
        if not os.path.exists(self.expected_folder):
            return

        # State persistence files that should be excluded from export
        state_files = {'decomposition_mapping.json', 'multigrid_groupings.json'}

        self.json_files = [
            os.path.join(self.expected_folder, f)
            for f in os.listdir(self.expected_folder)
            if f.endswith('.json') and f not in state_files
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

        # Start worker
        self.export_worker = MUEditExportWorker(self.json_files, self.grid_groupings)
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()

        logger.info(f"Starting export of {len(self.json_files)} file(s) to MUEdit format...")

    def on_export_progress(self, current, total, message):
        """Handle export progress updates."""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def on_export_finished(self, success_count, error_count, error_messages):
        """Handle export completion."""
        self.progress_bar.setVisible(False)

        # Re-enable buttons
        self.btn_configure_groups.setEnabled(len(self.json_files) >= 2)
        self.btn_export.setEnabled(True)

        # Filter out errors related to state files (these are already filtered in scan now, but handle legacy errors)
        state_files = {'decomposition_mapping.json', 'multigrid_groupings.json'}
        non_state_errors = [
            msg for msg in error_messages
            if not any(state_file in msg for state_file in state_files)
        ]
        actual_error_count = len(non_state_errors)

        # Show summary
        if success_count > 0 and actual_error_count == 0:
            multi_grid_count = len(self.grid_groupings)
            summary = f"Successfully exported {success_count} file(s) to MUEdit format."
            if multi_grid_count > 0:
                summary += f"\n• {multi_grid_count} multi-grid group(s)"

            self.success(summary)
            self.status_label.setText(f"✓ Export complete: {success_count} file(s) exported")

            # Save state to JSON
            self.save_groupings_to_json()

            # Mark step as completed
            self.complete_step()

        elif success_count > 0 and actual_error_count > 0:
            # Some real files failed, but check if all required files actually exist
            if self.is_completed():
                # All required files exist despite some errors, mark as complete
                self.success(f"Export completed with warnings. All required files exist.")
                self.save_groupings_to_json()
                self.complete_step()
            else:
                self.warn(f"Exported {success_count} file(s), but {actual_error_count} failed:\n" + "\n".join(non_state_errors))
        else:
            self.error(f"Export failed:\n" + "\n".join(error_messages))

    def on_export_error(self, error_msg):
        """Handle export worker error."""
        self.progress_bar.setVisible(False)
        self.btn_configure_groups.setEnabled(len(self.json_files) >= 2)
        self.btn_export.setEnabled(True)

        self.error(f"Export failed: {error_msg}")

    def is_completed(self):
        """Check if this step is completed."""
        # Step is completed when MUEdit files exist for all JSON files
        if not self.json_files:
            return False

        # Track which files are in multi-grid groups
        files_in_groups = set()
        for group_files in self.grid_groupings.values():
            files_in_groups.update(group_files)

        # Check multi-grid group files exist
        for group_name in self.grid_groupings.keys():
            # Sanitize group name for file path
            safe_group_name = "".join(c for c in group_name if c.isalnum() or c in (' ', '_', '-')).strip()
            safe_group_name = safe_group_name.replace(' ', '_')

            # Check if the multi-grid file exists
            expected_path = os.path.join(self.expected_folder, f"{safe_group_name}_multigrid_muedit.mat")
            if not os.path.exists(expected_path):
                return False

        # Check single-grid files for remaining JSON files (not in any group)
        for json_file in self.json_files:
            json_filename = os.path.basename(json_file)

            # Skip files that are in multi-grid groups (already checked above)
            if json_filename in files_in_groups:
                continue

            # Check if single-grid MUEdit file exists
            if not is_muedit_file_exists(json_file):
                return False

        return True

    def save_groupings_to_json(self):
        """Save the multi-grid groupings to a JSON file for state persistence."""
        decomp_auto_folder = os.path.join(global_state.workfolder, "decomposition_auto")

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
        decomp_auto_folder = os.path.join(global_state.workfolder, "decomposition_auto")
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

        # Scan for JSON files
        self.scan_json_files()

        # Load groupings from JSON for state reconstruction
        if self.load_groupings_from_json():
            logger.info(f"State reconstructed from JSON: groupings loaded")

        logger.info(f"File checking initialized for folder: {self.expected_folder}")
