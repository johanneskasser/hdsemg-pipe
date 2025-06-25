import os

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.enum.FolderNames import FolderNames
from hdsemg_pipe.state.global_state import global_state
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.config.config_enums import Settings


def start_reconstruction_workflow(parent):
    workfolder_path = config.get(Settings.WORKFOLDER_PATH)
    if workfolder_path is None:
        workfolder_path = os.getcwd()

    if global_state.workfolder is None:
        selected_folder = QFileDialog.getExistingDirectory(parent, "Select existing pipeline folder", directory=workfolder_path)
        if selected_folder:
            try:
                reconstruct_folder_state(folderpath=selected_folder)
            except Exception as e:
                global_state.reset()
                logger.warning(f"Failed to reconstruct folder state: {e}")
                QMessageBox.warning(parent, "Error", f"Failed to reconstruct folder state: \n{str(e)}")
    else:
        QMessageBox.warning(parent, "Error", "A pipeline folder is already selected.")

def reconstruct_folder_state(folderpath):
    logger.info(f"Reconstructing folder state for: {folderpath}")
    folder_content_widget = global_state.get_widget("folder_content")
    global_state.reset()


    # initial checks
    _check_folder_existence(folderpath)
    _check_pipe_folder_structure(folderpath)

    global_state.workfolder = folderpath

    try:
        _original_files(folderpath)
        _associated_grid_files(folderpath)
        _roi_files(folderpath)
        _channel_selection_files(folderpath)
        msg_box = _show_restore_success(folderpath)
        msg_box.exec_()
        folder_content_widget.update_folder_content()
        return
    except FileNotFoundError as e:
        _decomposition_results_init()
        msg_box = _show_restore_success(folderpath)
        msg_box.exec_()
        folder_content_widget.update_folder_content()
        return


def _show_restore_success(folderpath):
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setWindowTitle("State restored")
    msg_box.setText(f"The state of folder {folderpath} has been restored.")
    return msg_box


def _check_folder_existence(folderpath):
    """Check if the folder exists and is a directory."""
    logger.debug(f"Checking if folder exists: {folderpath}")
    if not os.path.exists(folderpath):
        logger.warning(f"The specified path does not exist: {folderpath}")
        raise FileNotFoundError(f"The specified path does not exist: {folderpath}")
    if not os.path.isdir(folderpath):
        logger.warning(f"The specified path is not a directory: {folderpath}")
        raise NotADirectoryError(f"The specified path is not a directory: {folderpath}")


def _check_pipe_folder_structure(folderpath):
    """Check if the folder structure is valid for the application."""
    logger.debug(f"Checking folder structure for: {folderpath}")
    # Define the expected subfolders
    expected_subfolders = FolderNames.list_values()

    # Check if each expected subfolder exists
    for subfolder in expected_subfolders:
        subfolder_path = os.path.join(folderpath, subfolder)
        logger.debug(f"Checking for subfolder: {subfolder_path}")
        if not os.path.exists(subfolder_path):
            logger.warning(f"Missing expected subfolder: {subfolder_path}")
            raise FileNotFoundError(f"Missing expected subfolder: {subfolder_path}")

    logger.info(f"Folder structure is valid for: {folderpath}")


def _original_files(folderpath):
    """Check if the original files folder exists."""
    original_files_path = os.path.join(folderpath, str(FolderNames.ORIGINAL_FILES.value))
    files = os.listdir(original_files_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(original_files_path, file)
            global_state.add_original_file(file_path)

    orig_files = global_state.get_original_files()
    if not orig_files or len(orig_files) == 0:
        logger.warning(f"No original files found in: {original_files_path}")
        raise FileNotFoundError(f"No original files found in: {original_files_path}")

    logger.debug(f"Original files added to global state: {orig_files}")

    original_files_widget = global_state.get_widget("step0")
    if original_files_widget:
        original_files_widget.check()
        original_files_widget.complete_step()
        original_files_widget.fileSelected.emit(folderpath)
    else:
        logger.warning("Original files widget not found in global state.")
        raise ValueError("Original fi1les widget not found in global state.")

    return original_files_path

def _associated_grid_files(folderpath):
    """Check if the associated grid files folder exists."""
    associated_grids_path = os.path.join(folderpath, str(FolderNames.ASSOCIATED_GRIDS.value))
    files = os.listdir(associated_grids_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(associated_grids_path, file)
            global_state.associated_files.append(file_path)

    associated_files = global_state.associated_files.copy()
    if not associated_files or len(associated_files) == 0:
        logger.warning(f"No associated grid files found in: {associated_grids_path}")
        raise FileNotFoundError(f"No associated grid found in: {associated_grids_path}")

    logger.debug(f"associated grid added to global state: {associated_files}")

    associated_grids_widget = global_state.get_widget("step1")
    if associated_grids_widget:
        associated_grids_widget.check()
        associated_grids_widget.complete_step()
    else:
        logger.warning("associated grid widget not found in global state.")
        raise ValueError("associated grid widget not found in global state.")

    return associated_grids_path

def _roi_files(folderpath):
    """Check if the roi files folder exists."""
    roi_file_path = os.path.join(folderpath, str(FolderNames.CROPPED_SIGNAL.value))
    files = os.listdir(roi_file_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(roi_file_path, file)
            global_state.cropped_files.append(file_path)

    roi_files = global_state.cropped_files.copy()
    if not roi_files or len(roi_files) == 0:
        logger.warning(f"No roi files found in: {roi_file_path}")
        raise FileNotFoundError(f"No roi found in: {roi_file_path}")

    logger.debug(f"roi added to global state: {roi_files}")

    roi_file_widget = global_state.get_widget("step2")
    if roi_file_widget:
        roi_file_widget.check()
        roi_file_widget.complete_step()
    else:
        logger.warning("roi widget not found in global state.")
        raise ValueError("roi widget not found in global state.")

    return roi_file_path

def _channel_selection_files(folderpath):
    """Check if the channel selection files folder exists."""
    channel_selection_file_path = os.path.join(folderpath, str(FolderNames.CHANNELSELECTION.value))
    files = os.listdir(channel_selection_file_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(channel_selection_file_path, file)
            global_state.channel_selection_files.append(file_path)

    channel_selection_files = global_state.channel_selection_files.copy()
    if not channel_selection_files or len(channel_selection_files) == 0:
        logger.warning(f"No channelselection files found in: {channel_selection_file_path}")
        raise FileNotFoundError(f"No channelselection found in: {channel_selection_file_path}")

    logger.debug(f"channelselection added to global state: {channel_selection_files}")

    channel_selection_file_widget = global_state.get_widget("step3")
    if channel_selection_file_widget:
        channel_selection_file_widget.check()
        channel_selection_file_widget.complete_step(processed_files=len(channel_selection_files))
    else:
        logger.warning("channelselection widget not found in global state.")
        raise ValueError("channelselection widget not found in global state.")

    return channel_selection_file_path

def _decomposition_results_init():
    decomposition_widget = global_state.get_widget("step4")
    if decomposition_widget:
        decomposition_widget.init_file_checking()
    else:
        logger.warning("decomposition widget not found in global state.")
        raise ValueError("decomposition widget not found in global state.")



