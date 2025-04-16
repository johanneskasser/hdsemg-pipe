from pathlib import Path

import numpy as np

from .matlab_file_io import load_mat_file
from .otb_4_file_io import load_otb4_file
from .otb_plus_file_io import load_otb_file


def load_file(filepath):
    """
    Loads a file based on its file extension and extracts relevant data.

    Supported file types:
    - `.mat`: MATLAB files
    - `.otb+`: OTB+ and related files
    - `.otb4`: OTB4 and related files

    Args:
        filepath (str): The path to the file to be loaded.

    Returns:
        tuple: A tuple containing:
            - data: The loaded data.
            - time: The time information associated with the data.
            - description: A description of the data.
            - sampling_frequency: The sampling frequency of the data.
            - file_name: The name of the file.
            - file_size: The size of the file.

    Raises:
        ValueError: If the file type is unsupported.
    """
    file_suffix = Path(filepath).suffix
    if file_suffix == ".mat":
        data, time, description, sampling_frequency, file_name, file_size = load_mat_file(filepath)
    elif file_suffix in [".otb+", ".otb"]:
        data, time, description, sampling_frequency, file_name, file_size = load_otb_file(filepath)
    elif file_suffix == ".otb4":
        data, time, description, sampling_frequency, file_name, file_size = load_otb4_file(filepath)
    else:
        raise ValueError(f"Unsupported file type: {file_suffix}")

    # Handle case if data is int16 since we will run into issues with further processing
    if data.dtype == 'int16':
        data = data.astype(np.float32)

    return data, time, description, sampling_frequency, file_name, file_size