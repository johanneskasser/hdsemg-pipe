import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal
from config.config_manager import config
from config.config_enums import ChannelSelection
from log.log_config import logger

class ChannelSelectionWorker(QThread):
    finished = pyqtSignal()  # Signal emitted when the process is completed

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        """Starts the Channel Selection application and waits for it to complete."""
        logger.info(f"Processing: {self.file_path}")

        # Get the executable path from the config
        channelselection_exe_path = config.get(key=ChannelSelection.EXECUTABLE_PATH)

        # Check if the executable path is set
        if not channelselection_exe_path:
            logger.warning("Executable path to Channel Selection app is not set!")
            return

        # Ensure the executable exists and is accessible
        if not os.path.exists(channelselection_exe_path):
            logger.error(f"Executable not found: {channelselection_exe_path}")
            return

        if not os.access(channelselection_exe_path, os.X_OK):
            logger.error(f"Executable is not accessible: {channelselection_exe_path}")
            return

        # Define the command with start parameters
        command = [channelselection_exe_path, "--inputFile", self.file_path]  # Example start parameters

        try:
            # Start the application
            logger.info(f"Starting Channel Selection app: {command}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait for the process to finish
            stdout, stderr = process.communicate()

            # Log output
            if stdout:
                logger.info(stdout.decode("utf-8"))
            if stderr:
                logger.error(stderr.decode("utf-8"))

            # Notify that processing is done
            self.finished.emit()

        except Exception as e:
            logger.error(f"Failed to start Channel Selection app: {e}")
