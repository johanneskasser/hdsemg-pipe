import os
import subprocess
import platform

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLabel, QHBoxLayout, QPushButton, QStyle, QFileDialog, QDialog, QMessageBox
)
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.controller.automatic_state_reconstruction import start_reconstruction_workflow


class FolderContentWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        """Initialize the UI for displaying folder contents."""
        layout = QVBoxLayout(self)

        # Create a horizontal layout for the folder label and folder button
        top_layout = QHBoxLayout()
        self.folder_label = QLabel("")
        top_layout.addWidget(self.folder_label)

        # Add a stretch so that the button moves to the very right
        top_layout.addStretch()

        # Create the folder button using the native folder icon
        self.folder_button = QPushButton()
        folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self.folder_button.setIcon(folder_icon)
        self.update_tooltip()
        self.folder_button.clicked.connect(self.button_behaviour)
        top_layout.addWidget(self.folder_button)

        layout.addLayout(top_layout)

        # Create the text display area for folder contents
        self.folder_display = QTextEdit()
        self.folder_display.setReadOnly(True)
        self.folder_display.setPlaceholderText("Folder contents will be displayed here...")
        layout.addWidget(self.folder_display)

        self.setLayout(layout)

    def update_folder_content(self):
        """Updates the folder structure display when a new folder is set."""
        folder_path = global_state.workfolder
        if folder_path:
            self.folder_label.setText(f"{folder_path}")
            if os.path.isdir(folder_path):
                folder_structure = self.get_folder_structure(folder_path)
                # Enable the button only if the folder path is valid
            else:
                folder_structure = "Invalid folder."
        else:
            self.folder_label.setText("")
            folder_structure = ""

        self.folder_display.setText(folder_structure)
        self.update_tooltip()

    def update_tooltip(self):
        folder_path = global_state.workfolder
        if folder_path and os.path.isdir(folder_path):
            self.folder_button.setToolTip(f"Open Folder: {folder_path}")
        else:
            self.folder_button.setToolTip("Open a existing workfolder to continue the work where you have stopped.")

    def get_folder_structure(self, folder_path, indent=""):
        """Recursively get folder content as a structured string."""
        folder_content = ""
        try:
            for item in sorted(os.listdir(folder_path)):  # Sort for consistent order
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    folder_content += f"{indent}📂 {item}\n"
                    folder_content += self.get_folder_structure(item_path, indent + "   ")
                else:
                    folder_content += f"{indent}📄 {item}\n"
        except PermissionError:
            folder_content += f"{indent}❌ Access Denied\n"
        return folder_content

    def button_behaviour(self):
        """Open the system's file explorer for the associated folder."""
        folder_path = global_state.workfolder
        if folder_path and os.path.isdir(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])
        else:
            start_reconstruction_workflow(self)