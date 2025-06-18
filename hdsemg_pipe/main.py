import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QAction, qApp, QStyle, QFrame, QLabel

from hdsemg_pipe._log.exception_hook import exception_hook
from hdsemg_pipe.controller.automatic_state_reconstruction import start_reconstruction_workflow
from hdsemg_pipe.settings.settings_dialog import SettingsDialog
from hdsemg_pipe.actions.file_manager import start_file_processing
from hdsemg_pipe._log.log_config import logger, setup_logging
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.ChannelSelectionStepWidget import ChannelSelectionStepWidget
from hdsemg_pipe.widgets.DecompositionStepWidget import DecompositionResultsStepWidget
from hdsemg_pipe.widgets.DefineRoiStepWidget import DefineRoiStepWidget
from hdsemg_pipe.widgets.FolderContentWidget import FolderContentWidget
from hdsemg_pipe.widgets.GridAssociationStepWidget import GridAssociationWidget
from hdsemg_pipe.widgets.OpenFileStepWidget import OpenFileStepWidget
from hdsemg_pipe.version import __version__

import hdsemg_pipe.resources_rc


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.folder_content_widget = None
        self.steps = []
        self.settingsDialog = SettingsDialog(self)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("hdsemg-pipe")
        self.setWindowIcon(QIcon(":/resources/icon.png"))
        self.setGeometry(100, 100, 600, 400)

        # Menu Bar
        menubar = self.menuBar()
        settings_menu = menubar.addMenu('Settings')

        preferences_action = QAction('Preferences', self)
        preferences_action.triggered.connect(self.openPreferences)
        settings_menu.addAction(preferences_action)

        open_existing_workfolder_action = QAction('Open Existing Workfolder', self)
        open_existing_workfolder_action.triggered.connect(lambda: start_reconstruction_workflow(self))
        settings_menu.addAction(open_existing_workfolder_action)

        # Add a separator
        settings_menu.addSeparator()

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
        global_state.register_widget(name="folder_content", widget=self.folder_content_widget)
        grid_layout.addWidget(self.folder_content_widget, 0, 0, 1, 1)

        # Horizontal Line Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)  # Horizontal Line
        separator.setFrameShadow(QFrame.Sunken)
        grid_layout.addWidget(separator, 1, 0, 1, 1)  # Row after FolderContentWidget

        # Schritt 1: Datei öffnen
        step1 = OpenFileStepWidget(1, "Open File(s)", "Select the file containing your data. You can select a single file or a folder containing multiple files. The application will search for all supported files in the selected folder.")
        global_state.register_widget(step1)
        self.steps.append(step1)
        grid_layout.addWidget(step1, 2, 0)
        step1.check()
        self.settingsDialog.settingsAccepted.connect(step1.check)

        # Schritt 2: Grid-Assoziationen
        step2 = GridAssociationWidget(2)
        global_state.register_widget(step2)
        self.steps.append(step2)
        grid_layout.addWidget(step2, 3, 0)
        step2.check()
        self.settingsDialog.settingsAccepted.connect(step2.check)

        step3 = DefineRoiStepWidget(3)
        global_state.register_widget(step3)
        self.steps.append(step3)
        grid_layout.addWidget(step3, 4, 0)
        step3.check()
        self.settingsDialog.settingsAccepted.connect(step3.check)

        # Schritt 4: Kanal-Auswahl
        step4 = ChannelSelectionStepWidget(4)
        global_state.register_widget(step4)
        self.steps.append(step4)
        grid_layout.addWidget(step4, 5, 0)
        step4.check()
        self.settingsDialog.settingsAccepted.connect(step4.check)

        # Schritt 4: Descomposition
        step5 = DecompositionResultsStepWidget(4, "Decomposition Results", f"This widget watches the decomposition path for file changes. Please perform decomposition manually and this application will detect the changes and you will be able to proceed.")
        global_state.register_widget(step5)
        self.steps.append(step5)
        grid_layout.addWidget(step5, 6, 0)
        step5.check()
        self.settingsDialog.settingsAccepted.connect(step5.check)

        # Connect the Steps
        step1.fileSelected.connect(step2.check)
        step1.fileSelected.connect(self.folder_content_widget.update_folder_content)
        step1.fileSelected.connect(step5.init_file_checking)
        step2.stepCompleted.connect(step3.check)
        step2.stepCompleted.connect(self.folder_content_widget.update_folder_content)
        step3.stepCompleted.connect(step4.update)
        step3.stepCompleted.connect(self.folder_content_widget.update_folder_content)

        # Disable all steps except the first
        for step in self.steps[1:]:
            step.setActionButtonsEnabled(False)

        version_label = QLabel(f"hdsemg-pipe | University of Applied Sciences Campus Wien - Physiotherapy | Version: {__version__}")
        version_label.setStyleSheet("padding-right: 10px;")
        self.statusBar().addPermanentWidget(version_label)

    def openPreferences(self):
        """Open the settings dialog."""
        if self.settingsDialog.exec_():
            logger.debug("Settings dialog closed and accepted")
            for step in self.steps:
                step.check()
        else:
            logger.debug("Settings dialog closed")

    def start_processing_with_step(step):
        """Start processing files and update the given step dynamically."""
        start_file_processing(step)

def main():
    app = QApplication(sys.argv)
    setup_logging()
    sys.excepthook = exception_hook
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
