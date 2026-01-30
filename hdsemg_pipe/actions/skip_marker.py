"""Skip marker file management for wizard steps.

This module provides functions to save and check skip markers for wizard steps.
Skip markers are JSON files that indicate a step was skipped but still completed.
"""
import os
import json
from datetime import datetime
from hdsemg_pipe._log.log_config import logger


SKIP_MARKER_FILENAME = ".skip_marker.json"


def save_skip_marker(folder_path, reason="User skipped this step"):
    """Save a skip marker file in the specified folder.

    Args:
        folder_path: Path to the output folder for this step
        reason: Reason for skipping (default: "User skipped this step")

    Returns:
        bool: True if marker was saved successfully, False otherwise
    """
    try:
        marker_path = os.path.join(folder_path, SKIP_MARKER_FILENAME)
        marker_data = {
            "skipped": True,
            "timestamp": datetime.now().isoformat(),
            "reason": reason
        }

        os.makedirs(folder_path, exist_ok=True)
        with open(marker_path, 'w') as f:
            json.dump(marker_data, f, indent=2)

        logger.info(f"Skip marker saved to {marker_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save skip marker to {folder_path}: {e}")
        return False


def check_skip_marker(folder_path):
    """Check if a skip marker file exists in the specified folder.

    Args:
        folder_path: Path to the output folder for this step

    Returns:
        bool: True if skip marker exists, False otherwise
    """
    try:
        marker_path = os.path.join(folder_path, SKIP_MARKER_FILENAME)
        if os.path.exists(marker_path):
            with open(marker_path, 'r') as f:
                data = json.load(f)
                return data.get("skipped", False)
        return False
    except Exception as e:
        logger.debug(f"Could not read skip marker from {folder_path}: {e}")
        return False
