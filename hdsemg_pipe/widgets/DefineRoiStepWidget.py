import os
import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QPushButton

from hdsemg_pipe.actions.crop_roi import CropRoiDialog
from hdsemg_pipe.actions.file_utils import copy_files
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.state.global_state import global_state
from hdsemg_shared.fileio.file_io import EMGFile
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Styles

class DefineRoiStepWidget(BaseStepWidget):
    def __init__(self, step_index):
        super().__init__(step_index,
                         "Crop to Region of Interest (ROI)",
                         "Define the region of interest for analysis.")
        self.roi_dialog = None

    def create_buttons(self):
        btn_skip = QPushButton("Skip")
        btn_skip.setStyleSheet(Styles.button_secondary())
        btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(btn_skip)

        btn_roi = QPushButton("Start")
        btn_roi.setStyleSheet(Styles.button_primary())
        btn_roi.clicked.connect(self.start_roi)
        self.buttons.append(btn_roi)

    def skip_step(self):
        logger.debug("Skipping ROI step.")
        dest = global_state.get_cropped_signal_path()
        try:
            global_state.cropped_files = copy_files(global_state.line_noise_cleaned_files, dest)
            self.complete_step()
        except Exception as e:
            logger.error("Failed to copy files: %s", e)
            self.warn("Failed to copy files. Please check the destination folder.")

    def start_roi(self):
        logger.debug("Starting ROI definition.")
        files = global_state.line_noise_cleaned_files
        if not files:
            self.warn("No files selected for ROI definition.")
            return

        self.roi_dialog = CropRoiDialog(files, self)
        if self.roi_dialog.exec_() != self.roi_dialog.Accepted:
            logger.info("ROI definition canceled by the user.")
            self.warn("ROI definition was canceled.")
            return

        lower_val, upper_val = self.roi_dialog.selected_thresholds
        logger.info("User selected thresholds: lower=%.2f upper=%.2f", lower_val, upper_val)

        dest = global_state.get_cropped_signal_path()

        # Group grid_items by their source EMGFile to avoid duplicate processing
        # Each EMGFile should only be processed once, even if it contains multiple grids
        processed_files = set()

        for gd in self.roi_dialog.grid_items:
            emg: EMGFile = gd.emgfile

            # Use the EMGFile object's identity to check if we've already processed it
            emg_id = id(emg)
            if emg_id in processed_files:
                logger.debug("EMGFile already processed, skipping grid %s", gd.grid.grid_key)
                continue

            # Mark this EMGFile as processed
            processed_files.add(emg_id)

            # Get original filename from the source path
            original_filename = os.path.basename(emg.filepath) if hasattr(emg, 'filepath') and emg.filepath else None
            if not original_filename:
                # Fallback: try to get filename from the first grid's key
                original_filename = f"{gd.grid.grid_key.split('_')[0]}.mat"
                logger.warning("No filepath found in EMGFile, using fallback filename: %s", original_filename)

            out_path = os.path.join(dest, original_filename)

            if out_path in global_state.cropped_files:
                logger.info("File %s already processed. Skipping.", original_filename)
                continue

            # Build ROI slice - crop the data for ALL channels (including all grids)
            i0 = int(np.floor(lower_val))
            i1 = int(np.ceil(upper_val))
            emg.data = emg.data[i0:i1, :]
            emg.time = emg.time[i0:i1]

            # Save using low-level MATLAB saver
            # This saves the entire EMGFile with all its grids
            emg.save(out_path)
            logger.info("Saved ROI data to %s (containing %d grids)", out_path, len(emg.grids))
            global_state.cropped_files.append(out_path)

        QtWidgets.QMessageBox.information(
            self,
            "Success",
            f"Saved {len(global_state.cropped_files)} files to {dest}"
        )
        self.complete_step()

    def check(self):
        if config.get(Settings.WORKFOLDER_PATH) is None:
            self.warn("Workfolder Basepath is not set. Please set it first.")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)
