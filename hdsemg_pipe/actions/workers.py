import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.state.global_state import global_state
from hdsemg_shared.fileio.file_io import EMGFile
import numpy as np

class ChannelSelectionWorker(QThread):
    finished = pyqtSignal()  # Signal emitted when the process is completed

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        """Starts the Channel Selection application and waits for it to complete."""
        logger.info(f"Processing: {self.file_path}")

        output_filepath = self.get_output_filepath()

        # Define the command with start parameters
        command = ["hdsemg-select", "--inputFile", self.file_path, "--outputFile", output_filepath]

        try:
            # Start the application
            logger.info(f"Starting Channel Selection app: {command}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait for the process to finish
            stdout, stderr = process.communicate()

            # Log output
            if stdout:
                logger.info(stdout.decode("utf-8"))
            if stderr:
                logger.error(stderr.decode("utf-8"))

            # Notify that processing is done
            self.finished.emit()

        except Exception as e:
            logger.error(f"Failed to start Channel Selection app: {e}")

    def get_output_filepath(self):
        filename = os.path.basename(self.file_path)
        workfolder = global_state.workfolder
        output_filepath = os.path.join(workfolder, "channelselection", filename)
        output_filepath = os.path.normpath(output_filepath)
        return output_filepath


class LineNoiseRemovalWorker(QThread):
    """Worker thread for removing line noise from EMG data using MNE."""
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, file_path, line_freqs=None, sampling_freq=None, method='spectrum_fit'):
        super().__init__()
        self.file_path = file_path
        self.line_freqs = line_freqs if line_freqs is not None else [60, 120, 180, 240]
        self.sampling_freq = sampling_freq
        self.method = method  # 'notch' or 'spectrum_fit'

    def run(self):
        """Apply line noise removal and save the cleaned file."""
        try:
            logger.info(f"Processing line noise removal for: {self.file_path}")
            logger.info(f"Using MNE method: {self.method}")

            # Load the EMG file
            emg = EMGFile.load(self.file_path)

            # Get sampling frequency from file if not provided
            if self.sampling_freq is None:
                if hasattr(emg, 'sampling_frequency') and emg.sampling_frequency is not None:
                    self.sampling_freq = emg.sampling_frequency
                elif hasattr(emg, 'fsamp') and emg.fsamp is not None:
                    self.sampling_freq = emg.fsamp
                else:
                    # Default to 2048 Hz if not found (common for HD-sEMG)
                    self.sampling_freq = 2048
                    logger.warning(f"Sampling frequency not found in file, using default: {self.sampling_freq} Hz")

            logger.info(f"Using sampling frequency: {self.sampling_freq} Hz")
            logger.info(f"Removing line noise at frequencies: {self.line_freqs} Hz")

            # Apply notch filter using MNE
            # MNE expects data in shape (n_channels, n_times), but EMGFile.data is (n_times, n_channels)
            # So we need to transpose
            data_transposed = emg.data.T  # shape: (n_channels, n_times)

            # Import MNE filter function
            from mne.filter import notch_filter

            # Apply the notch filter with selected method
            if self.method == 'notch':
                # Simple notch filter (FIR)
                cleaned_data_transposed = notch_filter(
                    data_transposed,
                    Fs=self.sampling_freq,
                    freqs=self.line_freqs,
                    method='fir',
                    filter_length='auto',
                    notch_widths=None,
                    trans_bandwidth=1.0,
                    verbose=False
                )
            else:
                # Spectrum fit method (adaptive, similar to CleanLine)
                cleaned_data_transposed = notch_filter(
                    data_transposed,
                    Fs=self.sampling_freq,
                    freqs=self.line_freqs,
                    method='spectrum_fit',
                    filter_length='auto',
                    notch_widths=None,
                    trans_bandwidth=1.0,
                    verbose=False
                )

            # Transpose back to original shape (n_times, n_channels)
            emg.data = cleaned_data_transposed.T

            # Get output file path
            output_filepath = self.get_output_filepath()

            # Save the cleaned data
            emg.save(output_filepath)
            logger.info(f"Saved cleaned data to: {output_filepath}")

            # Add to global state
            if output_filepath not in global_state.line_noise_cleaned_files:
                global_state.line_noise_cleaned_files.append(output_filepath)

            self.finished.emit()

        except Exception as e:
            error_msg = f"Failed to process {self.file_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)

    def get_output_filepath(self):
        filename = os.path.basename(self.file_path)
        output_filepath = os.path.join(global_state.get_line_noise_cleaned_path(), filename)
        output_filepath = os.path.normpath(output_filepath)
        return output_filepath


class MatlabCleanLineWorker(QThread):
    """Worker thread for removing line noise using MATLAB CleanLine (EEGLAB plugin)."""
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, file_path, line_freqs=None):
        super().__init__()
        self.file_path = file_path
        self.line_freqs = line_freqs if line_freqs is not None else [60, 120, 180, 240]

    def run(self):
        """Apply line noise removal using MATLAB CleanLine and save the cleaned file."""
        try:
            logger.info(f"Processing line noise removal with MATLAB CleanLine for: {self.file_path}")

            import matlab.engine

            # Start MATLAB engine
            logger.info("Starting MATLAB engine...")
            eng = matlab.engine.start_matlab()

            # Load the EMG file
            emg = EMGFile.load(self.file_path)

            # Get sampling frequency
            if hasattr(emg, 'sampling_frequency') and emg.sampling_frequency is not None:
                fs = float(emg.sampling_frequency)
            elif hasattr(emg, 'fsamp') and emg.fsamp is not None:
                fs = float(emg.fsamp)
            else:
                fs = 2048.0
                logger.warning(f"Sampling frequency not found, using default: {fs} Hz")

            logger.info(f"Using sampling frequency: {fs} Hz")
            logger.info(f"Removing line noise at frequencies: {self.line_freqs} Hz")

            # Convert data to MATLAB format
            # CleanLine expects data as channels x samples
            data_matlab = matlab.double(emg.data.T.tolist())  # Transpose to channels x samples

            # Convert frequencies to MATLAB array
            freqs_matlab = matlab.double(self.line_freqs)

            # Initialize EEGLAB structure
            logger.info("Creating EEGLAB EEG structure...")
            eng.eval("EEG = struct();", nargout=0)
            eng.workspace['EEG'] = eng.struct()

            # Populate EEG structure with our data
            eng.eval(f"EEG.srate = {fs};", nargout=0)
            eng.workspace['EEG_data'] = data_matlab
            eng.eval("EEG.data = EEG_data;", nargout=0)
            eng.eval(f"EEG.pnts = {emg.data.shape[0]};", nargout=0)
            eng.eval(f"EEG.nbchan = {emg.data.shape[1]};", nargout=0)
            eng.eval("EEG.trials = 1;", nargout=0)
            eng.eval("EEG.xmin = 0;", nargout=0)
            eng.eval(f"EEG.xmax = {emg.data.shape[0] / fs};", nargout=0)

            # Try to add EEGLAB to path if not already there
            try:
                logger.info("Checking for EEGLAB...")
                eng.eval("eeglab_version = eeglab('version');", nargout=0)
                logger.info("EEGLAB found")
            except Exception as e:
                logger.warning(f"EEGLAB might not be on MATLAB path: {e}")
                logger.warning("Attempting to continue anyway...")

            # Call CleanLine
            logger.info("Calling CleanLine...")
            # CleanLine parameters:
            # - LineFrequencies: frequencies to remove
            # - Bandwidth: bandwidth for each frequency (default 2 Hz)
            # - SignalType: 'Channels' for channel data
            # - SmoothingFactor: for transition smoothing (default 100)
            # - VerboseOutput: verbosity level

            eng.workspace['line_freqs'] = freqs_matlab

            try:
                # Call CleanLine with parameters
                eng.eval("""
                EEG_clean = cleanline(EEG, ...
                    'LineFrequencies', line_freqs, ...
                    'Bandwidth', 2, ...
                    'SignalType', 'Channels', ...
                    'SmoothingFactor', 100, ...
                    'VerboseOutput', 0);
                """, nargout=0)

                # Get cleaned data
                cleaned_data_matlab = eng.eval("EEG_clean.data;")

            except Exception as e:
                error_msg = f"CleanLine execution failed: {str(e)}\n" \
                           f"Make sure CleanLine is installed in EEGLAB and EEGLAB is on MATLAB path."
                logger.error(error_msg)
                eng.quit()
                raise RuntimeError(error_msg)

            # Convert back to numpy array and transpose back to samples x channels
            cleaned_data = np.array(cleaned_data_matlab).T
            emg.data = cleaned_data

            # Get output file path
            output_filepath = self.get_output_filepath()

            # Save the cleaned data
            emg.save(output_filepath)
            logger.info(f"Saved cleaned data to: {output_filepath}")

            # Add to global state
            if output_filepath not in global_state.line_noise_cleaned_files:
                global_state.line_noise_cleaned_files.append(output_filepath)

            # Stop MATLAB engine
            eng.quit()

            self.finished.emit()

        except Exception as e:
            error_msg = f"Failed to process {self.file_path} with MATLAB CleanLine: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)

    def get_output_filepath(self):
        filename = os.path.basename(self.file_path)
        output_filepath = os.path.join(global_state.get_line_noise_cleaned_path(), filename)
        output_filepath = os.path.normpath(output_filepath)
        return output_filepath


class MatlabLineNoiseRemovalWorker(QThread):
    """Worker thread for removing line noise using MATLAB Engine."""
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, file_path, line_freqs=None):
        super().__init__()
        self.file_path = file_path
        self.line_freqs = line_freqs if line_freqs is not None else [60, 120, 180, 240]

    def run(self):
        """Apply line noise removal using MATLAB and save the cleaned file."""
        try:
            logger.info(f"Processing line noise removal with MATLAB for: {self.file_path}")

            import matlab.engine

            # Start MATLAB engine
            logger.info("Starting MATLAB engine...")
            eng = matlab.engine.start_matlab()

            # Load the EMG file
            emg = EMGFile.load(self.file_path)

            # Get sampling frequency
            if hasattr(emg, 'sampling_frequency') and emg.sampling_frequency is not None:
                fs = float(emg.sampling_frequency)
            elif hasattr(emg, 'fsamp') and emg.fsamp is not None:
                fs = float(emg.fsamp)
            else:
                fs = 2048.0
                logger.warning(f"Sampling frequency not found, using default: {fs} Hz")

            logger.info(f"Using sampling frequency: {fs} Hz")
            logger.info(f"Removing line noise at frequencies: {self.line_freqs} Hz")

            # Convert data to MATLAB format
            # MATLAB expects double array
            data_matlab = matlab.double(emg.data.tolist())

            # Convert frequencies to MATLAB array
            freqs_matlab = matlab.double(self.line_freqs)

            # Call MATLAB's notch filter (using built-in iirnotch and filtfilt)
            # This creates a notch filter for each frequency
            filtered_data = data_matlab
            for freq in self.line_freqs:
                # Design notch filter
                # wo = freq / (fs/2), normalized frequency
                # bw = freq / 35, bandwidth
                logger.info(f"Applying notch filter at {freq} Hz")
                wo = freq / (fs / 2.0)
                bw = wo / 35.0

                # Create notch filter using iirnotch
                b, a = eng.iirnotch(wo, bw, nargout=2)

                # Apply filter to each column (channel)
                filtered_data = eng.filtfilt(b, a, filtered_data)

            # Convert back to numpy array
            cleaned_data = np.array(filtered_data)
            emg.data = cleaned_data

            # Get output file path
            output_filepath = self.get_output_filepath()

            # Save the cleaned data
            emg.save(output_filepath)
            logger.info(f"Saved cleaned data to: {output_filepath}")

            # Add to global state
            if output_filepath not in global_state.line_noise_cleaned_files:
                global_state.line_noise_cleaned_files.append(output_filepath)

            # Stop MATLAB engine
            eng.quit()

            self.finished.emit()

        except Exception as e:
            error_msg = f"Failed to process {self.file_path} with MATLAB: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)

    def get_output_filepath(self):
        filename = os.path.basename(self.file_path)
        output_filepath = os.path.join(global_state.get_line_noise_cleaned_path(), filename)
        output_filepath = os.path.normpath(output_filepath)
        return output_filepath


class OctaveLineNoiseRemovalWorker(QThread):
    """Worker thread for removing line noise using Octave via oct2py."""
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, file_path, line_freqs=None):
        super().__init__()
        self.file_path = file_path
        self.line_freqs = line_freqs if line_freqs is not None else [60, 120, 180, 240]

    def run(self):
        """Apply line noise removal using Octave and save the cleaned file."""
        try:
            logger.info(f"Processing line noise removal with Octave for: {self.file_path}")

            from oct2py import Oct2Py

            # Start Octave
            logger.info("Starting Octave...")
            oc = Oct2Py()

            # Load the EMG file
            emg = EMGFile.load(self.file_path)

            # Get sampling frequency
            if hasattr(emg, 'sampling_frequency') and emg.sampling_frequency is not None:
                fs = float(emg.sampling_frequency)
            elif hasattr(emg, 'fsamp') and emg.fsamp is not None:
                fs = float(emg.fsamp)
            else:
                fs = 2048.0
                logger.warning(f"Sampling frequency not found, using default: {fs} Hz")

            logger.info(f"Using sampling frequency: {fs} Hz")
            logger.info(f"Removing line noise at frequencies: {self.line_freqs} Hz")

            # Apply notch filter for each frequency
            filtered_data = emg.data.copy()

            for freq in self.line_freqs:
                logger.info(f"Applying notch filter at {freq} Hz")
                wo = freq / (fs / 2.0)
                bw = wo / 35.0

                # Use Octave's iirnotch and filtfilt functions
                b, a = oc.iirnotch(wo, bw, nout=2)

                # Apply filter to data
                filtered_data = oc.filtfilt(b, a, filtered_data)

            # Update EMG data
            emg.data = np.array(filtered_data)

            # Get output file path
            output_filepath = self.get_output_filepath()

            # Save the cleaned data
            emg.save(output_filepath)
            logger.info(f"Saved cleaned data to: {output_filepath}")

            # Add to global state
            if output_filepath not in global_state.line_noise_cleaned_files:
                global_state.line_noise_cleaned_files.append(output_filepath)

            # Stop Octave
            oc.exit()

            self.finished.emit()

        except Exception as e:
            error_msg = f"Failed to process {self.file_path} with Octave: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)

    def get_output_filepath(self):
        filename = os.path.basename(self.file_path)
        output_filepath = os.path.join(global_state.get_line_noise_cleaned_path(), filename)
        output_filepath = os.path.normpath(output_filepath)
        return output_filepath


