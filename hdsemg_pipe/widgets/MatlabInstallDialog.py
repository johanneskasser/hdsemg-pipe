"""
Dialog for MATLAB Engine installation instructions with copy buttons.
"""
import sys
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QApplication, QFrame, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont


class FindMatlabWorker(QThread):
    """Worker thread to find MATLAB installation path."""
    finished = pyqtSignal(str)  # engine_path or empty string if not found

    def run(self):
        """Find MATLAB Engine path."""
        from hdsemg_pipe.settings.tabs.matlab_installer import MatlabEngineInstallThread
        installer = MatlabEngineInstallThread()
        engine_path = installer.find_matlab_engine_path()
        self.finished.emit(engine_path or "")


class CodeBox(QFrame):
    """A code box with a copy button (GitHub-style)."""

    def __init__(self, code=None, title=None, loading=False, parent=None):
        super().__init__(parent)
        self.code = code
        self.loading = loading
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setStyleSheet("""
            CodeBox {
                background-color: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with title and copy button
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #f6f8fa;
                border-bottom: 1px solid #d0d7de;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet("font-weight: bold; color: #24292f;")
            header_layout.addWidget(title_label)
        else:
            header_layout.addStretch()

        # Copy button
        self.copy_btn = QPushButton("📋")
        self.copy_btn.setToolTip("Copy")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 5px 8px;
                color: #24292f;
                font-size: 14px;
                min-width: 32px;
                max-width: 32px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
                border-color: #1b1f2326;
            }
            QPushButton:pressed {
                background-color: #e5e7eb;
            }
        """)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.copy_btn.setEnabled(not loading)
        header_layout.addWidget(self.copy_btn)

        layout.addWidget(header)

        # Code display or loading indicator
        if loading:
            # Show loading state
            loading_container = QFrame()
            loading_container.setStyleSheet("""
                QFrame {
                    background-color: #ffffff;
                    border: none;
                    border-bottom-left-radius: 6px;
                    border-bottom-right-radius: 6px;
                }
            """)
            loading_layout = QVBoxLayout(loading_container)
            loading_layout.setContentsMargins(12, 20, 12, 20)
            loading_layout.setAlignment(Qt.AlignCenter)

            # Spinner
            self.spinner = QProgressBar()
            self.spinner.setRange(0, 0)  # Indeterminate
            self.spinner.setTextVisible(False)
            self.spinner.setFixedWidth(200)
            self.spinner.setFixedHeight(4)
            self.spinner.setStyleSheet("""
                QProgressBar {
                    border: none;
                    background-color: #e5e7eb;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background-color: #3b82f6;
                    border-radius: 2px;
                }
            """)
            loading_layout.addWidget(self.spinner)

            loading_label = QLabel("🔍 Detecting MATLAB installation...")
            loading_label.setStyleSheet("color: #6b7280; margin-top: 8px; font-size: 12px;")
            loading_layout.addWidget(loading_label)

            loading_container.setFixedHeight(80)
            self.code_edit = loading_container  # Placeholder for replacement later
            layout.addWidget(loading_container)
        else:
            # Show code
            self.code_edit = QTextEdit()
            self.code_edit.setReadOnly(True)
            self.code_edit.setPlainText(code or "")
            self.code_edit.setStyleSheet("""
                QTextEdit {
                    background-color: #ffffff;
                    border: none;
                    border-bottom-left-radius: 6px;
                    border-bottom-right-radius: 6px;
                    padding: 12px;
                    color: #24292f;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    font-size: 13px;
                }
            """)

            # Set fixed height based on number of lines
            if code:
                lines = code.count('\n') + 1
                line_height = 20
                self.code_edit.setFixedHeight(lines * line_height + 24)
            else:
                self.code_edit.setFixedHeight(60)

            layout.addWidget(self.code_edit)

    def update_code(self, code):
        """Update the code content (called after loading)."""
        self.code = code
        self.loading = False

        # Replace loading container with code editor
        old_widget = self.code_edit
        parent_layout = self.layout()

        # Create new code editor
        self.code_edit = QTextEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setPlainText(code)
        self.code_edit.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                border: none;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                padding: 12px;
                color: #24292f;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
            }
        """)

        # Set fixed height based on number of lines
        lines = code.count('\n') + 1
        line_height = 20
        self.code_edit.setFixedHeight(lines * line_height + 24)

        # Replace widget
        parent_layout.removeWidget(old_widget)
        old_widget.deleteLater()
        parent_layout.addWidget(self.code_edit)

        # Enable copy button
        self.copy_btn.setEnabled(True)

    def copy_to_clipboard(self):
        """Copy code to clipboard and show success feedback."""
        if not self.code or self.loading:
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(self.code)

        # Change button to show success
        self.copy_btn.setText("✓")
        self.copy_btn.setToolTip("Copied!")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #dcfce7;
                border: 1px solid #86efac;
                border-radius: 6px;
                padding: 5px 8px;
                color: #166534;
                font-size: 14px;
                font-weight: bold;
                min-width: 32px;
                max-width: 32px;
            }
        """)

        # Reset button after 2 seconds
        QTimer.singleShot(2000, self.reset_button)

    def reset_button(self):
        """Reset button to original state."""
        self.copy_btn.setText("📋")
        self.copy_btn.setToolTip("Copy")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 5px 8px;
                color: #24292f;
                font-size: 14px;
                min-width: 32px;
                max-width: 32px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
                border-color: #1b1f2326;
            }
            QPushButton:pressed {
                background-color: #e5e7eb;
            }
        """)


class MatlabInstallDialog(QDialog):
    """Dialog showing MATLAB Engine installation instructions with copy buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine_path = None
        self.setWindowTitle("MATLAB Engine Installation Instructions")
        self.setMinimumWidth(700)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("📦 MATLAB Engine for Python Installation")
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #24292f;
            margin-bottom: 8px;
        """)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Choose one of the following methods to install the MATLAB Engine for Python. "
            "Click the copy button to copy the command to your clipboard."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #57606a; margin-bottom: 8px;")
        layout.addWidget(desc)

        # Option 1: MATLAB
        option1_label = QLabel("🔵 <b>Option 1: In MATLAB (Recommended)</b>")
        option1_label.setStyleSheet("font-size: 14px; margin-top: 8px; margin-bottom: 4px;")
        layout.addWidget(option1_label)

        option1_desc = QLabel("Open MATLAB and paste this command:")
        option1_desc.setStyleSheet("color: #57606a; margin-bottom: 8px;")
        layout.addWidget(option1_desc)

        # Create loading code box
        self.matlab_box = CodeBox(loading=True, title="MATLAB Command")
        layout.addWidget(self.matlab_box)

        # Option 2: Terminal/CMD
        option2_label = QLabel("🔵 <b>Option 2: In Terminal/Command Prompt</b>")
        option2_label.setStyleSheet("font-size: 14px; margin-top: 16px; margin-bottom: 4px;")
        layout.addWidget(option2_label)

        option2_desc = QLabel("Open Terminal/CMD and paste these commands:")
        option2_desc.setStyleSheet("color: #57606a; margin-bottom: 8px;")
        layout.addWidget(option2_desc)

        # Create loading code box
        self.terminal_box = CodeBox(loading=True, title="Terminal/CMD Commands")
        layout.addWidget(self.terminal_box)

        # Info note
        info_note = QLabel(
            "ℹ️ <b>After installation:</b> Restart this application for the changes to take effect."
        )
        info_note.setWordWrap(True)
        info_note.setStyleSheet("""
            background-color: #dbeafe;
            border: 1px solid #3b82f6;
            border-radius: 6px;
            padding: 12px;
            color: #1e40af;
            margin-top: 8px;
        """)
        layout.addWidget(info_note)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 8px 16px;
                color: #24292f;
                font-size: 14px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
                border-color: #1b1f2326;
            }
            QPushButton:pressed {
                background-color: #e5e7eb;
            }
        """)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Start worker thread to find MATLAB
        self.worker = FindMatlabWorker()
        self.worker.finished.connect(self.on_matlab_found)
        self.worker.start()

    def on_matlab_found(self, engine_path):
        """Called when MATLAB path is found (or not)."""
        self.engine_path = engine_path

        if not engine_path:
            # MATLAB not found - show error message in code boxes
            error_msg = "❌ MATLAB installation not found.\n\nPlease install MATLAB first."
            self.matlab_box.update_code(error_msg)
            self.terminal_box.update_code(error_msg)
            return

        # Update MATLAB command
        matlab_cmd = (
            f"cd(fullfile(matlabroot,'extern','engines','python'));\n"
            f"system('{sys.executable} setup.py install')"
        )
        self.matlab_box.update_code(matlab_cmd)

        # Update Terminal/CMD command
        if sys.platform == "win32":
            terminal_cmd = (
                f'cd "{engine_path}"\n'
                f'"{sys.executable}" setup.py install'
            )
        else:
            terminal_cmd = (
                f'cd "{engine_path}"\n'
                f'{sys.executable} setup.py install'
            )
        self.terminal_box.update_code(terminal_cmd)
