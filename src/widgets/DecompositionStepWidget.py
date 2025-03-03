from PyQt5.QtCore import pyqtSignal, QFileSystemWatcher
from PyQt5.QtWidgets import QPushButton, QVBoxLayout
import os

from widgets.BaseStepWidget import BaseStepWidget
from state.global_state import global_state

class DecompositionResultsStepWidget(BaseStepWidget):
    resultsDisplayed = pyqtSignal(str)

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(step_index, step_name, tooltip, parent)
        self.expected_folder = None

        # Initialize file system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(self.expected_folder)
        self.watcher.directoryChanged.connect(self.check)

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
        if not os.path.exists(self.expected_folder):
            self.error("The decomposition folder does not exist or is not accessible from the application.")
            return None
        for file in os.listdir(self.expected_folder):
            if file.endswith(".mat"):
                return os.path.join(self.expected_folder, file)
        return None

    def check(self):
        try:
            self.expected_folder = global_state.get_decomposition_path()
            self.clear_status()
        except ValueError:
            self.setActionButtonsEnabled(False)