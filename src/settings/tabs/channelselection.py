import os

from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog

from config.config_enums import Settings
from config.config_manager import config

def init(parent):
    layout = QVBoxLayout()
    # Create a horizontal layout for the file specification row
    file_layout = QHBoxLayout()

    # Information label
    info_label = QLabel(
        "Please provide the path to the executable file of the Channel Selection App.<br>"
        "This file is used to launch the Channel Selection App from the HDsEMG pipeline.<br>"
        "The channelselection App can be installed <a href=\"https://github.com/haripen/Neuromechanics_FHCW\">here.</a>"
    )
    info_label.setOpenExternalLinks(True)
    layout.addWidget(info_label)

    # Label prompting for file path
    file_label = QLabel("File Path:")
    file_layout.addWidget(file_label)

    # QLineEdit for entering the file path
    file_line_edit = QLineEdit()
    file_line_edit.setPlaceholderText("Enter the file path...")
    file_layout.addWidget(file_line_edit)

    browse_button = QPushButton("Browse")
    file_layout.addWidget(browse_button)

    # QLabel to display the validity icon (green check or red X)
    validity_indicator = QLabel()
    validity_indicator.setFixedWidth(30)
    file_layout.addWidget(validity_indicator)

    # Add the file layout to the main layout
    layout.addLayout(file_layout)

    # Function to update the validity indicator based on file status
    def update_validity():
        file_path = file_line_edit.text().strip()
        if os.path.exists(file_path) and file_path.lower().endswith('.exe') or file_path.lower().endswith('.py'):
            config.set(Settings.EXECUTABLE_PATH, file_path)
            validity_indicator.setText("✔")
            validity_indicator.setStyleSheet("color: green; font-size: 20px;")
        else:
            validity_indicator.setText("✖")
            validity_indicator.setStyleSheet("color: red; font-size: 20px;")

    # Update validity whenever the text changes
    file_line_edit.textChanged.connect(update_validity)
    if config.get(Settings.EXECUTABLE_PATH) is not None:
        file_line_edit.setText(config.get(Settings.EXECUTABLE_PATH))
        update_validity()

    def open_file_dialog():
        # Opens a file dialog. Adjust filters as needed.
        file_path, _ = QFileDialog.getOpenFileName(
            parent, "Select File", "",
            "Executable and Python Files (*.exe *.py);;All Files (*)"
        )
        if file_path:
            file_line_edit.setText(file_path)

    # Connect the browse button to the file dialog function
    browse_button.clicked.connect(open_file_dialog)

    return layout
