import json

import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def load_mat_file(file_path):
    mat_data = sio.loadmat(file_path)
    data = mat_data['Data']
    time = mat_data['Time'].flatten()
    description = mat_data['Description']
    sampling_frequency = mat_data.get('SamplingFrequency', [[1]])[0][0] if 'SamplingFrequency' in mat_data else 1
    file_name = Path(file_path).name
    file_size = os.path.getsize(file_path)
    return data, time, description, sampling_frequency, file_name, file_size


import os
import scipy.io as sio
from pathlib import Path
from _log.log_config import logger


def save_selection_to_mat(save_file_path, data, time, description, sampling_frequency, file_name,
                          grid_info):
    # Convert to Path object
    path_obj = Path(save_file_path)
    logger.debug(f"Requested save MAT file to: {path_obj}")

    # Check extension. If not .mat, replace it
    if path_obj.suffix.lower() != ".mat":
        logger.debug(f"Suffix was '{path_obj.suffix}'. Changing to '.mat'.")
        path_obj = path_obj.with_suffix(".mat")

    # For clarity, we reassign the string
    save_file_path = str(path_obj)
    logger.debug(f"Final MAT file path: {save_file_path}")

    # Build dictionary for .mat
    mat_dict = {
        "Data": data,
        "Time": time,
        "Description": description,
        "SamplingFrequency": sampling_frequency
    }

    # Actually save
    sio.savemat(save_file_path, mat_dict)
    logger.info(f"MAT file saved successfully: {save_file_path}")

    return save_file_path
