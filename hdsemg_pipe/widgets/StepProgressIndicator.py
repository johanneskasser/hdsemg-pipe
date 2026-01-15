from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont

from hdsemg_pipe.ui_elements.theme import Colors, Spacing, Fonts


class StepCircle(QWidget):
    """A single step circle widget with number and state."""

    clicked = pyqtSignal(int)

    # Step names for tooltips
    STEP_NAMES = [
        "Open File(s)",
        "Grid Association",
        "Line Noise Removal",
        "RMS Quality Analysis",
        "Define ROI",
        "Channel Selection",
        "Decomposition Results",
        "Multi-Grid Configuration",
        "MUEdit Cleaning",
        "Final Results"
    ]

    # State colors
    STATE_COLORS = {
        "completed": {
            "bg": Colors.GREEN_100,
            "border": Colors.GREEN_BORDER,
            "text": Colors.GREEN_800
        },
        "active": {
            "bg": "#fed7aa",  # Orange 200
            "border": "#f97316",  # Orange 500
            "text": "#9a3412"  # Orange 800
        },
        "pending": {
            "bg": Colors.GRAY_100,
            "border": Colors.BORDER_DEFAULT,
            "text": Colors.GRAY_500
        },
        "skipped": {
            "bg": Colors.YELLOW_100,
            "border": Colors.YELLOW_500,
            "text": Colors.YELLOW_600
        },
        "error": {
            "bg": Colors.RED_100,
            "border": Colors.RED_500,
            "text": Colors.RED_700
        }
    }

    def __init__(self, step_number, parent=None):
        super().__init__(parent)
        self.step_number = step_number
        self.state = "pending"
        self.clickable = False

        # Fixed size for circle
        self.setFixedSize(40, 40)
        self.setCursor(Qt.ArrowCursor)

        # Set tooltip
        if 1 <= step_number <= len(self.STEP_NAMES):
            self.setToolTip(f"Step {step_number}: {self.STEP_NAMES[step_number - 1]}")

    def setState(self, state, clickable=False):
        """Set the visual state of this circle."""
        self.state = state
        self.clickable = clickable
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        self.update()

    def paintEvent(self, event):
        """Custom paint for the circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get colors for current state
        colors = self.STATE_COLORS.get(self.state, self.STATE_COLORS["pending"])

        # Draw circle background
        painter.setBrush(QBrush(QColor(colors["bg"])))
        painter.setPen(QPen(QColor(colors["border"]), 2))
        painter.drawEllipse(2, 2, 36, 36)

        # Draw step number
        painter.setPen(QColor(colors["text"]))
        font = QFont(Fonts.FAMILY_SANS, 14, QFont.Bold)
        painter.setFont(font)
        painter.drawText(0, 0, 40, 40, Qt.AlignCenter, str(self.step_number))

    def mousePressEvent(self, event):
        """Handle click events."""
        if self.clickable and event.button() == Qt.LeftButton:
            self.clicked.emit(self.step_number)


class StepProgressIndicator(QWidget):
    """Top bar showing progress through all 10 steps."""

    stepClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.circles = []
        self.lines = []
        self.current_step = 1

        self.initUI()

    def initUI(self):
        """Initialize the UI."""
        # Set fixed height
        self.setFixedHeight(80)

        # Background styling
        self.setStyleSheet(f"""
            StepProgressIndicator {{
                background-color: {Colors.BG_PRIMARY};
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)

        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.LG, Spacing.XXL, Spacing.LG)
        layout.setSpacing(0)

        # Create 10 step circles with connecting lines
        for i in range(1, 11):
            # Add circle
            circle = StepCircle(i, self)
            circle.clicked.connect(self._onCircleClicked)
            self.circles.append(circle)
            layout.addWidget(circle)

            # Add connecting line (except after last circle)
            if i < 10:
                line = QLabel()
                line.setFixedSize(40, 2)
                line.setStyleSheet(f"background-color: {Colors.BORDER_DEFAULT};")
                self.lines.append(line)
                layout.addWidget(line, alignment=Qt.AlignCenter)

        # Set initial state (first step active, rest pending)
        self.setActiveStep(1)

    def setActiveStep(self, step_number):
        """Set which step is currently active."""
        self.current_step = step_number
        self._updateStates()

    def setStepState(self, step_number, state):
        """Set the state of a specific step.

        Args:
            step_number: 1-10
            state: "completed", "active", "pending", "skipped", "error"
        """
        if 1 <= step_number <= 10:
            idx = step_number - 1
            clickable = (state in ["completed", "active"])
            self.circles[idx].setState(state, clickable)

            # Update connection line color if this step is completed
            if step_number < 10:
                line = self.lines[step_number - 1]
                if state == "completed":
                    line.setStyleSheet(f"background-color: {Colors.GREEN_600};")
                else:
                    line.setStyleSheet(f"background-color: {Colors.BORDER_DEFAULT};")

    def _updateStates(self):
        """Update all circle states based on current step."""
        for i in range(10):
            step_num = i + 1
            if step_num < self.current_step:
                self.setStepState(step_num, "completed")
            elif step_num == self.current_step:
                self.setStepState(step_num, "active")
            else:
                self.setStepState(step_num, "pending")

    def _onCircleClicked(self, step_number):
        """Handle circle click - only emit if step is clickable."""
        if step_number <= self.current_step:
            self.stepClicked.emit(step_number)
