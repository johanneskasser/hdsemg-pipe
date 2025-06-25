import json
import os
from datetime import datetime

import numpy as np
from PyQt5.QtWidgets import QFileDialog

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.enum.FolderNames import FolderNames
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_shared.fileio.file_io import EMGFile
from hdsemg_pipe.state.global_state import global_state


def open_file_or_folder(mode='file'):
    """
    Opens a dialog to either select a file or choose a folder.

    Parameters:
        mode (str): Either 'file' (to open a file) or 'folder' (to select a folder).
        on_complete (function): A function called when the user presses the close button.

    Returns:
        str or None: The selected file path or folder path, or None if the user cancels.
    """
    workfolder_path = config.get(Settings.WORKFOLDER_PATH)

    if mode == 'file':
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select a File",
            os.getcwd(),  # Set a valid initial directory
            "MAT Files (*.mat);;OTB Files (*.otb+);;OTB4 Files (*.otb4);;All Files (*)",  # Corrected filter string
            options=options
        )
        logger.debug(f"File selected: {file_path}")
        if file_path:
            create_work_folder(workfolder_path, file_path)
            pre_process_files([file_path])

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
            files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if
                     f.endswith(('.mat', '.otb', '.otb+', '.otb4'))]
            create_work_folder(workfolder_path)
            pre_process_files(files)
        return folder_path if folder_path else None

    else:
        raise ValueError("Mode must be either 'file' or 'folder'")


def count_mat_files(folder_path):
    """Returns the number of wanted files in a folder"""
    if not folder_path or not os.path.isdir(folder_path):
        return 0
    return len([f for f in os.listdir(folder_path) if f.endswith(('.mat', '.otb', '.otb+', '.otb4'))])

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


    original_files_foldername = os.path.join(workfolder_path, FolderNames.ORIGINAL_FILES.value)
    original_files_foldername = os.path.normpath(original_files_foldername)
    channelselection_foldername = os.path.join(workfolder_path, FolderNames.CHANNELSELECTION.value)
    channelselection_foldername = os.path.normpath(channelselection_foldername)
    associated_grids_foldername = os.path.join(workfolder_path, FolderNames.ASSOCIATED_GRIDS.value)
    associated_grids_foldername = os.path.normpath(associated_grids_foldername)
    decomposition_foldername = os.path.join(workfolder_path, FolderNames.DECOMPOSITION.value)
    decomposition_foldername = os.path.normpath(decomposition_foldername)
    cropped_signal_foldername = os.path.join(workfolder_path, FolderNames.CROPPED_SIGNAL.value)
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
        emg = EMGFile.load(file)

        json_means = {}
        json_means["filename"] = os.path.basename(file)

        # Subtract Mean from data to remove DC offset so that signals oscillate around zero
        for grid in emg.grids:
            json_means[grid.grid_uid] = []  # Liste für jeden Channel dieses Grids
            for ch_index in grid.emg_indices:
                mean_before = emg.data[:, ch_index].mean()
                logger.debug(f"Grid: {grid.grid_uid}({grid.grid_key}), Channel Index: {ch_index}, Mean Before Subtraction: {mean_before}")
                emg.data[:, ch_index] -= mean_before
                mean_after = emg.data[:, ch_index].mean()
                logger.debug(f"Grid: {grid.grid_uid}({grid.grid_key}), Channel Index: {ch_index}, Mean After Subtraction: {mean_after}")
                # Speichern der Mittelwertdaten in json_means
                json_means[grid.grid_uid].append({
                    "channel_index": ch_index,
                    "method": "mean",
                    "mean_before": mean_before,
                    "mean_after": mean_after
                })
            for ref in grid.ref_indices:
                baseline_before = emg.data[:, ref].min()
                logger.debug(f"Grid: {grid.grid_uid}({grid.grid_key}), Channel Index: {ref}, Mean Before Subtraction: {baseline_before}")
                emg.data[:, ref] -= baseline_before # shift reference signals to zero
                baseline_after = emg.data[:, ref].min()
                logger.debug(f"Grid: {grid.grid_uid}({grid.grid_key}), Channel Index: {ref}, Mean After Subtraction: {baseline_after}")
                json_means[grid.grid_uid].append({
                    "reference_index": ref,
                    "method": "min",
                    "value_before": float(baseline_before),
                    "value_after": float(baseline_after)
                })
        # Save the pre-processed data to the original files folder
        logger.info(f"Finished pre-processing file: {file}")
        original_files_foldername = global_state.get_original_files_path()
        if not os.path.basename(file).endswith(".mat"):
            logger.debug(f"File {file} does not have a .mat extension. Saving as .mat")
            file = os.path.splitext(file)[0] + ".mat"
        new_file_path = os.path.join(original_files_foldername, os.path.basename(file))
        emg.save(str(new_file_path))
        logger.info(f"Saved pre-processed file to: {new_file_path}")
        save_json_means(json_means, new_file_path)
        global_state.add_original_file(new_file_path)


def save_json_means(json_means, new_file_path):
    def np_converter(obj):
        # Wenn es sich um ein numpy-Scalar handelt, geben wir dessen Python-Standardwert zurück
        if isinstance(obj, np.generic):
            return obj.item()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    # Erzeugen des Pfades der JSON-Datei: gleicher Ordner, gleicher Basisname, andere Extension
    json_file_path = os.path.splitext(new_file_path)[0] + ".json"
    with open(json_file_path, "w") as jf:
        json.dump(json_means, jf, indent=2, default=np_converter)
    logger.info(f"Saved mean values to JSON file: {json_file_path}")
