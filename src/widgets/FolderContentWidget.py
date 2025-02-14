import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel

from state.global_state import global_state


class FolderContentWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        """Initialize the UI for displaying folder contents."""
        layout = QVBoxLayout(self)

        self.folder_label = QLabel("Folder Path: Not Selected")
        layout.addWidget(self.folder_label)

        self.folder_display = QTextEdit()
        self.folder_display.setReadOnly(True)
        self.folder_display.setPlaceholderText("Folder contents will be displayed here...")
        layout.addWidget(self.folder_display)

        self.setLayout(layout)

    def update_folder_content(self):
        """Updates the folder structure display when a new file is loaded."""
        folder_path = global_state.workfolder
        self.folder_label.setText(f"Folder Path: {folder_path}")
        folder_structure = self.get_folder_structure(folder_path)
        self.folder_display.setText(folder_structure)

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
