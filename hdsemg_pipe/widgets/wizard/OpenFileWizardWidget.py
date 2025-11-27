from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QPushButton, QMessageBox

from hdsemg_pipe.actions.openfile import open_file_or_folder
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.ui_elements.theme import Styles
from hdsemg_pipe._log.log_config import logger


class OpenFileWizardWidget(WizardStepWidget):
    """Wizard-style widget for opening files or folders."""

    fileSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(
            step_index=1,
            step_name="Open File(s)",
            description="Select the file containing your data. You can select a single file or a folder containing multiple files.",
            parent=parent
        )

    def create_buttons(self):
        """Create buttons for opening a file or folder."""
        btn_open_file = QPushButton("Open File")
        btn_open_file.setStyleSheet(Styles.button_primary())
        btn_open_file.setToolTip("Select <b>one</b> file to open.")
        btn_open_file.clicked.connect(lambda: self.select_file_or_folder("file"))
        self.buttons.append(btn_open_file)

        btn_open_folder = QPushButton("Open Folder")
        btn_open_folder.setStyleSheet(Styles.button_secondary())
        btn_open_folder.setToolTip("Select a <b>folder</b> to open. The application will search for all supported files in this folder.")
        btn_open_folder.clicked.connect(lambda: self.select_file_or_folder("folder"))
        self.buttons.append(btn_open_folder)

    def select_file_or_folder(self, mode):
        """Select file or folder and save globally."""
        try:
            selected_path = open_file_or_folder(mode)
            if not selected_path:
                return  # User pressed cancel
            self.complete_step()  # Mark step as completed
            self.fileSelected.emit(selected_path)
        except Exception as e:
            logger.error(f"Error selecting file or folder: {str(e)}", exc_info=True)
            error_message = f"Error selecting file or folder:\n{str(e)}"
            QMessageBox.warning(self, "Error", error_message)

    def check(self):
        """Check if workfolder path is set."""
        if config.get(Settings.WORKFOLDER_PATH) is None:
            self.warn("Workfolder path is not set. Please set it in settings first.")
            self.setActionButtonsEnabled(enabled=False, override=True)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(enabled=True, override=True)
