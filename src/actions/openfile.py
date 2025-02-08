import os
import sys
from PyQt5.QtWidgets import QFileDialog
from log.log_config import logger
from state.global_state import global_state

def open_mat_file_or_folder(mode='file'):
    """
    Opens a dialog to either select a .mat file or choose a folder.

    Parameters:
        mode (str): Either 'file' (to open a .mat file) or 'folder' (to select a folder).
        on_complete (function): A function called when the user presses the close button.

    Returns:
        str or None: The selected file path or folder path, or None if the user cancels.
    """
    if mode == 'file':
        options = QFileDialog.Options()
        # Optionally set options, for example: options |= QFileDialog.DontUseNativeDialog
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select a MATLAB File",
            "",
            "MAT Files (*.mat);;All Files (*)",
            options=options
        )
        logger.debug(f"File selected: {file_path}")
        if file_path:
            global_state.file_path = file_path
            global_state.mat_files = [file_path]
        return file_path if file_path else None

    elif mode == 'folder':
        options = QFileDialog.Options()
        folder_path = QFileDialog.getExistingDirectory(
            None,
            "Select a Folder",
            "",
            options=options
        )
        logger.debug(f"Folder selected: {folder_path}")
        if folder_path:
            global_state.mat_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.mat')]
        return folder_path if folder_path else None

    else:
        raise ValueError("Mode must be either 'file' or 'folder'")

def count_mat_files(folder_path):
    """Returns the number of .mat files in a folder"""
    if not folder_path or not os.path.isdir(folder_path):
        return 0
    return len([f for f in os.listdir(folder_path) if f.endswith('.mat')])