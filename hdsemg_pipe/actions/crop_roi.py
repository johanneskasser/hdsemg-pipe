from pathlib import Path

import numpy as np
from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import RangeSlider

from hdsemg_pipe._log.log_config import logger
from hdsemg_shared.grid import load_single_grid_file


def _normalize_single(x):
    # Verarbeitet Elemente rekursiv, um verschachtelte Strukturen aufzulösen
    if isinstance(x, str):
        return x.lower()
    elif isinstance(x, (list, tuple, np.ndarray)):
        parts = []
        for item in x:
            parts.append(_normalize_single(item))
        return ' '.join(parts).lower()
    else:
        return str(x).lower()

def normalize(desc):
    if isinstance(desc, np.ndarray):
        return np.array([_normalize_single(item) for item in desc])
    else:
        return _normalize_single(desc)


class CropRoiDialog(QtWidgets.QDialog):
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        logger.info("Initializing Crop ROI Dialog with %d files", len(file_paths))
        self.file_paths = file_paths
        self.grids = []
        self.selected_thresholds = None

        self.reference_signal_map = {}
        self.threshold_lines = []
        self.load_files()
        self.init_ui()

    def load_files(self):
        logger.debug("Starting file loading process")
        for fp in self.file_paths:
            try:
                logger.info("Loading file: %s", fp)
                grids = load_single_grid_file(fp)
                self.grids.extend(grids)
                logger.debug("Extracted %d grids from %s", len(grids), Path(fp).name)
                for grid in grids:
                    logger.debug("Added grid %s from %s", grid['grid_key'], grid['file_name'])
            except Exception as e:
                logger.error("Failed to load %s: %s", fp, str(e), exc_info=True)
                QtWidgets.QMessageBox.warning(self, "Loading Error", f"Failed to load {fp}:\n{str(e)}")
        logger.info("Total grids loaded: %d", len(self.grids))

    def init_ui(self):
        logger.debug("Initializing UI components")
        self.setWindowTitle("Crop Region of Interest (ROI)")
        self.setGeometry(100, 100, 1200, 1000)

        self.reference_signal_map = self.build_reference_signal_map()

        layout = QtWidgets.QHBoxLayout(self)

        self.figure = Figure()
        self.figure.subplots_adjust(bottom=0.25)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas, stretch=1)

        # --- scrollbarer Bereich für das Control Panel ---
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setMaximumWidth(400)  # Maximalbreite für das Panel

        control_panel_widget = QtWidgets.QWidget()
        control_panel = QtWidgets.QVBoxLayout(control_panel_widget)
        self.checkbox_groups = {}
        self.checkboxes = {}

        for grid in self.grids:
            key = grid['grid_key']
            uid = grid['grid_uid']
            group_box = QtWidgets.QGroupBox(f"Grid: {key}")
            vbox = QtWidgets.QVBoxLayout()
            self.checkboxes[uid] = []

            ref_signals = self.reference_signal_map.get(uid).get("ref_signals", [])
            ref_descriptions = self.reference_signal_map.get(uid).get("ref_descriptions", [])
            emg_indices = grid.get('emg_indices', [])

            # Identify force channels based on keywords in reference signal names
            force_refs = {}
            # Use transpose to iterate over columns
            for i, ref in enumerate(ref_signals.T):
                ref_name = ref_descriptions[i]
                if "requested path" in ref_name or "performed path" in ref_name:
                    force_refs[ref_name] = ref

            if ref_signals.size > 0:
                # Case 1: There are reference signals
                if force_refs:
                    # Case 1a: Force channels found - check only these
                    for i, ref in enumerate(ref_signals.T):
                        is_checked = ref_descriptions[i] in force_refs
                        cb = QtWidgets.QCheckBox(f"Ref {i} - {'Force -' if is_checked else ''} {ref_descriptions[i]}")
                        cb.setChecked(is_checked)
                        cb.stateChanged.connect(self.update_plot)
                        vbox.addWidget(cb)
                        self.checkboxes[uid].append(cb)
                else:
                    # Case 1b: No force channels - check first reference channel
                    for i, ref in enumerate(ref_signals.T):
                        cb = QtWidgets.QCheckBox(f"Ref {i} - {ref_descriptions[i]}")
                        cb.setChecked(i == 0)
                        cb.stateChanged.connect(self.update_plot)
                        vbox.addWidget(cb)
                        self.checkboxes[uid].append(cb)
            else:
                # Case 2: No reference signals - check first EMG channel
                if emg_indices:
                    cb = QtWidgets.QCheckBox("EMG Channel 0")
                    cb.setChecked(True)
                    cb.stateChanged.connect(self.update_plot)
                    vbox.addWidget(cb)
                    self.checkboxes[uid].append(cb)

            group_box.setLayout(vbox)
            control_panel.addWidget(group_box)
        control_panel.addStretch(1)
        scroll_area.setWidget(control_panel_widget)
        layout.addWidget(scroll_area)

        ok_button = QtWidgets.QPushButton("OK")
        ok_button.clicked.connect(self.on_ok_pressed)
        control_panel.addWidget(ok_button)

        layout.addLayout(control_panel, stretch=0)

        slider_ax = self.figure.add_axes([0.1, 0.1, 0.8, 0.03])
        x_min, x_max = self.compute_data_xrange()
        self.x_slider = RangeSlider(
            slider_ax,
            label="",
            valmin=x_min,
            valmax=x_max,
            valinit=(x_min, x_max),
            orientation="horizontal"
        )
        self.x_slider.on_changed(self.update_threshold_lines)

        self.update_plot()

    def compute_data_xrange(self):
        """
        Returns (x_min, x_max) based on the maximum data length of the loaded grids.
        """
        max_length = 0
        for grid in self.grids:
            data = grid['data']
            if data.shape[0] > max_length:
                max_length = data.shape[0]
        return (0, max_length - 1 if max_length > 0 else 0)

    def on_ok_pressed(self):
        """
        Called when the user presses OK. Store the slider values as the selected thresholds.
        """
        lower_x, upper_x = self.x_slider.val
        self.selected_thresholds = (lower_x, upper_x)
        logger.info("User selected x-range: (%.2f, %.2f)", lower_x, upper_x)
        self.accept()

    def update_threshold_lines(self, val=None):
        """
        Updates vertical threshold lines based on the RangeSlider values.
        """
        for line in self.threshold_lines:
            try:
                line.remove()
            except Exception:
                pass
        self.threshold_lines.clear()

        lower_x, upper_x = self.x_slider.val
        line1 = self.ax.axvline(lower_x, color='red', linestyle='--', label='Lower Threshold')
        line2 = self.ax.axvline(upper_x, color='green', linestyle='--', label='Upper Threshold')
        self.threshold_lines.extend([line1, line2])
        self.canvas.draw_idle()

    def update_plot(self):
        """
        Updates the plot with the selected reference signals.
        """
        self.ax.clear()
        colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k']
        color_index = 0

        for grid in self.grids:
            key = grid['grid_key']
            uid = grid['grid_uid']
            ref_data = self.reference_signal_map.get(uid).get("ref_signals", None)
            if ref_data is None:
                continue

            for i, cb in enumerate(self.checkboxes[uid]):
                if cb.isChecked():
                    color = colors[color_index % len(colors)]
                    self.ax.plot(ref_data[:, i], label=f"{key} - Ref {i}", color=color)
                    color_index += 1

        self.ax.legend(loc='upper right')
        self.update_threshold_lines()
        self.canvas.draw_idle()

    def build_reference_signal_map(self):
        """
        Creates a dictionary { grid_uid -> { 'ref_signals': array_of_reference_signals, 'descriptions': array_of_reference_signal_descriptions } }
        where the array has the shape (N, number_of_channels). If no reference channels are available,
        the first EMG channel is used as a fallback.
        """
        logger.debug("Building reference signal map from loaded grids")
        ref_signal_map = {}
        for grid in self.grids:
            uid = grid['grid_uid']
            try:
                data = grid['data']
                ref_indices = grid.get('ref_indices', [])
                descriptions = grid.get('description', None)
                if not ref_indices and not descriptions:
                    ref_data = data[:, 0:1]
                    ref_descriptions = []
                else:
                    ref_descriptions = normalize(descriptions[ref_indices, :])
                    ref_data = data[:, ref_indices]

                ref_signal_map[uid] = {
                    'ref_signals': ref_data,
                    'ref_descriptions': ref_descriptions
                }

                logger.debug("Mapped grid '%s' with %d reference channels", uid, len(ref_indices) if ref_indices else 1)
            except Exception as e:
                logger.error("Error processing grid '%s': %s", uid, str(e), exc_info=True)
        return ref_signal_map
