from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QPushButton, QVBoxLayout

from actions.openfile import open_file_or_folder
from config.config_enums import Settings
from config.config_manager import config
from widgets.BaseStepWidget import BaseStepWidget


class OpenFileStepWidget(BaseStepWidget):
    fileSelected = pyqtSignal(str)

    def create_buttons(self):
        """Erstellt Buttons für das Öffnen einer Datei oder eines Ordners."""
        btn_open_file = QPushButton("Open File")
        btn_open_file.clicked.connect(lambda: self.select_file_or_folder("file"))
        self.buttons.append(btn_open_file)

        btn_open_folder = QPushButton("Open Folder")
        btn_open_folder.clicked.connect(lambda: self.select_file_or_folder("folder"))
        self.buttons.append(btn_open_folder)


    def select_file_or_folder(self, mode):
        """Datei oder Ordner auswählen und global speichern."""
        try:
            selected_path = open_file_or_folder(mode)
            if not selected_path:
                return  # Nutzer hat Abbrechen gedrückt
            self.complete_step()  # Schritt als abgeschlossen markieren
            self.fileSelected.emit(selected_path)
        except Exception as e:
            self.warn(f"Error selecting file or folder: {str(e)}")

    def check(self):
        if config.get(Settings.WORKFOLDER_PATH) is None:
            self.warn("Workfolder path is not set. Please set it in settings first.")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)
