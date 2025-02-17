from PyQt5.QtWidgets import QPushButton

from config.config_enums import ChannelSelection
from state.global_state import global_state
from widgets.BaseStepWidget import BaseStepWidget
from actions.grid_associations import AssociationDialog
from config.config_manager import config


class GridAssociationWidget(BaseStepWidget):
    def __init__(self, step_index):
        super().__init__(step_index, "Grid Association", "Create Grid Associations from the current File Pool.")

    def create_buttons(self):
        """Create the buttons for the grid association"""
        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(btn_skip)

        btn_associate = QPushButton("Start")
        btn_associate.clicked.connect(self.start_association)
        self.buttons.append(btn_associate)

    def skip_step(self):
        self.complete_step()

    def start_association(self):
        files = global_state.mat_files
        dialog = AssociationDialog(files)
        dialog.exec_()

    def check(self):
        if config.get(ChannelSelection.WORKFOLDER_PATH) is None:
            self.warn("Workfolder Basepath is not set. Please set it in the Settings first to enable this step.")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)
