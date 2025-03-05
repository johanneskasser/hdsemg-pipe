from PyQt5.QtCore import pyqtSignal, QFileSystemWatcher
from PyQt5.QtWidgets import QPushButton, QVBoxLayout
import os
from log.log_config import logger
from actions.file_utils import update_extras_in_pickle_file

from widgets.BaseStepWidget import BaseStepWidget
from state.global_state import global_state

class DecompositionResultsStepWidget(BaseStepWidget):
    resultsDisplayed = pyqtSignal(str)

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(step_index, step_name, tooltip, parent)
        self.expected_folder = None

        # Initialize file system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.get_decomposition_results)

        self.error_messages = []

        # Perform an initial check
        self.check()

    def create_buttons(self):
        """Creates buttons for displaying decomposition results."""
        btn_show_results = QPushButton("Show Decomposition Results")
        btn_show_results.clicked.connect(self.display_results)
        self.buttons.append(btn_show_results)

    def display_results(self):
        """Displays the decomposition results in the UI."""
        results_path = self.get_decomposition_results()
        if not results_path:
            return
        self.resultsDisplayed.emit(results_path)
        self.complete_step()  # Mark step as complete

    def get_decomposition_results(self):
        """Retrieves the decomposition results from a predefined folder."""
        resultfiles = []
        self.error_messages = []
        if not os.path.exists(self.expected_folder):
            self.error("The decomposition folder does not exist or is not accessible from the application.")
            return None
        for file in os.listdir(self.expected_folder):
            if file.endswith(".mat") or file.endswith(".pkl"):
                file_path = os.path.join(self.expected_folder, file)
                logger.info(f"Result file {file_path} found.")
                resultfiles.append(file_path)
        if len(resultfiles) != 0 and self.error_messages.__len__() == 0:
            self.complete_step()
            return resultfiles
        elif len(resultfiles) != 0 and self.error_messages.__len__() > 0:
            self.warn(*self.error_messages)
            return resultfiles

    def process_file(self, file_path):
        _, file_extension = os.path.splitext(file_path)
        if file_extension == ".pkl":
            logger.info(f"Processing pickle file: {file_path}")
            try:
                update_extras_in_pickle_file(file_path, "Test1")
            except ValueError as e:
                self.error_messages.append(f"{str(e)}\n")

    def init_file_checking(self):
        self.expected_folder = global_state.get_decomposition_path()
        self.watcher.addPath(self.expected_folder)

    def check(self):
        logger.debug("Decomposition Result Step Widget check method called.")
        try:
            self.expected_folder = global_state.get_decomposition_path()
            self.clear_status()
        except ValueError:
            self.setActionButtonsEnabled(False)