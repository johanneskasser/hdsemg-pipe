from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QStyle
from PyQt5.QtCore import pyqtSignal
from log.log_config import logger

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

        self.layout = QHBoxLayout(self)
        self.setToolTip(tooltip)

        # Step Label
        self.name_label = QLabel(self.step_name)
        self.layout.addWidget(self.name_label)

        # Status Indicator (Icon)
        self.status_icon = QLabel()
        self.status_icon.setFixedWidth(30)
        self.layout.addWidget(self.status_icon)

        # Buttons
        self.buttons = []
        self.create_buttons()

        self.setLayout(self.layout)

        # Default to no status
        self.clear_status()

    def create_buttons(self):
        """Creates buttons. Must be overridden by subclasses."""
        pass

    def complete_step(self):
        """Marks the step as completed."""
        self.success("Step completed successfully")
        self.stepCompleted.emit(self.step_index)

    def setActionButtonsEnabled(self, enabled):
        """Enables or disables action buttons."""
        for button in self.buttons:
            button.setEnabled(enabled)

    def success(self, message):
        """Displays a success message with a checkmark icon."""
        success_icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
        self.status_icon.setPixmap(success_icon.pixmap(20, 20))
        self.setToolTip(message)
        logger.info(f"Success: {message}")

    def warn(self, message):
        """Displays a warning message with a warning icon."""
        warn_icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
        self.status_icon.setPixmap(warn_icon.pixmap(20, 20))
        self.setToolTip(message)
        logger.warning(f"Warning: {message}")

    def error(self, message):
        """Displays an error message with a critical error icon."""
        error_icon = self.style().standardIcon(QStyle.SP_MessageBoxCritical)
        self.status_icon.setPixmap(error_icon.pixmap(20, 20))
        self.setToolTip(message)
        logger.error(f"Error: {message}")

    def info(self, message):
        """Displays an info message"""
        info_icon = self.style().standardIcon(QStyle.SP_InfoIcon)
        self.status_icon.setPixmap(info_icon.pixmap(20, 20))
        self.setToolTip(message)
        logger.info(f"Info: {message}")

    def clear_status(self):
        """Clears the status and resets the tooltip."""
        self.status_icon.clear()
        self.setToolTip("")
