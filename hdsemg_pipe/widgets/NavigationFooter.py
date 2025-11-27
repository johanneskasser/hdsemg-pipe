from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QKeySequence

from hdsemg_pipe.ui_elements.theme import Colors, Spacing, Styles


class NavigationFooter(QWidget):
    """Footer widget with Previous and Next navigation buttons."""

    previousClicked = pyqtSignal()
    nextClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        """Initialize the UI."""
        # Set fixed height
        self.setFixedHeight(60)

        # Background styling with top border
        self.setStyleSheet(f"""
            NavigationFooter {{
                background-color: {Colors.BG_PRIMARY};
                border-top: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)

        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        # Previous Button (left-aligned)
        self.btn_previous = QPushButton("← Previous")
        self.btn_previous.setStyleSheet(Styles.button_secondary())
        self.btn_previous.setToolTip("Go back to previous step (←)")
        self.btn_previous.setMinimumWidth(120)
        self.btn_previous.clicked.connect(self.previousClicked.emit)
        layout.addWidget(self.btn_previous)

        # Add stretch to push Next button to the right
        layout.addStretch()

        # Next Button (right-aligned)
        self.btn_next = QPushButton("Next →")
        self.btn_next.setStyleSheet(Styles.button_primary())
        self.btn_next.setToolTip("Continue to next step (→)")
        self.btn_next.setMinimumWidth(120)
        self.btn_next.clicked.connect(self.nextClicked.emit)
        layout.addWidget(self.btn_next)

    def setPreviousEnabled(self, enabled):
        """Enable or disable the Previous button."""
        self.btn_previous.setEnabled(enabled)

    def setNextEnabled(self, enabled):
        """Enable or disable the Next button."""
        self.btn_next.setEnabled(enabled)

    def setNextText(self, text):
        """Change the text of the Next button.

        Args:
            text: New button text (e.g., "Complete" for last step)
        """
        self.btn_next.setText(text)

    def setNextVisible(self, visible):
        """Show or hide the Next button."""
        self.btn_next.setVisible(visible)

    def setPreviousVisible(self, visible):
        """Show or hide the Previous button."""
        self.btn_previous.setVisible(visible)
