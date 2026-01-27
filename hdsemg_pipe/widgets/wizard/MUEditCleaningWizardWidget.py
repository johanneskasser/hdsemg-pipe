"""
Step 10: MUEdit Manual Cleaning (Wizard Version)

This step launches MUEdit for manual cleaning of decomposition results
and monitors progress.
"""
import os
import subprocess
from PyQt5.QtCore import QFileSystemWatcher, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QPushButton, QLabel, QVBoxLayout, QFrame, QScrollArea,
    QWidget, QProgressBar, QCheckBox
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget
from hdsemg_pipe.widgets.MUEditInstructionDialog import MUEditInstructionDialog
from hdsemg_pipe.config.config_enums import Settings, MUEditLaunchMethod
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts


class MUFileScanWorker(QThread):
    """Worker thread for scanning MUEdit files and checking for motor units."""

    scan_complete = pyqtSignal(list, dict)  # (valid_files, mu_check_cache)

    def __init__(self, folder_path, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path

    def run(self):
        """Scan folder and check which files have motor units."""
        import h5py
        import scipy.io as sio

        valid_files = []
        mu_check_cache = {}

        if not os.path.exists(self.folder_path):
            self.scan_complete.emit(valid_files, mu_check_cache)
            return

        all_filenames = os.listdir(self.folder_path)

        for file in all_filenames:
            if file.endswith('_muedit.mat') or file.endswith('_multigrid_muedit.mat'):
                full_path = os.path.join(self.folder_path, file)

                # Check if file has motor units
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
        step_index = 10
        step_name = "MUEdit Manual Cleaning"
        description = "Launch MUEdit for manual cleaning and quality control of motor unit decomposition results."

        super().__init__(step_index, step_name, description, parent)

        self.expected_folder = None
        self.muedit_files = []
        self.edited_files = []
        self.last_file_count = 0

        # Cache for motor unit checks (to avoid re-scanning files every time)
        self.mu_check_cache = {}
        self.scan_worker = None
        self.is_scanning = False

        # Loading animation timer
        self.loading_animation_timer = QTimer(self)
        self.loading_animation_timer.timeout.connect(self._update_loading_animation)
        self.loading_dots = 0

        # Initialize file system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.scan_muedit_files)

        # Add polling timer for reliable file detection (QFileSystemWatcher can miss events on Windows)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.scan_muedit_files)
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

        # Checkbox to skip original muedit files when covisi filtered versions exist
        self.chk_skip_originals = QCheckBox("Nur CoVISI-gefilterte Dateien verwenden (Originale auslassen)")
        self.chk_skip_originals.setStyleSheet(f"font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;")
        self.chk_skip_originals.setChecked(False)
        self.chk_skip_originals.toggled.connect(self.scan_muedit_files)
        status_layout.addWidget(self.chk_skip_originals)

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
        self.btn_launch_muedit = QPushButton("Open MUEdit")
        self.btn_launch_muedit.setStyleSheet(Styles.button_primary())
        self.btn_launch_muedit.setToolTip("Launch MUEdit for manual cleaning")
        self.btn_launch_muedit.clicked.connect(self.launch_muedit)
        self.btn_launch_muedit.setEnabled(False)
        self.buttons.append(self.btn_launch_muedit)

    def check(self):
        """Check if this step can be activated."""
        workfolder = global_state.workfolder
        if not workfolder:
            return False

        self.expected_folder = global_state.get_decomposition_path()

        # Add watcher
        if os.path.exists(self.expected_folder):
            if self.expected_folder not in self.watcher.directories():
                self.watcher.addPath(self.expected_folder)

            # Start polling timer for reliable file detection
            if not self.poll_timer.isActive():
                self.poll_timer.start()
                logger.info("Started MUEdit file polling timer (2s interval)")

        # Always scan files to show status, even if step is not yet activated
        self.scan_muedit_files()

        # Check if previous step is completed
        if not global_state.is_widget_completed(f"step{self.step_index - 1}"):
            return False

        return True

    def _start_initial_scan(self):
        """Start initial scan in background thread."""
        if self.is_scanning or not self.expected_folder:
            return

        self.is_scanning = True
        self.loading_dots = 0
        self.loading_label.setVisible(True)
        self.loading_animation_timer.start(500)  # Update every 500ms

        # Create and start worker thread
        self.scan_worker = MUFileScanWorker(self.expected_folder)
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

        logger.info(f"Scan complete: {len(valid_files)} files with motor units found")

        # Now do the normal scan
        self.scan_muedit_files()

    def scan_muedit_files(self):
        """Scan for MUEdit files and track progress."""
        if not os.path.exists(self.expected_folder):
            return

        # If cache is empty and we're not already scanning, start initial scan
        if not self.mu_check_cache and not self.is_scanning:
            self._start_initial_scan()
            return

        # If still scanning, skip this iteration
        if self.is_scanning:
            return

        # Find all _muedit.mat files
        all_muedit_files = []
        edited_files = []
        new_files_found = []

        all_filenames = os.listdir(self.expected_folder)

        for file in all_filenames:
            if file.endswith('_muedit.mat') or file.endswith('_multigrid_muedit.mat'):
                full_path = os.path.join(self.expected_folder, file)

                # Check if file is in cache
                if full_path not in self.mu_check_cache:
                    # New file found - mark for scanning but include it for now
                    new_files_found.append(full_path)
                    has_mus = True  # Assume True for new files until scanned
                else:
                    has_mus = self.mu_check_cache[full_path]

                if not has_mus:
                    continue

                all_muedit_files.append(full_path)

                # Check if edited version exists
                # MUEdit creates files by appending "_edited.mat" to the entire filename
                # e.g., "file_muedit.mat" -> "file_muedit.mat_edited.mat"
                edited_path = os.path.join(self.expected_folder, file + '_edited.mat')
                if os.path.exists(edited_path):
                    edited_files.append(edited_path)

        # If new files were found, trigger a background scan for them
        if new_files_found and not self.is_scanning:
            logger.info(f"Found {len(new_files_found)} new files, starting background check")
            self._scan_new_files(new_files_found)

        # Build set of originals that have a covisi filtered counterpart
        # e.g. "base_covisi_filtered_muedit.mat" exists -> "base_muedit.mat" is the original to skip
        covisi_filtered_names = set()
        originals_with_covisi = set()
        for f in all_muedit_files:
            fname = os.path.basename(f)
            if '_covisi_filtered_muedit.mat' in fname:
                covisi_filtered_names.add(fname)
                original_name = fname.replace('_covisi_filtered_muedit.mat', '_muedit.mat')
                originals_with_covisi.add(original_name)

        # Show/hide checkbox based on whether any covisi filtered muedit files exist
        has_covisi = len(covisi_filtered_names) > 0
        self.chk_skip_originals.setVisible(has_covisi)

        # Filter out original muedit files when covisi filtered versions exist
        if has_covisi and self.chk_skip_originals.isChecked():
            muedit_files = [
                f for f in all_muedit_files
                if os.path.basename(f) not in originals_with_covisi
            ]
            # Also filter edited_files to only include those matching kept muedit_files
            kept_basenames = {os.path.basename(f) for f in muedit_files}
            edited_files = [
                ef for ef in edited_files
                if any(os.path.basename(ef).startswith(kb.replace('.mat', '')) for kb in kept_basenames)
            ]
        else:
            muedit_files = all_muedit_files

        # Check if file count changed (for logging)
        file_count = len(muedit_files) + len(edited_files)
        file_count_changed = file_count != self.last_file_count
        self.last_file_count = file_count

        self.muedit_files = muedit_files
        self.edited_files = edited_files

        # Update UI
        self.update_progress_ui()

        # Enable button if files exist
        self.btn_launch_muedit.setEnabled(len(muedit_files) > 0)

        # Only log when file count changes to avoid spam
        if file_count_changed:
            logger.info(f"MUEdit files: {len(muedit_files)}, Edited files: {len(edited_files)}")

    def update_progress_ui(self):
        """Update progress UI with current status."""
        total = len(self.muedit_files)
        edited = len(self.edited_files)

        # Update progress bar
        self.progress_bar.setMaximum(total if total > 0 else 1)
        self.progress_bar.setValue(edited)
        self.progress_bar.setFormat(f"{edited}/{total} files edited ({int(edited/total*100) if total > 0 else 0}%)")

        # Clear existing status labels
        while self.file_status_layout.count():
            child = self.file_status_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Add status for each file
        for muedit_file in self.muedit_files:
            filename = os.path.basename(muedit_file)
            is_edited = any(os.path.basename(ef).startswith(filename.replace('.mat', '')) for ef in self.edited_files)

            status_label = QLabel()
            if is_edited:
                status_label.setText(f"✓ {filename}")
                status_label.setStyleSheet(f"color: {Colors.GREEN_700}; font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;")
            else:
                status_label.setText(f"⏳ {filename}")
                status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SM}; padding: {Spacing.XS}px;")

            self.file_status_layout.addWidget(status_label)

        # Check if completed
        if total > 0 and edited >= total:
            logger.info("All MUEdit files have been edited!")
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
                "Configure in Settings → MUEdit"
            )

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
            parent=self
        )
        dialog.exec_()

    def is_completed(self):
        """Check if this step is completed."""
        # Step is completed when all MUEdit files have been edited
        total = len(self.muedit_files)
        edited = len(self.edited_files)

        return total > 0 and edited >= total

    def init_file_checking(self):
        """Initialize file checking for state reconstruction."""
        self.expected_folder = global_state.get_decomposition_path()

        if os.path.exists(self.expected_folder):
            if self.expected_folder not in self.watcher.directories():
                self.watcher.addPath(self.expected_folder)

            # Start polling timer for reliable file detection
            if not self.poll_timer.isActive():
                self.poll_timer.start()

        # Scan for files
        self.scan_muedit_files()
        logger.info(f"File checking initialized for folder: {self.expected_folder}")

    def cleanup(self):
        """Clean up timers and threads when widget is destroyed."""
        if hasattr(self, 'poll_timer') and self.poll_timer.isActive():
            self.poll_timer.stop()

        if hasattr(self, 'loading_animation_timer') and self.loading_animation_timer.isActive():
            self.loading_animation_timer.stop()

        if hasattr(self, 'scan_worker') and self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.quit()
            self.scan_worker.wait(1000)  # Wait up to 1 second

        logger.debug("MUEditCleaningWizardWidget cleanup completed")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
