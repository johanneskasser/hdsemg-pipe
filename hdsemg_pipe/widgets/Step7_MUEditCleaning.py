"""
Step 7: MUEdit Manual Cleaning

This step launches MUEdit for manual cleaning of decomposition results
and monitors progress.
"""
import os
import subprocess
from PyQt5.QtCore import QFileSystemWatcher, QTimer
from PyQt5.QtWidgets import (
    QPushButton, QLabel, QVBoxLayout, QFrame, QScrollArea,
    QWidget, QProgressBar
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.widgets.MUEditInstructionDialog import MUEditInstructionDialog
from hdsemg_pipe.config.config_enums import Settings, MUEditLaunchMethod
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius, Fonts


class Step7_MUEditCleaning(BaseStepWidget):
    """
    Step 7: Manual cleaning with MUEdit.

    This step:
    - Launches MUEdit for manual cleaning
    - Shows instruction dialog
    - Monitors edited files with FileSystemWatcher
    - Tracks progress for each file
    - Completes when all files are edited
    """

    def __init__(self, step_index, step_name, tooltip, parent=None):
        super().__init__(step_index, step_name, tooltip, parent)

        self.expected_folder = None
        self.muedit_files = []
        self.edited_files = []
        self.last_file_count = 0

        # Initialize file system watcher
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.scan_muedit_files)

        # Add polling timer for reliable file detection (QFileSystemWatcher can miss events on Windows)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.scan_muedit_files)
        self.poll_timer.setInterval(2000)  # Check every 2 seconds

        # Create status UI
        self.create_status_ui()
        self.col_additional.addWidget(self.status_container)

        # Perform initial check
        self.check()

    def create_status_ui(self):
        """Create compact status UI with progress tracking."""
        self.status_container = QFrame()
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setSpacing(Spacing.SM)
        status_layout.setContentsMargins(0, 0, 0, 0)

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

    def scan_muedit_files(self):
        """Scan for MUEdit files and track progress."""
        if not os.path.exists(self.expected_folder):
            return

        # Find all _muedit.mat files
        muedit_files = []
        edited_files = []

        for file in os.listdir(self.expected_folder):
            if file.endswith('_muedit.mat') or file.endswith('_multigrid_muedit.mat'):
                full_path = os.path.join(self.expected_folder, file)
                muedit_files.append(full_path)

                # Check if edited version exists
                # MUEdit creates files by appending "_edited.mat" to the entire filename
                # e.g., "file_muedit.mat" -> "file_muedit.mat_edited.mat"
                edited_path = os.path.join(self.expected_folder, file + '_edited.mat')
                if os.path.exists(edited_path):
                    edited_files.append(edited_path)

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
                    eng.addpath(muedit_path, nargout=0)

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
                    f"addpath('{muedit_path}'); "
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
