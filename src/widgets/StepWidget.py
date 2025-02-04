from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QSizePolicy, QHBoxLayout, QLabel, QStyle, QPushButton
from log.log_config import logger

class StepWidget(QWidget):
    stepCompleted = pyqtSignal()

    def __init__(self, step_name, tooltip, action_function, action_button_text="Complete", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Layout for the step elements
        layout = QHBoxLayout(self)

        # Step Number Cell (Info Icon)
        self.info_label = QLabel()
        info_icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
        self.info_label.setPixmap(info_icon.pixmap(16, 16))
        self.info_label.setToolTip(tooltip)
        self.info_label.setFixedSize(40, 20)
        layout.addWidget(self.info_label)

        # Step Name (Bold)
        self.name_label = QLabel(f"{step_name}")
        self.name_label.setFont(QFont("Arial", weight=QFont.Bold))
        layout.addWidget(self.name_label)

        # Action Button
        self.action_button = QPushButton(action_button_text)
        self.action_button.clicked.connect(lambda: self.complete_step(action_function))
        layout.addWidget(self.action_button)

        # Progress Indicator
        self.progress_indicator = QLabel()
        self.progress_indicator.setFixedWidth(30)
        critical_icon = self.style().standardIcon(QStyle.SP_MessageBoxCritical)
        self.progress_indicator.setPixmap(critical_icon.pixmap(20, 20))
        layout.addWidget(self.progress_indicator)

    def complete_step(self, action_function):
        """Execute the step's action and mark it as complete."""
        try:
            action_function()
            apply_icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
            self.progress_indicator.setPixmap(apply_icon.pixmap(20, 20))
            self.action_button.setEnabled(False)
            self.stepCompleted.emit()
        except Exception as e:
            logger.error(f"Error executing step action: {e}")

    def setActionButtonEnabled(self, enabled):
        self.action_button.setEnabled(enabled)
