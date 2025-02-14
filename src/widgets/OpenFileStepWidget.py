import os

from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import pyqtSignal

from config.config_enums import ChannelSelection
from config.config_manager import config
from widgets.BaseStepWidget import BaseStepWidget
from actions.openfile import open_mat_file_or_folder, count_mat_files
from state.global_state import global_state



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

        for button in self.buttons:
            self.layout.addWidget(button)

    def select_file_or_folder(self, mode):
        """Datei oder Ordner auswählen und global speichern."""
        selected_path = open_mat_file_or_folder(mode)
        if not selected_path:
            return  # Nutzer hat Abbrechen gedrückt
        self.fileSelected.emit(selected_path)
        self.complete_step()  # Schritt als abgeschlossen markieren

    def check(self):
        if config.get(ChannelSelection.WORKFOLDER_PATH) is None:
            self.warn("Workfolder path is not set. Please set it in settings first.")
            self.setActionButtonsEnabled(False)
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)
