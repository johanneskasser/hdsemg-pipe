import os

from PyQt5.QtWidgets import QPushButton, QDialog, QLabel

from hdsemg_pipe.actions.file_utils import copy_files
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.actions.grid_associations import AssociationDialog
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger


def check_target_directory():
    """
    Check if the target directory for associated grids exists and is not empty.

    Returns:
        bool: True if the directory exists and contains files, False otherwise.
    """
    dest_folder = global_state.get_associated_grids_path()
    return os.path.isdir(dest_folder) and any(os.listdir(dest_folder))


class GridAssociationWidget(BaseStepWidget):
    """
    Widget for managing grid associations in the application.

    Attributes:
        info_label (QLabel): Label displaying information to the user.
    """

    def __init__(self, step_index):
        """
        Initialize the GridAssociationWidget.

        Args:
            step_index (int): The index of the step in the workflow.
        """
        super().__init__(step_index, "Grid Association", "Create Grid Associations from the current File Pool.")

    def create_buttons(self):
        """
        Create the buttons for the grid association step.
        """
        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(btn_skip)

        btn_associate = QPushButton("Start")
        btn_associate.clicked.connect(self.start_association)
        self.buttons.append(btn_associate)

    def skip_step(self):
        """
        Skip the grid association step by copying files to the destination folder.
        """
        dest_folder = global_state.get_associated_grids_path()
        files = global_state.get_original_files()
        try:
            global_state.associated_files = copy_files(files, dest_folder)
            self.complete_step()
            return
        except Exception as e:
            logger.error(f"Failed to copy files to dest folder {dest_folder} with error: {str(e)}")
            self.error("Failed to complete step. Please consult logs for further information.")
            return

    def start_association(self):
        """
        Start the grid association process by opening the AssociationDialog.
        """
        files = global_state.get_original_files()
        dialog = AssociationDialog(files)
        if dialog.exec_() == QDialog.Accepted:
            if check_target_directory():
                self.complete_step()
            else:
                self.warn(
                    "No files have been generated in this step. Please make sure to either generate Grid Associations or press \"Skip\"")
        else:
            self.error("Failed to complete step. Please consult logs for further information.")

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