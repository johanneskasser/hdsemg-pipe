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

    # Reconstruct each step independently to handle optional/skipped steps
    # Original files are mandatory - fail if missing
    try:
        _original_files(folderpath)
    except FileNotFoundError as e:
        logger.error(f"Cannot reconstruct state: {e}")
        raise

    # All subsequent steps are optional - continue even if they fail
    try:
        _associated_grid_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping grid association reconstruction: {e}")

    try:
        _line_noise_cleaned_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping line noise cleaned reconstruction: {e}")

    try:
        _analysis_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping RMS analysis reconstruction: {e}")

    try:
        _roi_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping ROI reconstruction: {e}")

    try:
        _channel_selection_files(folderpath)
    except FileNotFoundError as e:
        logger.info(f"Skipping channel selection reconstruction: {e}")

    # Always initialize decomposition results (Step 5)
    try:
        _decomposition_results_init()
    except Exception as e:
        logger.info(f"Skipping decomposition results reconstruction: {e}")

    # Try to reconstruct multi-grid configuration (Step 8)
    try:
        _multigrid_config()
    except Exception as e:
        logger.info(f"Skipping multi-grid configuration reconstruction: {e}")

    # Try to reconstruct CoVISI pre-filter (Step 9)
    try:
        _covisi_pre_filter()
    except Exception as e:
        logger.info(f"Skipping CoVISI pre-filter reconstruction: {e}")

    # Try to reconstruct MUEdit cleaning (Step 10)
    try:
        _muedit_cleaning()
    except Exception as e:
        logger.info(f"Skipping MUEdit cleaning reconstruction: {e}")

    # Try to reconstruct CoVISI post-validation (Step 11)
    try:
        _covisi_post_validation()
    except Exception as e:
        logger.info(f"Skipping CoVISI post-validation reconstruction: {e}")

    # Try to reconstruct final results (Step 12)
    try:
        _final_results()
    except Exception as e:
        logger.info(f"Skipping final results reconstruction: {e}")

    msg_box = _show_restore_success(folderpath)
    msg_box.exec_()
    folder_content_widget.update_folder_content()

    # Navigate wizard to the last completed step + 1 (or last step if all complete)
    last_completed_step = _get_last_completed_step()
    logger.info(f"Last completed step: {last_completed_step}")

    return last_completed_step


def _get_last_completed_step():
    """Get the index of the last completed step."""
    for step_index in range(12, 0, -1):  # Check from step 12 down to 1
        if global_state.is_widget_completed(f"step{step_index}"):
            return step_index
    return 0  # No steps completed, return first step


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
    # Define the expected subfolders (some are optional for backwards compatibility)
    expected_subfolders = FolderNames.list_values()
    optional_folders = [FolderNames.DECOMPOSITION_RESULTS.value, FolderNames.ANALYSIS.value]

    # Check if each expected subfolder exists
    for subfolder in expected_subfolders:
        subfolder_path = os.path.join(folderpath, subfolder)
        logger.debug(f"Checking for subfolder: {subfolder_path}")
        if not os.path.exists(subfolder_path):
            if subfolder in optional_folders:
                logger.info(f"Optional subfolder not found (will be created): {subfolder_path}")
                # Create optional folders if they don't exist
                try:
                    os.makedirs(subfolder_path, exist_ok=True)
                    logger.info(f"Created optional subfolder: {subfolder_path}")
                except Exception as e:
                    logger.warning(f"Failed to create optional subfolder {subfolder_path}: {e}")
            else:
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

    original_files_widget = global_state.get_widget("step1")
    if original_files_widget:
        original_files_widget.check()
        original_files_widget.complete_step()
        original_files_widget.fileSelected.emit(folderpath)
    else:
        logger.warning("Original files widget not found in global state.")
        raise ValueError("Original files widget not found in global state.")

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

    associated_grids_widget = global_state.get_widget("step2")
    if associated_grids_widget:
        associated_grids_widget.check()
        associated_grids_widget.complete_step()
    else:
        logger.warning("associated grid widget not found in global state.")
        raise ValueError("associated grid widget not found in global state.")

    return associated_grids_path

def _line_noise_cleaned_files(folderpath):
    """Check if the line noise cleaned files folder exists."""
    line_noise_cleaned_path = os.path.join(folderpath, str(FolderNames.LINE_NOISE_CLEANED.value))
    files = os.listdir(line_noise_cleaned_path)

    for file in files:
        if file.endswith(".mat"):
            file_path = os.path.join(line_noise_cleaned_path, file)
            global_state.line_noise_cleaned_files.append(file_path)

    line_noise_cleaned_files = global_state.line_noise_cleaned_files.copy()
    if not line_noise_cleaned_files or len(line_noise_cleaned_files) == 0:
        logger.warning(f"No line noise cleaned files found in: {line_noise_cleaned_path}")
        raise FileNotFoundError(f"No line noise cleaned files found in: {line_noise_cleaned_path}")

    logger.debug(f"Line noise cleaned files added to global state: {line_noise_cleaned_files}")

    line_noise_cleaned_widget = global_state.get_widget("step3")
    if line_noise_cleaned_widget:
        line_noise_cleaned_widget.check()
        line_noise_cleaned_widget.complete_step(processed_files=len(line_noise_cleaned_files))
    else:
        logger.warning("Line noise removal widget not found in global state.")
        raise ValueError("Line noise removal widget not found in global state.")

    return line_noise_cleaned_path

def _analysis_files(folderpath):
    """Check if the analysis folder exists and contains results."""
    analysis_path = os.path.join(folderpath, str(FolderNames.ANALYSIS.value))

    if not os.path.exists(analysis_path):
        logger.warning(f"Analysis folder not found: {analysis_path}")
        raise FileNotFoundError(f"Analysis folder not found: {analysis_path}")

    files = os.listdir(analysis_path)

    # Check for analysis output files (PNG, CSV, or TXT)
    analysis_files = [f for f in files if f.endswith(('.png', '.csv', '.txt'))]

    if not analysis_files or len(analysis_files) == 0:
        logger.warning(f"No analysis files found in: {analysis_path}")
        raise FileNotFoundError(f"No analysis files found in: {analysis_path}")

    logger.debug(f"Analysis files found: {analysis_files}")

    rms_quality_widget = global_state.get_widget("step4")
    if rms_quality_widget:
        rms_quality_widget.check()
        rms_quality_widget.complete_step()
    else:
        logger.warning("RMS Quality Analysis widget not found in global state.")
        raise ValueError("RMS Quality Analysis widget not found in global state.")

    return analysis_path

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

    roi_file_widget = global_state.get_widget("step5")
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

    channel_selection_file_widget = global_state.get_widget("step6")
    if channel_selection_file_widget:
        channel_selection_file_widget.check()
        channel_selection_file_widget.complete_step(processed_files=len(channel_selection_files))
    else:
        logger.warning("channelselection widget not found in global state.")
        raise ValueError("channelselection widget not found in global state.")

    return channel_selection_file_path

def _decomposition_results_init():
    """Initialize Step 7: Decomposition Results monitoring and load mapping state."""
    decomposition_widget = global_state.get_widget("step7")
    if decomposition_widget:
        decomposition_widget.init_file_checking()

        # Check if mapping was completed (JSON file exists and files present)
        if decomposition_widget.decomp_mapping is not None and decomposition_widget.resultfiles:
            logger.info("Step 7 state reconstructed: mapping loaded and files found")
            decomposition_widget.complete_step()
    else:
        logger.warning("decomposition widget not found in global state.")
        raise ValueError("decomposition widget not found in global state.")

def _multigrid_config():
    """Reconstruct Step 8: Multi-Grid Configuration from JSON state."""
    multigrid_widget = global_state.get_widget("step8")
    if multigrid_widget:
        multigrid_widget.init_file_checking()

        # Check if step was completed (groupings JSON exists and MUEdit files present)
        if multigrid_widget.grid_groupings is not None and multigrid_widget.is_completed():
            logger.info("Step 8 state reconstructed: groupings loaded and MUEdit files found")
            multigrid_widget.complete_step()
    else:
        logger.warning("Multi-grid configuration widget not found in global state.")
        raise ValueError("Multi-grid configuration widget not found in global state.")

def _covisi_pre_filter():
    """Reconstruct Step 9: CoVISI Pre-Filtering state."""
    covisi_pre_filter_widget = global_state.get_widget("step9")
    if covisi_pre_filter_widget:
        covisi_pre_filter_widget.init_file_checking()

        # Check if step was completed (report JSON exists)
        if covisi_pre_filter_widget.is_completed():
            logger.info("Step 9 state reconstructed: CoVISI pre-filter report found")
            covisi_pre_filter_widget.complete_step()
    else:
        logger.warning("CoVISI pre-filter widget not found in global state.")
        raise ValueError("CoVISI pre-filter widget not found in global state.")

def _muedit_cleaning():
    """Reconstruct Step 10: MUEdit Cleaning state."""
    muedit_cleaning_widget = global_state.get_widget("step10")
    if muedit_cleaning_widget:
        muedit_cleaning_widget.init_file_checking()

        # Check if edited files exist
        if muedit_cleaning_widget.is_completed():
            logger.info("Step 10 state reconstructed: edited MUEdit files found")
            muedit_cleaning_widget.complete_step()
    else:
        logger.warning("MUEdit cleaning widget not found in global state.")
        raise ValueError("MUEdit cleaning widget not found in global state.")

def _covisi_post_validation():
    """Reconstruct Step 11: CoVISI Post-Validation state."""
    covisi_post_validation_widget = global_state.get_widget("step11")
    if covisi_post_validation_widget:
        covisi_post_validation_widget.init_file_checking()

        # Check if step was completed (report JSON exists)
        if covisi_post_validation_widget.is_completed():
            logger.info("Step 11 state reconstructed: CoVISI post-validation report found")
            covisi_post_validation_widget.complete_step()
    else:
        logger.warning("CoVISI post-validation widget not found in global state.")
        raise ValueError("CoVISI post-validation widget not found in global state.")

def _final_results():
    """Reconstruct Step 12: Final Results state."""
    final_results_widget = global_state.get_widget("step12")
    if final_results_widget:
        final_results_widget.init_file_checking()

        # Check if cleaned JSON files exist in decomposition_results folder
        if final_results_widget.is_completed():
            logger.info("Step 12 state reconstructed: cleaned JSON files found in decomposition_results")
            final_results_widget.complete_step()
    else:
        logger.warning("Final results widget not found in global state.")
        raise ValueError("Final results widget not found in global state.")



