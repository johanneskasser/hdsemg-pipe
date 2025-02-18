import shutil
import os
from log.log_config import logger

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