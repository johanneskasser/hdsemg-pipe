import os
import subprocess
import threading
import time

from PyQt5.QtCore import pyqtSignal, QFileSystemWatcher
from PyQt5.QtWidgets import QPushButton, QDialog, QLabel, QVBoxLayout, QWidget, QProgressBar, QScrollArea

from hdsemg_pipe.actions.file_utils import update_extras_in_pickle_file, update_extras_in_json_file
from hdsemg_pipe.actions.decomposition_export import export_to_muedit_mat, is_muedit_file_exists
from hdsemg_pipe.config.config_enums import Settings, MUEditLaunchMethod
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.loadingbutton import LoadingButton
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.widgets.MappingDialog import MappingDialog
from hdsemg_pipe.widgets.MUEditInstructionDialog import MUEditInstructionDialog
from hdsemg_pipe.ui_elements.theme import Styles, Colors


class DecompositionResultsStepWidget(BaseStepWidget):
    resultsDisplayed = pyqtSignal(str)

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(step_index, step_name, tooltip, parent)
        self.expected_folder = None

        # Initialize file system watcher and connect its signal
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.get_decomposition_results)

        self.error_messages = []
        self.decomp_mapping = None
        self.processed_files = []
        self.result_files = []

        # Progress tracking for MUEdit workflow
        self.original_decomp_files = []  # Original .json/.pkl files
        self.muedit_files = []  # _muedit.mat files (ready for editing)
        self.edited_files = []  # _muedit_edited.mat files (finished editing)

        # Perform an initial check
        self.check()

        # Create progress UI elements and add to layout
        self.create_progress_ui()
        # Add progress container to the additional info column
        self.col_additional.addWidget(self.progress_container)

    def create_progress_ui(self):
        """Creates the progress tracking UI for MUEdit workflow."""
        # Progress container
        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 10, 0, 10)

        # Progress header
        self.progress_label = QLabel("Manual Cleaning Progress")
        self.progress_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_PRIMARY};")
        progress_layout.addWidget(self.progress_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                text-align: center;
                height: 24px;
                background-color: {Colors.BG_SECONDARY};
            }}
            QProgressBar::chunk {{
                background-color: {Colors.GREEN_600};
                border-radius: 3px;
            }}
        """)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # File status list (scrollable)
        self.file_status_scroll = QScrollArea()
        self.file_status_scroll.setWidgetResizable(True)
        self.file_status_scroll.setMaximumHeight(200)
        self.file_status_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: 4px;
                background-color: {Colors.BG_PRIMARY};
            }}
        """)

        self.file_status_widget = QWidget()
        self.file_status_layout = QVBoxLayout(self.file_status_widget)
        self.file_status_layout.setContentsMargins(8, 8, 8, 8)
        self.file_status_scroll.setWidget(self.file_status_widget)
        progress_layout.addWidget(self.file_status_scroll)

        # Initially hide progress UI
        self.progress_container.setVisible(False)

    def create_buttons(self):
        """Creates buttons for displaying decomposition results."""
        # Mapping button is initially disabled and will be enabled if files are detected
        self.btn_apply_mapping = QPushButton("Apply Mapping")
        self.btn_apply_mapping.setStyleSheet(Styles.button_secondary())
        self.btn_apply_mapping.setToolTip("Map decomposition results to their source channel selection files")
        self.btn_apply_mapping.clicked.connect(self.open_mapping_dialog)
        self.btn_apply_mapping.setEnabled(False)
        self.buttons.append(self.btn_apply_mapping)

        # Button to export JSON files to MUEdit format
        self.btn_export_to_muedit = QPushButton("Export to MUEdit")
        self.btn_export_to_muedit.setStyleSheet(Styles.button_secondary())
        self.btn_export_to_muedit.setToolTip("Convert OpenHD-EMG JSON files to MUEdit MAT format")
        self.btn_export_to_muedit.clicked.connect(self.export_json_to_muedit)
        self.btn_export_to_muedit.setEnabled(False)
        self.buttons.append(self.btn_export_to_muedit)

        # Button to launch MUEdit
        self.btn_launch_muedit = QPushButton("Open MUEdit")
        self.btn_launch_muedit.setStyleSheet(Styles.button_secondary())
        self.btn_launch_muedit.setToolTip("Launch MUEdit for manual cleaning of decomposition results")
        self.btn_launch_muedit.clicked.connect(self.launch_muedit)
        self.btn_launch_muedit.setEnabled(False)
        self.buttons.append(self.btn_launch_muedit)

        self.btn_show_results = LoadingButton("Show Decomposition Results")
        self.btn_show_results.setStyleSheet(Styles.button_primary())
        self.btn_show_results.setToolTip("Open OpenHD-EMG to view decomposition results")
        self.btn_show_results.clicked.connect(self.display_results)
        self.buttons.append(self.btn_show_results)

    def export_json_to_muedit(self):
        """Export all OpenHD-EMG JSON files to MUEdit MAT format."""
        if not self.resultfiles:
            self.warn("No decomposition files found to export.")
            return

        # Filter for JSON files only
        json_files = [f for f in self.resultfiles if f.endswith('.json')]
        if not json_files:
            self.warn("No JSON files found. Only JSON files can be exported to MUEdit format.")
            return

        logger.info(f"Exporting {len(json_files)} JSON file(s) to MUEdit format...")
        success_count = 0
        error_count = 0
        error_messages = []

        for json_file in json_files:
            try:
                # Check if MUEdit file already exists
                if is_muedit_file_exists(json_file):
                    logger.info(f"MUEdit file already exists for {os.path.basename(json_file)}, skipping...")
                    continue

                # Export to MUEdit format
                muedit_file = export_to_muedit_mat(json_file)
                if muedit_file:
                    success_count += 1
                    logger.info(f"Successfully exported: {os.path.basename(muedit_file)}")
            except Exception as e:
                error_count += 1
                error_msg = f"Failed to export {os.path.basename(json_file)}: {str(e)}"
                error_messages.append(error_msg)
                logger.error(error_msg)

        # Update file list to include new MUEdit files
        self.get_decomposition_results()

        # Show summary to user
        if success_count > 0 and error_count == 0:
            self.success(f"Successfully exported {success_count} file(s) to MUEdit format.")
            self.btn_launch_muedit.setEnabled(True)
        elif success_count > 0 and error_count > 0:
            self.warn(f"Exported {success_count} file(s) successfully, but {error_count} file(s) failed:\n" +
                     "\n".join(error_messages))
            self.btn_launch_muedit.setEnabled(True)
        else:
            self.error(f"Failed to export files:\n" + "\n".join(error_messages))

    def _launch_muedit_via_matlab_engine(self):
        """
        Launch MUEdit using MATLAB Engine API.
        Reuses existing MATLAB session if available, otherwise starts a new one.
        Returns: (success: bool, message: str)
        """
        try:
            import matlab.engine
        except ImportError:
            return False, "MATLAB Engine API not available (pip install matlabengine)"

        try:
            # Get MUEdit path from config
            muedit_path = config.get(Settings.MUEDIT_PATH)

            # Find running MATLAB sessions
            engines = matlab.engine.find_matlab()

            if engines:
                logger.info(f"Found {len(engines)} running MATLAB session(s), connecting to first one...")
                eng = matlab.engine.connect_matlab(engines[0])
                logger.info("Connected to existing MATLAB session")
            else:
                logger.info("No running MATLAB session found, starting new session...")
                eng = matlab.engine.start_matlab()
                logger.info("Started new MATLAB session")

            # Add MUEdit to path if configured and not already present
            if muedit_path and os.path.exists(muedit_path):
                # Check if path is already in MATLAB's path
                current_path = eng.path(nargout=1)
                if muedit_path not in current_path:
                    logger.info(f"Adding MUEdit path to MATLAB: {muedit_path}")
                    eng.addpath(muedit_path, nargout=0)
                else:
                    logger.debug(f"MUEdit path already in MATLAB path, skipping addpath")

            # Launch MUEdit GUI
            logger.info("Launching MUEdit GUI in MATLAB session...")
            eng.eval("MUedit_exported", nargout=0, background=True)

            return True, "MUEdit launched successfully in MATLAB session"

        except Exception as e:
            return False, f"Failed to launch via MATLAB Engine: {str(e)}"

    def _launch_muedit_via_matlab_cli(self):
        """
        Launch MUEdit by starting a new MATLAB process via command line.
        Returns: (success: bool, message: str)
        """
        try:
            muedit_path = config.get(Settings.MUEDIT_PATH)

            # Build MATLAB command - check if path exists before adding
            if muedit_path and os.path.exists(muedit_path):
                # Use contains() to check if path is already present
                matlab_cmd = (
                    f"if ~contains(path, '{muedit_path}'), "
                    f"addpath('{muedit_path}'); "
                    f"end; "
                    f"MUedit"
                )
            else:
                matlab_cmd = "MUedit"

            logger.info(f"Starting MATLAB with command: {matlab_cmd}")
            subprocess.Popen(["matlab", "-automation", "-r", matlab_cmd])

            return True, "MUEdit launched via MATLAB CLI"

        except FileNotFoundError:
            return False, "MATLAB executable not found in PATH"
        except Exception as e:
            return False, f"Failed to launch via MATLAB CLI: {str(e)}"

    def _launch_muedit_standalone(self):
        """
        Launch MUEdit as a standalone command.
        Returns: (success: bool, message: str)
        """
        try:
            logger.info("Launching MUEdit as standalone executable...")
            subprocess.Popen(["muedit"])
            return True, "MUEdit launched as standalone executable"
        except FileNotFoundError:
            return False, "MUEdit executable not found in PATH"
        except Exception as e:
            return False, f"Failed to launch standalone: {str(e)}"

    def launch_muedit(self):
        """
        Launches MUEdit for manual cleaning of decomposition results.
        Shows instruction dialog to guide the user.
        """
        logger.info("Launching MUEdit for manual cleaning...")

        # Get configured launch method (default to AUTO)
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
                self.success(f"{message}")
                self._show_instruction_dialog()
                return
            else:
                self.error(message)
                return

        elif launch_method == MUEditLaunchMethod.MATLAB_CLI:
            success, message = self._launch_muedit_via_matlab_cli()
            if success:
                self.success(f"{message}")
                self._show_instruction_dialog()
                return
            else:
                self.error(message)
                return

        elif launch_method == MUEditLaunchMethod.STANDALONE:
            success, message = self._launch_muedit_standalone()
            if success:
                self.success(f"{message}")
                self._show_instruction_dialog()
                return
            else:
                self.error(message)
                return

        # AUTO mode: Try all methods with intelligent fallback
        elif launch_method == MUEditLaunchMethod.AUTO:
            # 1. Try MATLAB Engine (best option - reuses existing session)
            success, message = self._launch_muedit_via_matlab_engine()
            if success:
                logger.info(f"AUTO mode: {message}")
                self.success(f"{message}")
                self._show_instruction_dialog()
                return
            else:
                logger.debug(f"AUTO mode: MATLAB Engine failed - {message}")

            # 2. Try MATLAB CLI (second best - starts new session)
            success, message = self._launch_muedit_via_matlab_cli()
            if success:
                logger.info(f"AUTO mode: {message}")
                self.success(f"{message}")
                self._show_instruction_dialog()
                return
            else:
                logger.debug(f"AUTO mode: MATLAB CLI failed - {message}")

            # 3. Try standalone (last resort)
            success, message = self._launch_muedit_standalone()
            if success:
                logger.info(f"AUTO mode: {message}")
                self.success(f"{message}")
                self._show_instruction_dialog()
                return
            else:
                logger.debug(f"AUTO mode: Standalone failed - {message}")

            # All methods failed
            self.error(
                "Failed to launch MUEdit using any available method.\n\n"
                "Please ensure one of the following:\n"
                "1. MATLAB Engine API is installed (pip install matlabengine) and MATLAB is running\n"
                "2. MATLAB is installed and accessible via PATH\n"
                "3. MUEdit is available as a standalone executable\n\n"
                "Repository: https://github.com/haripen/MUedit/tree/devHP\n"
                "Configure MUEdit path and launch method in Settings."
            )

    def _show_instruction_dialog(self):
        """Shows the instruction dialog for manual MUEdit workflow."""
        dialog = MUEditInstructionDialog(
            muedit_files=self.muedit_files,
            edited_files=self.edited_files,
            folder_path=self.expected_folder,
            parent=self
        )
        dialog.exec_()

    def display_results(self):
        """Displays the decomposition results in the UI."""
        results_path = self.get_decomposition_results()
        self.btn_show_results.start_loading()
        if not results_path:
            return
        self.start_openhdemg(self.btn_show_results.stop_loading)
        self.resultsDisplayed.emit(results_path)
        self.complete_step()  # Mark step as complete

    def start_openhdemg(self, on_started_callback=None):
        """Starts the OpenHD-EMG application and optionally calls a callback when it appears to be running."""
        if not config.get(Settings.OPENHDEMG_INSTALLED) or None:
            self.warn("OpenHD-EMG virtual environment path is not set or invalid. Please set it in Settings first.")
            return

        logger.info(f"Starting openhdemg!")
        command = ["openhdemg", "-m", "openhdemg.gui.openhdemg_gui"]
        proc = subprocess.Popen(command)

        # Starten eines Threads, der nach einer kurzen Zeit prüft, ob der Prozess noch läuft.
        def poll_process():
            time.sleep(2)
            if proc.poll() is None:
                logger.debug("OpenHD-EMG has started.")
                if on_started_callback:
                    on_started_callback()
            else:
                logger.error("OpenHD-EMG terminated unexpectedly.")

        threading.Thread(target=poll_process, daemon=True).start()

    def get_decomposition_results(self):
        """
        Retrieves the decomposition results from the decomposition_auto folder.

        File workflow:
        1. Original files: .json or .pkl (decomposition results)
        2. MUEdit export: *_muedit.mat (exported for manual cleaning)
        3. Edited files: *_muedit_edited.mat (manually cleaned in MUEdit)

        Progress tracking is based on _muedit.mat files being edited to _muedit_edited.mat
        """
        self.resultfiles = []
        self.error_messages = []
        self.original_decomp_files = []
        self.muedit_files = []
        self.edited_files = []

        folder_content_widget = global_state.get_widget("folder_content")
        if not os.path.exists(self.expected_folder):
            self.error("The decomposition_auto folder does not exist or is not accessible from the application.")
            self.btn_apply_mapping.setEnabled(False)
            self.btn_export_to_muedit.setEnabled(False)
            self.btn_launch_muedit.setEnabled(False)
            self.progress_container.setVisible(False)
            return None

        # First pass: identify muedit files and original files
        all_mat_files = []
        for file in os.listdir(self.expected_folder):
            file_path = os.path.join(self.expected_folder, file)

            # Collect all .mat files for second pass
            if file.endswith(".mat"):
                all_mat_files.append(file)

            # Check for MUEdit export files (ready for editing)
            # Support both single-grid (_muedit.mat) and multi-grid (_multigrid_muedit.mat) variants
            if file.endswith("_muedit.mat") or file.endswith("_multigrid_muedit.mat"):
                logger.debug(f"MUEdit MAT file (for editing): {file}")
                # Extract base name: filename_muedit.mat -> filename or filename_multigrid_muedit.mat -> filename
                if file.endswith("_multigrid_muedit.mat"):
                    base_name = file.replace("_multigrid_muedit.mat", "")
                else:
                    base_name = file.replace("_muedit.mat", "")
                self.muedit_files.append(base_name)

            # Check for original decomposition results
            elif file.endswith(".json") or file.endswith(".pkl"):
                logger.info(f"Original decomposition file found: {file}")
                self.resultfiles.append(file_path)
                # Extract base name for tracking (without extension)
                base_name = os.path.splitext(file)[0]
                self.original_decomp_files.append(base_name)

        # Second pass: check which muedit files have been edited
        # Look for any .mat file that contains the base name (flexible naming)
        for base_name in self.muedit_files:
            # Check if any .mat file exists that:
            # 1. Contains the base_name
            # 2. Is NOT the original _muedit.mat or _multigrid_muedit.mat file
            # 3. Is a .mat file (edited result from MUEdit)

            muedit_file_single = f"{base_name}_muedit.mat"
            muedit_file_multi = f"{base_name}_multigrid_muedit.mat"

            for mat_file in all_mat_files:
                # Skip the original _muedit.mat or _multigrid_muedit.mat file itself
                if mat_file == muedit_file_single or mat_file == muedit_file_multi:
                    continue

                # Check if this .mat file contains the base name
                # This handles files like: basename_muedit.mat_edited.mat, basename_edited.mat, etc.
                if base_name in mat_file and mat_file.endswith(".mat"):
                    logger.info(f"Edited file detected for {base_name}: {mat_file}")
                    self.edited_files.append(base_name)
                    break  # Only count once per base_name

        # Update UI based on files found
        if self.resultfiles:
            folder_content_widget.update_folder_content()
            self.btn_apply_mapping.setEnabled(True)

            # Enable "Export to MUEdit" button logic:
            # Only enable if there are JSON files WITHOUT corresponding _muedit.mat files
            json_files_needing_export = []
            for f in self.resultfiles:
                if f.endswith('.json'):
                    base_name = os.path.splitext(os.path.basename(f))[0]
                    if base_name not in self.muedit_files:
                        json_files_needing_export.append(base_name)

            should_enable_export = len(json_files_needing_export) > 0
            self.btn_export_to_muedit.setEnabled(should_enable_export)

            if should_enable_export:
                logger.info(f"Export button enabled: {len(json_files_needing_export)} files need export")
            else:
                logger.info("Export button disabled: All JSON files already have _muedit.mat files")

            # Enable "Open MUEdit" button if _muedit.mat files exist
            has_muedit_files = len(self.muedit_files) > 0
            self.btn_launch_muedit.setEnabled(has_muedit_files)

            if has_muedit_files:
                logger.info(f"MUEdit launch button enabled: {len(self.muedit_files)} _muedit.mat files found")

            # Show and update progress UI
            self.update_progress_ui()

            # If mapping exists, process mapped files
            self.process_mapped_files()
        else:
            self.btn_apply_mapping.setEnabled(False)
            self.btn_export_to_muedit.setEnabled(False)
            self.btn_launch_muedit.setEnabled(False)
            self.progress_container.setVisible(False)

        if self.resultfiles and not self.error_messages:
            return self.resultfiles
        elif self.resultfiles and self.error_messages:
            self.warn(*self.error_messages)
            return self.resultfiles

        return None

    def update_progress_ui(self):
        """
        Updates the progress UI to show MUEdit cleaning status.

        Progress tracking logic:
        - Tracks both _muedit.mat and _multigrid_muedit.mat files (files that need manual cleaning)
        - Shows which files have been edited (_muedit_edited.mat exists)
        - Progress: edited_files / muedit_files
        - Supports both single-grid and multi-grid recordings
        """
        # Only show progress if there are _muedit.mat files to track
        if not self.muedit_files:
            self.progress_container.setVisible(False)
            return

        # Show progress container
        self.progress_container.setVisible(True)

        # Calculate progress based on _muedit.mat files
        total_muedit_files = len(self.muedit_files)
        edited_count = len(self.edited_files)
        progress_percentage = int((edited_count / total_muedit_files) * 100) if total_muedit_files > 0 else 0

        # Update progress bar and label
        self.progress_bar.setValue(progress_percentage)
        self.progress_label.setText(
            f"Manual Cleaning Progress: {edited_count}/{total_muedit_files} files ({progress_percentage}%)"
        )

        # Clear existing file status items
        for i in reversed(range(self.file_status_layout.count())):
            widget = self.file_status_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Create file status items for each _muedit.mat file
        for base_name in self.muedit_files:
            # Check if this file has been edited (_muedit_edited.mat exists)
            is_edited = base_name in self.edited_files

            # Create status label
            if is_edited:
                status_text = f"✅ {base_name} (cleaned)"
                status_color = Colors.GREEN_700
            else:
                status_text = f"⏳ {base_name} (needs cleaning)"
                status_color = Colors.TEXT_MUTED

            status_label = QLabel(status_text)
            status_label.setStyleSheet(f"""
                color: {status_color};
                padding: 4px;
                font-size: 12px;
            """)
            self.file_status_layout.addWidget(status_label)

        # Add stretch to push items to top
        self.file_status_layout.addStretch()

        # Check if all _muedit.mat files have been cleaned
        if edited_count == total_muedit_files and total_muedit_files > 0:
            self.success(f"All {total_muedit_files} files have been cleaned in MUEdit!")
            # Could auto-complete step here if desired

    def process_file_with_channel(self, file_path, channel_selection):
        """
        Processes a .pkl file using its associated channel selection file.
        Calls the update_extras_in_pickle_file method with the channel selection info.
        """
        _, file_extension = os.path.splitext(file_path)
        if file_extension == ".pkl" or file_extension == ".json" and file_path not in self.processed_files:
            logger.info(f"Processing {file_extension} file: {file_path} with channel selection: {channel_selection}")
            self.processed_files.append(file_path)
            try:
                if file_extension == ".pkl":
                    update_extras_in_pickle_file(file_path, channel_selection)
                elif file_extension == ".json":
                    update_extras_in_json_file(file_path, channel_selection)
                self.btn_show_results.setEnabled(True)
                self.btn_apply_mapping.setEnabled(False)
            except ValueError as e:
                error_msg = f"Error processing {file_path}: {str(e)}"
                self.error_messages.append(error_msg)
                logger.error(error_msg)
                self.warn("\n".join(self.error_messages))

    def init_file_checking(self):
        self.expected_folder = global_state.get_decomposition_path()
        self.watcher.addPath(self.expected_folder)
        logger.info(f"File checking initialized for folder: {self.expected_folder}")
        self.get_decomposition_results()

    def check(self):
        venv_openhdemg = config.get(Settings.OPENHDEMG_INSTALLED)
        if venv_openhdemg is None or False:
            self.warn("openhdemg is not installed. Please download it in Settings first.")
        else:
            self.clear_status()
            self.setActionButtonsEnabled(True)

        try:
            self.expected_folder = global_state.get_decomposition_path()
            self.clear_status()
            logger.info(f"Decomposition folder set to: {self.expected_folder}")
        except ValueError:
            self.setActionButtonsEnabled(False)

    def open_mapping_dialog(self):
        """
        Opens the mapping dialog to allow the user to create a 1:1 mapping between
        decomposition files and channel selection files.
        """
        dialog = MappingDialog(existing_mapping=self.decomp_mapping)
        if dialog.exec_() == QDialog.Accepted:
            self.decomp_mapping = dialog.mapping
            logger.info(f"Mapping dialog accepted. Mapping: {self.decomp_mapping}")
            # If a mapping has been performed, process each mapped file
            self.process_mapped_files()
        else:
            logger.info("Mapping dialog canceled.")

    def process_mapped_files(self):
        if self.decomp_mapping is not None:
            for file_path in self.resultfiles:
                file_name = os.path.basename(file_path)
                if file_name in self.decomp_mapping:
                    chan_file = self.decomp_mapping[file_name]
                    chan_file = os.path.join(global_state.get_channel_selection_path(), chan_file)
                    logger.info(f"Processing file {file_path} with channel selection file {chan_file}.")
                    self.process_file_with_channel(file_path, chan_file)
