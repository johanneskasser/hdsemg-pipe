"""
Dialog that shows instructions for manual MUEdit workflow and displays the next file to edit.
"""
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtMultimedia import QSound

from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius
from hdsemg_pipe._log.log_config import logger


class MUEditInstructionDialog(QDialog):
    """
    Dialog that provides instructions for the MUEdit manual workflow.
    Shows which files need to be edited and highlights the next file to process.
    """

    def __init__(self, muedit_files, edited_files, folder_path, parent=None):
        """
        Args:
            muedit_files: List of base names of _muedit.mat files
            edited_files: List of base names of already edited files
            folder_path: Path to the decomposition folder
        """
        super().__init__(parent)
        self.muedit_files = muedit_files
        self.edited_files = edited_files
        self.folder_path = folder_path
        self.parent_widget = parent

        self.setWindowTitle("MUEdit Manual Cleaning Instructions")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        # Track last edited count for sound notification
        self.last_edited_count = len(edited_files)

        # Setup update timer to check for new edited files
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._check_for_updates)
        self.update_timer.start(2000)  # Check every 2 seconds

        # Setup blink timer for live indicator
        self.blink_state = True
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._toggle_live_indicator)
        self.blink_timer.start(1000)  # Blink every second

        self.init_ui()

    def init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        # Title
        title_label = QLabel("Manual Cleaning Workflow")
        title_label.setStyleSheet(f"""
            QLabel {{
                font-size: 20px;
                font-weight: bold;
                color: {Colors.TEXT_PRIMARY};
                padding-bottom: 5px;
            }}
        """)
        layout.addWidget(title_label)

        # Instructions section
        instructions_label = QLabel(
            "MUEdit has been launched. Follow these steps to process your files:"
        )
        instructions_label.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; padding-bottom: 10px;")
        layout.addWidget(instructions_label)

        # Step-by-step instructions
        steps_widget = self._create_steps_widget()
        layout.addWidget(steps_widget)

        # Current progress section with live indicator
        progress_header_layout = QHBoxLayout()
        progress_label = QLabel("File Status:")
        progress_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_PRIMARY};")
        progress_header_layout.addWidget(progress_label)

        # Live update indicator
        self.live_indicator = QLabel("● Live")
        self.live_indicator.setStyleSheet(f"""
            QLabel {{
                color: {Colors.GREEN_600};
                font-size: 11px;
                padding-left: 10px;
            }}
        """)
        progress_header_layout.addWidget(self.live_indicator)
        progress_header_layout.addStretch()

        progress_header_widget = QWidget()
        progress_header_widget.setLayout(progress_header_layout)
        progress_header_widget.setStyleSheet("margin-top: 15px; margin-bottom: 5px;")
        layout.addWidget(progress_header_widget)

        # File list with status (store container reference)
        self.file_list_container = self._create_file_list_widget()
        layout.addWidget(self.file_list_container)

        # Next file to edit section (store layout reference)
        next_file_container = QWidget()
        self.next_file_container_layout = QVBoxLayout(next_file_container)
        self.next_file_container_layout.setContentsMargins(0, 0, 0, 0)
        next_file_widget = self._create_next_file_content()
        self.next_file_container_layout.addWidget(next_file_widget)
        layout.addWidget(next_file_container)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.setStyleSheet(Styles.button_primary())
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

    def _check_for_updates(self):
        """Check if new files have been edited and update the dialog."""
        if not self.parent_widget:
            return

        try:
            # Get updated file lists from parent widget
            updated_muedit_files = self.parent_widget.muedit_files
            updated_edited_files = self.parent_widget.edited_files

            # Check if anything changed
            if (updated_muedit_files != self.muedit_files or
                updated_edited_files != self.edited_files):

                # Check if new file was completed (play sound)
                new_edited_count = len(updated_edited_files)
                if new_edited_count > self.last_edited_count:
                    self._play_success_sound()
                    logger.info(f"✓ File completed! Progress: {new_edited_count}/{len(updated_muedit_files)}")

                    # Show visual notification
                    self._show_completion_notification()

                # Update stored data
                self.muedit_files = updated_muedit_files
                self.edited_files = updated_edited_files
                self.last_edited_count = new_edited_count

                # Rebuild UI with new data
                self._refresh_ui()

        except Exception as e:
            logger.error(f"Error checking for updates in dialog: {e}")

    def _refresh_ui(self):
        """Refresh only the dynamic parts of the UI."""
        try:
            # Update file list
            if hasattr(self, 'file_list_container'):
                # Remove old file list
                old_widget = self.file_list_container.widget()
                if old_widget:
                    old_widget.deleteLater()

                # Create new file list
                new_file_list = self._create_file_list_content()
                self.file_list_container.setWidget(new_file_list)

            # Update next file widget
            if hasattr(self, 'next_file_container_layout'):
                # Clear old widgets
                while self.next_file_container_layout.count():
                    item = self.next_file_container_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

                # Add new next file widget
                next_file_widget = self._create_next_file_content()
                self.next_file_container_layout.addWidget(next_file_widget)

        except Exception as e:
            logger.error(f"Error refreshing UI: {e}")

    def _play_success_sound(self):
        """Play a success sound when a file is completed."""
        try:
            # Try system beep
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                # Play double beep for success
                app.beep()
                QTimer.singleShot(150, app.beep)

            logger.info("✓ Success sound played")
        except Exception as e:
            logger.debug(f"Could not play sound: {e}")
            # Fallback: no sound
            pass

    def _show_completion_notification(self):
        """Briefly highlight the live indicator when a file is completed."""
        if hasattr(self, 'live_indicator'):
            # Flash green
            self.live_indicator.setText("● Completed!")
            self.live_indicator.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.GREEN_700};
                    font-size: 11px;
                    font-weight: bold;
                    padding-left: 10px;
                }}
            """)

            # Reset after 2 seconds
            QTimer.singleShot(2000, lambda: self._reset_live_indicator())

    def _reset_live_indicator(self):
        """Reset the live indicator to normal state."""
        if hasattr(self, 'live_indicator'):
            self.live_indicator.setText("● Live")
            self.live_indicator.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.GREEN_600};
                    font-size: 11px;
                    padding-left: 10px;
                }}
            """)

    def _toggle_live_indicator(self):
        """Toggle the live indicator to create a blinking effect."""
        if hasattr(self, 'live_indicator') and self.live_indicator.text() == "● Live":
            self.blink_state = not self.blink_state
            opacity = "1.0" if self.blink_state else "0.3"
            self.live_indicator.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.GREEN_600};
                    font-size: 11px;
                    padding-left: 10px;
                    opacity: {opacity};
                }}
            """)

    def closeEvent(self, event):
        """Stop the timers when dialog is closed."""
        self.update_timer.stop()
        self.blink_timer.stop()
        super().closeEvent(event)

    def _create_steps_widget(self):
        """Creates the step-by-step instruction widget."""
        steps_widget = QWidget()
        steps_layout = QVBoxLayout(steps_widget)
        steps_layout.setSpacing(Spacing.XS)
        steps_layout.setContentsMargins(0, 0, 0, 0)

        steps = [
            "1. In MUEdit, click 'Load' and navigate to the file shown below",
            "2. Review and manually clean the motor unit decomposition",
            "3. Click 'Save' in MUEdit - this will create an edited .mat file",
            "4. Progress updates automatically when you save",
            "5. Repeat for all remaining files"
        ]

        for step in steps:
            step_label = QLabel(step)
            step_label.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.TEXT_PRIMARY};
                    font-size: 13px;
                    padding: 2px 0px;
                }}
            """)
            step_label.setWordWrap(True)
            steps_layout.addWidget(step_label)

        return steps_widget

    def _create_file_list_widget(self):
        """Creates the scrollable file status list container."""
        # Scrollable container
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(150)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)

        # Create initial content
        content = self._create_file_list_content()
        scroll_area.setWidget(content)
        return scroll_area

    def _create_file_list_content(self):
        """Creates the file status list content."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(Spacing.XS)

        for base_name in self.muedit_files:
            is_edited = base_name in self.edited_files

            if is_edited:
                status_text = f"✅ {base_name}"
                status_color = Colors.GREEN_700
            else:
                status_text = f"⏳ {base_name}"
                status_color = Colors.TEXT_MUTED

            status_label = QLabel(status_text)
            status_label.setStyleSheet(f"""
                QLabel {{
                    color: {status_color};
                    font-size: 12px;
                    padding: 3px 0px;
                }}
            """)
            layout.addWidget(status_label)

        layout.addStretch()
        return widget

    def _create_next_file_content(self):
        """Creates the 'Next File to Edit' content."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(Spacing.SM)
        layout.setContentsMargins(0, Spacing.MD, 0, 0)

        # Find next file to edit
        next_file = None
        for base_name in self.muedit_files:
            if base_name not in self.edited_files:
                next_file = base_name
                break

        if next_file:
            # Header
            header_label = QLabel("📂 Next File to Edit:")
            header_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 14px;
                    font-weight: bold;
                    color: {Colors.TEXT_PRIMARY};
                    padding-bottom: 5px;
                }}
            """)
            layout.addWidget(header_label)

            # File name
            filename = f"{next_file}_muedit.mat"
            filename_label = QLabel(filename)
            filename_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 13px;
                    color: {Colors.TEXT_PRIMARY};
                    padding: 2px 0px;
                }}
            """)
            layout.addWidget(filename_label)

            # Full path with copy button
            file_path = os.path.join(self.folder_path, filename)

            path_layout = QHBoxLayout()
            path_layout.setSpacing(Spacing.SM)

            # Copyable path field
            self.path_field = QLineEdit(file_path)
            self.path_field.setReadOnly(True)
            self.path_field.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {Colors.BG_SECONDARY};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: {BorderRadius.SM};
                    padding: 6px 8px;
                    font-family: monospace;
                    font-size: 11px;
                    color: {Colors.TEXT_PRIMARY};
                }}
            """)
            path_layout.addWidget(self.path_field, stretch=1)

            # Copy button
            copy_button = QPushButton("Copy")
            copy_button.setStyleSheet(Styles.button_secondary())
            copy_button.setFixedWidth(80)
            copy_button.clicked.connect(self._copy_path_to_clipboard)
            path_layout.addWidget(copy_button)

            layout.addLayout(path_layout)

        else:
            # All files completed
            complete_label = QLabel("🎉 All files have been cleaned!")
            complete_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 14px;
                    font-weight: bold;
                    color: {Colors.GREEN_700};
                    padding: 10px 0px;
                }}
            """)
            layout.addWidget(complete_label)

        return widget

    def _copy_path_to_clipboard(self):
        """Copies the file path to the clipboard."""
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.path_field.text())

        # Visual feedback
        original_text = self.sender().text()
        self.sender().setText("✓ Copied!")
        self.sender().setEnabled(False)

        # Reset after 1.5 seconds
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self._reset_copy_button(original_text))

    def _reset_copy_button(self, original_text):
        """Resets the copy button to its original state."""
        try:
            # Find the copy button
            for widget in self.findChildren(QPushButton):
                if widget.text() == "✓ Copied!":
                    widget.setText(original_text)
                    widget.setEnabled(True)
        except:
            pass
