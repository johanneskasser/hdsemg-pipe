import shutil
import os
from log.log_config import logger
import pickle
import pandas as pd



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

def validate_pickle_openhdemg_structure(data):
    """
        Checks if the loaded data has all the expected keys.
        Raises an error if any key is missing.
    """
    missing_keys = [key for key in OPENHDEMG_PICKLE_EXPECTED_KEYS if key not in data]
    if missing_keys:
        raise ValueError(f"The following keys are missing from the file: {missing_keys}")
    else:
        return


def update_extras_in_pickle_file(filepath, extras_df):
    """
    Opens the pickle file, validates its structure, updates the 'EXTRAS'
    field with a given pandas DataFrame, and then saves the file back.

    Parameters:
        filepath (str): Path to the pickle file.
        extras_df (pd.DataFrame): DataFrame to store in the 'EXTRAS' field.
    """
    # Load the pickle file
    with open(filepath, 'rb') as f:
        data = pickle.load(f)

    # Validate the structure
    validate_pickle_openhdemg_structure(data)

    if not isinstance(data.get('EXTRAS'), pd.DataFrame):
        logger.debug("Note: 'EXTRAS' field is not a DataFrame. It will be replaced with the new DataFrame.")

    # Update the 'EXTRAS' field
    data['EXTRAS'] = extras_df

    # Save the updated file under the same name and location
    with open(filepath, 'wb') as f:
        pickle.dump(data, f)

    logger.info(f"File {filepath} updated and saved successfully.")