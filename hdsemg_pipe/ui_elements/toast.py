"""
Modern toast notification system for hdsemg-pipe.
Displays temporary, dismissible notifications that auto-hide after a few seconds.
"""
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QPushButton, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QFont

from hdsemg_pipe.ui_elements.theme import Colors, Fonts, Spacing, BorderRadius


class Toast(QWidget):
    """A single toast notification widget."""

    def __init__(self, message, toast_type="info", duration=4000, parent=None):
        super().__init__(parent)
        self.duration = duration
        self.toast_type = toast_type

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.initUI(message)

    def initUI(self, message):
        """Initialize the toast UI."""
        # Container
        container = QWidget(self)
        container.setObjectName("toastContainer")

        layout = QHBoxLayout(container)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        # Icon/emoji
        icon_label = QLabel()
        icon_label.setFont(QFont(Fonts.FAMILY_SANS, 18))

        # Message
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setMaximumWidth(400)
        message_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-size: {Fonts.SIZE_BASE};
            }}
        """)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
                border-radius: 4px;
            }
        """)
        close_btn.clicked.connect(self.hide_toast)

        # Add widgets to layout
        layout.addWidget(icon_label)
        layout.addWidget(message_label, stretch=1)
        layout.addWidget(close_btn)

        # Style based on type
        if self.toast_type == "success":
            icon_label.setText("✓")
            bg_color = Colors.GREEN_600
            border_color = Colors.GREEN_700
        elif self.toast_type == "error":
            icon_label.setText("✕")
            bg_color = Colors.RED_600
            border_color = Colors.RED_700
        elif self.toast_type == "warning":
            icon_label.setText("⚠")
            bg_color = Colors.YELLOW_600
            border_color = "#ca8a04"
        else:  # info
            icon_label.setText("ℹ")
            bg_color = Colors.BLUE_600
            border_color = Colors.BLUE_700

        container.setStyleSheet(f"""
            #toastContainer {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: {BorderRadius.LG};
            }}
        """)

        # Set container as the main widget
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        # Opacity effect for fade animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        container.setGraphicsEffect(self.opacity_effect)

        # Auto-hide timer
        if self.duration > 0:
            QTimer.singleShot(self.duration, self.hide_toast)

    def show_toast(self):
        """Show the toast with fade-in animation."""
        self.show()

        # Fade in animation
        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_in.start()

    def hide_toast(self):
        """Hide the toast with fade-out animation."""
        # Fade out animation
        self.fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out.setDuration(300)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out.finished.connect(self.close)
        self.fade_out.start()


class ToastManager:
    """Manages multiple toast notifications with proper positioning."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToastManager, cls).__new__(cls)
            cls._instance.toasts = []
            cls._instance.parent_widget = None
        return cls._instance

    def set_parent(self, parent_widget):
        """Set the parent widget for positioning toasts."""
        self.parent_widget = parent_widget

    def show_toast(self, message, toast_type="info", duration=4000):
        """Show a toast notification."""
        if not self.parent_widget:
            return

        toast = Toast(message, toast_type, duration, self.parent_widget)
        self.toasts.append(toast)

        # Position toast
        self._position_toast(toast)

        # Show with animation
        toast.show_toast()

        # Remove from list when closed
        toast.destroyed.connect(lambda: self._remove_toast(toast))

    def _position_toast(self, toast):
        """Position the toast at the top-right of the parent widget."""
        if not self.parent_widget:
            return

        # Get global position of parent widget
        parent_global_pos = self.parent_widget.mapToGlobal(self.parent_widget.rect().topRight())
        toast_height = 80  # Approximate height

        # Calculate vertical offset based on existing toasts
        offset = len(self.toasts) - 1
        y_pos = parent_global_pos.y() + Spacing.XXL + (offset * (toast_height + Spacing.MD))

        # Position at top-right with margin from right edge
        toast.adjustSize()
        x_pos = parent_global_pos.x() - toast.width() - Spacing.XXL

        toast.move(x_pos, y_pos)

    def _remove_toast(self, toast):
        """Remove toast from the list."""
        if toast in self.toasts:
            self.toasts.remove(toast)

            # Reposition remaining toasts
            for i, t in enumerate(self.toasts):
                self._position_toast_at_index(t, i)

    def _position_toast_at_index(self, toast, index):
        """Position a specific toast at a given index."""
        if not self.parent_widget:
            return

        # Get global position of parent widget
        parent_global_pos = self.parent_widget.mapToGlobal(self.parent_widget.rect().topRight())
        toast_height = 80

        y_pos = parent_global_pos.y() + Spacing.XXL + (index * (toast_height + Spacing.MD))
        x_pos = parent_global_pos.x() - toast.width() - Spacing.XXL

        toast.move(x_pos, y_pos)


# Global toast manager instance
toast_manager = ToastManager()
