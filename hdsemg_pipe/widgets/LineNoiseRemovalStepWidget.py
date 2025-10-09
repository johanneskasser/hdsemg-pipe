import os
from PyQt5.QtWidgets import QMessageBox, QPushButton, QProgressBar, QVBoxLayout
from PyQt5.QtCore import Qt

from hdsemg_pipe.actions.workers import (
    LineNoiseRemovalWorker,
    MatlabCleanLineWorker,
    MatlabLineNoiseRemovalWorker,
    OctaveLineNoiseRemovalWorker
)
from hdsemg_pipe.config.config_enums import Settings, LineNoiseRegion, LineNoiseMethod
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.loadingbutton import LoadingButton
from hdsemg_pipe.widgets.BaseStepWidget import BaseStepWidget
from hdsemg_pipe.widgets.LineNoiseInfoDialog import LineNoiseInfoDialog


class LineNoiseRemovalStepWidget(BaseStepWidget):
    def __init__(self, step_index):
        """Step for removing line noise from HD-sEMG data."""
        super().__init__(step_index, "Line Noise Removal", "Remove power line noise (50/60 Hz) from EMG signals.")
        self.processed_files = 0
        self.total_files = 0
        self.current_worker = None

        # Setup additional info area with method display and progress
        self.setup_additional_info()

        # Update initial display
        self.update_method_display()

    def setup_additional_info(self):
        """Setup the additional information area with method and progress display."""
        # Clear the default layout
        while self.col_additional.count():
            child = self.col_additional.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Create a vertical layout for method and progress info
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        # Method label
        self.method_label = QPushButton()
        self.method_label.setFlat(True)
        self.method_label.setStyleSheet("text-align: left; padding: 2px;")
        self.method_label.clicked.connect(self.show_info_dialog)
        self.method_label.setCursor(Qt.PointingHandCursor)
        info_layout.addWidget(self.method_label)

        # Progress info container
        progress_container = QVBoxLayout()
        progress_container.setSpacing(2)

        # Files counter label
        self.files_label = QPushButton("Files: 0/0")
        self.files_label.setFlat(True)
        self.files_label.setStyleSheet("text-align: left; padding: 2px; font-size: 10px;")
        progress_container.addWidget(self.files_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setVisible(False)  # Hidden by default
        progress_container.addWidget(self.progress_bar)

        info_layout.addLayout(progress_container)

        # Add to the column
        self.col_additional.addLayout(info_layout)

    def create_buttons(self):
        """Creates the buttons for line noise removal."""
        # Info button to explain methods
        self.btn_info = QPushButton("Methods Info")
        self.btn_info.clicked.connect(self.show_info_dialog)
        self.buttons.append(self.btn_info)

        # Main processing button
        self.btn_remove_noise = LoadingButton("Remove Noise")
        self.btn_remove_noise.clicked.connect(self.start_processing)
        self.buttons.append(self.btn_remove_noise)

    def show_info_dialog(self):
        """Show information dialog about line noise removal methods."""
        dialog = LineNoiseInfoDialog(self)
        dialog.exec_()

    def start_processing(self):
        """Starts line noise removal processing and updates progress dynamically."""
        if not global_state.associated_files:
            logger.warning("No .mat files found for line noise removal.")
            self.warn("No files available for processing.")
            return

        logger.debug("Starting line noise removal processing.")
        self.btn_remove_noise.setEnabled(False)
        self.btn_remove_noise.start_loading()

        # Ensure output directory exists
        output_dir = global_state.get_line_noise_cleaned_path()
        os.makedirs(output_dir, exist_ok=True)

        self.processed_files = 0
        self.total_files = len(global_state.associated_files)
        self.update_progress(self.processed_files, self.total_files)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Clear the list of cleaned files at the start
        global_state.line_noise_cleaned_files.clear()

        self.process_next_file()

    def process_next_file(self):
        """Process the next file in the queue."""
        if self.processed_files < self.total_files:
            file_path = global_state.associated_files[self.processed_files]
            logger.info(f"Processing file {self.processed_files + 1}/{self.total_files}: {file_path}")

            # Get line noise frequencies based on region setting
            line_freqs = self.get_line_noise_frequencies()

            # Get selected method from config
            method = config.get(Settings.LINE_NOISE_METHOD, LineNoiseMethod.MNE_SPECTRUM_FIT.value)

            # Create appropriate worker based on method
            try:
                self.current_worker = self.create_worker(file_path, line_freqs, method)
                self.current_worker.finished.connect(self.on_file_processed)
                self.current_worker.error.connect(self.on_processing_error)
                self.current_worker.start()
            except Exception as e:
                error_msg = f"Failed to create worker: {str(e)}"
                logger.error(error_msg, exc_info=True)
                self.on_processing_error(error_msg)
        else:
            # All files processed
            self.finalize_processing()

    def create_worker(self, file_path, line_freqs, method):
        """Create the appropriate worker based on selected method."""
        if method == LineNoiseMethod.MNE_NOTCH.value:
            logger.info("Using MNE-Python Notch Filter (FIR)")
            return LineNoiseRemovalWorker(file_path, line_freqs=line_freqs, method='notch')

        elif method == LineNoiseMethod.MNE_SPECTRUM_FIT.value:
            logger.info("Using MNE-Python Spectrum Fit (Adaptive)")
            return LineNoiseRemovalWorker(file_path, line_freqs=line_freqs, method='spectrum_fit')

        elif method == LineNoiseMethod.MATLAB_CLEANLINE.value:
            # Check if MATLAB is available
            if not config.get(Settings.MATLAB_INSTALLED, False):
                raise RuntimeError("MATLAB is not available. Please install MATLAB Engine for Python or choose a different method in Settings.")
            logger.info("Using MATLAB CleanLine (EEGLAB Plugin)")
            return MatlabCleanLineWorker(file_path, line_freqs=line_freqs)

        elif method == LineNoiseMethod.MATLAB_IIR.value:
            # Check if MATLAB is available
            if not config.get(Settings.MATLAB_INSTALLED, False):
                raise RuntimeError("MATLAB is not available. Please install MATLAB Engine for Python or choose a different method in Settings.")
            logger.info("Using MATLAB IIR Notch Filter")
            return MatlabLineNoiseRemovalWorker(file_path, line_freqs=line_freqs)

        elif method == LineNoiseMethod.OCTAVE.value:
            # Check if Octave is available
            if not config.get(Settings.OCTAVE_INSTALLED, False):
                raise RuntimeError("Octave is not available. Please install Octave and oct2py or choose a different method in Settings.")
            logger.info("Using Octave IIR Notch Filter")
            return OctaveLineNoiseRemovalWorker(file_path, line_freqs=line_freqs)

        else:
            # Default to MNE Spectrum Fit
            logger.warning(f"Unknown method '{method}', defaulting to MNE Spectrum Fit")
            return LineNoiseRemovalWorker(file_path, line_freqs=line_freqs, method='spectrum_fit')

    def on_file_processed(self):
        """Called when a single file has been successfully processed."""
        self.processed_files += 1
        self.update_progress(self.processed_files, self.total_files)

        # Process next file
        self.process_next_file()

    def on_processing_error(self, error_msg):
        """Called when an error occurs during processing."""
        logger.error(f"Processing error: {error_msg}")
        self.error(f"Error processing file: {error_msg}")
        self.btn_remove_noise.stop_loading()
        self.btn_remove_noise.setEnabled(True)
        self.progress_bar.setVisible(False)

    def finalize_processing(self):
        """Called when all files have been processed."""
        self.btn_remove_noise.stop_loading()
        self.progress_bar.setVisible(False)

        # Verify all files were processed
        if len(global_state.line_noise_cleaned_files) == self.total_files:
            logger.info(f"Successfully processed {self.total_files} files.")
            self.complete_step()
            QMessageBox.information(
                self,
                "Success",
                f"Line noise removal completed for {self.total_files} files."
            )
        else:
            error_msg = f"Expected {self.total_files} files, but only {len(global_state.line_noise_cleaned_files)} were processed."
            logger.error(error_msg)
            self.error(error_msg)
            self.btn_remove_noise.setEnabled(True)

    def update(self, path):
        """Updates the label when a file or folder is selected."""
        self.total_files = len(global_state.associated_files)
        self.update_progress(self.processed_files, self.total_files)
        self.update_method_display()
        if self.total_files != 0:
            self.setActionButtonsEnabled(True)

    def update_progress(self, processed, total):
        """Updates the progress display dynamically."""
        # Update files counter
        self.files_label.setText(f"Files: {processed}/{total}")

        # Update progress bar
        if total > 0:
            percentage = int((processed / total) * 100)
            self.progress_bar.setValue(percentage)

        # Mark step as complete when all files are processed
        if processed >= total > 0:
            self.btn_remove_noise.stop_loading()
            self.progress_bar.setVisible(False)

    def check(self):
        """Check if this step can be enabled and validate method availability."""
        # Update method display
        self.update_method_display()

        # Get selected method
        method = config.get(Settings.LINE_NOISE_METHOD, LineNoiseMethod.MNE_SPECTRUM_FIT.value)

        # Check if selected method is available
        if method in [LineNoiseMethod.MATLAB_CLEANLINE.value, LineNoiseMethod.MATLAB_IIR.value]:
            if not config.get(Settings.MATLAB_INSTALLED, False):
                self.warn("MATLAB is not available. Please install MATLAB Engine or select a different method in Settings.")
                self.setActionButtonsEnabled(False)
                return

        elif method == LineNoiseMethod.OCTAVE.value:
            if not config.get(Settings.OCTAVE_INSTALLED, False):
                self.warn("Octave is not available. Please install Octave and oct2py or select a different method in Settings.")
                self.setActionButtonsEnabled(False)
                return

        self.clear_status()
        self.setActionButtonsEnabled(True)

    def update_method_display(self):
        """Update the display of the current method."""
        method = config.get(Settings.LINE_NOISE_METHOD, LineNoiseMethod.MNE_SPECTRUM_FIT.value)
        region = config.get(Settings.LINE_NOISE_REGION, LineNoiseRegion.US.value)

        # Get friendly method name
        method_names = {
            LineNoiseMethod.MNE_NOTCH.value: "⚡ MNE Notch (FIR)",
            LineNoiseMethod.MNE_SPECTRUM_FIT.value: "⭐ MNE Spectrum Fit",
            LineNoiseMethod.MATLAB_CLEANLINE.value: "🏆 MATLAB CleanLine",
            LineNoiseMethod.MATLAB_IIR.value: "🔬 MATLAB IIR",
            LineNoiseMethod.OCTAVE.value: "🐙 Octave IIR"
        }

        method_name = method_names.get(method, method)

        # Get region info
        if region == LineNoiseRegion.EU.value:
            region_info = "50 Hz (EU)"
        else:
            region_info = "60 Hz (US)"

        # Update label
        self.method_label.setText(f"Method: {method_name} | {region_info}")
        self.method_label.setToolTip("Click for detailed method information")

    def get_line_noise_frequencies(self):
        """Get line noise frequencies based on user's region setting."""
        region = config.get(Settings.LINE_NOISE_REGION, LineNoiseRegion.US.value)

        if region == LineNoiseRegion.EU.value:
            # European power line frequency (50 Hz + harmonics)
            return [50, 100, 150, 200]
        else:
            # US/North American power line frequency (60 Hz + harmonics)
            return [60, 120, 180, 240]

    def complete_step(self, processed_files: int | None = None):
        """Mark the step as completed."""
        # Refresh counts
        self.total_files = len(global_state.line_noise_cleaned_files)
        self.processed_files = processed_files if processed_files is not None else self.total_files

        # Update the progress display
        self.update_progress(self.processed_files, self.total_files)

        # Make sure the loading spinner is off
        self.btn_remove_noise.stop_loading()

        # Hide progress bar when complete
        self.progress_bar.setVisible(False)

        # Mark the step as complete (signals, styling, etc.)
        super().complete_step()
