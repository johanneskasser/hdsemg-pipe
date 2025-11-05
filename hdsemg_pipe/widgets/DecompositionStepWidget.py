import os
import subprocess
import threading
import time

from PyQt5.QtCore import pyqtSignal, QFileSystemWatcher
from PyQt5.QtWidgets import QPushButton, QDialog, QLabel, QVBoxLayout, QWidget, QProgressBar, QScrollArea

from hdsemg_pipe.actions.file_utils import update_extras_in_pickle_file, update_extras_in_json_file
from hdsemg_pipe.actions.decomposition_export import export_to_muedit_mat, is_muedit_file_exists
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.loadingbutton import LoadingButton
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.widgets.MappingDialog import MappingDialog
from hdsemg_pipe.ui_elements.theme import Styles, Colors


class DecompositionResultsStepWidget(BaseStepWidget):
    resultsDisplayed = pyqtSignal(str)

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(step_index, step_name, tooltip, parent)
        self.expected_folder = None

        # Initialize file system watcher and connect its signal
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.get_decomposition_results)

        self.error_messages = []
        self.decomp_mapping = None
        self.processed_files = []
        self.result_files = []

        # Progress tracking for MUEdit workflow
        self.original_decomp_files = []  # Files that need cleaning
        self.edited_files = []  # Files that have been cleaned (_muedit_edited.mat)

        # Perform an initial check
        self.check()

        # Create progress UI elements and add to layout
        self.create_progress_ui()
        # Add progress container to the additional info column
        self.col_additional.addWidget(self.progress_container)

    def create_progress_ui(self):
        """Creates the progress tracking UI for MUEdit workflow."""
        # Progress container
        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 10, 0, 10)

        # Progress header
        self.progress_label = QLabel("Manual Cleaning Progress")
        self.progress_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_PRIMARY};")
        progress_layout.addWidget(self.progress_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                text-align: center;
                height: 24px;
                background-color: {Colors.BG_SECONDARY};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.GREEN_600};
                border-radius: 3px;
            }}
        """)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # File status list (scrollable)
        self.file_status_scroll = QScrollArea()
        self.file_status_scroll.setWidgetResizable(True)
        self.file_status_scroll.setMaximumHeight(200)
        self.file_status_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                background-color: {Colors.BG_PRIMARY};
            }}
        """)

        self.file_status_widget = QWidget()
        self.file_status_layout = QVBoxLayout(self.file_status_widget)
        self.file_status_layout.setContentsMargins(8, 8, 8, 8)
        self.file_status_scroll.setWidget(self.file_status_widget)
        progress_layout.addWidget(self.file_status_scroll)

        # Initially hide progress UI
        self.progress_container.setVisible(False)

    def create_buttons(self):
        """Creates buttons for displaying decomposition results."""
        # Mapping button is initially disabled and will be enabled if files are detected
        self.btn_apply_mapping = QPushButton("Apply Mapping")
        self.btn_apply_mapping.setStyleSheet(Styles.button_secondary())
        self.btn_apply_mapping.setToolTip("Map decomposition results to their source channel selection files")
        self.btn_apply_mapping.clicked.connect(self.open_mapping_dialog)
        self.btn_apply_mapping.setEnabled(False)
        self.buttons.append(self.btn_apply_mapping)

        # Button to export JSON files to MUEdit format
        self.btn_export_to_muedit = QPushButton("Export to MUEdit")
        self.btn_export_to_muedit.setStyleSheet(Styles.button_secondary())
        self.btn_export_to_muedit.setToolTip("Convert OpenHD-EMG JSON files to MUEdit MAT format")
        self.btn_export_to_muedit.clicked.connect(self.export_json_to_muedit)
        self.btn_export_to_muedit.setEnabled(False)
        self.buttons.append(self.btn_export_to_muedit)

        # Button to launch MUEdit
        self.btn_launch_muedit = QPushButton("Open MUEdit")
        self.btn_launch_muedit.setStyleSheet(Styles.button_secondary())
        self.btn_launch_muedit.setToolTip("Launch MUEdit for manual cleaning of decomposition results")
        self.btn_launch_muedit.clicked.connect(self.launch_muedit)
        self.btn_launch_muedit.setEnabled(False)
        self.buttons.append(self.btn_launch_muedit)

        self.btn_show_results = LoadingButton("Show Decomposition Results")
        self.btn_show_results.setStyleSheet(Styles.button_primary())
        self.btn_show_results.setToolTip("Open OpenHD-EMG to view decomposition results")
        self.btn_show_results.clicked.connect(self.display_results)
        self.buttons.append(self.btn_show_results)

    def export_json_to_muedit(self):
        """Export all OpenHD-EMG JSON files to MUEdit MAT format."""
        if not self.resultfiles:
            self.warn("No decomposition files found to export.")
            return

        # Filter for JSON files only
        json_files = [f for f in self.resultfiles if f.endswith('.json')]
        if not json_files:
            self.warn("No JSON files found. Only JSON files can be exported to MUEdit format.")
            return

        logger.info(f"Exporting {len(json_files)} JSON file(s) to MUEdit format...")
        success_count = 0
        error_count = 0
        error_messages = []

        for json_file in json_files:
            try:
                # Check if MUEdit file already exists
                if is_muedit_file_exists(json_file):
                    logger.info(f"MUEdit file already exists for {os.path.basename(json_file)}, skipping...")
                    continue

                # Export to MUEdit format
                muedit_file = export_to_muedit_mat(json_file)
                if muedit_file:
                    success_count += 1
                    logger.info(f"Successfully exported: {os.path.basename(muedit_file)}")
            except Exception as e:
                error_count += 1
                error_msg = f"Failed to export {os.path.basename(json_file)}: {str(e)}"
                error_messages.append(error_msg)
                logger.error(error_msg)

        # Update file list to include new MUEdit files
        self.get_decomposition_results()

        # Show summary to user
        if success_count > 0 and error_count == 0:
            self.info(f"Successfully exported {success_count} file(s) to MUEdit format.")
            self.btn_launch_muedit.setEnabled(True)
        elif success_count > 0 and error_count > 0:
            self.warn(f"Exported {success_count} file(s) successfully, but {error_count} file(s) failed:\n" +
                     "\n".join(error_messages))
            self.btn_launch_muedit.setEnabled(True)
        else:
            self.error(f"Failed to export files:\n" + "\n".join(error_messages))

    def launch_muedit(self):
        """Launches MUEdit for manual cleaning of decomposition results."""
        logger.info("Launching MUEdit for manual cleaning...")
        try:
            # Launch MUEdit - adjust command based on installation
            # User needs to have MUEdit installed and accessible
            subprocess.Popen(["muedit"])
            self.info("MUEdit launched. Please manually clean the decomposition files and save them back to the decomposition_auto folder.")
        except FileNotFoundError:
            self.error("MUEdit is not installed or not in PATH. Please install MUEdit first.\n"
                      "Repository: https://github.com/haripen/MUedit/tree/devHP")
        except Exception as e:
            self.error(f"Failed to launch MUEdit: {str(e)}")

    def display_results(self):
        """Displays the decomposition results in the UI."""
        results_path = self.get_decomposition_results()
        self.btn_show_results.start_loading()
        if not results_path:
            return
        self.start_openhdemg(self.btn_show_results.stop_loading)
        self.resultsDisplayed.emit(results_path)
        self.complete_step()  # Mark step as complete

    def start_openhdemg(self, on_started_callback=None):
        """Starts the OpenHD-EMG application and optionally calls a callback when it appears to be running."""
        if not config.get(Settings.OPENHDEMG_INSTALLED) or None:
            self.warn("OpenHD-EMG virtual environment path is not set or invalid. Please set it in Settings first.")
            return

        logger.info(f"Starting openhdemg!")
        command = ["openhdemg", "-m", "openhdemg.gui.openhdemg_gui"]
        proc = subprocess.Popen(command)

        # Starten eines Threads, der nach einer kurzen Zeit prüft, ob der Prozess noch läuft.
        def poll_process():
            time.sleep(2)
            if proc.poll() is None:
                logger.debug("OpenHD-EMG has started.")
                if on_started_callback:
                    on_started_callback()
            else:
                logger.error("OpenHD-EMG terminated unexpectedly.")

        threading.Thread(target=poll_process, daemon=True).start()

    def get_decomposition_results(self):
        """
        Retrieves the decomposition results from the decomposition_auto folder.
        Detects original decomposition files (.json/.pkl) and tracks which have been cleaned in MUEdit.
        Updates progress UI to show cleaning status.
        """
        self.resultfiles = []
        self.error_messages = []
        self.original_decomp_files = []
        self.edited_files = []

        folder_content_widget = global_state.get_widget("folder_content")
        if not os.path.exists(self.expected_folder):
            self.error("The decomposition_auto folder does not exist or is not accessible from the application.")
            self.btn_apply_mapping.setEnabled(False)
            self.btn_launch_muedit.setEnabled(False)
            self.progress_container.setVisible(False)
            return None

        # Scan folder for decomposition result files and edited files
        for file in os.listdir(self.expected_folder):
            file_path = os.path.join(self.expected_folder, file)

            # Check for edited files from MUEdit
            if file.endswith("_muedit_edited.mat"):
                logger.info(f"MUEdit edited file found: {file_path}")
                self.edited_files.append(file)
            # Check for MUEdit MAT files (not edited yet)
            elif file.endswith("_muedit.mat") and not file.endswith("_muedit_edited.mat"):
                logger.debug(f"MUEdit MAT file (not edited): {file_path}")
                # These are intermediate files, don't add to main result list
            # Check for original decomposition results
            elif file.endswith(".json") or file.endswith(".pkl"):
                logger.info(f"Decomposition result file found: {file_path}")
                self.resultfiles.append(file_path)
                # Extract base name for tracking (without extension)
                base_name = os.path.splitext(file)[0]
                self.original_decomp_files.append(base_name)

        # Update UI based on files found
        if self.resultfiles:
            folder_content_widget.update_folder_content()
            self.btn_apply_mapping.setEnabled(True)

            # Enable export button if JSON files are present
            has_json_files = any(f.endswith('.json') for f in self.resultfiles)
            self.btn_export_to_muedit.setEnabled(has_json_files)

            # Enable MUEdit launch button if MUEdit files exist
            has_muedit_files = any(
                os.path.exists(f.replace('.json', '_muedit.mat'))
                for f in self.resultfiles if f.endswith('.json')
            )
            self.btn_launch_muedit.setEnabled(has_muedit_files)

            # Show and update progress UI
            self.update_progress_ui()

            # If mapping exists, process mapped files
            self.process_mapped_files()
        else:
            self.btn_apply_mapping.setEnabled(False)
            self.btn_export_to_muedit.setEnabled(False)
            self.btn_launch_muedit.setEnabled(False)
            self.progress_container.setVisible(False)

        if self.resultfiles and not self.error_messages:
            return self.resultfiles
        elif self.resultfiles and self.error_messages:
            self.warn(*self.error_messages)
            return self.resultfiles

        return None

    def update_progress_ui(self):
        """Updates the progress UI to show MUEdit cleaning status."""
        if not self.original_decomp_files:
            self.progress_container.setVisible(False)
            return

        # Show progress container
        self.progress_container.setVisible(True)

        # Calculate progress
        total_files = len(self.original_decomp_files)
        edited_count = len(self.edited_files)
        progress_percentage = int((edited_count / total_files) * 100) if total_files > 0 else 0

        # Update progress bar and label
        self.progress_bar.setValue(progress_percentage)
        self.progress_label.setText(f"Manual Cleaning Progress: {edited_count}/{total_files} files ({progress_percentage}%)")

        # Clear existing file status items
        for i in reversed(range(self.file_status_layout.count())):
            widget = self.file_status_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Create file status items
        for base_name in self.original_decomp_files:
            # Check if this file has been edited
            edited_name = f"{base_name}_muedit_edited.mat"
            is_edited = edited_name in self.edited_files

            # Create status label
            if is_edited:
                status_text = f"✅ {base_name}"
                status_color = Colors.GREEN_700
            else:
                status_text = f"⏳ {base_name} (pending)"
                status_color = Colors.TEXT_MUTED

            status_label = QLabel(status_text)
            status_label.setStyleSheet(f"""
                color: {status_color};
                padding: 4px;
                font-size: 12px;
            """)
            self.file_status_layout.addWidget(status_label)

        # Add stretch to push items to top
        self.file_status_layout.addStretch()

        # Check if all files are cleaned - enable completion
        if edited_count == total_files and total_files > 0:
            self.info(f"All {total_files} files have been cleaned in MUEdit!")
            # Could auto-complete step here if desired

    def process_file_with_channel(self, file_path, channel_selection):
        """
        Processes a .pkl file using its associated channel selection file.
        Calls the update_extras_in_pickle_file method with the channel selection info.
        """
        _, file_extension = os.path.splitext(file_path)
        if file_extension == ".pkl" or file_extension == ".json" and file_path not in self.processed_files:
            logger.info(f"Processing {file_extension} file: {file_path} with channel selection: {channel_selection}")
            self.processed_files.append(file_path)
            try:
                if file_extension == ".pkl":
                    update_extras_in_pickle_file(file_path, channel_selection)
                elif file_extension == ".json":
                    update_extras_in_json_file(file_path, channel_selection)
                self.btn_show_results.setEnabled(True)
                self.btn_apply_mapping.setEnabled(False)
            except ValueError as e:
                error_msg = f"Error processing {file_path}: {str(e)}"
                self.error_messages.append(error_msg)
                logger.error(error_msg)
                self.warn("\n".join(self.error_messages))

    def init_file_checking(self):
        self.expected_folder = global_state.get_decomposition_path()
        self.watcher.addPath(self.expected_folder)
        logger.info(f"File checking initialized for folder: {self.expected_folder}")
        self.get_decomposition_results()

    def check(self):
        venv_openhdemg = config.get(Settings.OPENHDEMG_INSTALLED)
        if venv_openhdemg is None or False:
            self.warn("openhdemg is not installed. Please download it in Settings first.")
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)

        try:
            self.expected_folder = global_state.get_decomposition_path()
            self.clear_status()
            logger.info(f"Decomposition folder set to: {self.expected_folder}")
        except ValueError:
            self.setActionButtonsEnabled(False)

    def open_mapping_dialog(self):
        """
        Opens the mapping dialog to allow the user to create a 1:1 mapping between
        decomposition files and channel selection files.
        """
        dialog = MappingDialog(existing_mapping=self.decomp_mapping)
        if dialog.exec_() == QDialog.Accepted:
            self.decomp_mapping = dialog.mapping
            logger.info(f"Mapping dialog accepted. Mapping: {self.decomp_mapping}")
            # If a mapping has been performed, process each mapped file
            self.process_mapped_files()
        else:
            logger.info("Mapping dialog canceled.")

    def process_mapped_files(self):
        if self.decomp_mapping is not None:
            for file_path in self.resultfiles:
                file_name = os.path.basename(file_path)
                if file_name in self.decomp_mapping:
                    chan_file = self.decomp_mapping[file_name]
                    chan_file = os.path.join(global_state.get_channel_selection_path(), chan_file)
                    logger.info(f"Processing file {file_path} with channel selection file {chan_file}.")
                    self.process_file_with_channel(file_path, chan_file)
