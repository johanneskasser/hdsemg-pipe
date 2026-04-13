"""
Step 10: MUEdit Manual Cleaning (Wizard Version)

This step launches MUEdit for manual cleaning of decomposition results
and monitors progress.
"""
import os
import re
import subprocess
from PyQt5.QtCore import QFileSystemWatcher, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QPushButton, QLabel, QVBoxLayout, QFrame, QScrollArea,
    QWidget, QProgressBar
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.widgets.MUEditInstructionDialog import MUEditInstructionDialog
from hdsemg_pipe.config.config_enums import Settings, MUEditLaunchMethod
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts
from hdsemg_pipe.actions.process_log import (
    read_manual_cleaning_tool,
    read_process_log,
    write_manual_cleaning_tool,
)

_GRID_KEY_RE = re.compile(r'\d+mm_\d+x\d+(?:_\d+)?')


class MUFileScanWorker(QThread):
    """Worker thread for scanning MUEdit files and checking for motor units."""

    scan_complete = pyqtSignal(list, dict)  # (valid_files, mu_check_cache)

    def __init__(self, muedit_folder_path, parent=None):
        super().__init__(parent)
        self.muedit_folder_path = muedit_folder_path

    def run(self):
        """Scan decomposition_muedit/ and check which files have motor units."""
        import h5py
        import scipy.io as sio

        valid_files = []
        mu_check_cache = {}

        if self.muedit_folder_path and os.path.exists(self.muedit_folder_path):
            for file in os.listdir(self.muedit_folder_path):
                if file.endswith('_muedit.mat'):
                    full_path = os.path.join(self.muedit_folder_path, file)
                    has_mus = self._check_motor_units(full_path, h5py, sio)
                    mu_check_cache[full_path] = has_mus
                    if has_mus:
                        valid_files.append(full_path)
                    else:
                        logger.info(f"Skipping {file} - no motor units found")

        self.scan_complete.emit(valid_files, mu_check_cache)

    def _check_motor_units(self, mat_path, h5py, sio):
        """Check if a MUedit MAT file contains motor units."""
        try:
            # Try loading with scipy.io first (older MAT format)
            try:
                mat_data = sio.loadmat(mat_path, squeeze_me=True, struct_as_record=False)
                signal = mat_data.get('signal')
                if signal is not None:
                    discharge_times = getattr(signal, 'Dischargetimes', None)
                    if discharge_times is not None:
                        if hasattr(discharge_times, '__len__'):
                            return len(discharge_times) > 0
                        return True
                return False
            except NotImplementedError:
                pass

            # Load with h5py for HDF5/v7.3 format
            with h5py.File(mat_path, 'r') as f:
                if 'signal' in f:
                    signal_group = f['signal']
                    if 'Dischargetimes' in signal_group:
                        discharge_times = signal_group['Dischargetimes']
                        if discharge_times.size > 0:
                            if discharge_times.ndim == 2:
                                n_grids, n_mus = discharge_times.shape
                                if n_mus > 0:
                                    for mu_idx in range(n_mus):
                                        ref = discharge_times[0, mu_idx]
                                        if isinstance(ref, h5py.Reference):
                                            data = f[ref]
                                            if data.size > 0:
                                                return True
                                        elif ref.size > 0:
                                            return True
                                return False
                            return True

                if 'edition' in f:
                    edition_group = f['edition']
                    if 'Distimeclean' in edition_group:
                        distimeclean = edition_group['Distimeclean']
                        if distimeclean.size > 0:
                            return True

            return False

        except Exception as e:
            logger.warning(f"Could not check motor units in {os.path.basename(mat_path)}: {e}")
            return True


class JSONExportWorker(QThread):
    """Worker thread for exporting JSON files to MUEdit MAT format."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(int, list)  # success_count, output_paths
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
            output_paths = []

            for idx, json_path in enumerate(self.json_files):
                filename = os.path.basename(json_path)
                self.progress.emit(idx, len(self.json_files), f"Exporting {filename}...")

                try:
                    # Export JSON file to MAT (function loads JSON internally)
                    output_path = export_to_muedit_mat(
                        json_load_filepath=json_path,
                        ngrid=None,  # Single-grid export
                        output_dir=self.output_folder
                    )
                    output_paths.append(output_path)
                    success_count += 1
                    logger.info(f"Exported {filename} to {output_path}")

                except Exception as e:
                    logger.error(f"Failed to export {filename}: {e}")
                    logger.exception(f"Full error for {filename}")
                    continue

            self.finished.emit(success_count, output_paths)

        except Exception as e:
            logger.exception("Export worker failed")
            self.error.emit(f"Export failed: {str(e)}")


class ScdEditionWorker(QThread):
    """Worker thread for sequential scd-edition manual cleaning of PKL files."""

    progress = pyqtSignal(int, int, str)   # current, total, message
    file_done = pyqtSignal(str)            # path of successfully produced _edited.pkl
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, pkl_files, parent=None):
        super().__init__(parent)
        self.pkl_files = list(pkl_files)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.pkl_files)
        done = 0
        try:
            for pkl_path in self.pkl_files:
                if self._cancelled:
                    break
                stem = os.path.splitext(os.path.basename(pkl_path))[0]
                output_path = os.path.join(os.path.dirname(pkl_path), f"{stem}_edited.pkl")
                if os.path.exists(output_path):
                    done += 1
                    self.file_done.emit(output_path)
                    self.progress.emit(done, total, f"Already edited: {stem}")
                    continue
                self.progress.emit(done, total, f"Editing: {stem}...")
                proc = subprocess.Popen([
                    "scd-edition",
                    "--open", pkl_path,
                    "--output", output_path,
                    "--quit-after-save",
                ])
                proc.wait()
                if os.path.exists(output_path):
                    done += 1
                    self.file_done.emit(output_path)
                    self.progress.emit(done, total, f"Done: {stem}")
                else:
                    logger.warning("scd-edition closed without saving: %s", pkl_path)
        except Exception as e:
            logger.exception("ScdEditionWorker failed")
            self.error.emit(str(e))
        self.finished.emit()


class _PklMergeWorker(QThread):
    """Upgrade old-format PKLs then merge single-grid PKLs into multi-port PKLs.

    Thin wrapper around detect_and_upgrade_pkl and merge_grid_pkls.
    Emits ``finished`` with the list of merged PKL paths on success.
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, decomp_auto_path: str, channelselection_path: str, parent=None):
        super().__init__(parent)
        self.decomp_auto_path = decomp_auto_path
        self.channelselection_path = channelselection_path

    def run(self):
        try:
            from pathlib import Path as _Path
            from hdsemg_pipe.scd_utils import detect_and_upgrade_pkl, merge_grid_pkls

            target = _Path(self.decomp_auto_path)
            channelselection = _Path(self.channelselection_path)

            self.progress.emit("Checking PKL format compatibility…")
            detect_and_upgrade_pkl.process_path(target)

            self.progress.emit("Merging single-grid PKLs into multi-port files…")
            mat_dirs = [str(channelselection)] if channelselection.is_dir() else []
            merge_grid_pkls.process(target=target, out_dir=target, mat_dirs=mat_dirs)

            merged = [
                str(p) for p in sorted(target.glob("*.pkl"))
                if not p.name.endswith(".bak")
                and not _GRID_KEY_RE.search(p.stem)
                and not p.stem.endswith("_edited")
            ]
            self.finished.emit(merged)
        except Exception as exc:
            import traceback
            logger.error("PKL merge failed: %s\n%s", exc, traceback.format_exc())
            self.error.emit(str(exc))


class MUEditCleaningWizardWidget(WizardStepWidget):
    """
    Step 10: Manual cleaning with MUEdit.

    This step:
    - Launches MUEdit for manual cleaning
    - Shows instruction dialog
    - Monitors edited files with FileSystemWatcher
    - Tracks progress for each file
    - Completes when all files are edited
    """

    def __init__(self, parent=None):
        # Hardcoded step configuration
        step_index = 11
        step_name = "MUEdit Manual Cleaning"
        description = "Launch MUEdit for manual cleaning and quality control of motor unit decomposition results."

        super().__init__(step_index, step_name, description, parent)

        self.expected_folder = None
        self.muedit_folder = None
        self.muedit_files = []
        self.edited_files = []
        self.skipped_files = {}  # Dict: file_path -> skip_reason
        self.last_file_count = 0

        # Cache for motor unit checks (to avoid re-scanning files every time).
        # None = never populated; {} = populated but no files with MUs found.
        self.mu_check_cache = None
        self.scan_worker = None
        self.is_scanning = False
        self.indexing_needed = False  # Flag to track if manual indexing is needed

        # Export-related
        self.json_files = []
        self.export_worker = None
        self.export_completed = False

        # scd-edition path state
        self.pkl_files = []
        self.edited_pkl_files = []
        self.scd_worker = None
        self.pkl_merge_worker = None
        self._use_pkl = False

        # Loading animation timer
        self.loading_animation_timer = QTimer(self)
        self.loading_animation_timer.timeout.connect(self._update_loading_animation)
        self.loading_dots = 0

        # Initialize file system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._poll_scan)

        # Add polling timer for reliable file detection (QFileSystemWatcher can miss events on Windows)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_scan)
        self.poll_timer.setInterval(2000)  # Check every 2 seconds

        # Create status UI
        self.create_status_ui()
        self.content_layout.addWidget(self.status_container)

        # Perform initial check
        self.check()

    def create_status_ui(self):
        """Create compact status UI with progress tracking."""
        self.status_container = QFrame()
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setSpacing(Spacing.SM)
        status_layout.setContentsMargins(0, 0, 0, 0)

        # Button to manually trigger motor unit indexing (hidden by default)
        self.btn_index_motor_units = QPushButton("⚡ Index Motor Units")
        self.btn_index_motor_units.setStyleSheet(Styles.button_secondary())
        self.btn_index_motor_units.setToolTip(
            "Scan MUEdit files and check which ones contain motor units.\n"
            "This helps identify files that can be skipped."
        )
        self.btn_index_motor_units.clicked.connect(self._trigger_manual_indexing)
        self.btn_index_motor_units.setVisible(False)
        status_layout.addWidget(self.btn_index_motor_units)

        # Loading indicator (hidden by default)
        self.loading_label = QLabel("Scanning files and checking for motor units...")
        self.loading_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
                font-style: italic;
                padding: {Spacing.SM}px;
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
            }}
        """)
        self.loading_label.setVisible(False)
        status_layout.addWidget(self.loading_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                text-align: center;
                height: 24px;
                background-color: {Colors.BG_SECONDARY};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.GREEN_600};
                border-radius: {BorderRadius.SM};
            }}
        """)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        # File status list (compact, scrollable)
        self.file_status_scroll = QScrollArea()
        self.file_status_scroll.setWidgetResizable(True)
        self.file_status_scroll.setMaximumHeight(150)
        self.file_status_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                background-color: {Colors.BG_SECONDARY};
            }}
        """)

        self.file_status_widget = QWidget()
        self.file_status_layout = QVBoxLayout(self.file_status_widget)
        self.file_status_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        self.file_status_layout.setSpacing(Spacing.XS)
        self.file_status_scroll.setWidget(self.file_status_widget)

        status_layout.addWidget(self.file_status_scroll)

    def create_buttons(self):
        """Create buttons for this step."""
        self.btn_launch_muedit = QPushButton("Edit with MUedit")
        self.btn_launch_muedit.setStyleSheet(Styles.button_primary())
        self.btn_launch_muedit.setToolTip("Launch MUEdit (MATLAB-based) for manual cleaning")
        self.btn_launch_muedit.clicked.connect(self._on_choose_muedit)
        self.btn_launch_muedit.setEnabled(False)
        self.buttons.append(self.btn_launch_muedit)

        self.btn_launch_scd = QPushButton("Edit with scd-edition")
        self.btn_launch_scd.setStyleSheet(Styles.button_secondary())
        self.btn_launch_scd.setToolTip("Launch scd-edition (Python-native) for manual cleaning")
        self.btn_launch_scd.clicked.connect(self._on_choose_scd)
        self.btn_launch_scd.setEnabled(False)
        self.buttons.append(self.btn_launch_scd)

    def check(self):
        """Check if this step can be activated."""
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        # Priority order for source folder:
        # 1. decomposition_removed_duplicates/ (if step 10 completed and not skipped)
        # 2. decomposition_covisi_filtered/ (if step 9 completed and not skipped)
        # 3. decomposition_auto/ (fallback)
        removed_dups_folder = global_state.get_decomposition_removed_duplicates_path()
        covisi_folder = global_state.get_decomposition_covisi_filtered_path()
        auto_folder = global_state.get_decomposition_path()

        # Check step 10 (Remove Duplicates)
        if (global_state.is_widget_completed("step10") and
            not global_state.is_widget_skipped("step10") and
            removed_dups_folder and os.path.exists(removed_dups_folder)):
            self.expected_folder = removed_dups_folder
            logger.info("Using duplicate-removed files for MUEdit export")
        # Check step 9 (CoVISI)
        elif (global_state.is_widget_completed("step9") and
              not global_state.is_widget_skipped("step9") and
              covisi_folder and os.path.exists(covisi_folder)):
            self.expected_folder = covisi_folder
            logger.info("Using CoVISI-filtered files for MUEdit export")
        # Fallback
        else:
            self.expected_folder = auto_folder
            logger.info("Using decomposition_auto files for MUEdit export")

        self.muedit_folder = global_state.get_decomposition_muedit_path()

        # Load skipped files from disk (MAT path only; harmless on PKL path)
        self.skipped_files = self._load_skipped_files()

        # Detect which tool to use and route accordingly
        tool = read_manual_cleaning_tool()
        self._use_pkl = (tool == "scd_edition")

        if self._use_pkl:
            if self.expected_folder and os.path.exists(self.expected_folder):
                if self.expected_folder not in self.watcher.directories():
                    self.watcher.addPath(self.expected_folder)
            if self.expected_folder and os.path.exists(self.expected_folder):
                if not self.poll_timer.isActive():
                    self.poll_timer.start()
                    logger.info("Started PKL file polling timer (2s interval)")
            self._scan_pkl_files()
        else:
            if os.path.exists(self.muedit_folder):
                if self.muedit_folder not in self.watcher.directories():
                    self.watcher.addPath(self.muedit_folder)
            if os.path.exists(self.muedit_folder):
                if not self.poll_timer.isActive():
                    self.poll_timer.start()
                    logger.info("Started MUEdit file polling timer (2s interval)")
            self.scan_muedit_files()

        self._update_button_states()

        # Check if previous step is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        return True

    def scan_json_files(self):
        """Scan for JSON files in expected folder that need to be exported."""
        if not self.expected_folder or not os.path.exists(self.expected_folder):
            self.json_files = []
            return

        # State files to exclude
        state_files = {
            'decomposition_mapping.json',
            'multigrid_groupings.json',
            'covisi_pre_filter_report.json',
            'duplicate_detection_params.json',
            'duplicate_detection_report.json',
            '.muedit_skipped_files.json',
            '.skip_marker.json'
        }

        # Find all JSON files
        self.json_files = []
        all_files = os.listdir(self.expected_folder)
        logger.debug(f"All files in {self.expected_folder}: {all_files}")

        for filename in all_files:
            if filename.endswith('.json') and filename not in state_files:
                if not filename.startswith('algorithm_params') and not filename.startswith('.'):
                    json_path = os.path.join(self.expected_folder, filename)
                    self.json_files.append(json_path)
                    logger.debug(f"  Including: {filename}")
                else:
                    logger.debug(f"  Skipping (algorithm_params or hidden): {filename}")
            elif filename.endswith('.json'):
                logger.debug(f"  Skipping (state file): {filename}")

        logger.info(f"Found {len(self.json_files)} JSON files to export from {self.expected_folder}")
        if self.json_files:
            logger.info(f"Files to export: {[os.path.basename(f) for f in self.json_files]}")

    def auto_export_json_files(self):
        """Automatically export JSON files to MAT format."""
        if not self.json_files:
            return

        logger.info(f"Starting auto-export of {len(self.json_files)} JSON files")

        # Show progress
        self.loading_label.setText(f"Exporting {len(self.json_files)} files to MUEdit format...")
        self.loading_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Start export worker
        self.export_worker = JSONExportWorker(
            self.json_files,
            self.muedit_folder
        )
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()

    def on_export_progress(self, current, total, message):
        """Handle export progress updates."""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)
        self.loading_label.setText(message)

    def on_export_finished(self, success_count, output_paths):
        """Handle export completion."""
        self.export_completed = True
        self.export_worker = None

        self.loading_label.setVisible(False)
        self.progress_bar.setVisible(False)

        logger.info(f"Export completed: {success_count}/{len(self.json_files)} files exported")

        # Refresh MAT file list
        self.scan_muedit_files()

        # Show success message
        self.success(f"Exported {success_count} files to MUEdit format")

    def on_export_error(self, error_msg):
        """Handle export error."""
        self.export_worker = None

        self.loading_label.setVisible(False)
        self.progress_bar.setVisible(False)

        logger.error(f"Export failed: {error_msg}")
        self.error(f"Export failed: {error_msg}")

    def _get_skipped_files_path(self):
        """Get the path to the skipped files JSON file."""
        if not self.expected_folder:
            return None
        return os.path.join(self.expected_folder, '.muedit_skipped_files.json')

    def _load_skipped_files(self):
        """Load skipped files from JSON file."""
        skipped_path = self._get_skipped_files_path()
        if not skipped_path or not os.path.exists(skipped_path):
            return {}

        try:
            import json
            with open(skipped_path, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded {len(data)} skipped files from {skipped_path}")
                return data
        except Exception as e:
            logger.error(f"Failed to load skipped files: {e}")
            return {}

    def _save_skipped_files(self):
        """Save skipped files to JSON file."""
        skipped_path = self._get_skipped_files_path()
        if not skipped_path:
            return

        try:
            import json
            with open(skipped_path, 'w') as f:
                json.dump(self.skipped_files, f, indent=2)
                logger.info(f"Saved {len(self.skipped_files)} skipped files to {skipped_path}")
        except Exception as e:
            logger.error(f"Failed to save skipped files: {e}")

    def _trigger_manual_indexing(self):
        """Manually trigger motor unit indexing in background thread."""
        logger.info("Manual motor unit indexing triggered by user")
        self.indexing_needed = False
        self.btn_index_motor_units.setVisible(False)
        self._start_initial_scan()

    def _scan_files_fast(self):
        """Fast file scanning without motor unit checking (for state reconstruction).

        This method quickly lists all _muedit.mat and _edited.mat files without
        checking if they contain motor units. Used during automatic state reconstruction
        to avoid blocking the UI.
        """
        all_muedit_files = []
        edited_files = []

        # Scan decomposition_muedit only — all MAT files live here in the new design
        if self.muedit_folder and os.path.exists(self.muedit_folder):
            for file in os.listdir(self.muedit_folder):
                # Only scan single-grid files (exclude multi-grid files)
                if file.endswith('_muedit.mat') and '_multigrid_' not in file:
                    full_path = os.path.join(self.muedit_folder, file)
                    all_muedit_files.append(full_path)
                    edited_path = os.path.join(self.muedit_folder, file + '_edited.mat')
                    if os.path.exists(edited_path):
                        edited_files.append(edited_path)

        self.muedit_files = all_muedit_files
        self.edited_files = edited_files

        # Show indexing button only when cache has never been populated (None = never scanned)
        if len(self.muedit_files) > 0 and self.mu_check_cache is None and not self.is_scanning:
            self.indexing_needed = True
            self.btn_index_motor_units.setVisible(True)
        else:
            self.indexing_needed = False
            self.btn_index_motor_units.setVisible(False)

        # Update UI
        self.update_progress_ui()
        self._update_button_states()

    def _start_initial_scan(self):
        """Start initial scan in background thread."""
        if self.is_scanning or not self.muedit_folder:
            return

        self.is_scanning = True
        self.loading_dots = 0
        self.loading_label.setVisible(True)
        self.loading_animation_timer.start(500)  # Update every 500ms

        # Create and start worker thread (scan decomposition_muedit only)
        self.scan_worker = MUFileScanWorker(self.muedit_folder)
        self.scan_worker.scan_complete.connect(self._on_scan_complete)
        self.scan_worker.start()

        logger.info("Started background scan for MUEdit files with motor units")

    def _update_loading_animation(self):
        """Update loading animation dots."""
        self.loading_dots = (self.loading_dots + 1) % 4
        dots = "." * self.loading_dots
        self.loading_label.setText(f"Scanning files and checking for motor units{dots}")

    def _scan_new_files(self, new_file_paths):
        """Scan newly discovered files in background without blocking UI."""
        if self.is_scanning:
            return

        self.is_scanning = True

        # Create custom worker for just these files
        class NewFileWorker(QThread):
            scan_complete = pyqtSignal(dict)

            def __init__(self, file_paths):
                super().__init__()
                self.file_paths = file_paths

            def run(self):
                import h5py
                import scipy.io as sio
                cache_update = {}

                for path in self.file_paths:
                    # Use same logic as main worker
                    has_mus = self._check_motor_units(path, h5py, sio)
                    cache_update[path] = has_mus
                    if not has_mus:
                        logger.info(f"New file {os.path.basename(path)} has no motor units")

                self.scan_complete.emit(cache_update)

            def _check_motor_units(self, mat_path, h5py, sio):
                try:
                    try:
                        mat_data = sio.loadmat(mat_path, squeeze_me=True, struct_as_record=False)
                        signal = mat_data.get('signal')
                        if signal is not None:
                            discharge_times = getattr(signal, 'Dischargetimes', None)
                            if discharge_times is not None:
                                if hasattr(discharge_times, '__len__'):
                                    return len(discharge_times) > 0
                                return True
                        return False
                    except NotImplementedError:
                        pass

                    with h5py.File(mat_path, 'r') as f:
                        if 'signal' in f:
                            signal_group = f['signal']
                            if 'Dischargetimes' in signal_group:
                                discharge_times = signal_group['Dischargetimes']
                                if discharge_times.size > 0:
                                    if discharge_times.ndim == 2:
                                        n_grids, n_mus = discharge_times.shape
                                        if n_mus > 0:
                                            for mu_idx in range(n_mus):
                                                ref = discharge_times[0, mu_idx]
                                                if isinstance(ref, h5py.Reference):
                                                    data = f[ref]
                                                    if data.size > 0:
                                                        return True
                                                elif ref.size > 0:
                                                    return True
                                        return False
                                    return True

                        if 'edition' in f:
                            edition_group = f['edition']
                            if 'Distimeclean' in edition_group:
                                distimeclean = edition_group['Distimeclean']
                                if distimeclean.size > 0:
                                    return True
                    return False
                except Exception as e:
                    logger.warning(f"Could not check motor units in {os.path.basename(mat_path)}: {e}")
                    return True

        self.scan_worker = NewFileWorker(new_file_paths)
        self.scan_worker.scan_complete.connect(self._on_new_files_scan_complete)
        self.scan_worker.start()

    def _on_new_files_scan_complete(self, cache_update):
        """Handle completion of new files scan."""
        self.is_scanning = False
        if self.mu_check_cache is None:
            self.mu_check_cache = cache_update
        else:
            self.mu_check_cache.update(cache_update)
        logger.info(f"New files scan complete, cache updated with {len(cache_update)} entries")

        # Trigger another scan to update UI
        self.scan_muedit_files()

    def _on_scan_complete(self, valid_files, mu_check_cache):
        """Handle completion of background scan."""
        self.is_scanning = False
        self.loading_animation_timer.stop()
        self.loading_label.setVisible(False)
        self.mu_check_cache = mu_check_cache

        # Hide indexing button now that indexing is complete
        self.indexing_needed = False
        self.btn_index_motor_units.setVisible(False)

        logger.info(f"Scan complete: {len(valid_files)} files with motor units found")

        # Now do the normal scan (with cache populated, this will be fast)
        self.scan_muedit_files()

    def scan_muedit_files(self, skip_mu_check=False):
        """Scan decomposition_muedit/ for MUEdit files and track progress.

        Args:
            skip_mu_check: If True, skip motor unit checking (fast path for state reconstruction)
        """
        if not self.muedit_folder or not os.path.exists(self.muedit_folder):
            return

        # Fast path: Skip motor unit checking entirely (for state reconstruction)
        if skip_mu_check:
            self._scan_files_fast()
            return

        # If cache has never been populated and we're not already scanning, start initial scan.
        # None = never scanned; {} = scanned but no MU files found (don't re-scan).
        if self.mu_check_cache is None and not self.is_scanning:
            self._start_initial_scan()
            return

        # If still scanning, skip this iteration
        if self.is_scanning:
            return

        # Scan decomposition_muedit only — all MAT files live here in the new design
        all_muedit_files = []
        edited_files = []
        new_files_found = []

        if self.muedit_folder not in self.watcher.directories():
            self.watcher.addPath(self.muedit_folder)

        for file in os.listdir(self.muedit_folder):
            # Only scan single-grid files (exclude multi-grid files)
            if file.endswith('_muedit.mat') and '_multigrid_' not in file:
                full_path = os.path.join(self.muedit_folder, file)

                if full_path not in self.mu_check_cache:
                    new_files_found.append(full_path)
                    has_mus = True
                else:
                    has_mus = self.mu_check_cache[full_path]

                if not has_mus:
                    continue

                all_muedit_files.append(full_path)
                edited_path = os.path.join(self.muedit_folder, file + '_edited.mat')
                if os.path.exists(edited_path):
                    edited_files.append(edited_path)

        # If new files were found, trigger a background scan for them
        if new_files_found and not self.is_scanning:
            logger.info(f"Found {len(new_files_found)} new files, starting background check")
            self._scan_new_files(new_files_found)

        # Check if file count changed (for logging)
        file_count = len(all_muedit_files) + len(edited_files)
        self.last_file_count = file_count

        self.muedit_files = all_muedit_files
        self.edited_files = edited_files

        # Update UI
        self.update_progress_ui()
        self._update_button_states()

        logger.debug(f"MUEdit files: {len(self.muedit_files)}, Edited files: {len(self.edited_files)}")

    def update_progress_ui(self):
        """Update progress UI with current status."""
        if self._use_pkl:
            self._update_pkl_progress_ui()
            return
        total = len(self.muedit_files)
        edited = len(self.edited_files)
        skipped = len([f for f in self.muedit_files if f in self.skipped_files])
        completed = edited + skipped

        # Update progress bar
        self.progress_bar.setMaximum(total if total > 0 else 1)
        self.progress_bar.setValue(completed)
        self.progress_bar.setFormat(
            f"{edited} edited, {skipped} skipped / {total} total ({int(completed/total*100) if total > 0 else 0}%)"
        )

        # Clear existing status labels
        while self.file_status_layout.count():
            child = self.file_status_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Add status for each file
        for muedit_file in self.muedit_files:
            filename = os.path.basename(muedit_file)
            is_edited = any(os.path.basename(ef).startswith(filename.replace('.mat', '')) for ef in self.edited_files)
            is_skipped = muedit_file in self.skipped_files

            status_label = QLabel()
            if is_edited:
                status_label.setText(f"✓ {filename}")
                status_label.setStyleSheet(f"color: {Colors.GREEN_700}; font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;")
            elif is_skipped:
                skip_reason = self.skipped_files[muedit_file]
                if skip_reason:
                    status_label.setText(f"⊘ {filename} ({skip_reason})")
                else:
                    status_label.setText(f"⊘ {filename} (Skipped)")
                status_label.setStyleSheet(f"color: {Colors.ORANGE_600}; font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;")
            else:
                status_label.setText(f"⏳ {filename}")
                status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;")

            self.file_status_layout.addWidget(status_label)

        # Check if completed (all files either edited or skipped)
        if total > 0 and completed >= total:
            # Only complete if not already completed (prevent multiple emissions)
            if not self.step_completed:
                logger.info(f"All MUEdit files processed! {edited} edited, {skipped} skipped")
                self.complete_step()

    def launch_muedit(self):
        """Launch MUEdit for manual cleaning."""
        logger.info("Launching MUEdit for manual cleaning...")

        # Get configured launch method
        launch_method_str = config.get(Settings.MUEDIT_LAUNCH_METHOD)
        if launch_method_str:
            try:
                launch_method = MUEditLaunchMethod(launch_method_str)
            except ValueError:
                launch_method = MUEditLaunchMethod.AUTO
        else:
            launch_method = MUEditLaunchMethod.AUTO

        logger.info(f"MUEdit launch method: {launch_method.value}")

        # Try methods based on configuration
        if launch_method == MUEditLaunchMethod.MATLAB_ENGINE:
            success, message = self._launch_muedit_via_matlab_engine()
            if success:
                self.success(message)
                self._show_instruction_dialog()
            else:
                self.error(message)

        elif launch_method == MUEditLaunchMethod.MATLAB_CLI:
            success, message = self._launch_muedit_via_matlab_cli()
            if success:
                self.success(message)
                self._show_instruction_dialog()
            else:
                self.error(message)

        elif launch_method == MUEditLaunchMethod.STANDALONE:
            success, message = self._launch_muedit_standalone()
            if success:
                self.success(message)
                self._show_instruction_dialog()
            else:
                self.error(message)

        elif launch_method == MUEditLaunchMethod.AUTO:
            # Try all methods
            success, message = self._launch_muedit_via_matlab_engine()
            if success:
                logger.info(f"AUTO mode: {message}")
                self.success(message)
                self._show_instruction_dialog()
                return

            success, message = self._launch_muedit_via_matlab_cli()
            if success:
                logger.info(f"AUTO mode: {message}")
                self.success(message)
                self._show_instruction_dialog()
                return

            success, message = self._launch_muedit_standalone()
            if success:
                logger.info(f"AUTO mode: {message}")
                self.success(message)
                self._show_instruction_dialog()
                return

            # All methods failed
            self.error(
                "Failed to launch MUEdit using any available method.\n\n"
                "Please ensure one of the following:\n"
                "1. MATLAB Engine API is installed (pip install matlabengine)\n"
                "2. MATLAB is in PATH\n"
                "3. MUEdit is available as standalone\n\n"
                "Configure in Settings → MUEdit\n"
                "Open Matlab manually and start MUedit."
            )
            self._show_instruction_dialog()

    def _launch_muedit_via_matlab_engine(self):
        """Launch MUEdit using MATLAB Engine API."""
        try:
            import matlab.engine
        except ImportError:
            return False, "MATLAB Engine API not available (pip install matlabengine)"

        try:
            muedit_path = config.get(Settings.MUEDIT_PATH)

            # Find running MATLAB sessions
            engines = matlab.engine.find_matlab()

            if engines:
                logger.info(f"Found {len(engines)} running MATLAB session(s)")
                eng = matlab.engine.connect_matlab(engines[0])
            else:
                logger.info("Starting new MATLAB session...")
                eng = matlab.engine.start_matlab()

            # Add MUEdit to path
            if muedit_path and os.path.exists(muedit_path):
                current_path = eng.path(nargout=1)
                if muedit_path not in current_path:
                    logger.info(f"Adding MUEdit path: {muedit_path}")
                    gen_path_cmd = f"addpath(genpath('{muedit_path}'))"
                    eng.eval(gen_path_cmd, nargout=0)

            # Launch MUEdit GUI
            logger.info("Launching MUEdit GUI...")
            eng.eval("MUedit_exported", nargout=0, background=True)

            return True, "MUEdit launched successfully via MATLAB Engine"

        except Exception as e:
            return False, f"MATLAB Engine failed: {str(e)}"

    def _launch_muedit_via_matlab_cli(self):
        """Launch MUEdit via MATLAB command line."""
        try:
            muedit_path = config.get(Settings.MUEDIT_PATH)

            if muedit_path and os.path.exists(muedit_path):
                matlab_cmd = (
                    f"if ~contains(path, '{muedit_path}'), "
                    f"addpath(genpath('{muedit_path}')); "
                    f"end; MUedit"
                )
            else:
                matlab_cmd = "MUedit"

            logger.info(f"Starting MATLAB: {matlab_cmd}")
            subprocess.Popen(["matlab", "-automation", "-r", matlab_cmd])

            return True, "MUEdit launched via MATLAB CLI"

        except FileNotFoundError:
            return False, "MATLAB executable not found in PATH"
        except Exception as e:
            return False, f"MATLAB CLI failed: {str(e)}"

    def _launch_muedit_standalone(self):
        """Launch MUEdit as standalone."""
        try:
            logger.info("Launching MUEdit as standalone...")
            subprocess.Popen(["muedit"])
            return True, "MUEdit launched as standalone"
        except FileNotFoundError:
            return False, "MUEdit executable not found in PATH"
        except Exception as e:
            return False, f"Standalone launch failed: {str(e)}"

    def _show_instruction_dialog(self):
        """Show instruction dialog for manual workflow."""
        dialog = MUEditInstructionDialog(
            muedit_files=self.muedit_files,
            edited_files=self.edited_files,
            folder_path=self.expected_folder,
            skipped_files=self.skipped_files,
            muedit_folder_path=self.muedit_folder,
            parent=self
        )
        dialog.exec_()

        # Update skipped files from dialog and save to disk
        self.skipped_files = dialog.skipped_files
        self._save_skipped_files()

        # Refresh UI to show updated skipped status
        self.update_progress_ui()

    # ------------------------------------------------------------------
    # Tool routing helpers
    # ------------------------------------------------------------------

    def _poll_scan(self):
        """Dispatch file-change polling to the correct scanner."""
        if self._use_pkl:
            self._scan_pkl_files()
        else:
            self.scan_muedit_files(skip_mu_check=self.indexing_needed)

    def _get_stored_tool(self):
        """Return the explicitly stored manual_cleaning_tool value, or None."""
        return read_process_log().get("manual_cleaning_tool")

    def _has_any_pkl(self) -> bool:
        """Return True if any PKL (including single-grid) exists in the priority chain."""
        removed_dups = global_state.get_decomposition_removed_duplicates_path()
        covisi_filtered = global_state.get_decomposition_covisi_filtered_path()
        auto_folder = global_state.get_decomposition_path()

        if (removed_dups and os.path.isdir(removed_dups) and
                any(f.endswith("_duplicates_removed.pkl") for f in os.listdir(removed_dups))):
            return True
        if (covisi_filtered and os.path.isdir(covisi_filtered) and
                any(f.endswith("_covisi_filtered.pkl") for f in os.listdir(covisi_filtered))):
            return True
        if auto_folder and os.path.isdir(auto_folder):
            return any(
                f.endswith(".pkl") and not f.endswith(".pkl.bak")
                for f in os.listdir(auto_folder)
            )
        return False

    def _update_button_states(self):
        """Enable/disable tool buttons based on stored tool choice and file availability."""
        _LOCKED_TIP = (
            "Tool already chosen for this workfolder. "
            "Start a new workfolder to use a different tool."
        )
        stored = self._get_stored_tool()
        has_mat = bool(self.muedit_files)
        # Enable scd button if merged PKLs are ready OR if any PKL exists (can be merged on click)
        has_pkl = bool(self.pkl_files) or self._has_any_pkl()

        if stored == "muedit":
            self.btn_launch_muedit.setEnabled(has_mat)
            self.btn_launch_scd.setEnabled(False)
            self.btn_launch_scd.setToolTip(_LOCKED_TIP)
        elif stored == "scd_edition":
            self.btn_launch_scd.setEnabled(has_pkl)
            self.btn_launch_muedit.setEnabled(False)
            self.btn_launch_muedit.setToolTip(_LOCKED_TIP)
        else:
            # No explicit choice yet — enable each button only if its files exist
            self.btn_launch_muedit.setEnabled(has_mat)
            self.btn_launch_scd.setEnabled(has_pkl)

    def _on_choose_muedit(self):
        """Handle 'Edit with MUedit' button click."""
        if not self._get_stored_tool():
            write_manual_cleaning_tool("muedit")
            self._use_pkl = False
            self._update_button_states()
        self.launch_muedit()

    def _on_choose_scd(self):
        """Handle 'Edit with scd-edition' button click."""
        if not self._get_stored_tool():
            write_manual_cleaning_tool("scd_edition")
            self._use_pkl = True
            self._update_button_states()
        # If merged PKLs are already scanned, start immediately.
        # Otherwise run upgrade+merge first, then start.
        if self.pkl_files:
            self._start_scd_edition()
        else:
            self._run_pkl_merge_then_edit()

    def _run_pkl_merge_then_edit(self):
        """Run PKL upgrade+merge in background, then start scd-edition."""
        auto_folder = global_state.get_decomposition_path()
        channelselection = global_state.get_channel_selection_path()
        if not auto_folder or not os.path.isdir(auto_folder):
            self.error("decomposition_auto folder not found.")
            return

        self.btn_launch_scd.setEnabled(False)
        self.loading_label.setText("Preparing PKL files…")
        self.loading_label.setVisible(True)

        self.pkl_merge_worker = _PklMergeWorker(auto_folder, channelselection or "")
        self.pkl_merge_worker.progress.connect(self._on_pkl_merge_progress)
        self.pkl_merge_worker.finished.connect(self._on_pkl_merge_finished)
        self.pkl_merge_worker.error.connect(self._on_pkl_merge_error)
        self.pkl_merge_worker.start()

    def _on_pkl_merge_progress(self, msg: str):
        self.loading_label.setText(msg)

    def _on_pkl_merge_finished(self, _merged_paths: list):
        self.pkl_merge_worker = None
        self.loading_label.setVisible(False)
        self._scan_pkl_files()
        if self.pkl_files:
            self._start_scd_edition()
        else:
            self.error("PKL merge produced no files. Check decomposition_auto/ folder.")
            self._update_button_states()

    def _on_pkl_merge_error(self, msg: str):
        self.pkl_merge_worker = None
        self.loading_label.setVisible(False)
        self.error(f"PKL preparation failed: {msg}")
        self._update_button_states()

    # ------------------------------------------------------------------
    # PKL path: scanning and progress UI
    # ------------------------------------------------------------------

    def _scan_pkl_files(self):
        """Scan for merged PKL files using the scd-edition priority chain.

        Only merged multi-port PKLs (no grid-key pattern in stem) are usable
        by scd-edition directly.  Individual per-grid PKLs (e.g.
        ``*_8mm_5x13_2*.pkl``) are skipped in all folders — they must be
        merged first via ``_run_pkl_merge_then_edit()``.
        """
        removed_dups = global_state.get_decomposition_removed_duplicates_path()
        covisi_filtered = global_state.get_decomposition_covisi_filtered_path()
        auto_folder = global_state.get_decomposition_path()

        def _has_merged_pkl(folder: str) -> bool:
            """Return True if *folder* contains at least one merged (non-grid-key) PKL."""
            if not folder or not os.path.isdir(folder):
                return False
            return any(
                f.endswith(".pkl") and not f.endswith(".pkl.bak")
                and not f[:-4].endswith("_edited")
                and not _GRID_KEY_RE.search(f[:-4])
                for f in os.listdir(folder)
            )

        source_dir = None
        if _has_merged_pkl(removed_dups):
            source_dir = removed_dups
        elif _has_merged_pkl(covisi_filtered):
            source_dir = covisi_filtered
        elif _has_merged_pkl(auto_folder):
            source_dir = auto_folder

        if not source_dir:
            self.pkl_files = []
            self.edited_pkl_files = []
            self._update_button_states()
            return

        if source_dir not in self.watcher.directories():
            self.watcher.addPath(source_dir)

        pkl_files = []
        for fname in os.listdir(source_dir):
            if not fname.endswith(".pkl") or fname.endswith(".pkl.bak"):
                continue
            stem = fname[:-4]
            if stem.endswith("_edited"):
                continue  # output file, not a source
            if _GRID_KEY_RE.search(stem):
                continue  # single-grid PKL — skip, needs merge first
            pkl_files.append(os.path.join(source_dir, fname))

        edited_pkl_files = []
        for pkl in pkl_files:
            stem = os.path.splitext(os.path.basename(pkl))[0]
            edited = os.path.join(source_dir, f"{stem}_edited.pkl")
            if os.path.exists(edited):
                edited_pkl_files.append(edited)

        self.pkl_files = pkl_files
        self.edited_pkl_files = edited_pkl_files
        self._update_pkl_progress_ui()
        self._update_button_states()

    def _update_pkl_progress_ui(self):
        """Update progress UI for scd-edition PKL path."""
        total = len(self.pkl_files)
        edited = len(self.edited_pkl_files)

        self.progress_bar.setMaximum(total if total > 0 else 1)
        self.progress_bar.setValue(edited)
        self.progress_bar.setFormat(
            f"{edited} edited / {total} total "
            f"({int(edited / total * 100) if total > 0 else 0}%)"
        )

        while self.file_status_layout.count():
            child = self.file_status_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        edited_stems = {os.path.splitext(os.path.basename(ep))[0] for ep in self.edited_pkl_files}
        for pkl_path in self.pkl_files:
            stem = os.path.splitext(os.path.basename(pkl_path))[0]
            status_label = QLabel()
            if stem + "_edited" in edited_stems:
                status_label.setText(f"✓ {stem}.pkl")
                status_label.setStyleSheet(
                    f"color: {Colors.GREEN_700}; font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;"
                )
            else:
                status_label.setText(f"⏳ {stem}.pkl")
                status_label.setStyleSheet(
                    f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;"
                )
            self.file_status_layout.addWidget(status_label)

        if total > 0 and edited >= total and not self.step_completed:
            logger.info(f"All PKL files edited! {edited} total")
            self.complete_step()

    # ------------------------------------------------------------------
    # PKL path: scd-edition worker
    # ------------------------------------------------------------------

    def _start_scd_edition(self):
        """Start sequential scd-edition processing for all PKL files."""
        if not self.pkl_files:
            self.error("No PKL files found to edit.")
            return

        self.scd_worker = ScdEditionWorker(self.pkl_files)
        self.scd_worker.progress.connect(self._on_scd_progress)
        self.scd_worker.file_done.connect(self._on_scd_file_done)
        self.scd_worker.finished.connect(self._on_scd_finished)
        self.scd_worker.error.connect(self._on_scd_error)
        self.scd_worker.start()
        self.loading_label.setText(f"Opening scd-edition for {len(self.pkl_files)} file(s)...")
        self.loading_label.setVisible(True)
        self.btn_launch_scd.setEnabled(False)

    def _on_scd_progress(self, current, total, message):
        self.progress_bar.setMaximum(total if total > 0 else 1)
        self.progress_bar.setValue(current)
        self.loading_label.setText(message)

    def _on_scd_file_done(self, edited_path):
        if edited_path not in self.edited_pkl_files:
            self.edited_pkl_files.append(edited_path)
        self._update_pkl_progress_ui()

    def _on_scd_finished(self):
        self.scd_worker = None
        self.loading_label.setVisible(False)
        self._scan_pkl_files()
        self._update_button_states()
        self.success("scd-edition session complete.")

    def _on_scd_error(self, error_msg):
        self.scd_worker = None
        self.loading_label.setVisible(False)
        logger.error("scd-edition worker error: %s", error_msg)
        self.error(f"scd-edition error: {error_msg}")

    def is_completed(self):
        """Check if this step is completed."""
        if self._use_pkl:
            total = len(self.pkl_files)
            edited = len(self.edited_pkl_files)
            return total > 0 and edited >= total

        # MAT path: completed when all MUEdit files have been either edited or skipped
        total = len(self.muedit_files)
        edited = len(self.edited_files)
        skipped = len([f for f in self.muedit_files if f in self.skipped_files])
        completed = edited + skipped

        return total > 0 and completed >= total

    def init_file_checking(self):
        """Initialize file checking for state reconstruction.

        Uses fast path (skips motor unit checking) during state reconstruction
        to avoid blocking the UI. If motor unit indexing is needed, a button
        will be shown for the user to trigger it manually.
        """
        # Priority order for source folder (same as check())
        removed_dups_folder = global_state.get_decomposition_removed_duplicates_path()
        covisi_folder = global_state.get_decomposition_covisi_filtered_path()
        auto_folder = global_state.get_decomposition_path()

        # Check step 10
        if (global_state.is_widget_completed("step10") and
            not global_state.is_widget_skipped("step10") and
            removed_dups_folder and os.path.exists(removed_dups_folder)):
            self.expected_folder = removed_dups_folder
        # Check step 9
        elif (global_state.is_widget_completed("step9") and
              not global_state.is_widget_skipped("step9") and
              covisi_folder and os.path.exists(covisi_folder)):
            self.expected_folder = covisi_folder
        # Fallback
        else:
            self.expected_folder = auto_folder

        self.muedit_folder = global_state.get_decomposition_muedit_path()

        # Load skipped files from disk
        self.skipped_files = self._load_skipped_files()

        if os.path.exists(self.expected_folder):
            if self.expected_folder not in self.watcher.directories():
                self.watcher.addPath(self.expected_folder)

        if os.path.exists(self.muedit_folder):
            if self.muedit_folder not in self.watcher.directories():
                self.watcher.addPath(self.muedit_folder)

        # Start polling timer for reliable file detection
        if os.path.exists(self.expected_folder) or os.path.exists(self.muedit_folder):
            if not self.poll_timer.isActive():
                self.poll_timer.start()

        # Detect tool and use appropriate fast scan
        tool = read_manual_cleaning_tool()
        self._use_pkl = (tool == "scd_edition")

        if self._use_pkl:
            self._scan_pkl_files()
        else:
            # Fast scan: skip motor unit checking to avoid blocking the UI
            self.scan_muedit_files(skip_mu_check=True)

        logger.info(f"File checking initialized for folder (fast mode): {self.expected_folder}")

    def cleanup(self):
        """Clean up timers and threads when widget is destroyed."""
        if hasattr(self, 'poll_timer') and self.poll_timer.isActive():
            self.poll_timer.stop()

        if hasattr(self, 'loading_animation_timer') and self.loading_animation_timer.isActive():
            self.loading_animation_timer.stop()

        if hasattr(self, 'scan_worker') and self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.quit()
            self.scan_worker.wait(1000)  # Wait up to 1 second

        if hasattr(self, 'scd_worker') and self.scd_worker and self.scd_worker.isRunning():
            self.scd_worker.cancel()
            self.scd_worker.wait(2000)

        if hasattr(self, 'pkl_merge_worker') and self.pkl_merge_worker and self.pkl_merge_worker.isRunning():
            self.pkl_merge_worker.quit()
            self.pkl_merge_worker.wait(2000)

        logger.debug("MUEditCleaningWizardWidget cleanup completed")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
