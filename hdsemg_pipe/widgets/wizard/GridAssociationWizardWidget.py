import os

from PyQt5.QtWidgets import QPushButton, QDialog

from hdsemg_pipe.actions.file_utils import copy_files
from hdsemg_pipe.actions.skip_marker import save_skip_marker
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.actions.grid_associations import AssociationDialog
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Styles


def check_target_directory():
    """Check if the target directory for associated grids exists and is not empty."""
    dest_folder = global_state.get_associated_grids_path()
    return os.path.isdir(dest_folder) and any(os.listdir(dest_folder))


class GridAssociationWizardWidget(WizardStepWidget):
    """Wizard widget for managing grid associations."""

    def __init__(self, parent=None):
        super().__init__(
            step_index=2,
            step_name="Grid Association",
            description="Create grid associations from the current file pool. You can skip this step if your files don't require grid associations.",
            parent=parent
        )

    def create_buttons(self):
        """Create the buttons for the grid association step."""
        btn_skip = QPushButton("Skip")
        btn_skip.setStyleSheet(Styles.button_secondary())
        btn_skip.setToolTip("Skip grid associations and copy files directly")
        btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(btn_skip)

        btn_associate = QPushButton("Start Association")
        btn_associate.setStyleSheet(Styles.button_primary())
        btn_associate.setToolTip("Open grid association dialog")
        btn_associate.clicked.connect(self.start_association)
        self.buttons.append(btn_associate)

    def skip_step(self):
        """Skip the grid association step by copying files to the destination folder."""
        dest_folder = global_state.get_associated_grids_path()
        files = global_state.get_original_files()
        try:
            global_state.associated_files = copy_files(files, dest_folder)
            # Save skip marker for state reconstruction
            save_skip_marker(dest_folder, "Grid association skipped - files copied directly")
            # Call parent skip_step to mark as skipped in GlobalState
            super().skip_step("Grid association skipped - files copied directly")
            return
        except Exception as e:
            logger.error(f"Failed to copy files to dest folder {dest_folder} with error: {str(e)}")
            self.error("Failed to complete step. Please consult logs for further information.")
            return

    def start_association(self):
        """Start the grid association process by opening the AssociationDialog."""
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
        """Check if the workfolder basepath is set in the configuration."""
        if config.get(Settings.WORKFOLDER_PATH) is None:
            self.warn("Workfolder Basepath is not set. Please set it in the Settings first to enable this step.")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)
