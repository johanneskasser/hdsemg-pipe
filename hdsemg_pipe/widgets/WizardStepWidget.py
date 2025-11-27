from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import Colors, Fonts, Spacing, BorderRadius
from hdsemg_pipe.ui_elements.toast import toast_manager


class WizardStepWidget(QWidget):
    """Base widget for wizard-style step interface."""

    stepCompleted = pyqtSignal(int)

    def __init__(self, step_index, step_name, description="", parent=None):
        super().__init__(parent)
        self.step_index = step_index
        self.step_name = step_name
        self.description = description
        self.step_completed = False
        self.buttons = []

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Main vertical layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(Spacing.XXXL, Spacing.XXXL, Spacing.XXXL, Spacing.XXXL)
        self.main_layout.setSpacing(Spacing.XL)

        self._createHeader()
        self._createContentArea()
        self._createStatusArea()

        # Add stretch to push content to top
        self.main_layout.addStretch()

        # Initialize components
        self.create_buttons()
        self.add_buttons_to_layout()
        self.clear_status()

        # Override setText for additional_information_label to auto-show/hide
        self._setup_additional_info_auto_visibility()

    def _createHeader(self):
        """Create the header with step number and title."""
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Spacing.SM)

        # Step number label
        self.step_number_label = QLabel(f"Step {self.step_index}")
        self.step_number_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
        """)
        header_layout.addWidget(self.step_number_label)

        # Title label
        self.title_label = QLabel(self.step_name)
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 32px;
                font-weight: {Fonts.WEIGHT_BOLD};
            }}
        """)
        header_layout.addWidget(self.title_label)

        # Description label (if provided)
        if self.description:
            self.description_label = QLabel(self.description)
            self.description_label.setWordWrap(True)
            self.description_label.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.TEXT_SECONDARY};
                    font-size: {Fonts.SIZE_LG};
                    line-height: 1.5;
                }}
            """)
            header_layout.addWidget(self.description_label)

        self.main_layout.addWidget(header_widget)

    def _createContentArea(self):
        """Create the content area for action buttons and custom content."""
        # Content card
        self.content_card = QFrame()
        self.content_card.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.LG};
                padding: {Spacing.XXL}px;
            }}
        """)

        self.content_layout = QVBoxLayout(self.content_card)
        self.content_layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        self.content_layout.setSpacing(Spacing.LG)

        # Additional info label (like in BaseStepWidget) - hidden by default
        self.additional_information_label = QLabel("")
        self.additional_information_label.setWordWrap(True)
        self.additional_information_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
                font-style: italic;
            }}
        """)
        self.additional_information_label.setVisible(False)
        self.content_layout.addWidget(self.additional_information_label)

        # Buttons container
        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_layout.setSpacing(Spacing.MD)
        self.content_layout.addWidget(self.button_container)

        self.main_layout.addWidget(self.content_card)

    def _createStatusArea(self):
        """Create the status message area (deprecated - using toasts now)."""
        # Status area removed - using toast notifications instead
        pass

    def create_buttons(self):
        """Subclasses override this to define their step's action buttons."""
        raise NotImplementedError("Subclasses must implement the create_buttons method.")

    def add_buttons_to_layout(self):
        """Populates the horizontal layout with the self.buttons list."""
        for btn in self.buttons:
            self.button_layout.addWidget(btn)
        # Add stretch to left-align buttons
        self.button_layout.addStretch()

    def check(self):
        """Checks if the step can be completed. Subclasses should implement this."""
        raise NotImplementedError("Subclasses must implement the check method.")

    def complete_step(self):
        """Marks the step as completed."""
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
        """Show success toast notification."""
        toast_manager.show_toast(message, "success", duration=4000)
        logger.info("Success: " + message)

    def warn(self, message):
        """Show warning toast notification."""
        toast_manager.show_toast(message, "warning", duration=5000)
        logger.warning("Warning: " + message)

    def error(self, message):
        """Show error toast notification."""
        toast_manager.show_toast(message, "error", duration=6000)
        logger.error("Error: " + message)

    def info(self, message):
        """Show info toast notification."""
        toast_manager.show_toast(message, "info", duration=4000)
        logger.info("Info: " + message)

    def clear_status(self):
        """Clear status display (legacy - toasts auto-hide)."""
        pass  # Toasts handle their own lifecycle

    def _setup_additional_info_auto_visibility(self):
        """Override setText for additional_information_label to auto-show/hide."""
        original_setText = self.additional_information_label.setText

        def custom_setText(text):
            original_setText(text)
            # Show label only if text is not empty
            self.additional_information_label.setVisible(bool(text.strip()) if text else False)

        self.additional_information_label.setText = custom_setText
