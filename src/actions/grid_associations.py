import os
import re
from datetime import datetime

import numpy as np
from PyQt5 import QtWidgets, QtCore
from pathlib import Path
import scipy.io as sio
import json

from logic.file_io import load_mat_file
from logic.grid import extract_grid_info
from state.global_state import global_state


class AssociationDialog(QtWidgets.QDialog):
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        self.grids = []
        self.load_files()
        self.init_ui()
        self.setWindowTitle("Grid Association Tool")
        self.resize(800, 600)

    def load_files(self):
        for fp in self.file_paths:
            try:
                data, time, description, sf, fn, fs = load_mat_file(fp)
                grid_info = extract_grid_info(description)
                for grid_key, gi in grid_info.items():
                    self.grids.append({
                        'file_path': fp,
                        'file_name': fn,
                        'data': data,
                        'time': time,
                        'description': description,
                        'sf': sf,
                        'emg_indices': gi['indices'],
                        'ref_indices': [ref['index'] for ref in gi['reference_signals']],
                        'rows': gi['rows'],
                        'cols': gi['cols'],
                        'ied_mm': gi['ied_mm'],
                        'electrodes': gi['electrodes']
                    })
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Loading Error", f"Failed to load {fp}:\n{str(e)}")

    def init_ui(self):
        # Create list widgets
        self.available_list = QtWidgets.QListWidget()
        self.selected_list = QtWidgets.QListWidget()
        self.selected_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)

        # Populate available list
        for grid in self.grids:
            item_text = f"{grid['rows']}x{grid['cols']} Grid ({len(grid['ref_indices'])} refs) - {grid['file_name']}"
            item = QtWidgets.QListWidgetItem(item_text)
            item.setData(QtCore.Qt.UserRole, grid)
            self.available_list.addItem(item)

        # Buttons
        self.add_btn = QtWidgets.QPushButton(">>")
        self.remove_btn = QtWidgets.QPushButton("<<")
        self.add_btn.clicked.connect(self.add_selected)
        self.remove_btn.clicked.connect(self.remove_selected)

        # Name input
        self.name_edit = QtWidgets.QLineEdit()
        self.save_btn = QtWidgets.QPushButton("Save Association")
        self.save_btn.clicked.connect(self.save_association)

        # Layout
        layout = QtWidgets.QHBoxLayout()

        # Left panel
        left_panel = QtWidgets.QVBoxLayout()
        left_panel.addWidget(QtWidgets.QLabel("Available Grids:"))
        left_panel.addWidget(self.available_list)

        # Button panel
        btn_panel = QtWidgets.QVBoxLayout()
        btn_panel.addStretch()
        btn_panel.addWidget(self.add_btn)
        btn_panel.addWidget(self.remove_btn)
        btn_panel.addStretch()

        # Right panel
        right_panel = QtWidgets.QVBoxLayout()
        right_panel.addWidget(QtWidgets.QLabel("Selected Grids (Order Matters):"))
        right_panel.addWidget(self.selected_list)

        # Main layout
        layout.addLayout(left_panel)
        layout.addLayout(btn_panel)
        layout.addLayout(right_panel)

        # Main container
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(layout)

        # Form layout
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow("Association Name:", self.name_edit)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.save_btn)

        self.setLayout(main_layout)

    def add_selected(self):
        selected_item = self.available_list.currentItem()
        if selected_item:
            new_item = selected_item.clone()
            self.selected_list.addItem(new_item)

    def remove_selected(self):
        current_row = self.selected_list.currentRow()
        if current_row >= 0:
            self.selected_list.takeItem(current_row)

    def save_association(self):
        selected_grids = []
        for i in range(self.selected_list.count()):
            item = self.selected_list.item(i)
            selected_grids.append(item.data(QtCore.Qt.UserRole))

        if not selected_grids:
            QtWidgets.QMessageBox.warning(self, "Error", "No grids selected for association!")
            return

        assoc_name = self.name_edit.text().strip()
        if not assoc_name:
            QtWidgets.QMessageBox.warning(self, "Error", "Please enter an association name!")
            return

        # Initialize combined data structures
        combined_data = None
        combined_time = None
        combined_description = []
        combined_sf = None
        combined_grid_info = {}
        current_index = 0

        try:
            for grid in selected_grids:
                # Combine indices and extract data
                all_indices = grid['emg_indices'] + grid['ref_indices']
                data_slice = grid['data'][:, all_indices]

                # Update descriptions
                desc_list = []
                for idx in all_indices:
                    if idx in grid['emg_indices']:
                        desc = grid['description'][idx, 0].item()
                    else:
                        desc = f"refSig-{Path(grid['file_path']).stem}-{idx}"
                    desc_list.append(desc)

                # Handle first grid initialization
                if combined_data is None:
                    combined_data = data_slice
                    combined_time = grid['time']
                    combined_sf = grid['sf']
                else:
                    # Validate consistency
                    if not np.array_equal(combined_time, grid['time']):
                        raise ValueError("Time vectors mismatch between selected grids!")
                    if combined_sf != grid['sf']:
                        raise ValueError("Sampling frequency mismatch between selected grids!")

                    combined_data = np.hstack((combined_data, data_slice))

                # Update descriptions
                combined_description.extend(desc_list)

                # Update grid info
                grid_key = f"{grid['rows']}x{grid['cols']}"
                suffix = 1
                while grid_key in combined_grid_info:
                    grid_key = f"{grid['rows']}x{grid['cols']}_{suffix}"
                    suffix += 1

                combined_grid_info[grid_key] = {
                    "rows": grid['rows'],
                    "cols": grid['cols'],
                    "indices": list(range(current_index, current_index + len(grid['emg_indices']))),
                    "ied_mm": grid['ied_mm'],
                    "electrodes": grid['electrodes']
                }
                current_index += len(all_indices)

            # Prepare final data structures
            combined_description = np.array([[d] for d in combined_description], dtype=object)
            channel_status = [True] * combined_data.shape[1]

            # Get save path
            workfolder = global_state.get_associated_grids_path()
            save_path = os.path.join(workfolder, format_filename(assoc_name))

            # Save the combined data
            save_selection_to_mat(
                save_path,
                combined_data,
                combined_time,
                combined_description,
                combined_sf,
                channel_status,
                assoc_name,
                combined_grid_info
            )

            QtWidgets.QMessageBox.information(self, "Success", "Association saved successfully!")
            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save association:\n{str(e)}")


def save_selection_to_mat(save_file_path, data, time, description, sampling_frequency, channel_status, file_name,
                          grid_info):
    mat_dict = {
        "Data": data,
        "Time": time,
        "Description": description,
        "SamplingFrequency": sampling_frequency
    }
    sio.savemat(save_file_path, mat_dict)


def sanitize_filename(filename, replace_with="_"):
    # Define forbidden characters for Windows & Linux
    forbidden_chars = r'<>:"/\\|?*\x00-\x1F'  # Control characters and special ones
    filename = re.sub(f"[{re.escape(forbidden_chars)}]", replace_with, filename)

    # Remove leading/trailing spaces and dots
    filename = filename.strip().strip(".")

    # Ensure filename is not empty or just dots
    if not filename or filename in {".", ".."}:
        filename = "associated_grids"

    return filename


def format_filename(filename):
    # Replace spaces with underscores and make it lowercase
    filename = filename.replace(" ", "_").lower()

    # Sanitize the filename
    filename = sanitize_filename(filename)

    # Append a timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    return f"{filename}_{timestamp}.mat"
