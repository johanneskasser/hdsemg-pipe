from pathlib import Path
from dataclasses import dataclass
import numpy as np
from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import RangeSlider

from hdsemg_shared.fileio.file_io import EMGFile, Grid
from hdsemg_pipe._log.log_config import logger

@dataclass
class GridData:
    """Helper to pair an EMGFile with one of its Grids."""
    emgfile: EMGFile
    grid: Grid

def _normalize_single(x):
    if isinstance(x, str):
        return x.lower()
    if isinstance(x, (list, tuple, np.ndarray)):
        return " ".join(_normalize_single(xx) for xx in x)
    return str(x).lower()

def normalize(desc):
    if isinstance(desc, np.ndarray):
        return np.array([_normalize_single(item) for item in desc])
    return _normalize_single(desc)

class CropRoiDialog(QtWidgets.QDialog):
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        logger.info("Initializing Crop ROI Dialog for %d files", len(file_paths))

        self.file_paths = file_paths
        self.grid_items: list[GridData] = []
        self.selected_thresholds = (0,0)
        self.reference_signal_map = {}
        self.threshold_lines = []

        self.load_files()
        self.init_ui()

    def load_files(self):
        """Load each file via EMGFile and collect its Grids."""
        for fp in self.file_paths:
            try:
                logger.info("Loading file: %s", fp)
                emg = EMGFile.load(fp)
                for grid in emg.grids:
                    self.grid_items.append(GridData(emgfile=emg, grid=grid))
                logger.debug("→ %d grids from %s", len(emg.grids), Path(fp).name)
            except Exception as e:
                logger.error("Failed to load %s: %s", fp, e, exc_info=True)
                QtWidgets.QMessageBox.warning(self, "Loading Error", f"Failed to load {fp}:\n{e}")

        logger.info("Total grids loaded: %d", len(self.grid_items))

    def init_ui(self):
        self.setWindowTitle("Crop Region of Interest (ROI)")
        self.resize(1200, 1000)

        # Build ref-signal map now that grid_items exists
        self.reference_signal_map = self.build_reference_signal_map()

        layout = QtWidgets.QHBoxLayout(self)

        # --- Plot area ---
        self.figure = Figure()
        self.figure.subplots_adjust(bottom=0.25)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas, stretch=1)

        # --- Control panel ---
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumWidth(400)

        panel = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(panel)
        self.checkboxes = {}

        for gd in self.grid_items:
            key = gd.grid.grid_key
            uid = gd.grid.grid_uid
            box = QtWidgets.QGroupBox(f"Grid: {key}")
            box_layout = QtWidgets.QVBoxLayout()
            self.checkboxes[uid] = []

            ref_descs = self.reference_signal_map[uid]["ref_descriptions"]
            for idx, desc in enumerate(ref_descs):
                cb = QtWidgets.QCheckBox(f"Ref {idx} – {desc}")
                cb.setChecked(idx == 0)
                cb.stateChanged.connect(self.update_plot)
                box_layout.addWidget(cb)
                self.checkboxes[uid].append(cb)

            box.setLayout(box_layout)
            vbox.addWidget(box)

        ok = QtWidgets.QPushButton("OK")
        ok.clicked.connect(self.on_ok_pressed)
        vbox.addWidget(ok)
        vbox.addStretch(1)

        scroll.setWidget(panel)
        layout.addWidget(scroll, stretch=0)

        # --- Range slider ---
        slider_ax = self.figure.add_axes([0.1, 0.1, 0.8, 0.03])
        lo, hi = self.compute_data_xrange()
        self.x_slider = RangeSlider(slider_ax, "", lo, hi, valinit=(lo, hi))
        self.x_slider.on_changed(self.update_threshold_lines)

        self.update_plot()

    def compute_data_xrange(self):
        maxlen = max((gd.emgfile.data.shape[0] for gd in self.grid_items), default=0)
        return (0, maxlen - 1 if maxlen>0 else 0)

    def on_ok_pressed(self):
        self.selected_thresholds = tuple(self.x_slider.val)
        logger.info("User selected x-range: %s", self.selected_thresholds)
        self.accept()

    def update_threshold_lines(self, _=None):
        for ln in self.threshold_lines:
            try: ln.remove()
            except: pass
        self.threshold_lines.clear()
        lo, hi = self.x_slider.val
        l1 = self.ax.axvline(lo, linestyle='--', label='Lower')
        l2 = self.ax.axvline(hi, linestyle='--', label='Upper')
        self.threshold_lines.extend([l1, l2])
        self.canvas.draw_idle()

    def update_plot(self):
        self.ax.clear()
        for gd in self.grid_items:
            uid = gd.grid.grid_uid
            ref_data = self.reference_signal_map[uid]["ref_signals"]
            for idx, cb in enumerate(self.checkboxes[uid]):
                if cb.isChecked():
                    self.ax.plot(ref_data[:, idx], label=f"{gd.grid.grid_key}-Ref{idx}")
        self.ax.legend(loc='upper right')
        self.update_threshold_lines()
        self.canvas.draw_idle()

    def build_reference_signal_map(self):
        """
        Map each grid_uid → {
            'ref_signals': 2D np.array (samples×nRefs),
            'ref_descriptions': list[str]
        }
        """
        mp = {}
        for gd in self.grid_items:
            uid = gd.grid.grid_uid
            data = gd.emgfile.data
            desc = gd.emgfile.description
            idxs = gd.grid.ref_indices or []
            if not idxs:
                # fallback to first EMG channel
                idxs = [gd.grid.emg_indices[0]] if gd.grid.emg_indices else [0]

            ref_descs = [desc[i] for i in idxs]
            # normalize to str
            ref_descs = [normalize(rd) for rd in ref_descs]
            ref_data = data[:, idxs]

            mp[uid] = {
                "ref_signals": ref_data,
                "ref_descriptions": ref_descs
            }
        return mp
