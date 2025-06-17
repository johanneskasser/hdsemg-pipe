import sys
from PyQt5.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QDialogButtonBox
)
from hdsemg_pipe.settings.tabs.channelselection import init as channelselectiontab_init
from hdsemg_pipe.settings.tabs.workfolder import init_workfolder_widget
from hdsemg_pipe.settings.tabs.openhdemg import init as init_openhdemg_widget
from hdsemg_pipe.settings.tabs.log_setting import init as init_logging_widget
from hdsemg_pipe._log.log_config import logger
from PyQt5.QtCore import pyqtSignal

class SettingsDialog(QDialog):
    settingsAccepted = pyqtSignal()
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(400, 300)
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create individual tabs
        self.channel_selection_tab = QWidget()
        self.workfolder_tab = QWidget()
        self.openhdemg_tab = QWidget()
        self.logging_tab = QWidget()

        # Add tabs to the tab widget
        self.tab_widget.addTab(self.channel_selection_tab, "Channel Selection App")
        self.tab_widget.addTab(self.workfolder_tab, "Work Folder")
        self.tab_widget.addTab(self.openhdemg_tab, "openhdemg")
        self.tab_widget.addTab(self.logging_tab, "Logging")


        # Initialize content for each tab
        self.initChannelSelectionTab()
        self.initWorkfolderTab()
        self.initOpenHDsEMGTab()
        self.initLoggingTab()

        # Add standard dialog buttons (OK and Cancel)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def initChannelSelectionTab(self):
        """Initialize the 'General' settings tab."""
        channelselection_tab = channelselectiontab_init(self)
        self.channel_selection_tab.setLayout(channelselection_tab)

    def initWorkfolderTab(self):
        """Initialize the 'Workfolder' settings tab."""
        workfolder_tab = init_workfolder_widget(self)
        self.workfolder_tab.setLayout(workfolder_tab)

    def initOpenHDsEMGTab(self):
        """Initialize the 'openhdemg' settings tab."""
        openhdemg_tab = init_openhdemg_widget(self)
        self.openhdemg_tab.setLayout(openhdemg_tab)

    def initLoggingTab(self):
        """Initialize the 'Logging' settings tab."""
        log_tab = init_logging_widget(self)
        self.logging_tab.setLayout(log_tab)

    def accept(self):
        """Emit signal and close dialog when OK is pressed."""
        self.settingsAccepted.emit()  # Emit signal
        logger.info("Settings accepted and dialog closed.")
        super().accept()  # Call parent accept method to close the dialog
