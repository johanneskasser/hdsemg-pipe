from PyQt5.QtWidgets import QMessageBox

from hdsemg_pipe.actions.file_manager import start_file_processing
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.loadingbutton import LoadingButton
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget


class ChannelSelectionStepWidget(BaseStepWidget):
    def __init__(self, step_index):
        """Step 2: Channel selection from the loaded .mat files."""
        super().__init__(step_index, "Channel Selection", "Select the channels to be processed.")
        self.processed_files = 0
        self.total_files = 0
        self.additional_information_label.setText("0/0")

    def create_buttons(self):
        """Creates the button for channel selection."""
        self.btn_select_channels = LoadingButton("Select Channels")
        self.btn_select_channels.clicked.connect(self.start_processing)
        self.buttons.append(self.btn_select_channels)
        self.main_layout.addWidget(self.btn_select_channels)

    def start_processing(self):
        """Starts file processing and updates progress dynamically."""
        if not global_state.cropped_files:
            logger.warning("No .mat files found.")
            return
        if not config.get(Settings.HDSEMG_SELECT_INSTALLED):
            QMessageBox.information(self, "Warning", "hdsemg-select is not installed. Please install it in settings first.", QMessageBox.Ok)
            self.setActionButtonsEnabled(False)
            return
        logger.debug("Starting channel selection processing.")
        self.btn_select_channels.setEnabled(False)
        self.btn_select_channels.start_loading()
        self.processed_files = 0
        self.total_files = len(global_state.cropped_files)
        self.update_progress(self.processed_files, self.total_files)

        start_file_processing(self)

    def update(self, path):
        """Updates the label when a file or folder is selected."""
        self.total_files = len(global_state.cropped_files)
        self.update_progress(self.processed_files, self.total_files)
        if self.total_files != 0:
            self.setActionButtonsEnabled(True)

    def update_progress(self, processed, total):
        """Updates the progress display dynamically."""
        # Update progress label
        self.additional_information_label.setText(f"{processed}/{total}")

        # Mark step as complete when all files are processed
        if processed >= total > 0:
            self.btn_select_channels.stop_loading()
            self.complete_step()

    def check(self):
        if config.get(Settings.HDSEMG_SELECT_INSTALLED) is False:
            self.warn("hdsemg-select is not installed. Please install it to proceed (see Settings).")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)

    def complete_step(self, processed_files: int | None = None):
        # refresh counts
        self.total_files = len(global_state.channel_selection_files)
        self.processed_files = processed_files if processed_files is not None else self.total_files

        # update the label *inline*
        self.additional_information_label.setText(f"{self.processed_files}/{self.total_files}")

        # make sure the loading spinner is off
        self.btn_select_channels.stop_loading()

        # mark the step as complete (signals, styling, etc.)
        super().complete_step()
