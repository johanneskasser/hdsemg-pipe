from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont

from hdsemg_pipe.ui_elements.theme import Colors, Spacing, Fonts
from hdsemg_pipe.state.global_state import global_state


class StepCircle(QWidget):
    """A single step circle widget with number and state."""

    clicked = pyqtSignal(int)

    # Step names for tooltips (12 steps)
    STEP_NAMES = [
        "Open File(s)",
        "Grid Association",
        "Line Noise Removal",
        "RMS Quality Analysis",
        "Define ROI",
        "Channel Selection",
        "Decomposition Results",
        "Multi-Grid Configuration",
        "CoVISI Pre-Filtering",
        "MUEdit Cleaning",
        "CoVISI Post-Validation",
        "Final Results"
    ]

    # State colors with enhanced visual hierarchy
    STATE_COLORS = {
        "completed": {
            "bg": Colors.GREEN_600,  # Fully saturated green for completed
            "border": Colors.GREEN_600,
            "text": "#ffffff",  # White text for contrast
            "border_width": 2
        },
        "active": {
            "bg": "#ffffff",  # Clean white background
            "border": "#2563eb",  # Vibrant blue border
            "text": "#1e40af",  # Deep blue text
            "border_width": 4  # Thicker border for active step
        },
        "visited": {
            "bg": "#fef3c7",  # Soft amber background
            "border": "#f59e0b",  # Amber border
            "text": "#b45309",  # Amber text
            "border_width": 2
        },
        "pending": {
            "bg": Colors.GRAY_100,
            "border": Colors.BORDER_DEFAULT,
            "text": Colors.GRAY_500,
            "border_width": 2
        },
        "error": {
            "bg": Colors.RED_100,
            "border": Colors.RED_500,
            "text": Colors.RED_700,
            "border_width": 2
        }
    }

    def __init__(self, step_number, parent=None):
        super().__init__(parent)
        self.step_number = step_number
        self.state = "pending"
        self.clickable = False
        self.is_completed = False  # Track actual completion status
        self.is_skipped = False  # Track if step was skipped
        self.is_active = False  # Track if this is the currently active step

        # Fixed size for circle (slightly larger for thicker borders)
        self.setFixedSize(44, 44)
        self.setCursor(Qt.ArrowCursor)

        # Set tooltip
        if 1 <= step_number <= len(self.STEP_NAMES):
            self._updateTooltip()

    def setState(self, state, clickable=False, is_completed=False, is_skipped=False, is_active=False):
        """Set the visual state of this circle.

        Args:
            state: Visual state ("completed", "active", "visited", "pending", "error")
            clickable: Whether the circle is clickable
            is_completed: Whether the step is actually completed (from GlobalState)
            is_skipped: Whether the step was skipped (from GlobalState)
            is_active: Whether this is the currently active/viewing step
        """
        self.state = state
        self.clickable = clickable
        self.is_completed = is_completed
        self.is_skipped = is_skipped
        self.is_active = is_active
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        self._updateTooltip()
        self.update()

    def _updateTooltip(self):
        """Update tooltip based on current state."""
        if 1 <= self.step_number <= len(self.STEP_NAMES):
            base_tooltip = f"Step {self.step_number}: {self.STEP_NAMES[self.step_number - 1]}"

            if self.is_completed and self.is_skipped:
                status = " ✓ Completed (Skipped)"
            elif self.is_completed:
                status = " ✓ Completed"
            elif self.state == "active":
                status = " → Currently viewing"
            elif self.state == "visited":
                status = " ⚠ Visited but not completed"
            elif self.state == "pending":
                status = " ○ Not yet started"
            else:
                status = ""

            self.setToolTip(base_tooltip + status)

    def paintEvent(self, event):
        """Custom paint for the circle with enhanced visual hierarchy."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get colors for current state
        colors = self.STATE_COLORS.get(self.state, self.STATE_COLORS["pending"])
        border_width = colors.get("border_width", 2)

        # Special handling for completed + active: green background with thick blue border
        if self.is_completed and self.is_active:
            border_width = 4  # Thick border like active state
            border_color = "#2563eb"  # Blue border
            bg_color = Colors.GREEN_600  # Green background
        else:
            border_color = colors["border"]
            bg_color = colors["bg"]

        # Calculate dimensions based on border width
        offset = border_width / 2
        diameter = 44 - border_width

        # Draw subtle shadow for active state (both active-only and completed+active)
        if self.state == "active" or (self.is_completed and self.is_active):
            shadow_pen = QPen(QColor(37, 99, 235, 40), 8)  # Semi-transparent blue
            painter.setPen(shadow_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(int(offset - 2), int(offset - 2), int(diameter + 4), int(diameter + 4))

        # Draw circle background
        painter.setBrush(QBrush(QColor(bg_color)))
        painter.setPen(QPen(QColor(border_color), border_width))
        painter.drawEllipse(int(offset), int(offset), int(diameter), int(diameter))

        # Draw step number (white text for completed+active, otherwise use state color)
        if self.is_completed and self.is_active:
            text_color = "#ffffff"  # White text on green background
        else:
            text_color = colors["text"]
        painter.setPen(QColor(text_color))
        font = QFont(Fonts.FAMILY_SANS, 14, QFont.Bold)
        painter.setFont(font)
        painter.drawText(0, 0, 44, 44, Qt.AlignCenter, str(self.step_number))

        # Draw skip overlay icon if step is completed and skipped
        if self.is_completed and self.is_skipped:
            # Draw a small skip icon in the bottom-right corner
            painter.setPen(QColor("#ffffff"))  # White for contrast
            skip_font = QFont(Fonts.FAMILY_SANS, 12, QFont.Bold)
            painter.setFont(skip_font)

            # Draw small circular background for the icon
            icon_size = 16
            icon_x = 44 - icon_size - 2
            icon_y = 44 - icon_size - 2

            painter.setBrush(QBrush(QColor("#f97316")))  # Orange background
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawEllipse(icon_x, icon_y, icon_size, icon_size)

            # Draw skip symbol (forward arrow)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(icon_x, icon_y, icon_size, icon_size, Qt.AlignCenter, "⏭")

    def mousePressEvent(self, event):
        """Handle click events."""
        if self.clickable and event.button() == Qt.LeftButton:
            self.clicked.emit(self.step_number)


class StepProgressIndicator(QWidget):
    """Top bar showing progress through all 12 steps."""

    TOTAL_STEPS = 12

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
        layout.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        layout.setSpacing(0)

        # Create 12 step circles with connecting lines
        for i in range(1, self.TOTAL_STEPS + 1):
            # Add circle
            circle = StepCircle(i, self)
            circle.clicked.connect(self._onCircleClicked)
            self.circles.append(circle)
            layout.addWidget(circle)

            # Add connecting line (except after last circle)
            if i < self.TOTAL_STEPS:
                line = QLabel()
                line.setFixedSize(30, 2)  # Slightly smaller lines for 12 steps
                line.setStyleSheet(f"background-color: {Colors.BORDER_DEFAULT};")
                self.lines.append(line)
                layout.addWidget(line, alignment=Qt.AlignCenter)

        # Set initial state (first step active, rest pending)
        self.setActiveStep(1)

    def setActiveStep(self, step_number):
        """Set which step is currently active and update all states based on GlobalState."""
        self.current_step = step_number
        self._updateStates()

    def setStepState(self, step_number, state, is_completed=False, is_skipped=False, is_active=False):
        """Set the state of a specific step.

        Args:
            step_number: 1-12
            state: "completed", "active", "visited", "pending", "error"
            is_completed: Whether the step is actually completed (from GlobalState)
            is_skipped: Whether the step was skipped (from GlobalState)
            is_active: Whether this is the currently active/viewing step
        """
        if 1 <= step_number <= self.TOTAL_STEPS:
            idx = step_number - 1
            clickable = (state in ["completed", "active", "visited"])
            self.circles[idx].setState(state, clickable, is_completed, is_skipped, is_active)

            # Update connection line color and thickness based on completion
            if step_number < self.TOTAL_STEPS:
                line = self.lines[step_number - 1]
                if is_completed:
                    # Completed steps have thicker, green connection lines
                    line.setFixedSize(30, 3)
                    line.setStyleSheet(f"background-color: {Colors.GREEN_600};")
                else:
                    # Non-completed steps have standard thin lines
                    line.setFixedSize(30, 2)
                    line.setStyleSheet(f"background-color: {Colors.BORDER_DEFAULT};")

    def _updateStates(self):
        """Update all circle states based on current step and GlobalState completion status."""
        for i in range(self.TOTAL_STEPS):
            step_num = i + 1
            step_name = f"step{step_num}"

            # Check actual completion and skip status from GlobalState
            is_completed = global_state.is_widget_completed(step_name)
            is_skipped = global_state.is_widget_skipped(step_name)
            is_active = (step_num == self.current_step)

            if is_completed:
                # Completed steps ALWAYS show as green, even if currently active
                # If active: green with thick blue border; if not active: green with green border
                self.setStepState(step_num, "completed", True, is_skipped, is_active)
            elif step_num == self.current_step:
                # Active but not completed - thick blue border
                self.setStepState(step_num, "active", False, False, True)
            elif step_num < self.current_step:
                # Visited but not completed - amber warning state
                self.setStepState(step_num, "visited", False, False, False)
            else:
                # Future pending step - gray
                self.setStepState(step_num, "pending", False, False, False)

    def refreshStates(self):
        """Refresh all step states based on current GlobalState completion status.

        Call this method when a step is completed to update the visual indicators.
        """
        self._updateStates()

    def _onCircleClicked(self, step_number):
        """Handle circle click - only emit if step is clickable."""
        if step_number <= self.current_step:
            self.stepClicked.emit(step_number)
