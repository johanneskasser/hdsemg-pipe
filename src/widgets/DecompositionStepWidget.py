import os

from PyQt5.QtCore import pyqtSignal, QFileSystemWatcher
from PyQt5.QtWidgets import QPushButton, QDialog

from actions.file_utils import update_extras_in_pickle_file
from log.log_config import logger
from state.global_state import global_state
from widgets.BaseStepWidget import BaseStepWidget
from widgets.MappingDialog import MappingDialog


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

        self.btn_show_results = QPushButton("Show Decomposition Results")
        self.btn_show_results.clicked.connect(self.display_results)
        self.buttons.append(self.btn_show_results)

    def display_results(self):
        """Displays the decomposition results in the UI."""
        results_path = self.get_decomposition_results()
        if not results_path:
            return
        self.resultsDisplayed.emit(results_path)
        self.complete_step()  # Mark step as complete

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
            if file.endswith(".mat") or file.endswith(".pkl"):
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
        if file_extension == ".pkl" and file_path not in self.processed_files:
            logger.info(f"Processing pickle file: {file_path} with channel selection: {channel_selection}")
            self.processed_files.append(file_path)
            try:
                update_extras_in_pickle_file(file_path, channel_selection)
                self.btn_show_results.setEnabled(True)
                self.btn_apply_mapping.setEnabled(False)
            except ValueError as e:
                error_msg = f"Error processing {file_path}: {str(e)}"
                self.error_messages.append(error_msg)
                logger.error(error_msg)
                self.warn(*self.error_messages)

    def init_file_checking(self):
        self.expected_folder = global_state.get_decomposition_path()
        self.watcher.addPath(self.expected_folder)
        logger.info(f"File checking initialized for folder: {self.expected_folder}")

    def check(self):
        try:
            self.expected_folder = global_state.get_decomposition_path()
            self.clear_status()
            logger.info(f"Decomposition folder set to: {self.expected_folder}")
        except ValueError:
            self.setActionButtonsEnabled(False)
            logger.error("Failed to set decomposition folder.")

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
                    logger.info(f"Processing file {file_path} with channel selection file {chan_file}.")
                    self.process_file_with_channel(file_path, chan_file)
