from pathlib import Path
from dataclasses import dataclass
import numpy as np
from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

from hdsemg_shared.fileio.file_io import EMGFile, Grid
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, BorderRadius, Fonts, Styles

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
        self.selected_thresholds = (0, 0)
        self.reference_signal_map = {}
        self.threshold_lines = []
        self.span_selector = None
        self.lower_threshold = 0
        self.upper_threshold = 0

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
        """Initialize modern UI with GitHub-style design."""
        self.setWindowTitle("Crop Region of Interest (ROI)")
        self.resize(1400, 800)

        # Set dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_SECONDARY};
            }}
        """)

        # Build ref-signal map now that grid_items exists
        self.reference_signal_map = self.build_reference_signal_map()

        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        main_layout.setSpacing(Spacing.LG)

        # Header with instructions
        header = QtWidgets.QLabel("Select Region of Interest")
        header.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_XXL};
                font-weight: {Fonts.WEIGHT_BOLD};
                margin-bottom: {Spacing.SM}px;
            }}
        """)

        instruction = QtWidgets.QLabel(
            "Click and drag on the plot to select the time range you want to keep. "
            "The selected region will be highlighted in light blue."
        )
        instruction.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
                margin-bottom: {Spacing.MD}px;
            }}
        """)
        instruction.setWordWrap(True)

        main_layout.addWidget(header)
        main_layout.addWidget(instruction)

        # Content area (plot + sidebar)
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(Spacing.LG)

        # --- Plot area ---
        plot_container = QtWidgets.QFrame()
        plot_container.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.LG};
                padding: {Spacing.MD}px;
            }}
        """)
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)

        self.figure = Figure(facecolor=Colors.BG_PRIMARY)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(Colors.BG_PRIMARY)
        plot_layout.addWidget(self.canvas)

        # ROI info display
        roi_info_layout = QtWidgets.QHBoxLayout()
        roi_info_layout.setSpacing(Spacing.MD)

        self.roi_start_label = QtWidgets.QLabel("Start: 0")
        self.roi_end_label = QtWidgets.QLabel("End: 0")
        self.roi_duration_label = QtWidgets.QLabel("Duration: 0 samples")

        for label in [self.roi_start_label, self.roi_end_label, self.roi_duration_label]:
            label.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.TEXT_PRIMARY};
                    font-size: {Fonts.SIZE_SM};
                    font-weight: {Fonts.WEIGHT_MEDIUM};
                    background-color: {Colors.GRAY_100};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: {BorderRadius.SM};
                    padding: {Spacing.XS}px {Spacing.SM}px;
                }}
            """)

        roi_info_layout.addWidget(self.roi_start_label)
        roi_info_layout.addWidget(self.roi_end_label)
        roi_info_layout.addWidget(self.roi_duration_label)
        roi_info_layout.addStretch()

        plot_layout.addLayout(roi_info_layout)

        content_layout.addWidget(plot_container, stretch=3)

        # --- Control panel ---
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumWidth(350)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)

        panel = QtWidgets.QWidget()
        panel.setStyleSheet(f"background-color: transparent;")
        vbox = QtWidgets.QVBoxLayout(panel)
        vbox.setSpacing(Spacing.SM)
        vbox.setContentsMargins(0, 0, 0, 0)

        # Reference signals section
        ref_header = QtWidgets.QLabel("Reference Signals")
        ref_header.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_LG};
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
                margin-bottom: {Spacing.SM}px;
            }}
        """)
        vbox.addWidget(ref_header)

        ref_hint = QtWidgets.QLabel("Select signals to display in the plot:")
        ref_hint.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
                margin-bottom: {Spacing.SM}px;
            }}
        """)
        vbox.addWidget(ref_hint)

        self.checkboxes = {}

        for gd in self.grid_items:
            key = gd.grid.grid_key
            uid = gd.grid.grid_uid
            box = QtWidgets.QGroupBox(f"Grid: {key}")
            box.setStyleSheet(Styles.groupbox())
            box_layout = QtWidgets.QVBoxLayout()
            box_layout.setSpacing(Spacing.XS)
            self.checkboxes[uid] = []

            ref_descs = self.reference_signal_map[uid]["ref_descriptions"]
            for idx, desc in enumerate(ref_descs):
                cb = QtWidgets.QCheckBox(f"Ref {idx} – {desc}")
                cb.setChecked(idx == 0)
                cb.stateChanged.connect(self.update_plot)
                cb.setStyleSheet(f"""
                    QCheckBox {{
                        color: {Colors.TEXT_PRIMARY};
                        font-size: {Fonts.SIZE_BASE};
                        spacing: {Spacing.SM}px;
                    }}
                    QCheckBox::indicator {{
                        width: 16px;
                        height: 16px;
                        border-radius: {BorderRadius.SM};
                        border: 1px solid {Colors.BORDER_DEFAULT};
                    }}
                    QCheckBox::indicator:checked {{
                        background-color: {Colors.BLUE_600};
                        border-color: {Colors.BLUE_600};
                    }}
                """)
                box_layout.addWidget(cb)
                self.checkboxes[uid].append(cb)

            box.setLayout(box_layout)
            vbox.addWidget(box)

        vbox.addStretch(1)

        # Action buttons
        btn_layout = QtWidgets.QVBoxLayout()
        btn_layout.setSpacing(Spacing.SM)

        reset_btn = QtWidgets.QPushButton("Reset Selection")
        reset_btn.setStyleSheet(Styles.button_secondary())
        reset_btn.clicked.connect(self.reset_selection)
        btn_layout.addWidget(reset_btn)

        ok_btn = QtWidgets.QPushButton("Apply & Close")
        ok_btn.setStyleSheet(Styles.button_primary())
        ok_btn.clicked.connect(self.on_ok_pressed)
        btn_layout.addWidget(ok_btn)

        vbox.addLayout(btn_layout)

        scroll.setWidget(panel)
        content_layout.addWidget(scroll, stretch=1)

        main_layout.addLayout(content_layout)

        # Initialize ROI bounds
        lo, hi = self.compute_data_xrange()
        self.lower_threshold = lo
        self.upper_threshold = hi

        # Setup interactive span selector
        self.span_selector = SpanSelector(
            self.ax,
            self.on_span_select,
            'horizontal',
            useblit=True,
            props=dict(alpha=0.3, facecolor=Colors.BLUE_500),
            interactive=True,
            drag_from_anywhere=True
        )

        self.update_plot()
        self.update_roi_info()

    def compute_data_xrange(self):
        maxlen = max((gd.emgfile.data.shape[0] for gd in self.grid_items), default=0)
        return (0, maxlen - 1 if maxlen>0 else 0)

    def on_span_select(self, xmin, xmax):
        """Called when user selects a region with the span selector."""
        self.lower_threshold = int(xmin)
        self.upper_threshold = int(xmax)
        self.update_roi_info()
        logger.debug(f"ROI selected: {self.lower_threshold} - {self.upper_threshold}")

    def update_roi_info(self):
        """Update the ROI info labels."""
        duration = self.upper_threshold - self.lower_threshold
        self.roi_start_label.setText(f"Start: {self.lower_threshold}")
        self.roi_end_label.setText(f"End: {self.upper_threshold}")
        self.roi_duration_label.setText(f"Duration: {duration} samples")

    def reset_selection(self):
        """Reset the ROI selection to full range."""
        lo, hi = self.compute_data_xrange()
        self.lower_threshold = lo
        self.upper_threshold = hi
        self.update_roi_info()

        # Remove the old span selector completely
        if self.span_selector:
            self.span_selector.set_visible(False)
            self.span_selector = None

        # Redraw the plot to remove the highlight
        self.update_plot()
        logger.info("ROI selection reset to full range")

    def on_ok_pressed(self):
        """Apply the selected ROI and close dialog."""
        self.selected_thresholds = (self.lower_threshold, self.upper_threshold)
        logger.info("User selected x-range: %s", self.selected_thresholds)
        self.accept()

    def update_plot(self):
        """Update the plot with selected reference signals."""
        self.ax.clear()
        self.ax.set_facecolor(Colors.BG_PRIMARY)

        # Plot selected signals
        for gd in self.grid_items:
            uid = gd.grid.grid_uid
            ref_data = self.reference_signal_map[uid]["ref_signals"]
            for idx, cb in enumerate(self.checkboxes[uid]):
                if cb.isChecked():
                    self.ax.plot(
                        ref_data[:, idx],
                        label=f"{gd.grid.grid_key}-Ref{idx}",
                        linewidth=1.5
                    )

        # Style the plot
        self.ax.set_xlabel("Sample Index", fontsize=12)
        self.ax.set_ylabel("Amplitude", fontsize=12)
        self.ax.legend(loc='upper right', framealpha=0.9)
        self.ax.grid(True, alpha=0.3, linestyle='--')

        # Re-create span selector after plot update
        if self.span_selector:
            self.span_selector = None
        self.span_selector = SpanSelector(
            self.ax,
            self.on_span_select,
            'horizontal',
            useblit=True,
            props=dict(alpha=0.3, facecolor=Colors.BLUE_500),
            interactive=True,
            drag_from_anywhere=True
        )

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
