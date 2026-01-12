import sys
from PyQt5.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QDialogButtonBox, QDesktopWidget, QScrollArea
)
from hdsemg_pipe.settings.tabs.channelselection import init as channelselectiontab_init
from hdsemg_pipe.settings.tabs.workfolder import init_workfolder_widget
from hdsemg_pipe.settings.tabs.openhdemg import init as init_openhdemg_widget
from hdsemg_pipe.settings.tabs.line_noise import init as init_line_noise_widget
from hdsemg_pipe.settings.tabs.log_setting import init as init_logging_widget
from hdsemg_pipe.settings.tabs.muedit_settings import init as init_muedit_widget
from hdsemg_pipe._log.log_config import logger
from PyQt5.QtCore import pyqtSignal, Qt

class SettingsDialog(QDialog):
    settingsAccepted = pyqtSignal()
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle("Settings")
        # Make the dialog smaller and resizable
        self.resize(550, 400)
        self.setMinimumSize(450, 350)
        self.initUI()
        # Center the dialog on screen
        self.centerOnScreen()

    def initUI(self):
        """Initialize the settings dialog with default styling."""
        # Use default white background, no custom theme
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create individual tabs
        self.channel_selection_tab = QWidget()
        self.workfolder_tab = QWidget()
        self.line_noise_tab = QWidget()
        self.openhdemg_tab = QWidget()
        self.muedit_tab = QWidget()
        self.logging_tab = QWidget()

        # Add tabs to the tab widget
        self.tab_widget.addTab(self.channel_selection_tab, "Channel Selection App")
        self.tab_widget.addTab(self.workfolder_tab, "Work Folder")
        self.tab_widget.addTab(self.line_noise_tab, "Line Noise Removal")
        self.tab_widget.addTab(self.openhdemg_tab, "openhdemg")
        self.tab_widget.addTab(self.muedit_tab, "MUEdit")
        self.tab_widget.addTab(self.logging_tab, "Logging")


        # Initialize content for each tab
        self.initChannelSelectionTab()
        self.initWorkfolderTab()
        self.initLineNoiseTab()
        self.initOpenHDsEMGTab()
        self.initMUEditTab()
        self.initLoggingTab()

        # Add standard dialog buttons (OK and Cancel) with default styling
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        main_layout.addWidget(self.button_box)

    def initChannelSelectionTab(self):
        """Initialize the 'General' settings tab."""
        channelselection_tab = channelselectiontab_init(self)
        self._wrapInScrollArea(self.channel_selection_tab, channelselection_tab)

    def initWorkfolderTab(self):
        """Initialize the 'Workfolder' settings tab."""
        workfolder_tab = init_workfolder_widget(self)
        self._wrapInScrollArea(self.workfolder_tab, workfolder_tab)

    def initOpenHDsEMGTab(self):
        """Initialize the 'openhdemg' settings tab."""
        openhdemg_tab = init_openhdemg_widget(self)
        self._wrapInScrollArea(self.openhdemg_tab, openhdemg_tab)

    def initLineNoiseTab(self):
        """Initialize the 'Line Noise Removal' settings tab."""
        line_noise_tab = init_line_noise_widget(self)
        self._wrapInScrollArea(self.line_noise_tab, line_noise_tab)

    def initMUEditTab(self):
        """Initialize the 'MUEdit' settings tab."""
        muedit_tab = init_muedit_widget(self)
        self._wrapInScrollArea(self.muedit_tab, muedit_tab)

    def initLoggingTab(self):
        """Initialize the 'Logging' settings tab."""
        log_tab = init_logging_widget(self)
        self._wrapInScrollArea(self.logging_tab, log_tab)

    def _wrapInScrollArea(self, tab_widget, content_layout):
        """Wrap tab content in a scroll area to make it scrollable."""
        # Create a container widget for the content
        container = QWidget()
        container.setLayout(content_layout)

        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        # Set the scroll area as the tab's layout
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

    def accept(self):
        """Emit signal and close dialog when OK is pressed."""
        self.settingsAccepted.emit()  # Emit signal
        logger.info("Settings accepted and dialog closed.")
        super().accept()  # Call parent accept method to close the dialog

    def centerOnScreen(self):
        """Center the dialog on the screen."""
        screen = QApplication.desktop().screenGeometry()
        dialog_geometry = self.geometry()
        x = (screen.width() - dialog_geometry.width()) // 2
        y = (screen.height() - dialog_geometry.height()) // 2
        self.move(x, y)
