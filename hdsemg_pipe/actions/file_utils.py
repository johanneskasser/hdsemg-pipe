import gzip
import io
import json
import os
import pickle
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.json_file_utilities import concatenate_grid_and_channel_info
from hdsemg_pipe.state.global_state import global_state


def copy_files(file_paths, destination_folder):
    """
    Copies files from the given list of file paths to the destination folder.

    :param file_paths: List of file paths to be copied
    :param destination_folder: Destination directory where files will be copied
    :return: List of copied file paths in the destination folder
    """
    if not os.path.exists(destination_folder):
        logger.warning(f"{destination_folder} is not a directory or does not exist. Creating one.")
        os.makedirs(destination_folder)  # Create destination folder if it doesn't exist

    copied_files = []

    for file_path in file_paths:
        if os.path.isfile(file_path):  # Check if the file exists
            try:
                dest_path = shutil.copy(file_path, destination_folder)
                copied_files.append(dest_path)
                logger.info(f"Copied: {file_path} -> {destination_folder}")
            except Exception as e:
                logger.info(f"Error copying {file_path}: {e}")
        else:
            logger.info(f"File not found: {file_path}")

    return copied_files


# Expected Keys in a openhdemg ready file after decomp
OPENHDEMG_PICKLE_EXPECTED_KEYS = [
    'SOURCE', 'FILENAME', 'RAW_SIGNAL', 'REF_SIGNAL', 'ACCURACY',
    'IPTS', 'MUPULSES', 'FSAMP', 'IED', 'EMG_LENGTH',
    'NUMBER_OF_MUS', 'BINARY_MUS_FIRING', 'EXTRAS'
]


def validate_openhdemg_structure(data):
    """
    Checks if the loaded data has all the expected keys.
    Raises an error if any key is missing.

    :param data: Dictionary containing the data to be validated
    :raises ValueError: If any expected key is missing from the data
    """
    missing_keys = [key for key in OPENHDEMG_PICKLE_EXPECTED_KEYS if key not in data]
    if missing_keys:
        raise ValueError(f"The following keys are missing from the file: {missing_keys}")
    else:
        return


def update_extras_in_pickle_file(filepath, channelselection_file):
    """
    Opens the pickle file, validates its structure, updates the 'EXTRAS'
    field with a given pandas DataFrame, and then saves the file back.

    :param filepath: Path to the pickle file
    :param channelselection_file: Path to the associated channelselection .mat file
    """
    data = load_pickle_dynamically(filepath)

    if not isinstance(data.get('EXTRAS'), pd.DataFrame):
        logger.debug("Note: 'EXTRAS' field is not a DataFrame. It will be replaced with the new DataFrame.")

    # Update the 'EXTRAS' field
    extras_str = build_extras(channelselection_file)

    save_json(extras_str, os.path.basename(filepath))
    data = update_extras(data, extras_str)

    # Save the updated file under the same name and location
    with open(filepath, 'wb') as f:
        pickle.dump(data, f)

    logger.info(f"File {filepath} updated and saved successfully.")


def update_extras_in_json_file(filepath, channelselection_file):
    """
    Opens the json file, validates its structure, updates the 'EXTRAS'
    field with a given pandas DataFrame, and then saves the file back.

    :param filepath: Path to the json file
    :param channelselection_file: Path to the associated channelselection .mat file
    """
    data = load_openhdemg_json(filepath)
    validate_openhdemg_structure(data)

    extras_str = build_extras(channelselection_file)

    data = update_extras(data, extras_str)

    with gzip.open(filepath, 'wt', encoding='utf-8') as f:
        json.dump(data, f)

    logger.info(f"File {filepath} updated and saved successfully.")


def update_extras(data, extras_str):
    # Step 1: Parse the extras string into a dictionary
    try:
        new_extras = json.loads(extras_str)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse extras from build_extras: %s", e)
        new_extras = {}  # Fallback to empty dict or handle error appropriately
    # Step 2: Update data['EXTRAS']
    if 'EXTRAS' in data:
        if isinstance(data['EXTRAS'], dict):
            # Merge dictionaries if existing EXTRAS is a dict
            data['EXTRAS'].update(new_extras)
        elif isinstance(data['EXTRAS'], str):
            # Parse existing string, merge, then keep as dict
            try:
                existing_extras = json.loads(data['EXTRAS'])
                existing_extras.update(new_extras)
                data['EXTRAS'] = existing_extras  # Store merged dict
            except json.JSONDecodeError:
                logger.error("Failed to decode existing 'EXTRAS' string")
                data['EXTRAS'] = new_extras  # Override with new dict
    else:
        # No existing EXTRAS - store the parsed dict directly
        data['EXTRAS'] = new_extras

    return data


def build_extras(channelselectionpath):
    """
    Build the extras field from channelselection path. Searches for
    the .json metadata file from associated grids and channelselection
    step file.

    :param channelselectionpath: Path to the associated channelselection .mat file
    :return: JSON string containing the concatenated grid and channel information
    """
    files = get_json_file_path(channelselectionpath)

    # Check if both files exist:
    if "associated_grids_json" in files and os.path.exists(files["associated_grids_json"]):
        extras_dict = concatenate_grid_and_channel_info(files["channelselection_json"], files["associated_grids_json"])
    else:
        with open(files["channelselection_json"], 'rb') as f:
            extras_dict = json.load(f)

    return json.dumps(extras_dict)


def load_openhdemg_json(json_file):
    """
    Loads an OpenHD-EMG JSON file and converts necessary fields to their correct data formats.
    And decompresses the file using gzip.

    :param json_file: Path to the OpenHD-EMG JSON file
    :return: Dictionary containing the decomposed HD-EMG data
    :raises FileNotFoundError: If the JSON file does not exist
    """
    json_file = Path(json_file)

    if not json_file.exists():
        raise FileNotFoundError(f"File {json_file} not found.")

    # Load the JSON file
    with gzip.open(json_file, 'rt', encoding='utf-8') as f:
        data = json.load(f)

    # Convert stored data back into correct formats
    if 'RAW_SIGNAL' in data and isinstance(data['RAW_SIGNAL'], list):
        data['RAW_SIGNAL'] = pd.DataFrame(data['RAW_SIGNAL'])

    if 'REF_SIGNAL' in data and isinstance(data['REF_SIGNAL'], list):
        data['REF_SIGNAL'] = pd.DataFrame(data['REF_SIGNAL'])

    if 'ACCURACY' in data and isinstance(data['ACCURACY'], list):
        data['ACCURACY'] = pd.DataFrame(data['ACCURACY'])

    if 'IPTS' in data and isinstance(data['IPTS'], list):
        data['IPTS'] = pd.DataFrame(data['IPTS'])

    if 'BINARY_MUS_FIRING' in data and isinstance(data['BINARY_MUS_FIRING'], list):
        data['BINARY_MUS_FIRING'] = pd.DataFrame(data['BINARY_MUS_FIRING'])

    if 'MUPULSES' in data and isinstance(data['MUPULSES'], list):
        data['MUPULSES'] = [np.array(mup, dtype=np.int32) for mup in data['MUPULSES']]

    return data


def get_json_file_path(channelselection_filepath: str) -> dict:
    """
    Given the path to a channel selection file (e.g., '/home/ex/test1.mat'),
    constructs the corresponding JSON file paths:
      - The channel selection JSON file is mandatory.
      - The associated grids JSON file is optional.

    The channel selection JSON is expected to be at the same base path (with a .json extension),
    while the associated grids JSON file is expected to be located in the folder defined by
    global_state.get_associated_grids_path() with the same base filename.

    :param channelselection_filepath: Path to the channel selection file
    :return: Dictionary with keys "channelselection_json" and "associated_grids_json"
    :raises FileNotFoundError: If the channel selection JSON file does not exist
    """
    # Build channel selection JSON file path.
    base, _ = os.path.splitext(channelselection_filepath)
    channelselection_json_file = base + '.json'

    # Build associated grids JSON file path.
    base_filename = os.path.splitext(os.path.basename(channelselection_filepath))[0]
    associated_grids_folder = global_state.get_associated_grids_path()
    # Assuming the associated grids JSON file is named like "<base_filename>.json" inside the folder.
    associated_grids_json_file = os.path.join(associated_grids_folder, base_filename + '.json')

    # Check mandatory channel selection JSON file.
    if not os.path.exists(channelselection_json_file):
        raise FileNotFoundError(f"Channel selection JSON file not found: {channelselection_json_file}")

    # Check associated grids JSON file. It's optional.
    if not os.path.exists(associated_grids_json_file):
        logger.info(f"Associated grids JSON file not found: {associated_grids_json_file}. "
                    "Only channel selection file will be used.")
        return {"channelselection_json": channelselection_json_file}

    # Both files exist.
    return {
        "channelselection_json": channelselection_json_file,
        "associated_grids_json": associated_grids_json_file
    }

def save_json(json_content, file_name):
    """
    Saves the given JSON content to a file.

    :param json_content: JSON content to be saved
    :param file_path: Path where the JSON file will be saved
    """
    decomposition_folder = global_state.get_decomposition_path()
    json_name = os.path.splitext(os.path.basename(file_name))[0] + ".json"
    file_path = os.path.join(decomposition_folder, json_name)

    with open(file_path, 'w') as f:
        json.dump(json_content, f, indent=4)
    logger.info(f"JSON file saved at {file_path}")



def load_pickle_dynamically(filepath):
    """
    Loads a pickle file and maps it to CUDA if available, otherwise CPU.

    :param filepath: Path to the pickle file
    :return: Loaded data from the pickle file
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"

    with open(filepath, 'rb') as f:
        data = DynamicUnpickler(f).load()

    # Ensure all tensors are moved to the appropriate device
    if isinstance(data, dict):
        for key in data:
            if isinstance(data[key], torch.Tensor):
                data[key] = data[key].to(device)
    elif isinstance(data, torch.Tensor):
        data = data.to(device)

    logger.info(f"Loaded pickle file {filepath} on {device}.")
    return data


class DynamicUnpickler(pickle.Unpickler):
    """
    Custom unpickler that dynamically maps torch storage to the appropriate device.
    """

    def find_class(self, module, name):
        """
        Overrides the find_class method to handle torch storage loading.

        :param module: Module name
        :param name: Class name
        :return: Loaded class or function
        """
        if module == 'torch.storage' and name == '_load_from_bytes':
            device = "cuda" if torch.cuda.is_available() else "cpu"
            return lambda b: torch.load(io.BytesIO(b), map_location=device)
        return super().find_class(module, name)
