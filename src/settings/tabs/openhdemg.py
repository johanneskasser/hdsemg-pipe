import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog
)

from config.config_enums import Settings
from config.config_manager import config


def init(parent):
    """
    Initialize the OpenHD-EMG settings tab.

    Args:
        parent (QWidget): The parent widget.

    Returns:
        QWidget: The initialized settings tab widget.
    """
    layout = QVBoxLayout()

    # Information label
    info_label = QLabel(
        "openhdemg is an open-source project to analyse HD-EMG recordings [<a href=\"https://doi.org/10.1016/j.jelekin.2023.102850\">Valli et al. 2024</a>].<br>"
        "Specify the base path of the virtual environment (venv).<br>"
        "In anaconda prompt type 'conda info --envs' for all environments and paths.<br>"
        "Install <a href=\"https://github.com/GiacomoValliPhD/openhdemg\">openhdemg</a> if you have not done so already.<br>"
        "Then provide the path to the venv here."
    )
    info_label.setOpenExternalLinks(True)
    layout.addWidget(info_label)

    # Create a horizontal layout row for the path input
    h_layout = QHBoxLayout()
    label = QLabel("Venv Base Path:")
    h_layout.addWidget(label)

    # QLineEdit for entering the base path
    venv_line_edit = QLineEdit()
    venv_line_edit.setPlaceholderText("Enter the base path of the venv...")
    h_layout.addWidget(venv_line_edit)

    # Button to browse the folder
    browse_button = QPushButton("Browse")
    h_layout.addWidget(browse_button)

    # Label for the validity indicator (green check or red X)
    validity_indicator = QLabel()
    validity_indicator.setFixedWidth(30)
    h_layout.addWidget(validity_indicator)

    layout.addLayout(h_layout)

    def is_valid_venv(path):
        """
        Check if the given path is a valid virtual environment.

        Args:
            path (str): The path to check.

        Returns:
            bool: True if the path is a valid virtual environment, False otherwise.
        """
        # Check if the path is a directory
        if not os.path.isdir(path):
            return False
        # A typical indicator of a venv is the pyvenv.cfg file in the root directory
        if os.path.exists(os.path.join(path, "pyvenv.cfg")):
            return True
        # Alternatively, on Windows check if python.exe is in the "Scripts" folder,
        # otherwise (Linux/Mac) check if a python script is in the "bin" folder
        if os.name == "nt":
            if os.path.exists(os.path.join(path, "Scripts", "python.exe")):
                return True
        else:
            if os.path.exists(os.path.join(path, "bin", "python")):
                return True
        return False

    def update_validity():
        """
        Update the validity indicator based on the entered path.
        """
        path = venv_line_edit.text().strip()
        if is_valid_venv(path):
            # Save the valid venv path in the configuration
            config.set(Settings.VENV_PATH, path)
            validity_indicator.setText("✔")
            validity_indicator.setStyleSheet("color: green; font-size: 20px;")
        else:
            validity_indicator.setText("✖")
            validity_indicator.setStyleSheet("color: red; font-size: 20px;")

    # Update the validity indicator when the input changes
    venv_line_edit.textChanged.connect(update_validity)
    existing_path = config.get(Settings.VENV_PATH)
    if existing_path:
        venv_line_edit.setText(existing_path)
        update_validity()

    def open_folder_dialog():
        """
        Open a folder dialog to select the virtual environment base path.
        """
        folder = QFileDialog.getExistingDirectory(parent, "Select Virtual Environment Base Path", "")
        if folder:
            venv_line_edit.setText(folder)

    browse_button.clicked.connect(open_folder_dialog)

    return layout