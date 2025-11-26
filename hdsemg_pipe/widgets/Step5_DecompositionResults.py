"""
Step 5: Decomposition Results

This step monitors the decomposition folder for results and allows mapping
of decomposition files to their source channel selection files.
"""
import os
import json
from PyQt5.QtCore import QFileSystemWatcher, QTimer
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
        self.last_file_count = 0

        # Initialize file system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.scan_decomposition_folder)

        # Add polling timer for reliable file detection (QFileSystemWatcher can miss events on Windows)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.scan_decomposition_folder)
        self.poll_timer.setInterval(2000)  # Check every 2 seconds

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
        self.btn_skip = QPushButton("Skip")
        self.btn_skip.setStyleSheet(Styles.button_secondary())
        self.btn_skip.setToolTip("Skip mapping and continue without associating files")
        self.btn_skip.clicked.connect(self.skip_mapping)
        self.btn_skip.setEnabled(False)
        self.buttons.append(self.btn_skip)

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

            # Start polling timer for reliable file detection
            if not self.poll_timer.isActive():
                self.poll_timer.start()
                logger.info("Started file polling timer (2s interval)")

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

        # State persistence files that should be excluded from results
        state_files = {'decomposition_mapping.json', 'multigrid_groupings.json'}

        # Find JSON and PKL files (excluding state persistence files)
        files = []
        for file in os.listdir(self.expected_folder):
            if (file.endswith('.json') or file.endswith('.pkl')) and file not in state_files:
                full_path = os.path.join(self.expected_folder, file)
                files.append(full_path)

        # Check if file count changed
        file_count = len(files)
        file_count_changed = file_count != self.last_file_count
        self.last_file_count = file_count

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
            self.btn_skip.setEnabled(True)
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
            self.btn_skip.setEnabled(False)

        # Only log when file count changes to avoid spam
        if file_count_changed:
            logger.info(f"Decomposition folder scan: {len(files)} file(s) found")

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.expected_folder = global_state.get_decomposition_path()
        if os.path.exists(self.expected_folder):
            if self.expected_folder not in self.watcher.directories():
                self.watcher.addPath(self.expected_folder)

            # Start polling timer for reliable file detection
            if not self.poll_timer.isActive():
                self.poll_timer.start()

        self.scan_decomposition_folder()

        # Load mapping from JSON for state reconstruction
        if self.load_mapping_from_json():
            logger.info(f"State reconstructed from JSON: mapping loaded")

        logger.info(f"File checking initialized for folder: {self.expected_folder}")

    def skip_mapping(self):
        """Skip the mapping step and continue without file association."""
        if not self.resultfiles:
            self.warn("No decomposition files found.")
            return

        logger.info("Mapping step skipped by user")
        self.success("Mapping skipped. Continuing without file association.")

        # Set mapping to empty dict to indicate skip (different from None = not configured)
        self.decomp_mapping = {}

        # Save state to JSON
        self.save_mapping_to_json()

        # Mark step as completed
        self.complete_step()

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

                # Save state to JSON
                self.save_mapping_to_json()

                # Mark step as completed
                self.complete_step()
            else:
                logger.info("No mapping configured.")

    def is_completed(self):
        """Check if this step is completed."""
        # Step is completed when:
        # 1. JSON files exist
        # 2. Mapping has been applied OR skipped (empty dict means skipped, None means not configured)
        has_json_files = any(f.endswith('.json') for f in self.resultfiles)
        has_mapping_or_skipped = self.decomp_mapping is not None  # Both {} (skipped) and {k:v} (mapped) are valid

        return has_json_files and has_mapping_or_skipped

    def save_mapping_to_json(self):
        """Save the decomposition mapping to a JSON file for state persistence."""
        decomp_auto_folder = os.path.join(global_state.workfolder, "decomposition_auto")

        # Ensure folder exists
        if not os.path.exists(decomp_auto_folder):
            os.makedirs(decomp_auto_folder)
            logger.info(f"Created decomposition_auto folder: {decomp_auto_folder}")

        mapping_file = os.path.join(decomp_auto_folder, "decomposition_mapping.json")

        try:
            with open(mapping_file, 'w') as f:
                json.dump(self.decomp_mapping, f, indent=2)
            logger.info(f"Saved decomposition mapping to {mapping_file}: {self.decomp_mapping}")
        except Exception as e:
            logger.error(f"Failed to save decomposition mapping: {e}")
            self.error(f"Failed to save mapping: {e}")

    def load_mapping_from_json(self):
        """Load the decomposition mapping from JSON file for state reconstruction."""
        decomp_auto_folder = os.path.join(global_state.workfolder, "decomposition_auto")
        mapping_file = os.path.join(decomp_auto_folder, "decomposition_mapping.json")

        if os.path.exists(mapping_file):
            try:
                with open(mapping_file, 'r') as f:
                    self.decomp_mapping = json.load(f)
                logger.info(f"Loaded decomposition mapping from {mapping_file}: {self.decomp_mapping}")
                return True
            except Exception as e:
                logger.error(f"Failed to load decomposition mapping: {e}")
                return False

        return False
