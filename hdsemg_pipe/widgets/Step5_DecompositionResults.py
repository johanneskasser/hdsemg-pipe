"""
Step 5: Decomposition Results

This step monitors the decomposition folder for results and allows mapping
of decomposition files to their source channel selection files.
"""
import os
from PyQt5.QtCore import QFileSystemWatcher
from PyQt5.QtWidgets import QPushButton, QLabel, QVBoxLayout, QFrame

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.widgets.MappingDialog import MappingDialog
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, Fonts


class Step5_DecompositionResults(BaseStepWidget):
    """
    Step 5: Wait for decomposition results and apply mapping.

    This step:
    - Monitors the decomposition folder with FileSystemWatcher
    - Detects JSON decomposition files
    - Provides mapping dialog to associate files with their sources
    - Completes when mapping is applied and JSON files exist
    """

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(step_index, step_name, tooltip, parent)

        self.expected_folder = None
        self.decomp_mapping = None
        self.resultfiles = []
        self.error_messages = []

        # Initialize file system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.scan_decomposition_folder)

        # Create status UI
        self.create_status_ui()
        self.col_additional.addWidget(self.status_container)

        # Perform initial check
        self.check()

    def create_status_ui(self):
        """Create compact status UI."""
        self.status_container = QFrame()
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setSpacing(Spacing.SM)
        status_layout.setContentsMargins(0, 0, 0, 0)

        # File counter
        self.file_counter_label = QLabel("Monitoring for decomposition files...")
        self.file_counter_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
                padding: {Spacing.SM}px;
            }}
        """)
        status_layout.addWidget(self.file_counter_label)

    def create_buttons(self):
        """Create buttons for this step."""
        self.btn_apply_mapping = QPushButton("Apply Mapping")
        self.btn_apply_mapping.setStyleSheet(Styles.button_primary())
        self.btn_apply_mapping.setToolTip("Map decomposition results to their source channel selection files")
        self.btn_apply_mapping.clicked.connect(self.open_mapping_dialog)
        self.btn_apply_mapping.setEnabled(False)
        self.buttons.append(self.btn_apply_mapping)

    def check(self):
        """Check if this step can be activated."""
        # This step requires the previous step (channel selection) to be completed
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        self.expected_folder = global_state.get_decomposition_path()

        # Add watcher if folder exists
        if os.path.exists(self.expected_folder):
            if self.expected_folder not in self.watcher.directories():
                self.watcher.addPath(self.expected_folder)
                logger.info(f"Monitoring decomposition folder: {self.expected_folder}")

        # Always scan folder to show files, even if step is not yet activated
        self.scan_decomposition_folder()

        # Check if previous step is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        return True

    def scan_decomposition_folder(self):
        """Scan the decomposition folder for result files."""
        if not os.path.exists(self.expected_folder):
            self.file_counter_label.setText("⚠️ Decomposition folder not found")
            self.btn_apply_mapping.setEnabled(False)
            return

        # Find JSON and PKL files
        files = []
        for file in os.listdir(self.expected_folder):
            if file.endswith('.json') or file.endswith('.pkl'):
                full_path = os.path.join(self.expected_folder, file)
                files.append(full_path)

        self.resultfiles = files

        # Update UI
        json_count = len([f for f in files if f.endswith('.json')])
        pkl_count = len([f for f in files if f.endswith('.pkl')])

        if files:
            self.file_counter_label.setText(
                f"✓ Found {len(files)} file(s): {json_count} JSON, {pkl_count} PKL"
            )
            self.file_counter_label.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.GREEN_700};
                    font-size: {Fonts.SIZE_SM};
                    padding: {Spacing.SM}px;
                }}
            """)
            self.btn_apply_mapping.setEnabled(True)
        else:
            self.file_counter_label.setText("Monitoring for decomposition files...")
            self.file_counter_label.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.TEXT_SECONDARY};
                    font-size: {Fonts.SIZE_SM};
                    padding: {Spacing.SM}px;
                }}
            """)
            self.btn_apply_mapping.setEnabled(False)

        logger.info(f"Decomposition folder scan: {len(files)} file(s) found")

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.expected_folder = global_state.get_decomposition_path()
        if os.path.exists(self.expected_folder):
            if self.expected_folder not in self.watcher.directories():
                self.watcher.addPath(self.expected_folder)
        self.scan_decomposition_folder()
        logger.info(f"File checking initialized for folder: {self.expected_folder}")

    def open_mapping_dialog(self):
        """Open the mapping dialog to associate decomposition files with sources."""
        if not self.resultfiles:
            self.warn("No decomposition files found to map.")
            return

        dialog = MappingDialog(
            existing_mapping=self.decomp_mapping,
            parent=self
        )

        if dialog.exec_():
            self.decomp_mapping = dialog.get_mapping()

            if self.decomp_mapping:
                mapped_count = len(self.decomp_mapping)
                self.success(f"Mapping applied successfully: {mapped_count} file(s) mapped.")
                logger.info(f"Decomposition mapping: {self.decomp_mapping}")

                # Mark step as completed
                self.complete_step()
            else:
                logger.info("No mapping configured.")

    def is_completed(self):
        """Check if this step is completed."""
        # Step is completed when:
        # 1. JSON files exist
        # 2. Mapping has been applied
        has_json_files = any(f.endswith('.json') for f in self.resultfiles)
        has_mapping = self.decomp_mapping is not None and len(self.decomp_mapping) > 0

        return has_json_files and has_mapping
