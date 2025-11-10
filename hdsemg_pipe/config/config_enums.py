from enum import Enum


class Settings(Enum):
    HDSEMG_SELECT_INSTALLED = "HDSEMG_SELECT_INSTALLED"
    WORKFOLDER_PATH = "WORKFOLDER_PATH"
    OPENHDEMG_INSTALLED = "OPENHDEMG_INSTALLED"
    LOG_LEVEL = "LOG_LEVEL"
    LINE_NOISE_REGION = "LINE_NOISE_REGION"  # "US" (60Hz) or "EU" (50Hz)
    LINE_NOISE_METHOD = "LINE_NOISE_METHOD"  # Method for line noise removal
    MATLAB_INSTALLED = "MATLAB_INSTALLED"  # MATLAB Engine available
    OCTAVE_INSTALLED = "OCTAVE_INSTALLED"  # Octave + oct2py available
    MUEDIT_PATH = "MUEDIT_PATH"  # Path to MUEdit folder (to add to MATLAB path)
    MUEDIT_LAUNCH_METHOD = "MUEDIT_LAUNCH_METHOD"  # Method to launch MUEdit


class LineNoiseRegion(Enum):
    US = "US"  # 60 Hz line noise
    EU = "EU"  # 50 Hz line noise


class LineNoiseMethod(Enum):
    """Methods for line noise removal."""
    MNE_NOTCH = "MNE_NOTCH"  # MNE-Python notch filter (simple, fast)
    MNE_SPECTRUM_FIT = "MNE_SPECTRUM_FIT"  # MNE-Python spectrum fitting (adaptive, similar to CleanLine)
    MATLAB_CLEANLINE = "MATLAB_CLEANLINE"  # MATLAB CleanLine (EEGLAB plugin - gold standard)
    MATLAB_IIR = "MATLAB_IIR"  # MATLAB IIR notch filter
    OCTAVE = "OCTAVE"  # Octave-based IIR notch filter


class MUEditLaunchMethod(Enum):
    """Methods for launching MUEdit."""
    AUTO = "AUTO"  # Automatically detect best method
    MATLAB_ENGINE = "MATLAB_ENGINE"  # Use MATLAB Engine API (reuse existing session)
    MATLAB_CLI = "MATLAB_CLI"  # Start new MATLAB process via CLI
    STANDALONE = "STANDALONE"  # Assume MUEdit is available as standalone command


