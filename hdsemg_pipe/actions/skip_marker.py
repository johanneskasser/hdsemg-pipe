"""Skip marker file management for wizard steps.

This module provides functions to save and check skip markers for wizard steps.
Skip markers are JSON files that indicate a step was skipped but still completed.
"""
import os
import json
from datetime import datetime
from hdsemg_pipe._log.log_config import logger


SKIP_MARKER_FILENAME = ".skip_marker.json"


def save_skip_marker(folder_path, reason="User skipped this step", user_note=None):
    """Save a skip marker file in the specified folder.

    Args:
        folder_path: Path to the output folder for this step
        reason: Default reason for skipping (default: "User skipped this step")
        user_note: Optional free-text justification given by the operator

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
        if user_note:
            marker_data["user_note"] = user_note

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


def ask_skip_reason(parent, default_reason):
    """Ask the operator why a step is skipped; the dialog is prefilled with ``default_reason``.

    Returns the (stripped) text, "" when left empty, or None if the dialog was cancelled
    (callers should then abort the skip).
    """
    from PyQt5.QtWidgets import QInputDialog

    text, ok = QInputDialog.getText(
        parent, "Reason for skipping",
        "Why is this step skipped? (stored in the workfolder for later reference)",
        text=default_reason,
    )
    return text.strip() if ok else None
