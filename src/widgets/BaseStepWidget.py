from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QStyle, QToolButton, QSpacerItem, QSizePolicy, QVBoxLayout
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import pyqtSignal
from _log.log_config import logger
from state.global_state import global_state


class BaseStepWidget(QWidget):
    stepCompleted = pyqtSignal(int)  # Signal to report completed steps

    def __init__(self, step_index, step_name, tooltip, parent=None):
        """
        Base class for a step widget.

        :param step_index: The index number of the step
        :param step_name: The name of the step
        :param tooltip: Tooltip text for the widget
        """
        super().__init__(parent)
        self.step_index = step_index
        self.step_name = step_name
        self.step_completed = False

        self.layout = QHBoxLayout(self)
        self.setToolTip(tooltip)

        # Step Label (Bold Font, Fixed Width)
        self.name_label = QLabel(self.step_name)
        font = QFont()
        font.setBold(True)
        self.name_label.setFont(font)
        self.name_label.setFixedWidth(300)  # Fixed width to align icons
        self.layout.addWidget(self.name_label)

        # Info Icon with Tooltip
        self.info_button = QToolButton()
        self.info_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.info_button.setToolTip(tooltip)
        self.layout.addWidget(self.info_button)

        # Progress Display Label (e.g., "0/0")
        self.additional_information_label = QLabel("")
        self.layout.addWidget(self.additional_information_label)

        # Spacer to push buttons and status indicator to the right
        #self.layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))


        # Button Layout (to accommodate multiple buttons properly)
        self.button_layout = QVBoxLayout()
        self.layout.addLayout(self.button_layout)

        # Placeholder for checkmark space
        self.checkmark_label = QLabel()
        self.checkmark_label.setFixedWidth(30)  # Reserve space for checkmark
        self.layout.addWidget(self.checkmark_label)

        # Buttons Placeholder (to be defined in subclasses)
        self.buttons = []
        self.create_buttons()
        self.add_buttons_to_layout()

        # Status Indicator (Icon for warn, error, success)
        self.status_icon = QLabel()
        self.status_icon.setFixedWidth(30)
        self.status_icon.setVisible(False)
        self.layout.addWidget(self.status_icon)

        self.setLayout(self.layout)
        self.clear_status()

    def create_buttons(self):
        """Creates buttons. Must be overridden by subclasses."""
        pass

    def add_buttons_to_layout(self):
        """Adds buttons to the correct layout position automatically using a vertical layout."""
        for button in self.buttons:
            self.button_layout.addWidget(button)  # Add to vertical layout to prevent distortion

    def complete_step(self):
        """Marks the step as completed and displays a checkmark."""
        self.success(f"Step {self.step_index} completed successfully!")
        self.step_completed = True
        global_state.complete_widget(f"step{self.step_index}")
        self.stepCompleted.emit(self.step_index)

    def setActionButtonsEnabled(self, enabled):
        """Enables or disables action buttons."""
        if enabled == True and global_state.is_widget_completed(f"step{self.step_index - 1}") or enabled == False:
            for button in self.buttons:
                button.setEnabled(enabled)

    def success(self, message):
        """Displays a success message with a checkmark icon."""
        success_icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
        self.status_icon.setPixmap(success_icon.pixmap(20, 20))
        self.setToolTip(message)
        self.status_icon.setVisible(True)
        logger.info(f"Success: {message}")

    def warn(self, message):
        """Displays a warning message with a warning icon."""
        warn_icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
        self.status_icon.setPixmap(warn_icon.pixmap(20, 20))
        self.setToolTip(message)
        self.status_icon.setVisible(True)
        logger.warning(f"Warning: {message}")

    def error(self, message):
        """Displays an error message with a critical error icon."""
        error_icon = self.style().standardIcon(QStyle.SP_MessageBoxCritical)
        self.status_icon.setPixmap(error_icon.pixmap(20, 20))
        self.setToolTip(message)
        self.status_icon.setVisible(True)
        logger.error(f"Error: {message}")

    def clear_status(self):
        """Clears the status and resets the tooltip."""
        self.status_icon.clear()
        self.checkmark_label.clear()
        self.setToolTip("")
