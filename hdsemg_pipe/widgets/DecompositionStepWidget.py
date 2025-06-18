import os
import subprocess
import threading
import time

from PyQt5.QtCore import pyqtSignal, QFileSystemWatcher
from PyQt5.QtWidgets import QPushButton, QDialog

from hdsemg_pipe.actions.file_utils import update_extras_in_pickle_file, update_extras_in_json_file
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.loadingbutton import LoadingButton
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.widgets.MappingDialog import MappingDialog


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

        # Perform an initial check
        self.check()

    def create_buttons(self):
        """Creates buttons for displaying decomposition results."""
        # Mapping button is initially disabled and will be enabled if files are detected
        self.btn_apply_mapping = QPushButton("Apply mapping")
        self.btn_apply_mapping.setToolTip("Apply mapping of decomposition results and source files")
        self.btn_apply_mapping.clicked.connect(self.open_mapping_dialog)
        self.btn_apply_mapping.setEnabled(False)
        self.buttons.append(self.btn_apply_mapping)

        self.btn_show_results = LoadingButton("Show Decomposition Results")
        self.btn_show_results.clicked.connect(self.display_results)
        self.buttons.append(self.btn_show_results)

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
        Retrieves the decomposition results from a predefined folder.
        If files of interest (.mat or .pkl) are detected, the mapping button is activated.
        If a mapping exists, each mapped file is processed by retrieving its associated channel selection file.
        """
        self.resultfiles = []
        self.error_messages = []
        folder_content_widget = global_state.get_widget("folder_content")
        if not os.path.exists(self.expected_folder):
            self.error("The decomposition folder does not exist or is not accessible from the application.")
            self.btn_apply_mapping.setEnabled(False)
            return None

        for file in os.listdir(self.expected_folder):
            if file.endswith(".json") or file.endswith(".pkl"):
                file_path = os.path.join(self.expected_folder, file)
                logger.info(f"Result file {file_path} found.")
                self.resultfiles.append(file_path)

        if self.resultfiles:
            folder_content_widget.update_folder_content()
            self.btn_apply_mapping.setEnabled(True)
            return
        else:
            self.btn_apply_mapping.setEnabled(False)

        # If a mapping has been performed, process each mapped file
        self.process_mapped_files()

        if self.resultfiles and not self.error_messages:
            self.complete_step()
            return self.resultfiles
        elif self.resultfiles and self.error_messages:
            self.warn(*self.error_messages)
            return self.resultfiles

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
