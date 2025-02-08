import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QAction, qApp, QStyle
from HDsEMG.pipeline.masterwindow.src.settings.settings_dialog import SettingsDialog
from log.log_config import logger, setup_logging
from actions.openfile import open_mat_file_or_folder, count_mat_files
from actions.file_manager import start_file_processing
from widgets.ChannelSelectionStepWidget import ChannelSelectionStepWidget
from widgets.OpenFileStepWidget import OpenFileStepWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.steps = []  # Define self.steps before use
        self.initUI()

    def initUI(self):
        self.setWindowTitle("HDsEMG Pipeline")
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.setGeometry(100, 100, 600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        grid_layout = QGridLayout(central_widget)
        grid_layout.setColumnStretch(0, 1)

        # Schritt 1: Datei öffnen
        step1 = OpenFileStepWidget(0, "Open .mat File", "Select the .mat file containing your data.")
        self.steps.append(step1)
        grid_layout.addWidget(step1, 0, 0)

        # Schritt 2: Kanal-Auswahl
        step2 = ChannelSelectionStepWidget(1)
        self.steps.append(step2)
        grid_layout.addWidget(step2, 1, 0)

        # Connect the fileSelected signal to update the ChannelSelectionStepWidget
        step1.fileSelected.connect(step2.update)


        # Disable all steps except the first
        for step in self.steps[1:]:
            step.setActionButtonsEnabled(False)

            # Menu Bar
            menubar = self.menuBar()
            settings_menu = menubar.addMenu('Settings')

            preferences_action = QAction('Preferences', self)
            preferences_action.triggered.connect(self.openPreferences)
            settings_menu.addAction(preferences_action)

            exit_action = QAction('Exit', self)
            exit_action.triggered.connect(qApp.quit)
            settings_menu.addAction(exit_action)

    def enable_next_step(self, index):
        """Enables the action button for the next step, if available."""
        if index + 1 < len(self.steps):
            self.steps[index + 1].setActionButtonsEnabled(True)

    def mark_step_completed(self, step_index):
        """Marks a step as completed and enables the next step."""
        if step_index < len(self.steps):
            self.steps[step_index].complete_step()

    def openPreferences(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self)
        if dialog.exec_():
            logger.debug("Settings dialog closed and accepted")
        else:
            logger.debug("Settings dialog closed")

    def select_file_or_folder(self, mode):
        """Handles file or folder selection and stores it globally."""
        selected_path = open_mat_file_or_folder(mode)
        if not selected_path:
            return  # User canceled selection

        # Store globally
        from state.global_state import mat_files
        mat_files.clear()

        # If folder, count .mat files
        if os.path.isdir(selected_path):
            mat_files.extend(count_mat_files(selected_path))

        self.steps[0].complete_step()  # Mark Step 1 as completed
        self.steps[1].setActionButtonsEnabled(True)  # Enable Step 2

    def start_processing_with_step(step):
        """Start processing files and update the given step dynamically."""
        start_file_processing(step)

    def decompose(self):
        logger.info("Performing decomposition...")

    def visualize(self):
        logger.info("Visualizing results...")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    setup_logging()
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
