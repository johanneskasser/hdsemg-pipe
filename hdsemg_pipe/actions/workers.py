import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state

class ChannelSelectionWorker(QThread):
    finished = pyqtSignal()  # Signal emitted when the process is completed

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        """Starts the Channel Selection application and waits for it to complete."""
        logger.info(f"Processing: {self.file_path}")

        output_filepath = self.get_output_filepath()

        # Define the command with start parameters
        command = ["hdsemg-select", "--inputFile", self.file_path, "--outputFile", output_filepath]

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

    def get_output_filepath(self):
        filename = os.path.basename(self.file_path)
        workfolder = global_state.workfolder
        output_filepath = os.path.join(workfolder, "channelselection", filename)
        output_filepath = os.path.normpath(output_filepath)
        return output_filepath


