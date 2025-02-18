import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QAction, qApp, QStyle, QTextEdit, QFrame
from HDsEMG.pipeline.masterwindow.src.settings.settings_dialog import SettingsDialog
from log.log_config import logger, setup_logging
from actions.openfile import open_mat_file_or_folder, count_mat_files
from actions.file_manager import start_file_processing
from state.global_state import global_state
from widgets.ChannelSelectionStepWidget import ChannelSelectionStepWidget
from widgets.FolderContentWidget import FolderContentWidget
from widgets.GridAssociationWidget import GridAssociationWidget
from widgets.OpenFileStepWidget import OpenFileStepWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.folder_content_widget = None
        self.steps = []
        self.settingsDialog = SettingsDialog(self)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("HDsEMG Pipeline")
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.setGeometry(100, 100, 600, 400)

        # Menu Bar
        menubar = self.menuBar()
        settings_menu = menubar.addMenu('Settings')

        preferences_action = QAction('Preferences', self)
        preferences_action.triggered.connect(self.openPreferences)
        settings_menu.addAction(preferences_action)

        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(qApp.quit)
        settings_menu.addAction(exit_action)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        grid_layout = QGridLayout(central_widget)
        grid_layout.setColumnStretch(0, 1)

        # Folder Content Widget
        self.folder_content_widget = FolderContentWidget()
        global_state.register_widget("folder_content", self.folder_content_widget)
        grid_layout.addWidget(self.folder_content_widget, 0, 0, 1, 1)

        # Horizontal Line Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)  # Horizontal Line
        separator.setFrameShadow(QFrame.Sunken)
        grid_layout.addWidget(separator, 1, 0, 1, 1)  # Row after FolderContentWidget

        # Schritt 1: Datei öffnen
        step1 = OpenFileStepWidget(0, "Open .mat File(s)", "Select the .mat file containing your data.")
        global_state.register_widget("step1", step1)
        self.steps.append(step1)
        grid_layout.addWidget(step1, 2, 0)
        step1.check()
        self.settingsDialog.settingsAccepted.connect(step1.check)

        # Schritt 2: Grid-Assoziationen
        step2 = GridAssociationWidget(1)
        global_state.register_widget("step2", step2)
        self.steps.append(step2)
        grid_layout.addWidget(step2, 3, 0)
        step2.check()
        self.settingsDialog.settingsAccepted.connect(step2.check)

        # Schritt 3: Kanal-Auswahl
        step3 = ChannelSelectionStepWidget(2)
        global_state.register_widget("step3", step3)
        self.steps.append(step3)
        grid_layout.addWidget(step3, 4, 0)
        step3.check()
        self.settingsDialog.settingsAccepted.connect(step3.check)

        # Connect the Steps
        step1.fileSelected.connect(step2.check)
        step1.fileSelected.connect(self.folder_content_widget.update_folder_content)
        step2.stepCompleted.connect(step3.update)
        step2.stepCompleted.connect(self.folder_content_widget.update_folder_content)


        # Disable all steps except the first
        for step in self.steps[1:]:
            step.setActionButtonsEnabled(False)

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
        if self.settingsDialog.exec_():
            logger.debug("Settings dialog closed and accepted")
        else:
            logger.debug("Settings dialog closed")

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
