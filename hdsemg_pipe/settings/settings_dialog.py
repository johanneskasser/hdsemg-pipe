import sys
from PyQt5.QtWidgets import (
    QApplication, QDialog, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QDialogButtonBox
)
from hdsemg_pipe.settings.tabs.channelselection import init as channelselectiontab_init
from hdsemg_pipe.settings.tabs.workfolder import init_workfolder_widget
from hdsemg_pipe.settings.tabs.openhdemg import init as init_openhdemg_widget
from hdsemg_pipe.settings.tabs.line_noise import init as init_line_noise_widget
from hdsemg_pipe.settings.tabs.log_setting import init as init_logging_widget
from hdsemg_pipe.settings.tabs.muedit_settings import init as init_muedit_widget
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, BorderRadius, Fonts, Styles
from PyQt5.QtCore import pyqtSignal

class SettingsDialog(QDialog):
    settingsAccepted = pyqtSignal()
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(700, 500)
        self.initUI()

    def initUI(self):
        """Initialize the settings dialog with modern styling."""
        # Apply modern dialog styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_SECONDARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                background-color: {Colors.BG_PRIMARY};
                border-radius: {BorderRadius.LG};
                padding: {Spacing.LG}px;
            }}
            QTabBar::tab {{
                background-color: {Colors.BG_SECONDARY};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-bottom: none;
                padding: {Spacing.SM}px {Spacing.LG}px;
                margin-right: 2px;
                border-top-left-radius: {BorderRadius.MD};
                border-top-right-radius: {BorderRadius.MD};
                font-size: {Fonts.SIZE_BASE};
            }}
            QTabBar::tab:selected {{
                background-color: {Colors.BG_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
            QTabBar::tab:hover {{
                background-color: {Colors.GRAY_100};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        main_layout.setSpacing(Spacing.LG)

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

        # Add standard dialog buttons (OK and Cancel) with modern styling
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # Style the button box buttons
        self.button_box.setStyleSheet(f"""
            QPushButton {{
                min-width: 80px;
                padding: {Spacing.SM}px {Spacing.LG}px;
                border-radius: {BorderRadius.MD};
                font-size: {Fonts.SIZE_BASE};
            }}
            QPushButton[text="OK"] {{
                background-color: {Colors.BLUE_600};
                color: white;
                border: none;
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
            QPushButton[text="OK"]:hover {{
                background-color: {Colors.BLUE_700};
            }}
            QPushButton[text="Cancel"] {{
                background-color: {Colors.BG_SECONDARY};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
            }}
            QPushButton[text="Cancel"]:hover {{
                background-color: {Colors.GRAY_100};
            }}
        """)

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

    def initLineNoiseTab(self):
        """Initialize the 'Line Noise Removal' settings tab."""
        line_noise_tab = init_line_noise_widget(self)
        self.line_noise_tab.setLayout(line_noise_tab)

    def initMUEditTab(self):
        """Initialize the 'MUEdit' settings tab."""
        muedit_tab = init_muedit_widget(self)
        self.muedit_tab.setLayout(muedit_tab)

    def initLoggingTab(self):
        """Initialize the 'Logging' settings tab."""
        log_tab = init_logging_widget(self)
        self.logging_tab.setLayout(log_tab)

    def accept(self):
        """Emit signal and close dialog when OK is pressed."""
        self.settingsAccepted.emit()  # Emit signal
        logger.info("Settings accepted and dialog closed.")
        super().accept()  # Call parent accept method to close the dialog
