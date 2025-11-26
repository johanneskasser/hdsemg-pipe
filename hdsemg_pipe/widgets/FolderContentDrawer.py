from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QStyle
)
from PyQt5.QtCore import (
    pyqtSignal, Qt, QPropertyAnimation, QEasingCurve,
    QPoint, QRect, pyqtProperty
)
from PyQt5.QtGui import QColor

from hdsemg_pipe.ui_elements.theme import Colors, Spacing, Fonts, BorderRadius
from hdsemg_pipe.widgets.FolderContentWidget import FolderContentWidget
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.controller.automatic_state_reconstruction import start_reconstruction_workflow


class DrawerOverlay(QWidget):
    """Semi-transparent overlay that dims the main content when drawer is open."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.3);")
        self.hide()

    def mousePressEvent(self, event):
        """Emit clicked signal when overlay is clicked."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class FolderContentDrawer(QWidget):
    """Slide-out drawer from the right containing FolderContentWidget."""

    drawerToggled = pyqtSignal(bool)  # True = opened, False = closed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drawer_width = 400
        self._is_open = False

        # Position will be set by parent
        self._x_pos = 0

        self.initUI()

    def initUI(self):
        """Initialize the drawer UI."""
        # Create overlay (will be positioned by parent)
        self.overlay = DrawerOverlay(self.parent())
        self.overlay.clicked.connect(self.close)
        self.overlay.hide()

        # Create floating toggle button
        self.toggle_btn = QPushButton("📁", self.parent())
        self.toggle_btn.setFixedSize(56, 56)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BLUE_600};
                color: white;
                border: none;
                border-radius: 28px;
                font-size: 24px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
            }}
            QPushButton:hover {{
                background-color: {Colors.BLUE_700};
            }}
            QPushButton:pressed {{
                background-color: {Colors.BLUE_500};
            }}
        """)
        self._updateFABTooltip()
        self.toggle_btn.clicked.connect(self._handleFABClick)
        self.toggle_btn.raise_()
        self._position_toggle_button()

        # Drawer container
        self.drawer_frame = QFrame(self)
        self.drawer_frame.setFixedWidth(self._drawer_width)
        self.drawer_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border-left: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)

        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(-2, 0)
        self.drawer_frame.setGraphicsEffect(shadow)

        # Drawer layout
        drawer_layout = QVBoxLayout(self.drawer_frame)
        drawer_layout.setContentsMargins(0, 0, 0, 0)
        drawer_layout.setSpacing(0)

        # Header with title and close button
        header = QWidget()
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.BG_SECONDARY};
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)

        title_label = QLabel("Workfolder")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
            }}
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # Close button
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                font-size: 20px;
                font-weight: bold;
                color: {Colors.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {Colors.GRAY_100};
                color: {Colors.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {Colors.GRAY_200};
            }}
        """)
        self.close_btn.setToolTip("Close drawer (Esc)")
        self.close_btn.clicked.connect(self.close)
        header_layout.addWidget(self.close_btn)

        drawer_layout.addWidget(header)

        # Add FolderContentWidget
        self.folder_content = FolderContentWidget()
        drawer_layout.addWidget(self.folder_content)

        # Initially hide drawer (position off-screen to the right)
        self.hide()

    def toggle(self):
        """Toggle drawer visibility."""
        if self._is_open:
            self.close()
        else:
            self.open()

    def open(self):
        """Open the drawer with animation."""
        if self._is_open:
            return

        # Update folder content
        self.folder_content.update_folder_content()

        # Update FAB tooltip
        self._updateFABTooltip()

        # Show overlay
        self.overlay.show()
        self.overlay.raise_()

        # Show drawer
        self.show()
        self.raise_()

        # Get parent geometry for positioning
        if self.parent():
            parent_rect = self.parent().rect()
            self.resize(self._drawer_width, parent_rect.height())

            # Animation: slide in from right
            self.animation = QPropertyAnimation(self, b"pos")
            self.animation.setDuration(250)
            self.animation.setStartValue(QPoint(parent_rect.width(), 0))
            self.animation.setEndValue(QPoint(parent_rect.width() - self._drawer_width, 0))
            self.animation.setEasingCurve(QEasingCurve.OutCubic)
            self.animation.start()

        self._is_open = True
        self.drawerToggled.emit(True)

    def close(self):
        """Close the drawer with animation."""
        if not self._is_open:
            return

        # Get parent geometry
        if self.parent():
            parent_rect = self.parent().rect()

            # Animation: slide out to right
            self.animation = QPropertyAnimation(self, b"pos")
            self.animation.setDuration(250)
            self.animation.setStartValue(self.pos())
            self.animation.setEndValue(QPoint(parent_rect.width(), 0))
            self.animation.setEasingCurve(QEasingCurve.InCubic)
            self.animation.finished.connect(self._onCloseAnimationFinished)
            self.animation.start()

        self._is_open = False
        self.drawerToggled.emit(False)

    def _onCloseAnimationFinished(self):
        """Hide drawer and overlay after close animation."""
        self.hide()
        self.overlay.hide()

    def isDrawerOpen(self):
        """Return True if drawer is currently open."""
        return self._is_open

    def updatePosition(self):
        """Update drawer position when parent is resized."""
        if not self.parent():
            return

        parent_rect = self.parent().rect()
        self.overlay.setGeometry(parent_rect)

        if self._is_open:
            self.resize(self._drawer_width, parent_rect.height())
            self.move(parent_rect.width() - self._drawer_width, 0)
        else:
            self.resize(self._drawer_width, parent_rect.height())
            self.move(parent_rect.width(), 0)

        # Update toggle button position
        self._position_toggle_button()

    def _position_toggle_button(self):
        """Position the floating toggle button."""
        if not self.parent():
            return

        parent_rect = self.parent().rect()
        # Position in bottom-right corner with some margin
        x_pos = parent_rect.width() - self.toggle_btn.width() - Spacing.XXL
        y_pos = parent_rect.height() - self.toggle_btn.height() - Spacing.XXL - 60  # Account for nav footer

        self.toggle_btn.move(x_pos, y_pos)

    def keyPressEvent(self, event):
        """Handle Esc key to close drawer."""
        if event.key() == Qt.Key_Escape and self._is_open:
            self.close()
        else:
            super().keyPressEvent(event)

    def _handleFABClick(self):
        """Handle FAB click - either toggle drawer or trigger state reconstruction."""
        if global_state.workfolder is None:
            # No workfolder selected - trigger state reconstruction
            start_reconstruction_workflow(self.parent())
            # Update tooltip after reconstruction
            self._updateFABTooltip()
        else:
            # Workfolder exists - toggle drawer
            self.toggle()

    def _updateFABTooltip(self):
        """Update FAB tooltip based on current state."""
        if global_state.workfolder is None:
            self.toggle_btn.setToolTip("Open existing workfolder")
        else:
            self.toggle_btn.setToolTip("Toggle folder view (Ctrl+F)")
