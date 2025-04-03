import json
import os
from pathlib import Path
import scipy.io as sio
import numpy as np
from _log.log_config import logger

def load_mat_file(file_path):
    mat_data = sio.loadmat(file_path)
    data = mat_data['Data']
    time = mat_data['Time'].flatten()
    description = mat_data['Description']
    sampling_frequency = mat_data.get('SamplingFrequency', [[1]])[0][0] if 'SamplingFrequency' in mat_data else 1
    file_name = Path(file_path).name
    file_size = os.path.getsize(file_path)
    return data, time, description, sampling_frequency, file_name, file_size

def save_selection_to_json(file_path, file_name, grid_info, channel_status, description):
    """
    Saves the selection information to a JSON file.

    :param file_path: The path where the JSON file should be saved.
    :param file_name: The name of the original file.
    :param grid_info: Dictionary containing info about all extracted grids, e.g.:
        {
            "8x8": {
                "rows": 8,
                "cols": 8,
                "indices": [0,1,2,...,63],
                "scale_mm": 10
            },
            "5x3": {
                "rows": 5,
                "cols": 3,
                "indices": [...],
                "scale_mm": 10
            }
        }
    :param channel_status: List of booleans indicating channel selection status.
    :param description: List of strings indicating channel description.
    """

    grids = []
    for grid_key, info in grid_info.items():
        rows = info["rows"]
        cols = info["cols"]
        scale = info["ied_mm"]
        indices = info["indices"]

        # Extract the channels specific to this grid and their selection states
        channels_for_grid = [
            {"channel": ch_idx + 1, "selected": channel_status[ch_idx], "description": description[ch_idx,0].item()}
            for ch_idx in indices
        ]

        grids.append({
            "columns": cols,
            "rows": rows,
            "inter_electrode_distance_mm": scale,
            "channels": channels_for_grid
        })

    result = {
        "filename": file_name,
        "grids": grids
    }

    with open(file_path, "w") as f:
        json.dump(result, f, indent=4)

def save_selection_to_mat(save_file_path, data, time, description, sampling_frequency, file_name,
                          grid_info):
    logger.debug("Saving MAT file to %s", save_file_path)
    mat_dict = {
        "Data": data,
        "Time": time,
        "Description": description,
        "SamplingFrequency": sampling_frequency
    }
    sio.savemat(save_file_path, mat_dict)
    logger.info("MAT file saved successfully: %s", save_file_path)