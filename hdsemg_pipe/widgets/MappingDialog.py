import os
from PyQt5.QtWidgets import (
    QDialog, QListWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QDialogButtonBox
)
from hdsemg_pipe.state.global_state import global_state

class MappingDialog(QDialog):
    def __init__(self, existing_mapping=None, parent=None):
        super(MappingDialog, self).__init__(parent)
        self.decomposition_folder = global_state.get_decomposition_path()
        self.channel_selection_folder = global_state.get_channel_selection_path()
        self.setWindowTitle("Mapping Decomposition and Channel Selection Files")

        # Initialize mapping with existing mappings if provided
        self.mapping = existing_mapping.copy() if existing_mapping else {}

        self.initUI()
        self.loadFiles()

    def initUI(self):
        layout = QVBoxLayout(self)

        lists_layout = QHBoxLayout()

        self.decomp_list = QListWidget()
        self.decomp_list.setSelectionMode(QListWidget.SingleSelection)
        self.decomp_list.setMinimumWidth(200)
        lists_layout.addWidget(self.decomp_list)

        self.chan_list = QListWidget()
        self.chan_list.setSelectionMode(QListWidget.SingleSelection)
        self.chan_list.setMinimumWidth(200)
        lists_layout.addWidget(self.chan_list)

        layout.addLayout(lists_layout)

        self.btn_add_mapping = QPushButton("Add Mapping")
        self.btn_add_mapping.clicked.connect(self.addMapping)
        layout.addWidget(self.btn_add_mapping)

        self.mapping_table = QTableWidget(0, 2)
        self.mapping_table.setHorizontalHeaderLabels(["Decomposition File", "Channel Selection File"])
        layout.addWidget(self.mapping_table)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

        # Populate mapping table if there is an existing mapping
        for decomp_file, chan_file in self.mapping.items():
            row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(row)
            self.mapping_table.setItem(row, 0, QTableWidgetItem(decomp_file))
            self.mapping_table.setItem(row, 1, QTableWidgetItem(chan_file))

    def loadFiles(self):
        # Load decomposition files if not already mapped
        if os.path.exists(self.decomposition_folder):
            for file in os.listdir(self.decomposition_folder):
                if (file.endswith(".mat") or file.endswith(".pkl") or file.endswith(".json")) and file not in self.mapping:
                    self.decomp_list.addItem(file)
        else:
            QMessageBox.warning(self, "Error", "Decomposition folder does not exist.")

        # Load channel selection files if not already mapped
        mapped_channel_files = set(self.mapping.values())
        if os.path.exists(self.channel_selection_folder):
            for file in os.listdir(self.channel_selection_folder):
                if file not in mapped_channel_files and file.endswith(".mat"):
                    self.chan_list.addItem(file)
        else:
            QMessageBox.warning(self, "Error", "Channel Selection folder does not exist.")

    def addMapping(self):
        decomp_item = self.decomp_list.currentItem()
        chan_item = self.chan_list.currentItem()

        if not decomp_item or not chan_item:
            QMessageBox.warning(self, "Warning", "Please select one file from each list.")
            return

        decomp_file = decomp_item.text()
        chan_file = chan_item.text()

        # Prevent redundant mappings
        if decomp_file in self.mapping:
            QMessageBox.warning(self, "Warning", "This decomposition file is already mapped.")
            return
        if chan_file in self.mapping.values():
            QMessageBox.warning(self, "Warning", "This channel selection file is already mapped.")
            return

        self.mapping[decomp_file] = chan_file

        row = self.mapping_table.rowCount()
        self.mapping_table.insertRow(row)
        self.mapping_table.setItem(row, 0, QTableWidgetItem(decomp_file))
        self.mapping_table.setItem(row, 1, QTableWidgetItem(chan_file))

        self.decomp_list.takeItem(self.decomp_list.row(decomp_item))
        self.chan_list.takeItem(self.chan_list.row(chan_item))
