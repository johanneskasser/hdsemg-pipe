import os
from datetime import datetime

from PyQt5.QtWidgets import QFileDialog

from _log.log_config import logger
from config.config_enums import Settings
from config.config_manager import config
from logic.file_io import load_mat_file, save_selection_to_mat
from logic.grid import extract_grid_info
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
    workfolder_path = config.get(Settings.WORKFOLDER_PATH)

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
            create_work_folder(workfolder_path, file_path)
            pre_process_files([file_path])
            new_file = global_state.mat_files[
                0]  # here we can safely assume that the first file is the one we want and it exists
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
            files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.mat')]
            create_work_folder(workfolder_path)
            pre_process_files(files)
        return folder_path if folder_path else None

    else:
        raise ValueError("Mode must be either 'file' or 'folder'")


def count_mat_files(folder_path):
    """Returns the number of .mat files in a folder"""
    if not folder_path or not os.path.isdir(folder_path):
        return 0
    return len([f for f in os.listdir(folder_path) if f.endswith('.mat')])


def create_work_folder(workfolder_path, file_path=None):
    """Creates a new folder in the workfolder based on the file name."""
    if not workfolder_path:
        logger.error("Workfolder path is not set.")
        return

    curr_time = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    if file_path is not None:
        base_name = os.path.basename(file_path)
        folder_name = os.path.splitext(base_name)[0]  # Remove extension
        folder_name = f"{folder_name}-{curr_time}"
        new_folder_path = os.path.join(workfolder_path, folder_name)
    else:
        foldername = f"folder-{curr_time}"
        new_folder_path = os.path.join(workfolder_path, foldername)
        new_folder_path = os.path.normpath(new_folder_path)  # Normalize path

    try:
        os.makedirs(new_folder_path, exist_ok=True)
        logger.info(f"Created folder: {new_folder_path}")
        global_state.workfolder = new_folder_path
        create_sub_work_folders(new_folder_path)
    except Exception as e:
        logger.error(f"Failed to create folder {new_folder_path}: {e}")


def create_sub_work_folders(workfolder_path):
    if not workfolder_path or not os.path.isdir(workfolder_path):
        logger.error("Created workfolder path does not exist. Please check.")
        return

    original_files_foldername = "original_files"
    channelselection_foldername = "channelselection"
    associated_grids_foldername = "associated_grids"
    decomposition_foldername = "decomposition"
    cropped_signal_foldername = "cropped_signal"

    original_files_foldername = os.path.join(workfolder_path, original_files_foldername)
    original_files_foldername = os.path.normpath(original_files_foldername)
    channelselection_foldername = os.path.join(workfolder_path, channelselection_foldername)
    channelselection_foldername = os.path.normpath(channelselection_foldername)
    associated_grids_foldername = os.path.join(workfolder_path, associated_grids_foldername)
    associated_grids_foldername = os.path.normpath(associated_grids_foldername)
    decomposition_foldername = os.path.join(workfolder_path, decomposition_foldername)
    decomposition_foldername = os.path.normpath(decomposition_foldername)
    cropped_signal_foldername = os.path.join(workfolder_path, cropped_signal_foldername)
    cropped_signal_foldername = os.path.normpath(cropped_signal_foldername)

    try:
        os.makedirs(original_files_foldername, exist_ok=True)
        logger.info(f"Created original_file Folder: {original_files_foldername}")
        os.makedirs(associated_grids_foldername, exist_ok=True)
        logger.info(f"Created associated_grids folder: {associated_grids_foldername}")
        os.makedirs(decomposition_foldername, exist_ok=True)
        logger.info(f"Created decomposition folder: {decomposition_foldername}")
        os.makedirs(channelselection_foldername, exist_ok=True)
        logger.info(f"Created channelselection folder: {channelselection_foldername}")
        os.makedirs(cropped_signal_foldername, exist_ok=True)
        logger.info(f"Created cropped_signal folder: {cropped_signal_foldername}")
    except Exception as e:
        logger.error(f"Failed to create sub-folder: {e}")


def pre_process_files(filepaths):
    for file in filepaths:
        logger.info(f"Pre-processing file: {file}")
        data, time, description, sf, fn, fs = load_mat_file(file)
        grid_info = extract_grid_info(description)

        # Subtract Mean from data to remove DC offset so that signals oscillate around zero
        for grid_key, grid_data in grid_info.items():
            for ch_index in grid_data['indices']:
                channel_mean = data[:, ch_index].mean()
                logger.debug(f"Grid: {grid_key}, Channel Index: {ch_index}, Mean Before Subtraction: {channel_mean}")
                data[:, ch_index] -= channel_mean
                logger.debug(f"Grid: {grid_key}, Channel Index: {ch_index}, Mean After Subtraction: {data[:, ch_index].mean()}")

        # Save the pre-processed data to the original files folder
        logger.info(f"Finished pre-processing file: {file}")
        original_files_foldername = global_state.get_original_files_path()
        new_file_path = os.path.join(original_files_foldername, os.path.basename(file))
        save_selection_to_mat(new_file_path, data, time, description, sf, fn, grid_info)
        logger.info(f"Saved pre-processed file to: {new_file_path}")
        global_state.mat_files.append(new_file_path)

