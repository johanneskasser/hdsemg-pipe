from PyQt5.QtWidgets import QPushButton, QLabel

from actions.file_manager import start_file_processing
from config.config_enums import Settings
from config.config_manager import config
from _log.log_config import logger
from state.global_state import global_state
from ui_elements.loadingbutton import LoadingButton
from widgets.BaseStepWidget import BaseStepWidget


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
        self.layout.addWidget(self.btn_select_channels)

    def start_processing(self):
        """Starts file processing and updates progress dynamically."""
        if not global_state.associated_files:
            logger.warning("No .mat files found.")
            return
        self.btn_select_channels.setEnabled(False)
        self.btn_select_channels.start_loading()
        self.processed_files = 0
        self.total_files = len(global_state.associated_files)
        self.update_progress(self.processed_files, self.total_files)

        start_file_processing(self)

    def update(self, path):
        """Updates the label when a file or folder is selected."""
        self.total_files = len(global_state.associated_files)
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
        if config.get(Settings.EXECUTABLE_PATH) is None:
            self.warn("Channel Selection App Executable Path is not set. Please set it in Settings first.")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)
