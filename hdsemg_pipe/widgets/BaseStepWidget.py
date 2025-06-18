from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QStyle, QToolButton,
    QSizePolicy, QVBoxLayout, QHBoxLayout
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state

class BaseStepWidget(QWidget):
    stepCompleted = pyqtSignal(int)

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(parent)
        self.step_index = step_index
        self.step_name = step_name
        self.step_completed = False
        self.buttons = []

        # Main horizontal layout
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.setSpacing(5)

        # Column 1 - Step Name (mit Container-Widget)
        self.col_name_widget = QWidget()
        self.col_name_widget.setFixedWidth(180)  # Feste Breite hier
        self.col_name = QVBoxLayout(self.col_name_widget)
        self.col_name.setContentsMargins(0, 0, 0, 0)
        self.name_label = QLabel(self.step_name)
        self.name_label.setFont(QFont("Arial", weight=QFont.Bold))
        self.col_name.addWidget(self.name_label, alignment=Qt.AlignLeft|Qt.AlignVCenter)
        self.main_layout.addWidget(self.col_name_widget)

        # Column 2 - Info Button
        self.col_info_widget = QWidget()
        self.col_info = QVBoxLayout(self.col_info_widget)
        self.info_button = QToolButton()
        self.info_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.info_button.setToolTip(tooltip)
        self.info_button.setFixedSize(24, 24)
        self.col_info.addWidget(self.info_button, alignment=Qt.AlignCenter)
        self.main_layout.addWidget(self.col_info_widget)

        # Column 3 - Additional Info (expandierend)
        self.col_additional_widget = QWidget()
        self.col_additional = QVBoxLayout(self.col_additional_widget)
        self.additional_information_label = QLabel("")
        self.col_additional.addWidget(self.additional_information_label, alignment=Qt.AlignLeft|Qt.AlignVCenter)
        self.main_layout.addWidget(self.col_additional_widget, stretch=1)

        # Column 4 - Action Buttons
        self.col_buttons_widget = QWidget()
        self.col_buttons_widget.setFixedWidth(140)
        self.button_layout = QVBoxLayout(self.col_buttons_widget)
        self.button_layout.setSpacing(3)
        self.main_layout.addWidget(self.col_buttons_widget)

        # Column 5 - Status Icons
        self.col_status_widget = QWidget()
        self.col_status_widget.setFixedWidth(60)
        self.col_status = QVBoxLayout(self.col_status_widget)
        self.checkmark_label = QLabel()
        self.status_icon = QLabel()
        self.status_icon.setVisible(False)
        self.col_status.addWidget(self.checkmark_label, alignment=Qt.AlignCenter)
        self.col_status.addWidget(self.status_icon, alignment=Qt.AlignCenter)
        self.main_layout.addWidget(self.col_status_widget)

        # Initialize components
        self.create_buttons()
        self.add_buttons_to_layout()
        self.setToolTip(tooltip)
        self.clear_status()

    def create_buttons(self):
        """Subclasses override this to define their step's action buttons."""
        raise NotImplementedError("Subclasses must implement the create_buttons method.")

    def add_buttons_to_layout(self):
        """Populates the vertical layout with the self.buttons list."""
        for btn in self.buttons:
            self.button_layout.addWidget(btn)

    def check(self):
        """Checks if the step can be completed. Subclasses should implement this."""
        raise NotImplementedError("Subclasses must implement the check method.")

    def complete_step(self):
        """Marks the step as completed and displays a checkmark icon."""
        self.success(f"Step {self.step_index} completed successfully!")
        self.step_completed = True
        global_state.complete_widget(f"step{self.step_index}")
        self.stepCompleted.emit(self.step_index)

    def setActionButtonsEnabled(self, enabled, override=False):
        """Enables or disables action buttons."""
        if enabled == True and global_state.is_widget_completed(f"step{self.step_index - 1}") or enabled == False or override:
            for button in self.buttons:
                button.setEnabled(enabled)

    def success(self, message):
        icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
        self.status_icon.setPixmap(icon.pixmap(20, 20))
        self.status_icon.setVisible(True)
        self.setToolTip(message)
        logger.info("Success: " + message)

    def warn(self, message):
        icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
        self.status_icon.setPixmap(icon.pixmap(20, 20))
        self.status_icon.setVisible(True)
        self.setToolTip(message)
        logger.warning("Warning: " + message)

    def error(self, message):
        icon = self.style().standardIcon(QStyle.SP_MessageBoxCritical)
        self.status_icon.setPixmap(icon.pixmap(20, 20))
        self.status_icon.setVisible(True)
        self.setToolTip(message)
        logger.error("Error: " + message)

    def clear_status(self):
        self.status_icon.clear()
        self.status_icon.setVisible(False)
        self.checkmark_label.clear()
        self.setToolTip("")