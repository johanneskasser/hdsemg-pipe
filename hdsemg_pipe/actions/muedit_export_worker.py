"""Worker thread for exporting MUEdit edited files to OpenHD-EMG format."""

from PyQt5.QtCore import QThread, pyqtSignal
from hdsemg_pipe._log.log_config import logger


class MUEditExportWorker(QThread):
    """
    Worker thread for exporting MUEdit edited MAT files to OpenHD-EMG JSON format.

    Processes edited MUEdit files asynchronously to avoid blocking the UI.
    """
    finished = pyqtSignal(str, str)  # Signals (base_name, output_path) when export completes
    error = pyqtSignal(str, str)     # Signals (base_name, error_message) on failure
    progress = pyqtSignal(int, int)  # Signals (current, total) for progress tracking

    def __init__(self, export_tasks):
        """
        Initialize the export worker.

        Args:
            export_tasks (list): List of tuples (base_name, original_json_path, edited_mat_path, output_json_path)
        """
        super().__init__()
        self.export_tasks = export_tasks

    def run(self):
        """Execute export tasks sequentially."""
        from hdsemg_pipe.actions.decomposition_export import apply_muedit_edits_to_json

        total = len(self.export_tasks)

        for idx, (base_name, original_json, edited_mat, output_json) in enumerate(self.export_tasks, 1):
            try:
                logger.info(f"Exporting {base_name} ({idx}/{total})...")

                # Emit progress
                self.progress.emit(idx, total)

                # Perform the export
                result_path = apply_muedit_edits_to_json(
                    json_in_path=original_json,
                    mat_edited_path=edited_mat,
                    json_out_path=output_json
                )

                # Emit success signal
                self.finished.emit(base_name, result_path)
                logger.info(f"Successfully exported {base_name}")

            except Exception as e:
                error_msg = f"Failed to export {base_name}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                self.error.emit(base_name, error_msg)
