import os

import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QPushButton

from hdsemg_pipe.actions.crop_roi import CropRoiDialog
from hdsemg_pipe.actions.file_utils import copy_files
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_shared.fileio.matlab_file_io import save_selection_to_mat
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe._log.log_config import logger

class DefineRoiStepWidget(BaseStepWidget):
    def __init__(self, step_index):
        """
        Initialize the DefineRoiStepWidget.

        Args:
            step_index (int): The index of the step in the workflow.
        """
        super().__init__(step_index, "Crop to Region of Interest (ROI)", "Define the region of interest for analysis.")
        self.roi_dialog = None

    def create_buttons(self):
        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(btn_skip)

        btn_roi = QPushButton("Start")
        btn_roi.clicked.connect(self.start_roi)
        self.buttons.append(btn_roi)

    def skip_step(self):
        """
        Skip the ROI definition step and copy files.
        """
        logger.debug("Skipping ROI step.")
        dest_folder = global_state.get_cropped_signal_path()
        files = global_state.associated_files
        try:
            global_state.cropped_files = copy_files(files, dest_folder)
            self.complete_step()
            return
        except Exception as e:
            logger.error(f"Failed to copy files to roi dest folder {dest_folder} with error: {str(e)}")
            self.warn("Failed to copy files. Please check the destination folder.")
            return

    def start_roi(self):
        """
        Start the ROI definition process.
        """
        logger.debug("Starting ROI definition.")
        file_paths = global_state.associated_files
        if not file_paths:
            self.warn("No files selected for ROI definition.")
            return

        # Open the CropRoiDialog.
        self.roi_dialog = CropRoiDialog(file_paths, self)
        if self.roi_dialog.exec_() != self.roi_dialog.Accepted:
            logger.info("ROI definition canceled by the user.")
            self.warn("ROI definition was canceled.")
            return

        lower_val, upper_val = self.roi_dialog.selected_thresholds
        logger.info("User selected thresholds: lower=%f, upper=%f", lower_val, upper_val)

        # Save grid data with the selected thresholds using the save_selection_to_mat function.
        dest_folder = global_state.get_cropped_signal_path()
        for grid in self.roi_dialog.grids:
            file_name = grid.get("file_name", f"{grid['grid_key']}.mat")
            save_file_path = os.path.join(dest_folder, file_name)
            if save_file_path in global_state.cropped_files:
                logger.info("File %s already processed. Skipping.", file_name)
                continue
            data = grid['data']
            description = grid.get("description", "")
            # Use the grid's sampling frequency if available; otherwise, assume 1.
            sampling_frequency = grid.get("sf", 1)
            # Create a full time vector based on the data length and sampling frequency.
            full_time = np.arange(data.shape[0]) / sampling_frequency

            # Slice the data and time vectors based on the thresholds. Lower and upper bounds are inclusive.
            roi_data = data[int(np.floor(lower_val)):int(np.ceil(upper_val)), :]
            roi_time = full_time[int(np.floor(lower_val)):int(np.ceil(upper_val))]

            save_file_path = save_selection_to_mat(save_file_path, roi_data, roi_time, description, sampling_frequency, file_name, grid)
            logger.info("Saved ROI data to %s", save_file_path)
            global_state.cropped_files.append(save_file_path)
        QtWidgets.QMessageBox.information(self, "Success: Saved ROI data", f"Saved {len(global_state.cropped_files)} files to destination folder.")
        # Mark the step as complete.
        self.complete_step()

    def check(self):
        """
        Check if the workfolder basepath is set in the configuration.

        If the basepath is not set, disable the action buttons and show a warning.
        """
        if config.get(Settings.WORKFOLDER_PATH) is None:
            self.warn("Workfolder Basepath is not set. Please set it in the Settings first to enable this step.")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)
