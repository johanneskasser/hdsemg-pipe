import os
from PyQt5.QtWidgets import (
    QDialog, QListWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QDialogButtonBox, QLabel
)
from PyQt5.QtCore import Qt
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import Styles, Colors

class MappingDialog(QDialog):
    def __init__(self, existing_mapping=None, parent=None):
        super(MappingDialog, self).__init__(parent)
        self.decomposition_folder = global_state.get_decomposition_path()
        self.channel_selection_folder = global_state.get_channel_selection_path()
        self.setWindowTitle("Map Decomposition to Channel Selection Files")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        # Initialize mapping with existing mappings if provided
        self.mapping = existing_mapping.copy() if existing_mapping else {}

        self.initUI()
        self.loadFiles()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        header_label = QLabel("Map decomposition files to their corresponding channel selection file.\n"
                              "You can map multiple decomposition files to the same channel selection file "
                              "(since channel files can contain multiple grids).")
        header_label.setStyleSheet(f"font-size: 14px; color: {Colors.TEXT_SECONDARY}; padding: 8px 0;")
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # Lists layout with labels
        lists_layout = QHBoxLayout()
        lists_layout.setSpacing(16)

        # Decomposition files column
        decomp_column = QVBoxLayout()
        decomp_label = QLabel("Decomposition Files (multi-select with Ctrl/Shift)")
        decomp_label.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_PRIMARY}; padding: 4px;")
        decomp_column.addWidget(decomp_label)

        self.decomp_list = QListWidget()
        self.decomp_list.setSelectionMode(QListWidget.ExtendedSelection)  # Allow multiple selection
        self.decomp_list.setMinimumWidth(280)
        self.decomp_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                background-color: {Colors.BG_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {Colors.BLUE_100};
                color: {Colors.BLUE_900};
            }}
            QListWidget::item:hover {{
                background-color: {Colors.GRAY_100};
            }}
        """)
        decomp_column.addWidget(self.decomp_list)
        lists_layout.addLayout(decomp_column)

        # Channel selection files column
        chan_column = QVBoxLayout()
        chan_label = QLabel("Channel Selection Files")
        chan_label.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_PRIMARY}; padding: 4px;")
        chan_column.addWidget(chan_label)

        self.chan_list = QListWidget()
        self.chan_list.setSelectionMode(QListWidget.SingleSelection)
        self.chan_list.setMinimumWidth(280)
        self.chan_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                background-color: {Colors.BG_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {Colors.BLUE_100};
                color: {Colors.BLUE_900};
            }}
            QListWidget::item:hover {{
                background-color: {Colors.GRAY_100};
            }}
        """)
        chan_column.addWidget(self.chan_list)
        lists_layout.addLayout(chan_column)

        layout.addLayout(lists_layout)

        # Add mapping button
        self.btn_add_mapping = QPushButton("➕ Add Mapping")
        self.btn_add_mapping.setStyleSheet(Styles.button_primary())
        self.btn_add_mapping.clicked.connect(self.addMapping)
        layout.addWidget(self.btn_add_mapping)

        # Current mappings table
        mappings_label = QLabel("Current Mappings")
        mappings_label.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_PRIMARY}; padding: 4px; margin-top: 8px;")
        layout.addWidget(mappings_label)

        self.mapping_table = QTableWidget(0, 2)
        self.mapping_table.setHorizontalHeaderLabels(["Decomposition File", "Channel Selection File"])
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        self.mapping_table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                background-color: {Colors.BG_PRIMARY};
            }}
            QTableWidget::item {{
                padding: 8px;
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_SECONDARY};
                padding: 8px;
                border: none;
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
                font-weight: bold;
            }}
        """)
        layout.addWidget(self.mapping_table)

        # Dialog buttons
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.button(QDialogButtonBox.Ok).setStyleSheet(Styles.button_primary())
        self.buttonBox.button(QDialogButtonBox.Cancel).setStyleSheet(Styles.button_secondary())
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

        # Load ALL channel selection files (they can be reused for multiple decomposition files)
        if os.path.exists(self.channel_selection_folder):
            for file in os.listdir(self.channel_selection_folder):
                if file.endswith(".mat"):
                    self.chan_list.addItem(file)
        else:
            QMessageBox.warning(self, "Error", "Channel Selection folder does not exist.")

    def addMapping(self):
        decomp_items = self.decomp_list.selectedItems()  # Get all selected items
        chan_item = self.chan_list.currentItem()

        if not decomp_items or not chan_item:
            QMessageBox.warning(self, "Warning", "Please select at least one decomposition file and one channel selection file.")
            return

        chan_file = chan_item.text()

        # Add mapping for each selected decomposition file
        mapped_files = []
        for decomp_item in decomp_items:
            decomp_file = decomp_item.text()

            # Prevent redundant mappings for the same decomposition file
            if decomp_file in self.mapping:
                QMessageBox.warning(self, "Warning", f"Decomposition file '{decomp_file}' is already mapped.")
                continue

            self.mapping[decomp_file] = chan_file

            row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(row)
            self.mapping_table.setItem(row, 0, QTableWidgetItem(decomp_file))
            self.mapping_table.setItem(row, 1, QTableWidgetItem(chan_file))

            mapped_files.append(decomp_file)

        # Remove mapped decomposition items from the list
        for decomp_item in decomp_items:
            if decomp_item.text() in mapped_files:
                self.decomp_list.takeItem(self.decomp_list.row(decomp_item))

        # Only remove channel file from list if ALL decomposition files are now mapped to it
        # (Allow same channel file to be mapped to multiple decomp files)
        # Note: We don't remove the channel file anymore since it can be reused

    def get_mapping(self):
        """Return the current mapping dictionary."""
        return self.mapping
