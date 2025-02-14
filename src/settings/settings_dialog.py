import sys
from PyQt5.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QDialogButtonBox
)
from .tabs.channelselection import init as channelselectiontab_init
from .tabs.workfolder import init_workfolder_widget
from log.log_config import logger
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
        self.advanced_tab = QWidget()
        self.network_tab = QWidget()

        # Add tabs to the tab widget
        self.tab_widget.addTab(self.channel_selection_tab, "Channel Selection App")
        self.tab_widget.addTab(self.workfolder_tab, "Work Folder")
        self.tab_widget.addTab(self.network_tab, "PlaceHolder2")

        # Initialize content for each tab
        self.initChannelSelectionTab()
        self.initWorkfolderTab()
        self.initNetworkTab()

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

    def initNetworkTab(self):
        """Initialize the 'Network' settings tab."""
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Network Settings"))
        # Add network-related settings widgets here.
        self.network_tab.setLayout(layout)

    def accept(self):
        """Emit signal and close dialog when OK is pressed."""
        self.settingsAccepted.emit()  # Emit signal
        logger.info("Settings accepted and dialog closed.")
        super().accept()  # Call parent accept method to close the dialog
