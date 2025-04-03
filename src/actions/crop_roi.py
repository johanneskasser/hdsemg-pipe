from pathlib import Path
import numpy as np

from PyQt5 import QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import RangeSlider

from _log.log_config import logger
from logic.grid import load_single_grid_file


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
        self.setGeometry(100, 100, 800, 600)

        # Build reference signals map
        self.reference_signal_map = self.build_reference_signal_map()

        # Main layout for the QDialog
        layout = QtWidgets.QHBoxLayout(self)

        # Create the Matplotlib figure/canvas
        self.figure = Figure()
        # Leave extra space at bottom for the RangeSlider
        self.figure.subplots_adjust(bottom=0.25)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas, stretch=1)

        # Create a control panel layout (only for checkboxes, OK button, etc.)
        control_panel = QtWidgets.QVBoxLayout()

        # Checkbox groups for all grids
        self.checkbox_groups = {}
        self.checkboxes = {}

        for grid in self.grids:
            group_box = QtWidgets.QGroupBox(f"Grid: {grid['grid_key']}")
            vbox = QtWidgets.QVBoxLayout()
            key = grid['grid_key']
            self.checkboxes[key] = []

            ref_indices = grid['ref_indices']
            for i in range(len(ref_indices)):
                cb = QtWidgets.QCheckBox(f"Ref {i}")
                cb.setChecked(True)
                cb.stateChanged.connect(self.update_plot)
                vbox.addWidget(cb)
                self.checkboxes[key].append(cb)

            group_box.setLayout(vbox)
            control_panel.addWidget(group_box)
            self.checkbox_groups[key] = group_box

        # Add an OK button if desired
        ok_button = QtWidgets.QPushButton("OK")
        ok_button.clicked.connect(self.on_ok_pressed)
        control_panel.addWidget(ok_button)

        # Add control panel to main layout
        layout.addLayout(control_panel, stretch=0)

        # Now add a RangeSlider below the main axes (in figure coordinates)
        slider_ax = self.figure.add_axes([0.1, 0.1, 0.8, 0.03])  # [left, bottom, width, height]

        # Determine the x-limits from the data to set a nice default slider range
        x_min, x_max = self.compute_data_xrange()
        # Create the RangeSlider
        self.x_slider = RangeSlider(
            slider_ax,
            "Time Range",
            valmin=x_min,
            valmax=x_max,
            valinit=(x_min, x_max),  # initial (lower, upper)
            orientation="horizontal"
        )
        self.x_slider.on_changed(self.update_threshold_lines)

        # Initial plot
        self.update_plot()

    def compute_data_xrange(self):
        """
        Returns (x_min, x_max) to define the range of the slider based on the largest data shape.
        For example, if the longest data has N samples, x_max = N-1, x_min = 0.
        """
        max_length = 0
        for grid in self.grids:
            data = grid['data']
            if data.shape[0] > max_length:
                max_length = data.shape[0]
        return (0, max_length - 1 if max_length > 0 else 0)

    def on_ok_pressed(self):
        """
        Called when the user presses OK. We store the slider values as the selected thresholds.
        """
        lower_x, upper_x = self.x_slider.val
        self.selected_thresholds = (lower_x, upper_x)
        logger.info("User selected x-range: (%.2f, %.2f)", lower_x, upper_x)
        self.accept()

    def update_threshold_lines(self, val=None):
        """
        Updates vertical threshold lines based on the RangeSlider values.
        """
        # Remove old threshold lines
        for line in self.threshold_lines:
            try:
                line.remove()
            except Exception:
                pass
        self.threshold_lines.clear()

        lower_x, upper_x = self.x_slider.val
        # Draw new vertical lines
        line1 = self.ax.axvline(lower_x, color='red', linestyle='--', label='Lower Threshold')
        line2 = self.ax.axvline(upper_x, color='green', linestyle='--', label='Upper Threshold')
        self.threshold_lines.extend([line1, line2])

        # Redraw
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
            ref_data = self.reference_signal_map.get(key)
            if ref_data is None:
                continue

            for i, cb in enumerate(self.checkboxes[key]):
                if cb.isChecked():
                    color = colors[color_index % len(colors)]
                    # Plot the signal vs sample index
                    self.ax.plot(ref_data[:, i], label=f"{key} - Ref {i}", color=color)
                    color_index += 1

        self.ax.legend(loc='upper right')

        # Update the threshold lines with the new axis limits
        self.update_threshold_lines()
        self.canvas.draw_idle()

    def build_reference_signal_map(self):
        """
        Builds a dictionary { grid_key -> array_of_reference_signals }
        where array_of_reference_signals has shape (N, #ref_indices).
        """
        logger.debug("Building reference signal map from loaded grids")
        ref_signal_map = {}
        for grid in self.grids:
            key = grid['grid_key']
            try:
                data = grid['data']
                ref_indices = grid['ref_indices']
                # Extract columns for the reference signals
                ref_data = data[:, ref_indices]
                ref_signal_map[key] = ref_data
                logger.debug("Mapped grid '%s' with %d reference channels", key, len(ref_indices))
            except Exception as e:
                logger.error("Error processing grid '%s': %s", key, str(e), exc_info=True)
        return ref_signal_map
