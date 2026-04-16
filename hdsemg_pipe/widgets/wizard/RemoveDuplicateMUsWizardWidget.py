"""
Step 10: Remove Duplicate MUs (Within/Between Grids)

This step detects and removes duplicate motor units within and between grids using
a Python implementation of MUEdit's remduplicatesbgrids algorithm.

Users can review duplicates visually and decide which MUs to remove.
This step is optional and skippable.
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from PyQt5.QtCore import QSize, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QStyleFactory
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.decomposition_file import DecompositionFile
from hdsemg_pipe.actions.process_log import read_manual_cleaning_tool
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.widgets.GridGroupingDialog import GridGroupingDialog
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts
from hdsemg_pipe.actions.duplicate_detection import (
    remove_duplicates_from_emgfiles,
    save_cleaned_jsons,
    get_discharge_times,
)
from hdsemg_pipe.actions.duplicate_detection_openhdemg import (
    detect_duplicates_in_group as _detect_duplicates_openhdemg,
)
from hdsemg_pipe.actions.decomposition_file import ReliabilityThresholds
from hdsemg_pipe.actions.decomposition_export import create_emgfile_groups

try:
    import openhdemg.library as emg
    OPENHDEMG_AVAILABLE = True
except ImportError:
    emg = None
    OPENHDEMG_AVAILABLE = False
    logger.warning("openhdemg not available - duplicate detection will not work")


# ============================================================================
# WORKER THREAD
# ============================================================================

class DuplicateDetectionWorker(QThread):
    """Worker thread for duplicate detection."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(dict)  # detection_results
    error = pyqtSignal(str)

    def __init__(self, groups, threshold, timewindow, orientation1=180, orientation2=180, show_gui=False, parent=None):
        super().__init__(parent)
        self.groups = groups  # Output from create_emgfile_groups
        self.threshold = threshold
        self.timewindow = timewindow
        self.orientation1 = orientation1  # first file in each group
        self.orientation2 = orientation2  # second and further files
        self.show_gui = show_gui

    def run(self):
        """Run duplicate detection on all groups."""
        if not OPENHDEMG_AVAILABLE or emg is None:
            self.error.emit("openhdemg library is not available. Please install it first.")
            return

        try:
            all_results = {
                'groups': [],
                'total_duplicate_groups': 0,
                'total_mus_to_remove': 0,
                'total_files': 0
            }

            default_thresholds = ReliabilityThresholds()

            for idx, group_info in enumerate(self.groups):
                group_name = group_info['name']
                json_paths = group_info['files']

                self.progress.emit(
                    idx, len(self.groups),
                    f"Detecting duplicates in {group_name}..."
                )

                # Load JSON files and compute per-file reliability
                emgfile_list = []
                reliability_per_file = []
                for json_path in json_paths:
                    try:
                        emgfile = emg.emg_from_json(str(json_path))
                        emgfile_list.append(emgfile)
                    except Exception as e:
                        logger.error(f"Failed to load {json_path}: {e}")
                        continue

                    try:
                        from hdsemg_pipe.actions.decomposition_file import DecompositionFile
                        dec = DecompositionFile.load(json_path)
                        rel_df = dec.compute_reliability(default_thresholds)
                    except Exception as e:
                        logger.warning(f"Could not compute reliability for {json_path}: {e}")
                        rel_df = None
                    reliability_per_file.append(rel_df)

                if len(emgfile_list) == 0:
                    logger.warning(f"Group '{group_name}': No files loaded, skipping")
                    continue

                # Build per-file orientations: first file → orientation1, rest → orientation2.
                orientations = [self.orientation1] + [self.orientation2] * (len(emgfile_list) - 1)

                # Run MUAP-shape-based detection
                detection_result = _detect_duplicates_openhdemg(
                    emgfile_list,
                    reliability_per_file=reliability_per_file,
                    threshold=self.threshold,
                    timewindow=self.timewindow,
                    orientations=orientations,
                    show_gui=self.show_gui,
                )

                # Store results with file paths (for later use)
                group_result = {
                    'group_name': group_name,
                    'json_paths': [str(p) for p in json_paths],
                    'detection': detection_result,
                    'emgfiles': emgfile_list  # Keep loaded for later
                }
                all_results['groups'].append(group_result)
                all_results['total_files'] += len(json_paths)

                # Update counts
                n_dup_groups = len(detection_result['duplicate_groups'])
                all_results['total_duplicate_groups'] += n_dup_groups

                # Count MUs to remove (all duplicates except survivors)
                for dup_group in detection_result['duplicate_groups']:
                    all_results['total_mus_to_remove'] += (
                        len(dup_group['mus']) - 1
                    )

            self.finished.emit(all_results)

        except Exception as e:
            logger.exception("Detection worker failed")
            self.error.emit(f"Detection failed: {str(e)}")


# ============================================================================
# VIEW DUPLICATE DIALOG
# ============================================================================

class ViewDuplicateDialog(QDialog):
    """Dialog to view duplicate MU comparison with spike train plots."""

    def __init__(self, group_result, dup_group_idx, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate MU Comparison")
        self.resize(1000, 700)

        self.group_result = group_result
        self.dup_group = group_result['detection']['duplicate_groups'][dup_group_idx]

        self.init_ui()

    def init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Header with overlap info
        mus_str = ", ".join([f"File{f}_MU{m}" for f, m in self.dup_group['mus']])
        survivor_str = f"File{self.dup_group['survivor'][0]}_MU{self.dup_group['survivor'][1]}"

        header = QLabel(
            f"<b>Duplicate Group:</b> {mus_str}<br>"
            f"<b>Survivor:</b> {survivor_str} (best reliability)"
        )
        header.setStyleSheet(Styles.label_heading(size="lg"))
        header.setWordWrap(True)
        layout.addWidget(header)

        # Reliability table
        rel_group = QGroupBox("Reliability Scores")
        rel_layout = QVBoxLayout(rel_group)

        rel_per_mu = self.dup_group.get('reliability_per_mu', {})
        xcc_pairs = self.dup_group.get('xcc_pairs', {})

        rel_str = "<table style='border-collapse: collapse;'>"
        rel_str += (
            "<tr>"
            "<th style='padding:5px;border:1px solid #ccc;'>MU</th>"
            "<th style='padding:5px;border:1px solid #ccc;'>Reliable</th>"
            "<th style='padding:5px;border:1px solid #ccc;'>SIL</th>"
            "<th style='padding:5px;border:1px solid #ccc;'>PNR</th>"
            "<th style='padding:5px;border:1px solid #ccc;'>CoVISI (%)</th>"
            "<th style='padding:5px;border:1px solid #ccc;'>Spikes</th>"
            "</tr>"
        )
        for (f, m) in self.dup_group['mus']:
            is_survivor = (f, m) == self.dup_group['survivor']
            row_style = "background-color: #d4edda;" if is_survivor else ""
            scores = rel_per_mu.get((f, m), {})
            rel_str += f"<tr style='{row_style}'>"
            rel_str += f"<td style='padding:5px;border:1px solid #ccc;'>File{f}_MU{m}</td>"
            rel_str += f"<td style='padding:5px;border:1px solid #ccc;'>{'Yes' if scores.get('is_reliable') else 'No'}</td>"
            sil = scores.get('sil', float('nan'))
            pnr = scores.get('pnr', float('nan'))
            covisi = scores.get('covisi', float('nan'))
            n_spikes = scores.get('n_spikes', '—')
            rel_str += f"<td style='padding:5px;border:1px solid #ccc;'>{sil:.3f if isinstance(sil, float) else '—'}</td>"
            rel_str += f"<td style='padding:5px;border:1px solid #ccc;'>{pnr:.1f if isinstance(pnr, float) else '—'}</td>"
            rel_str += f"<td style='padding:5px;border:1px solid #ccc;'>{covisi:.1f if isinstance(covisi, float) else '—'}</td>"
            rel_str += f"<td style='padding:5px;border:1px solid #ccc;'>{n_spikes}</td>"
            rel_str += "</tr>"
        rel_str += "</table>"

        # XCC values between pairs in this group
        if xcc_pairs:
            mus = self.dup_group['mus']
            for fi1, mi1 in mus:
                for fi2, mi2 in mus:
                    xcc = xcc_pairs.get((fi1, mi1, fi2, mi2))
                    if xcc is not None:
                        rel_str += (
                            f"<br><small>XCC File{fi1}_MU{mi1} ↔ File{fi2}_MU{mi2}: "
                            f"<b>{xcc:.3f}</b></small>"
                        )

        rel_label = QLabel(rel_str)
        rel_label.setTextFormat(Qt.RichText)
        rel_layout.addWidget(rel_label)
        layout.addWidget(rel_group)

        # Spike train plots
        plot_group = QGroupBox("Spike Trains")
        plot_layout = QVBoxLayout(plot_group)

        # Default view: matplotlib spike trains
        self.create_spike_train_plots(plot_layout)

        layout.addWidget(plot_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(Styles.button_secondary())
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def create_spike_train_plots(self, parent_layout):
        """Create spike train raster plots using matplotlib."""
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        except ImportError:
            parent_layout.addWidget(QLabel("Matplotlib not available for plotting"))
            return

        fig = Figure(figsize=(10, 6))
        emgfiles = self.group_result['emgfiles']

        n_mus = len(self.dup_group['mus'])

        for idx, (file_idx, mu_idx) in enumerate(self.dup_group['mus']):
            ax = fig.add_subplot(n_mus, 1, idx + 1)

            # Get discharge times
            emgfile = emgfiles[file_idx]
            discharge_times = get_discharge_times(emgfile, mu_idx)

            # Plot as event plot (raster)
            ax.eventplot(discharge_times, colors='blue', linewidths=1.0)
            ax.set_ylabel(f"File{file_idx}_MU{mu_idx}", fontsize=10)
            ax.set_xlim([0, max([get_discharge_times(emgfiles[f], m).max()
                                  for f, m in self.dup_group['mus']]) + 1])

            # Highlight survivor
            if (file_idx, mu_idx) == self.dup_group['survivor']:
                ax.set_ylabel(f"File{file_idx}_MU{mu_idx} ★", fontsize=10, color='green')
                ax.spines['left'].set_color('green')
                ax.spines['left'].set_linewidth(2)

            if idx == n_mus - 1:
                ax.set_xlabel("Time (s)")
            else:
                ax.set_xticklabels([])

        fig.tight_layout()
        canvas = FigureCanvasQTAgg(fig)
        parent_layout.addWidget(canvas)


class JSONExportWorker(QThread):
    """Worker thread for exporting cleaned JSONs to MUEdit MAT format."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(int, int, list, list)  # success_count, skipped_count, output_paths, skipped_files
    error = pyqtSignal(str)

    def __init__(self, json_files, output_folder, parent=None):
        super().__init__(parent)
        self.json_files = json_files
        self.output_folder = output_folder

    def run(self):
        """Export JSON files to MAT format."""
        try:
            from hdsemg_pipe.actions.decomposition_export import export_to_muedit_mat

            os.makedirs(self.output_folder, exist_ok=True)

            success_count = 0
            skipped_count = 0
            failed_count = 0
            output_paths = []
            skipped_files = []   # Files skipped because they have 0 MUs
            failed_files = []    # Files that failed due to an error

            total = len(self.json_files)
            for idx, json_path in enumerate(self.json_files):
                filename = os.path.basename(json_path)
                self.progress.emit(idx, total, f"Exporting {filename}...")

                try:
                    output_path = export_to_muedit_mat(
                        json_load_filepath=json_path,
                        ngrid=None,
                        output_dir=self.output_folder
                    )

                    if output_path is None:
                        # export_to_muedit_mat returns None when file has 0 MUs
                        skipped_count += 1
                        skipped_files.append(filename)
                        logger.info(f"Skipped MAT export for {filename} (0 MUs)")
                    else:
                        output_paths.append(output_path)
                        success_count += 1
                        logger.info(f"Exported {filename} -> {output_path}")

                except Exception as e:
                    failed_count += 1
                    failed_files.append(filename)
                    logger.error(f"Failed to export {filename}: {e}")
                    logger.exception(f"Full error for {filename}")
                    continue

            logger.info(
                f"MAT export summary: {total} JSON files processed → "
                f"{success_count} exported, "
                f"{skipped_count} skipped (0 MUs), "
                f"{failed_count} failed"
            )
            if skipped_files:
                logger.info(f"Skipped (0 MUs): {', '.join(skipped_files)}")
            if failed_files:
                logger.warning(f"Failed exports: {', '.join(failed_files)}")

            self.finished.emit(success_count, skipped_count, output_paths, skipped_files)

        except Exception as e:
            logger.exception("Export worker failed")
            self.error.emit(f"Export failed: {str(e)}")


class PklDuplicateWorker(QThread):
    """Duplicate detection + removal for merged PKL files (scd-edition path).

    Each port in the PKL is treated as a separate "file" for the duplicate
    detection algorithm.  Identified duplicates are removed from the PKL and
    the result is saved as ``*_duplicates_removed.pkl``.
    """

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int)   # saved_count, skipped_count
    error = pyqtSignal(str)

    def __init__(self, pkl_files, output_folder, maxlag=512, jitter=0.05, tol=0.8,
                 parent=None):
        super().__init__(parent)
        self.pkl_files = pkl_files
        self.output_folder = output_folder
        self.maxlag = maxlag
        self.jitter = jitter
        self.tol = tol

    def run(self):
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            saved = 0
            skipped = 0
            total = len(self.pkl_files)

            for idx, pkl_path in enumerate(self.pkl_files):
                filename = os.path.basename(pkl_path)
                self.progress.emit(idx, total, f"Processing {filename}…")
                try:
                    decomp = DecompositionFile.load(Path(pkl_path))
                    fsamp = decomp.get_sampling_rate() or 2048.0

                    # Build per-port minimal emgfile dicts for the algorithm
                    ports = decomp._pkl.get("ports", []) if decomp._pkl else []
                    dt_list = decomp._pkl.get("discharge_times", []) if decomp._pkl else []
                    emgfile_list = []
                    for port_idx, dt_port in enumerate(dt_list):
                        emgfile_list.append({
                            "NUMBER_OF_MUS": len(dt_port),
                            "MUPULSES": [
                                __import__("numpy").asarray(dt, dtype="int64").flatten()
                                for dt in dt_port
                            ],
                            "FSAMP": fsamp,
                        })

                    if not emgfile_list or all(ef["NUMBER_OF_MUS"] == 0 for ef in emgfile_list):
                        skipped += 1
                        continue

                    results = detect_duplicates_in_group(
                        emgfile_list, maxlag=self.maxlag,
                        jitter=self.jitter, tol=self.tol, fsamp=fsamp,
                    )

                    # Map duplicate removals back to (port_idx, mu_idx) keep sets
                    mus_to_remove = set()
                    for group in results.get("duplicate_groups", []):
                        for mu in group["mus"]:
                            if mu != group["survivor"]:
                                mus_to_remove.add(mu)

                    keep_indices = {}
                    for port_idx, dt_port in enumerate(dt_list):
                        keep = {
                            mu_idx for mu_idx in range(len(dt_port))
                            if (port_idx, mu_idx) not in mus_to_remove
                        }
                        keep_indices[port_idx] = keep

                    # Build filtered DecompositionFile and save
                    filtered = DecompositionFile()
                    filtered._path = decomp._path
                    filtered._backend = "pkl"
                    filtered._pkl = decomp._pkl
                    filtered._pkl_keep_indices = keep_indices

                    stem = Path(pkl_path).stem
                    out_path = Path(self.output_folder) / f"{stem}_duplicates_removed.pkl"
                    filtered.save(out_path)
                    saved += 1
                    logger.info("Saved duplicate-removed PKL: %s", out_path.name)

                except Exception as exc:
                    logger.error("PKL duplicate processing failed for %s: %s", filename, exc)
                    skipped += 1

            self.finished.emit(saved, skipped)

        except Exception as exc:
            import traceback
            self.error.emit(f"PKL duplicate detection failed: {exc}\n{traceback.format_exc()}")


# ============================================================================
# MAIN WIDGET
# ============================================================================

class RemoveDuplicateMUsWizardWidget(WizardStepWidget):
    """
    Step 10: Remove Duplicate MUs (Within/Between Grids)

    This step:
    - Groups JSON files (by file+muscle)
    - Detects duplicates using Python algorithm
    - Shows duplicates in UI for user review
    - Lets user confirm/modify removals
    - Saves cleaned JSONs to decomposition_removed_duplicates/
    - Can be skipped
    """

    def __init__(self, parent=None):
        step_index = 10
        step_name = "Remove Duplicate MUs"
        description = "Detect and remove duplicate motor units within and between grids (optional)"

        self.json_files = []
        self.grid_groupings = {}  # {group_name: [file1, file2, ...]}
        self.detection_results = None
        self.detection_worker = None
        self.export_worker = None
        self.saved_json_paths = []  # Paths to cleaned JSONs (for export)

        super().__init__(step_index, step_name, description, parent)

        self.init_ui()
        self.check()

    def create_buttons(self):
        """Create action buttons for this step."""
        # Configure grouping button
        self.btn_configure = QPushButton("Configure Grouping")
        self.btn_configure.setStyleSheet(Styles.button_secondary())
        self.btn_configure.clicked.connect(self.open_grouping_dialog)
        self.btn_configure.setEnabled(False)
        self.buttons.append(self.btn_configure)

        # Detect duplicates button
        self.btn_detect = QPushButton("Detect Duplicates")
        self.btn_detect.setStyleSheet(Styles.button_primary())
        self.btn_detect.clicked.connect(self.start_detection)
        self.btn_detect.setEnabled(False)
        self.buttons.append(self.btn_detect)

        # Apply removals button
        self.btn_apply = QPushButton("Apply Removals and Save")
        self.btn_apply.setStyleSheet(Styles.button_primary())
        self.btn_apply.clicked.connect(self.apply_removals)
        self.btn_apply.setEnabled(False)
        self.buttons.append(self.btn_apply)

        # Skip button
        self.btn_skip = QPushButton("Skip This Step")
        self.btn_skip.setStyleSheet(Styles.button_secondary())
        self.btn_skip.setToolTip(
            "Skip duplicate detection and proceed to next step.\n"
            "All files will be exported to MUEdit as-is."
        )
        self.btn_skip.clicked.connect(self.skip_step)
        self.buttons.append(self.btn_skip)

    def init_ui(self):
        """Initialize UI components."""
        # Status panel
        self.status_group = self.create_status_panel()
        self.content_layout.addWidget(self.status_group)

        # Parameters panel
        self.params_group = self.create_parameter_panel()
        self.content_layout.addWidget(self.params_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(Styles.progress_bar())
        self.progress_bar.setVisible(False)
        self.content_layout.addWidget(self.progress_bar)

        # Results panel
        self.results_group = self.create_results_panel()
        self.content_layout.addWidget(self.results_group)

    def create_status_panel(self):
        """Create status information panel."""
        group = QGroupBox("Status")
        group.setStyleSheet(Styles.groupbox())
        layout = QVBoxLayout(group)

        self.lbl_files_found = QLabel("No files found")
        layout.addWidget(self.lbl_files_found)

        self.lbl_grouping_strategy = QLabel("Grouping: File + Muscle (default)")
        layout.addWidget(self.lbl_grouping_strategy)

        return group

    def create_parameter_panel(self):
        """Create parameter configuration panel."""
        group = QGroupBox("Detection Parameters")
        group.setStyleSheet(Styles.groupbox())

        # Use compact single-row layout
        row = QHBoxLayout(group)
        row.setSpacing(Spacing.MD)
        row.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)

        # XCC threshold
        row.addWidget(QLabel("XCC threshold:"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.5, 1.0)
        self.threshold_spin.setValue(0.9)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setFixedWidth(70)
        self.threshold_spin.setToolTip(
            "Minimum normalised 2-D cross-correlation to consider two MUs duplicates.\n"
            "openhdemg default: 0.9  (range 0–1, higher = stricter)"
        )
        row.addWidget(self.threshold_spin)

        # STA timewindow
        row.addWidget(QLabel("Timewindow:"))
        self.timewindow_spin = QSpinBox()
        self.timewindow_spin.setRange(10, 200)
        self.timewindow_spin.setValue(50)
        self.timewindow_spin.setSuffix(" ms")
        self.timewindow_spin.setFixedWidth(80)
        self.timewindow_spin.setToolTip(
            "STA timewindow used to compute MUAPs (default: 50 ms)"
        )
        row.addWidget(self.timewindow_spin)

        # Fsamp (informational)
        row.addWidget(QLabel("Fsamp:"))
        self.lbl_fsamp = QLabel("Auto")
        self.lbl_fsamp.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-style: italic;")
        self.lbl_fsamp.setMinimumWidth(80)
        row.addWidget(self.lbl_fsamp)

        # Per-file grid orientations — Grid 1 / Grid 2+
        base_tooltip = (
            "Physical mounting orientation (same as in OTBiolab+).\n"
            "180° = connector toward the user (OT Biolab default).\n"
            "0° = connector away from the user.\n"
            "Ignored when matrixcode is not a known openhdemg code."
        )
        popup_view_style = f"""
            QAbstractItemView {{
                background-color: {Colors.BG_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.BLUE_100};
                selection-color: {Colors.TEXT_PRIMARY};
                outline: none;
            }}
            QAbstractItemView::item {{
                color: {Colors.TEXT_PRIMARY};
                background-color: {Colors.BG_PRIMARY};
                padding: 4px 8px;
                min-height: 22px;
            }}
            QAbstractItemView::item:selected,
            QAbstractItemView::item:hover {{
                background-color: {Colors.BLUE_100};
                color: {Colors.TEXT_PRIMARY};
            }}
        """
        fusion = QStyleFactory.create("Fusion")
        # Widget-level stylesheet on the combo itself is required to force Qt into
        # QStyleSheetStyle mode. Without it, macOS native rendering controls the popup
        # even when Fusion style is set, making view().setStyleSheet() ineffective.
        combo_style = f"""
            QComboBox {{
                background-color: {Colors.BG_PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: 2px 6px;
                font-size: {Fonts.SIZE_BASE};
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
        """

        # Palette to force Fusion's item delegate to render dark text on white background
        # regardless of the macOS dark-mode palette.
        popup_palette = QPalette()
        popup_palette.setColor(QPalette.All, QPalette.Base, QColor(Colors.BG_PRIMARY))
        popup_palette.setColor(QPalette.All, QPalette.Text, QColor(Colors.TEXT_PRIMARY))
        popup_palette.setColor(QPalette.All, QPalette.Window, QColor(Colors.BG_PRIMARY))
        popup_palette.setColor(QPalette.All, QPalette.WindowText, QColor(Colors.TEXT_PRIMARY))
        popup_palette.setColor(QPalette.All, QPalette.Highlight, QColor(Colors.BLUE_100))
        popup_palette.setColor(QPalette.All, QPalette.HighlightedText, QColor(Colors.TEXT_PRIMARY))

        row.addWidget(QLabel("Orientation:"))
        self.orientation1_combo = QComboBox()
        if fusion:
            self.orientation1_combo.setStyle(fusion)
        self.orientation1_combo.setStyleSheet(combo_style)
        self.orientation1_combo.addItem("180°", 180)
        self.orientation1_combo.setItemData(0, QSize(80, 24), Qt.SizeHintRole)
        self.orientation1_combo.addItem("0°", 0)
        self.orientation1_combo.setItemData(1, QSize(80, 24), Qt.SizeHintRole)
        self.orientation1_combo.setMinimumWidth(70)
        self.orientation1_combo.setToolTip("Grid 1 (first file in each group).\n" + base_tooltip)
        self.orientation1_combo.view().setStyleSheet(popup_view_style)
        self.orientation1_combo.view().setPalette(popup_palette)
        row.addWidget(self.orientation1_combo)
        row.addWidget(QLabel("/"))
        self.orientation2_combo = QComboBox()
        if fusion:
            self.orientation2_combo.setStyle(fusion)
        self.orientation2_combo.setStyleSheet(combo_style)
        self.orientation2_combo.addItem("180°", 180)
        self.orientation2_combo.setItemData(0, QSize(80, 24), Qt.SizeHintRole)
        self.orientation2_combo.addItem("0°", 0)
        self.orientation2_combo.setItemData(1, QSize(80, 24), Qt.SizeHintRole)
        self.orientation2_combo.setMinimumWidth(70)
        self.orientation2_combo.setToolTip("Grid 2+ (second and further files in each group).\n" + base_tooltip)
        self.orientation2_combo.view().setStyleSheet(popup_view_style)
        self.orientation2_combo.view().setPalette(popup_palette)
        row.addWidget(self.orientation2_combo)

        # openhdemg GUI toggle
        self.chk_show_gui = QCheckBox("Show openhdemg GUI")
        self.chk_show_gui.setChecked(False)
        self.chk_show_gui.setToolTip(
            "Open the openhdemg tracking GUI after each file pair to\n"
            "visually inspect and manually confirm/reject MU pairs.\n"
            "Leave unchecked for fully automatic detection."
        )
        row.addWidget(self.chk_show_gui)

        row.addStretch()

        return group

    def create_results_panel(self):
        """Create results display panel."""
        group = QGroupBox("Detection Results")
        group.setStyleSheet(Styles.groupbox())
        group.setVisible(False)  # Hidden until detection runs
        layout = QVBoxLayout(group)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "Group", "MUs in Duplicate", "Avg XCC", "Survivor", "Action", "View"
        ])
        self.results_table.horizontalHeader().setStretchLastSection(False)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.results_table)

        # Summary label
        self.lbl_summary = QLabel("")
        layout.addWidget(self.lbl_summary)

        return group

    def check(self):
        """Check if step can be activated."""
        # Don't show errors on initial load (no workfolder set)
        if not global_state.workfolder:
            return False

        if not OPENHDEMG_AVAILABLE:
            self.error("openhdemg library is required for duplicate detection")
            return False

        # Check if previous step completed
        if not global_state.is_widget_completed("step9"):
            # CoVISI not completed - check if we have files in decomposition_auto
            if not global_state.is_widget_completed("step8"):
                self.error("Please complete decomposition step first")
                return False

        self.scan_json_files()
        return True

    def scan_json_files(self):
        """Scan for JSON files to process."""
        # Priority order:
        # 1. decomposition_covisi_filtered/ (if step 9 completed and not skipped)
        # 2. decomposition_auto/ (fallback)

        try:
            covisi_folder = global_state.get_decomposition_covisi_filtered_path()
            auto_folder = global_state.get_decomposition_path()
        except (ValueError, AttributeError):
            # Workfolder not set
            return

        source_folder = None

        # Check step 9 (CoVISI)
        if (global_state.is_widget_completed("step9") and
            covisi_folder and os.path.exists(covisi_folder)):
            # Check if actually skipped (skip marker exists)
            skip_marker = os.path.join(covisi_folder, '.skip_marker.json')
            if not os.path.exists(skip_marker):
                source_folder = covisi_folder
                logger.info("Using CoVISI-filtered files for duplicate detection")

        # Fallback to auto folder
        if source_folder is None:
            source_folder = auto_folder
            logger.info("Using decomposition_auto files for duplicate detection")

        # Scan for JSON files
        if not source_folder or not os.path.exists(source_folder):
            # Don't show error on initial load
            if global_state.workfolder:
                self.error(f"Source folder not found: {source_folder}")
            return

        state_files = {
            'decomposition_mapping.json',
            'multigrid_groupings.json',
            'covisi_pre_filter_report.json',
            'duplicate_detection_params.json',
            'duplicate_detection_report.json'
        }

        self.json_files = [
            os.path.join(source_folder, f)
            for f in os.listdir(source_folder)
            if f.endswith('.json') and f not in state_files and not f.startswith('algorithm_params')
        ]

        self.lbl_files_found.setText(f"Found {len(self.json_files)} file(s) in {Path(source_folder).name}/")

        if len(self.json_files) > 0:
            self.btn_configure.setEnabled(True)
            self.btn_detect.setEnabled(True)

            # Auto-detect fsamp from first file
            try:
                emgfile = emg.emg_from_json(self.json_files[0])
                fsamp = emgfile.get('FSAMP', 2048.0)
                self.lbl_fsamp.setText(f"{fsamp} Hz")
            except Exception as e:
                logger.warning(f"Could not auto-detect fsamp: {e}")

    def open_grouping_dialog(self):
        """Open grouping configuration dialog."""
        if len(self.json_files) == 0:
            self.error("No JSON files found")
            return

        # Use existing GridGroupingDialog
        dialog = GridGroupingDialog(
            self.json_files,
            current_groupings=self.grid_groupings,
            parent=self
        )

        if dialog.exec_() == QDialog.Accepted:
            self.grid_groupings = dialog.get_groupings()
            self.info(f"Configured {len(self.grid_groupings)} groups")
            logger.info(f"Groups configured: {list(self.grid_groupings.keys())}")

    def start_detection(self):
        """Start duplicate detection."""
        if len(self.json_files) == 0:
            self.error("No files to process")
            return

        # PKL path: route to dedicated PKL worker
        pkl_files = [f for f in self.json_files if f.endswith(".pkl")]
        if pkl_files:
            self._start_detection_pkl(pkl_files)
            return

        # Create groups
        try:
            groups = []

            # If manual groupings configured, use those
            if self.grid_groupings:
                for group_name, file_basenames in self.grid_groupings.items():
                    # Resolve basenames to full paths
                    group_files = []
                    for basename in file_basenames:
                        matching = [f for f in self.json_files if Path(f).name == basename]
                        if matching:
                            group_files.extend(matching)

                    if len(group_files) > 0:
                        groups.append({'name': group_name, 'files': group_files})
            else:
                # Auto-group by muscle name (simple strategy)
                muscle_groups = {}
                for json_file in self.json_files:
                    # Extract muscle name from filename (simplified)
                    # Pattern: ..._{muscle}.json or ..._{muscle}_covisi_filtered.json
                    stem = Path(json_file).stem
                    # Remove common suffixes
                    for suffix in ['_covisi_filtered', '_duplicates_removed']:
                        if stem.endswith(suffix):
                            stem = stem[:-len(suffix)]

                    # Extract muscle name (last part before extensions)
                    parts = stem.split('_')
                    if len(parts) >= 2:
                        muscle = parts[-1]  # Last part is typically muscle name
                        if muscle not in muscle_groups:
                            muscle_groups[muscle] = []
                        muscle_groups[muscle].append(json_file)

                # Create groups from muscle groupings
                for muscle, files in muscle_groups.items():
                    if len(files) > 0:
                        groups.append({'name': muscle, 'files': files})

            logger.info(f"Created {len(groups)} groups for detection ({len([g for g in groups if len(g['files']) >= 2])} multi-file groups)")

            # Start worker
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)

            self.btn_detect.setEnabled(False)
            self.btn_configure.setEnabled(False)

            self.detection_worker = DuplicateDetectionWorker(
                groups,
                threshold=self.threshold_spin.value(),
                timewindow=self.timewindow_spin.value(),
                orientation1=self.orientation1_combo.currentData(),
                orientation2=self.orientation2_combo.currentData(),
                show_gui=self.chk_show_gui.isChecked(),
            )

            self.detection_worker.progress.connect(self.on_detection_progress)
            self.detection_worker.finished.connect(self.on_detection_finished)
            self.detection_worker.error.connect(self.on_detection_error)
            self.detection_worker.start()

        except Exception as e:
            logger.exception("Failed to start detection")
            self.error(f"Failed to start detection: {str(e)}")

    def _start_detection_pkl(self, pkl_files):
        """Run duplicate detection + save for PKL files (scd-edition path)."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(pkl_files))
        self.btn_detect.setEnabled(False)
        self.btn_apply.setEnabled(False)

        output_folder = global_state.get_decomposition_removed_duplicates_path()
        self.pkl_dup_worker = PklDuplicateWorker(
            pkl_files, output_folder,
        )
        self.pkl_dup_worker.progress.connect(
            lambda cur, tot, msg: (self.progress_bar.setValue(cur), self.lbl_summary.setText(msg))
        )
        self.pkl_dup_worker.finished.connect(self._on_pkl_dup_finished)
        self.pkl_dup_worker.error.connect(self._on_pkl_dup_error)
        self.pkl_dup_worker.start()
        logger.info("Starting PKL duplicate detection for %d file(s)…", len(pkl_files))

    def _on_pkl_dup_finished(self, saved, skipped):
        self.progress_bar.setVisible(False)
        self.btn_detect.setEnabled(True)
        msg = f"Duplicate removal complete: {saved} PKL(s) saved"
        if skipped:
            msg += f", {skipped} skipped"
        self.success(msg)
        self.results_group.setVisible(True)
        self.lbl_summary.setText(msg)
        self.complete_step()

    def _on_pkl_dup_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.btn_detect.setEnabled(True)
        self.error(error_msg)
        self.results_group.setVisible(True)
        self.lbl_summary.setText(f"Error: {error_msg}")

    def on_detection_progress(self, current, total, message):
        """Handle detection progress updates."""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)

        self.info(message)

    def on_detection_finished(self, results):
        """Handle detection completion."""
        self.progress_bar.setVisible(False)
        self.btn_detect.setEnabled(True)
        self.btn_configure.setEnabled(True)

        self.detection_results = results

        # Check if any duplicates were found
        if results['total_duplicate_groups'] > 0:
            # Display results for user review
            self.display_results(results)
            self.btn_apply.setEnabled(True)
            self.success(f"Found {results['total_duplicate_groups']} duplicate groups")
        else:
            # No duplicates found - automatically copy files and complete step
            self.info("No duplicates found — step completed. Adjust parameters and re-run if needed.")
            self.auto_complete_no_duplicates(results)

    def auto_complete_no_duplicates(self, results):
        """Automatically complete step when no duplicates are found."""
        try:
            output_folder = global_state.get_decomposition_removed_duplicates_path()
            os.makedirs(output_folder, exist_ok=True)

            # Copy all source files to output folder
            self.saved_json_paths = []
            processed_files = set()

            for group_result in results['groups']:
                for json_path in group_result['json_paths']:
                    # Copy file to output folder (no suffix change since no duplicates removed)
                    output_path = os.path.join(output_folder, Path(json_path).name)
                    shutil.copy2(json_path, output_path)
                    self.saved_json_paths.append(output_path)
                    processed_files.add(json_path)
                    logger.info(f"Copied {Path(json_path).name} (no duplicates found)")

            # Copy any files that were NOT in groups
            for json_path in self.json_files:
                if json_path not in processed_files:
                    output_path = os.path.join(output_folder, Path(json_path).name)
                    shutil.copy2(json_path, output_path)
                    self.saved_json_paths.append(output_path)
                    logger.info(f"Copied {Path(json_path).name} (not in any group)")

            # Save detection report
            self.save_detection_report(output_folder)

            logger.info(f"Copied {len(self.saved_json_paths)} files (no duplicates + ungrouped)")

            # Suppress auto-navigation so the user stays on this step and can re-run
            self._suppress_auto_navigate = True

            # Export to MAT format for MUEdit
            self.start_export_to_muedit()

        except Exception as e:
            logger.exception("Failed to auto-complete step")
            self.error(f"Failed to auto-complete: {str(e)}")

    def on_detection_error(self, error_msg):
        """Handle detection error."""
        self.progress_bar.setVisible(False)
        self.btn_detect.setEnabled(True)
        self.btn_configure.setEnabled(True)

        self.error(error_msg)

    def display_results(self, results):
        """Display detection results in table."""
        self.results_group.setVisible(True)
        self.results_table.setRowCount(0)

        row = 0
        for group_result in results['groups']:
            for dup_group_idx, dup_group in enumerate(group_result['detection']['duplicate_groups']):
                self.results_table.insertRow(row)

                # Column 0: Group name
                self.results_table.setItem(row, 0, QTableWidgetItem(group_result['group_name']))

                # Column 1: MUs in duplicate
                mus_str = ", ".join([f"F{f}M{m}" for f, m in dup_group['mus']])
                self.results_table.setItem(row, 1, QTableWidgetItem(mus_str))

                # Column 2: Average XCC across pairs in this group
                xcc_pairs = dup_group.get('xcc_pairs', {})
                mus = dup_group['mus']
                xcc_values = []
                for fi1, mi1 in mus:
                    for fi2, mi2 in mus:
                        v = xcc_pairs.get((fi1, mi1, fi2, mi2))
                        if v is not None:
                            xcc_values.append(v)
                avg_xcc = sum(xcc_values) / len(xcc_values) if xcc_values else 0.0
                self.results_table.setItem(row, 2, QTableWidgetItem(f"{avg_xcc:.3f}"))

                # Column 3: Survivor
                survivor_str = f"F{dup_group['survivor'][0]}M{dup_group['survivor'][1]}"
                self.results_table.setItem(row, 3, QTableWidgetItem(survivor_str))

                # Column 4: Checkbox (remove or keep both)
                chk_remove = QCheckBox("Remove")
                chk_remove.setChecked(True)  # Default: remove duplicates
                chk_remove.setToolTip("Uncheck to keep all MUs in this group")
                self.results_table.setCellWidget(row, 4, chk_remove)

                # Column 5: View button
                btn_view = QPushButton("View")
                btn_view.setStyleSheet(Styles.button_secondary())
                btn_view.clicked.connect(
                    lambda checked, gr=group_result, idx=dup_group_idx: self.view_duplicate(gr, idx)
                )
                self.results_table.setCellWidget(row, 5, btn_view)

                row += 1

        # Update summary
        self.lbl_summary.setText(
            f"Summary: {results['total_duplicate_groups']} duplicate groups found in {results['total_files']} files. "
            f"Action: Remove {results['total_mus_to_remove']} MUs (checked rows), keep survivors."
        )

    def view_duplicate(self, group_result, dup_group_idx):
        """Open dialog to view duplicate comparison."""
        dialog = ViewDuplicateDialog(group_result, dup_group_idx, parent=self)
        dialog.exec_()

    def apply_removals(self):
        """Apply duplicate removals, save cleaned files, and export to MAT."""
        if self.detection_results is None:
            self.error("No detection results available")
            return

        try:
            output_folder = global_state.get_decomposition_removed_duplicates_path()
            os.makedirs(output_folder, exist_ok=True)

            # Collect removals based on checkboxes
            self.saved_json_paths = []
            processed_files = set()  # Track which files were processed

            for group_result in self.detection_results['groups']:
                # Filter duplicate groups based on checkboxes
                groups_to_remove = []

                row = 0
                for dup_group_idx, dup_group in enumerate(group_result['detection']['duplicate_groups']):
                    # Check if removal is enabled
                    chk_remove = self.results_table.cellWidget(row, 4)
                    if isinstance(chk_remove, QCheckBox) and chk_remove.isChecked():
                        groups_to_remove.append(dup_group)
                    row += 1

                # Apply removals
                cleaned_emgfiles = remove_duplicates_from_emgfiles(
                    group_result['emgfiles'],
                    groups_to_remove
                )

                # Save cleaned JSONs
                original_paths = group_result['json_paths']
                output_paths = save_cleaned_jsons(
                    cleaned_emgfiles,
                    original_paths,
                    output_folder,
                    suffix='_duplicates_removed'
                )

                self.saved_json_paths.extend(output_paths)
                # Track processed files
                for path in original_paths:
                    processed_files.add(path)

            # Copy any files that were NOT in groups (to ensure ALL files are exported)
            for json_path in self.json_files:
                if json_path not in processed_files:
                    output_path = os.path.join(output_folder, Path(json_path).name)
                    shutil.copy2(json_path, output_path)
                    self.saved_json_paths.append(output_path)
                    logger.info(f"Copied {Path(json_path).name} (not in any group)")

            # Save report
            self.save_detection_report(output_folder)

            logger.info(f"Saved {len(self.saved_json_paths)} JSON files (cleaned + ungrouped)")

            # Now export to MAT format for MUEdit
            self.start_export_to_muedit()

        except Exception as e:
            logger.exception("Failed to apply removals")
            self.error(f"Failed to apply removals: {str(e)}")

    def start_export_to_muedit(self):
        """Export cleaned JSONs to MUEdit MAT format."""
        muedit_folder = global_state.get_decomposition_muedit_path()
        os.makedirs(muedit_folder, exist_ok=True)

        logger.info(f"Starting MAT export of {len(self.saved_json_paths)} JSON files to MUEdit format...")

        # Update UI
        self.lbl_summary.setText(f"Exporting {len(self.saved_json_paths)} JSON files to MUEdit MAT format...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Disable buttons during export
        self.btn_apply.setEnabled(False)
        self.btn_detect.setEnabled(False)
        self.btn_configure.setEnabled(False)

        # Start export worker
        self.export_worker = JSONExportWorker(self.saved_json_paths, muedit_folder)
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()

    def on_export_progress(self, current, total, message):
        """Handle export progress updates."""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)
        self.lbl_summary.setText(message)

    def on_export_finished(self, success_count, skipped_count, output_paths, skipped_files):
        """Handle export completion."""
        self.progress_bar.setVisible(False)

        total_json = len(self.saved_json_paths)
        failed_count = total_json - success_count - skipped_count

        # Build a detailed breakdown for the summary label
        parts = [f"{total_json} JSON files processed"]
        parts.append(f"{success_count} MAT files exported")
        if skipped_count > 0:
            parts.append(f"{skipped_count} skipped (0 MUs — no motor units to export)")
        if failed_count > 0:
            parts.append(f"{failed_count} failed (see log)")

        summary_text = " · ".join(parts)
        self.lbl_summary.setText(summary_text)

        if skipped_count > 0:
            logger.info(
                f"Note: {skipped_count} JSON file(s) were not converted to MAT because they "
                f"contain 0 motor units. This is expected when all MUs were removed by "
                f"CoVISI filtering or duplicate removal. "
                f"Affected files: {', '.join(skipped_files)}"
            )

        # Mark step as completed
        global_state.complete_widget(f"step{self.step_index}")

        self.success(
            f"Saved {total_json} cleaned JSON files · "
            f"Exported {success_count} MAT files for MUEdit"
            + (f" · {skipped_count} skipped (0 MUs)" if skipped_count > 0 else "")
        )
        self.complete_step()

        # Re-enable detection controls so user can adjust parameters and re-run
        self.btn_detect.setEnabled(True)
        self.btn_configure.setEnabled(True)

    def on_export_error(self, error_msg):
        """Handle export errors."""
        self.progress_bar.setVisible(False)
        self.lbl_summary.setText("Export failed")
        self.error(f"Export to MUEdit failed: {error_msg}")

        # Re-enable buttons
        self.btn_apply.setEnabled(True)
        self.btn_detect.setEnabled(True)
        self.btn_configure.setEnabled(True)

    def save_detection_report(self, output_folder):
        """Save detection report to JSON."""
        report_path = os.path.join(output_folder, 'duplicate_detection_report.json')

        report = {
            'timestamp': datetime.now().isoformat(),
            'algorithm': 'openhdemg_muap_tracking',
            'parameters': {
                'xcc_threshold': self.threshold_spin.value(),
                'timewindow_ms': self.timewindow_spin.value(),
                'orientation_grid1_deg': self.orientation1_combo.currentData(),
                'orientation_grid2plus_deg': self.orientation2_combo.currentData(),
                'grouping_strategy': 'file_and_muscle'
            },
            'summary': {
                'total_files': self.detection_results['total_files'],
                'total_duplicate_groups': self.detection_results['total_duplicate_groups'],
                'total_mus_removed': self.detection_results['total_mus_to_remove']
            }
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Saved detection report: {report_path}")

    def skip_step(self):
        """Skip duplicate detection step - copy files and export to MAT."""
        try:
            output_folder = global_state.get_decomposition_removed_duplicates_path()
            os.makedirs(output_folder, exist_ok=True)

            # Save skip marker
            skip_marker_path = os.path.join(output_folder, '.skip_marker.json')
            with open(skip_marker_path, 'w') as f:
                json.dump({'skipped': True, 'reason': 'User skipped duplicate detection'}, f)

            # Copy all source files to output folder
            self.saved_json_paths = []
            for json_path in self.json_files:
                output_path = os.path.join(output_folder, Path(json_path).name)
                shutil.copy2(json_path, output_path)
                self.saved_json_paths.append(output_path)
                logger.info(f"Copied {Path(json_path).name} (step skipped)")

            logger.info(f"Copied {len(self.saved_json_paths)} files (duplicate detection skipped)")

            # Export to MAT format for MUEdit
            self.start_export_to_muedit()

        except Exception as e:
            logger.exception("Failed to skip step")
            self.error(f"Failed to skip step: {str(e)}")
