import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import scipy.io as sio
from PyQt5 import QtWidgets, QtCore

from log.log_config import logger
from logic.file_io import load_mat_file
from logic.grid import extract_grid_info
from state.global_state import global_state


class AssociationDialog(QtWidgets.QDialog):
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        logger.info("Initializing AssociationDialog with %d files", len(file_paths))
        self.file_paths = file_paths
        self.grids = []
        self.load_files()
        self.init_ui()
        self.setWindowTitle("Grid Association Tool")
        self.resize(1000, 600)

    def load_files(self):
        logger.debug("Starting file loading process")
        for fp in self.file_paths:
            try:
                logger.info("Loading file: %s", fp)
                data, time, description, sf, fn, fs = load_mat_file(fp)
                grid_info = extract_grid_info(description)

                logger.debug("Extracted %d grids from %s", len(grid_info), fn)
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
                    logger.debug("Added grid %s from %s", grid_key, fn)
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Loading Error", f"Failed to load {fp}:\n{str(e)}")

            logger.info("Total grids loaded: %d", len(self.grids))

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

        # Name input and buttons
        self.name_edit = QtWidgets.QLineEdit()
        self.add_assoc_btn = QtWidgets.QPushButton("+")
        self.add_assoc_btn.setToolTip("Save current association and add another")
        self.save_close_btn = QtWidgets.QPushButton("Save && Close")
        self.add_assoc_btn.clicked.connect(lambda: self.save_association(close_dialog=False))
        self.save_close_btn.clicked.connect(lambda: self.save_association(close_dialog=True))

        # Saved files list
        self.saved_files_list = QtWidgets.QListWidget()
        self.saved_files_list.setToolTip("Successfully saved associations")
        self.saved_files_list.setAlternatingRowColors(True)

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
        right_panel.addWidget(self.add_assoc_btn)

        # Saved files panel
        saved_panel = QtWidgets.QVBoxLayout()
        saved_panel.addWidget(QtWidgets.QLabel("Saved Associations:"))
        saved_panel.addWidget(self.saved_files_list)
        right_panel.addLayout(saved_panel)

        # Main layout
        layout.addLayout(left_panel)
        layout.addLayout(btn_panel)
        layout.addLayout(right_panel)

        # Main container
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(layout)

        # Button row
        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.save_close_btn)
        button_row.addStretch()

        # Form layout
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow("Association Name:", self.name_edit)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_row)

        self.setLayout(main_layout)

    def add_selected(self):
        selected_item = self.available_list.currentItem()
        if selected_item:
            logger.debug("Adding grid to selection: %s", selected_item.text())
            new_item = selected_item.clone()
            self.selected_list.addItem(new_item)
            logger.info("Current selection count: %d", self.selected_list.count())

    def remove_selected(self):
        current_row = self.selected_list.currentRow()
        if current_row >= 0:
            item = self.selected_list.item(current_row)
            logger.debug("Removing grid from selection: %s", item.text())
            self.selected_list.takeItem(current_row)
            logger.info("Current selection count: %d", self.selected_list.count())

    def save_association(self, close_dialog=True):
        logger.info("Starting save association process")
        selected_grids = []
        for i in range(self.selected_list.count()):
            item = self.selected_list.item(i)
            selected_grids.append(item.data(QtCore.Qt.UserRole))

        assoc_name = self.name_edit.text().strip()

        if not selected_grids and not assoc_name and close_dialog:
            logger.info("No grids or association name provided. Closing dialog.")
            self.accept()
            return

        logger.debug("Selected grids count: %d", len(selected_grids))
        if not selected_grids:
            logger.warning("Save attempted with no grids selected")
            QtWidgets.QMessageBox.warning(self, "Error", "No grids selected for association!")
            return

        if not assoc_name:
            logger.warning("Save attempted with empty association name")
            QtWidgets.QMessageBox.warning(self, "Error", "Please enter an association name!")
            return

        # Validate grid dimensions consistency (based on original grid values)
        base_rows = selected_grids[0]['rows']
        base_cols = selected_grids[0]['cols']
        for grid in selected_grids[1:]:
            if grid['rows'] != base_rows or grid['cols'] != base_cols:
                error_msg = ("Cannot associate grids with different dimensions!\n"
                             f"First grid: {base_rows}x{base_cols}\n"
                             f"Conflict grid: {grid['rows']}x{grid['cols']}")
                logger.error(error_msg)
                QtWidgets.QMessageBox.critical(self, "Dimension Error", error_msg)
                return

        # Calculate new EMG grid dimensions
        new_rows = base_rows
        new_cols_total = base_cols * len(selected_grids)
        logger.info("New combined EMG grid dimensions will be: %dx%d", new_rows, new_cols_total)

        logger.info("Processing association '%s'", assoc_name)
        try:
            # Initialize containers for EMG and reference parts.
            combined_emg_data = None
            combined_ref_data = None
            combined_emg_desc = []
            combined_ref_desc = []
            combined_grid_info = {}
            emg_current_index = 0  # For indexing EMG channels in the new grid info
            ref_current_index = 0  # For indexing reference channels in the combined reference block
            combined_time = None
            combined_sf = None

            # Precompile regex to update grid dimension string in the description.
            # This matches something like "HD10MM0804" where "10" is the scale and "0804" are dimensions.
            pattern = re.compile(r"(HD\d{2}MM)(\d{2})(\d{2})")

            for grid in selected_grids:
                logger.debug("Processing grid from file: %s", grid['file_name'])
                # Validate time and sampling frequency consistency.
                if combined_time is None:
                    combined_time = grid['time']
                    combined_sf = grid['sf']
                else:
                    if not np.array_equal(combined_time, grid['time']):
                        logger.error("Time vector mismatch detected for file: %s", grid['file_name'])
                        raise ValueError("Time vectors mismatch between selected grids!")
                    if combined_sf != grid['sf']:
                        logger.error("Sampling frequency mismatch detected for file: %s", grid['file_name'])
                        raise ValueError("Sampling frequency mismatch between selected grids!")

                # --- Extract EMG and Reference Data Separately ---
                emg_data_slice = grid['data'][:, grid['emg_indices']]
                ref_data_slice = grid['data'][:, grid['ref_indices']]
                logger.debug("Extracted %d EMG channels and %d reference channels from %s",
                             len(grid['emg_indices']), len(grid['ref_indices']), grid['file_name'])

                # --- Generate Descriptions with Updated Grid Dimensions and File Origin ---
                emg_desc_list = []
                for idx in grid['emg_indices']:
                    desc_str = extract_description(grid, idx)
                    # Replace the grid dimension part with the new dimensions
                    new_dims = f"{new_rows:02d}{new_cols_total:02d}"
                    # e.g., transforms "HD10MM0804" into "HD10MM{new_rows}{new_cols_total}"
                    updated_desc = pattern.sub(r"\g<1>" + new_dims, desc_str)
                    emg_desc = f"{updated_desc}-{Path(grid['file_path']).stem}"
                    emg_desc_list.append(emg_desc)
                logger.debug("Updated EMG descriptions for %s: %s", grid['file_name'], emg_desc_list)

                # For reference channels, we keep the old label with file origin.
                ref_desc_list = []
                for idx in grid['ref_indices']:
                    ref_desc = f"refSig-{Path(grid['file_path']).stem}-{idx + 1}"
                    ref_desc_list.append(ref_desc)
                logger.debug("Reference descriptions for %s: %s", grid['file_name'], ref_desc_list)

                # --- Combine Data from Each Grid ---
                if combined_emg_data is None:
                    combined_emg_data = emg_data_slice
                    combined_ref_data = ref_data_slice
                else:
                    combined_emg_data = np.hstack((combined_emg_data, emg_data_slice))
                    combined_ref_data = np.hstack((combined_ref_data, ref_data_slice))
                logger.debug("Combined EMG data shape now: %s", combined_emg_data.shape)
                logger.debug("Combined reference data shape now: %s", combined_ref_data.shape)

                combined_emg_desc.extend(emg_desc_list)
                combined_ref_desc.extend(ref_desc_list)

                # --- Update Grid Info for EMG Part Only ---
                grid_key = f"{grid['rows']}x{grid['cols']}"
                suffix = 1
                while grid_key in combined_grid_info:
                    grid_key = f"{grid['rows']}x{grid['cols']}_{suffix}"
                    suffix += 1
                combined_grid_info[grid_key] = {
                    "rows": grid['rows'],
                    "cols": len(emg_desc_list),  # number of EMG channels for this grid
                    "emg_indices": list(range(emg_current_index, emg_current_index + len(grid['emg_indices']))),
                    "ied_mm": grid['ied_mm'],
                    "electrodes": grid['electrodes']
                }
                logger.debug("Updated grid info for %s: %s", grid_key, combined_grid_info[grid_key])
                emg_current_index += len(grid['emg_indices'])

                # --- Update Reference Signals Info Separately ---
                if "reference_signals" not in combined_grid_info:
                    combined_grid_info["reference_signals"] = []
                combined_grid_info["reference_signals"].append({
                    "file_name": grid['file_name'],
                    "indices": list(range(ref_current_index, ref_current_index + len(grid['ref_indices'])))
                })
                logger.debug("Added reference signal info for file %s", grid['file_name'])
                ref_current_index += len(grid['ref_indices'])

            # --- Final Combination ---
            # Combine the EMG block with the appended reference block.
            combined_data = np.hstack((combined_emg_data, combined_ref_data))
            combined_description = combined_emg_desc + combined_ref_desc
            combined_description = np.array([[d] for d in combined_description], dtype=object)
            logger.debug("Final combined data shape: %s", combined_data.shape)
            logger.debug("Final combined description length: %d", len(combined_description))

            # --- Save Files ---
            workfolder = global_state.get_associated_grids_path()
            filename = format_filename(assoc_name)
            save_path = os.path.join(workfolder, filename)
            logger.info("Saving association '%s' to MAT file: %s", assoc_name, save_path)

            save_selection_to_mat(
                save_path,
                combined_data,
                combined_time,
                combined_description,
                combined_sf,
                assoc_name,
                combined_grid_info
            )
            logger.info("MAT file saved successfully at %s", save_path)

            save_association_json(save_path, assoc_name, selected_grids, combined_grid_info)
            logger.info("JSON metadata file saved successfully for association '%s'", assoc_name)

            self.saved_files_list.addItem(filename)
            global_state.associated_files.append(save_path)
            QtWidgets.QMessageBox.information(self, "Success",
                                              f"Association saved successfully!\n{filename}")

            if not close_dialog:
                self.selected_list.clear()
                self.name_edit.clear()
            else:
                logger.info("Closing association dialog for '%s'", assoc_name)
                self.accept()

        except Exception as e:
            logger.error("Failed to save association: %s", str(e), exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save association:\n{str(e)}")


def save_selection_to_mat(save_file_path, data, time, description, sampling_frequency, file_name,
                          grid_info):
    logger.debug("Saving MAT file to %s", save_file_path)
    mat_dict = {
        "Data": data,
        "Time": time,
        "Description": description,
        "SamplingFrequency": sampling_frequency
    }
    sio.savemat(save_file_path, mat_dict)
    logger.info("MAT file saved successfully: %s", save_file_path)


import json


def save_association_json(save_file_path, assoc_name, selected_grids, combined_grid_info):
    """
    Save association metadata to a JSON file.

    Parameters:
        save_file_path (str): The file path used for the .mat file.
        assoc_name (str): The name of the association.
        selected_grids (list): List of grid dictionaries with original grid info.
        combined_grid_info (dict): The combined grid info structure used in the MAT file.
    """
    metadata = {
        "association_name": assoc_name,
        "timestamp": datetime.now().isoformat(),
        "grids": [],
        "combined_grid_info": combined_grid_info
    }

    for grid in selected_grids:
        grid_data = {
            "file_name": grid['file_name'],
            "file_path": grid['file_path'],
            "rows": grid['rows'],
            "cols": grid['cols'],
            "emg_count": len(grid['emg_indices']),
            "ref_count": len(grid['ref_indices']),
            "ied_mm": grid['ied_mm'],
            "electrodes": grid['electrodes']
        }
        metadata["grids"].append(grid_data)

    # Create a JSON file path based on the .mat file path.
    json_file_path = save_file_path.replace(".mat", ".json")

    with open(json_file_path, "w") as json_file:
        json.dump(metadata, json_file, indent=4)

    logger.info("JSON metadata file saved successfully: %s", json_file_path)


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

def extract_description(grid, idx):
    # Try to extract the description string robustly.
    try:
        if isinstance(grid['description'], np.ndarray):
            if grid['description'].ndim == 2:
                desc_candidate = grid['description'][idx, 0]
            else:
                desc_candidate = grid['description'][idx]
        else:
            desc_candidate = grid['description'][idx]
        try:
            desc_str = desc_candidate.item()
        except AttributeError:
            desc_str = desc_candidate
    except Exception as e:
        logger.error("Failed to extract description for index %d in file %s: %s",
                     idx, grid['file_name'], str(e))
        desc_str = ""

    return desc_str

def format_filename(filename):
    # Replace spaces with underscores and make it lowercase
    filename = filename.replace(" ", "_").lower()

    # Sanitize the filename
    filename = sanitize_filename(filename)

    # Append a timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    return f"{filename}_{timestamp}.mat"
