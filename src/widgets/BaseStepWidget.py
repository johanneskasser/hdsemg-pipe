from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QStyle
from PyQt5.QtCore import pyqtSignal
from log.log_config import logger

class BaseStepWidget(QWidget):
    stepCompleted = pyqtSignal(int)  # Signal, um abgeschlossene Schritte zu melden

    def __init__(self, step_index, step_name, tooltip, parent=None):
        """
        Basisklasse für ein Schritt-Widget.
        :param step_index: Die Indexnummer des Schritts
        :param step_name: Der Name des Schritts
        :param tooltip: Tooltip-Text für das Widget
        """
        super().__init__(parent)
        self.step_index = step_index
        self.step_name = step_name

        self.layout = QHBoxLayout(self)
        self.setToolTip(tooltip)

        # Schritt-Label
        self.name_label = QLabel(self.step_name)
        self.layout.addWidget(self.name_label)

        # Fortschrittsanzeige (Icon)
        self.progress_indicator = QLabel()
        self.progress_indicator.setFixedWidth(30)
        critical_icon = self.style().standardIcon(QStyle.SP_MessageBoxCritical)
        self.progress_indicator.setPixmap(critical_icon.pixmap(20, 20))
        self.layout.addWidget(self.progress_indicator)

        # Buttons
        self.buttons = []
        self.create_buttons()

        self.setLayout(self.layout)

    def create_buttons(self):
        """Erstellt Buttons. Muss von Subklassen überschrieben werden."""
        pass

    def complete_step(self):
        """Markiert den Schritt als abgeschlossen."""
        apply_icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
        self.progress_indicator.setPixmap(apply_icon.pixmap(20, 20))
        self.stepCompleted.emit(self.step_index)

    def setActionButtonsEnabled(self, enabled):
        """Aktiviert oder deaktiviert die Action-Buttons."""
        for button in self.buttons:
            button.setEnabled(enabled)
