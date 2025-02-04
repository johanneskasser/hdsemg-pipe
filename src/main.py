import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QAction,
    qApp, QStyle
)

from HDsEMG.pipeline.masterwindow.src.settings.settings_dialog import SettingsDialog
from log.log_config import logger, setup_logging
from widgets.StepWidget import StepWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("HDsEMG Pipeline")
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.setGeometry(100, 100, 600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        grid_layout = QGridLayout(central_widget)
        grid_layout.setColumnStretch(0, 1)

        step_data = [
            {"name": "Open .mat File", "tooltip": "Select the .mat file containing your data.",
             "button_text": "Open File", "action": self.open_file},
            {"name": "Channel Selection", "tooltip": "Select the channels to be processed.",
             "button_text": "Select Channels", "action": self.select_channels},
            {"name": "Decomposition", "tooltip": "Perform signal decomposition on the selected channels.",
             "button_text": "Decompose", "action": self.decompose},
            {"name": "Result Visualization", "tooltip": "Visualize the results of the analysis.",
             "button_text": "Visualize", "action": self.visualize}
        ]

        # Create StepWidget instances
        self.steps = []
        for i, data in enumerate(step_data):
            step = StepWidget(data["name"], data["tooltip"], data["action"], data["button_text"])
            self.steps.append(step)
            grid_layout.addWidget(step, i, 0)

        # Disable all steps except the first
        for step in self.steps[1:]:
            step.setActionButtonEnabled(False)

        # Connect step completion signals
        for i, step in enumerate(self.steps[:-1]):
            step.stepCompleted.connect(lambda idx=i: self.enable_next_step(idx))

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
            self.steps[index + 1].setActionButtonEnabled(True)

    def openPreferences(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self)
        if dialog.exec_():
            logger.debug("Settings dialog closed and accepted")
        else:
            logger.debug("Settings dialog closed")

    # Define placeholder functions for each step's execution
    def open_file(self):
        logger.info("Opening .mat file...")

    def select_channels(self):
        logger.info("Selecting channels...")

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
