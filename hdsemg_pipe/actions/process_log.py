"""Process log module for tracking pipeline step statuses.

Writes/reads a JSON log file at ``{workfolder}/hdsemg-pipe-process.log``.
This log is the canonical record of which steps completed or were skipped and
is used by ``automatic_state_reconstruction`` to restore the wizard state when
opening an existing workfolder.
"""

import json
import os
from datetime import datetime

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.enum.FolderNames import FolderNames
from hdsemg_pipe.state.global_state import global_state

LOG_FILENAME = "hdsemg-pipe-process.log"

STEP_NAMES = {
    "step1": "Open Files",
    "step2": "Grid Association",
    "step3": "Line Noise Removal",
    "step4": "RMS Quality Analysis",
    "step5": "File Quality Selection",
    "step6": "Crop to Region of Interest (ROI)",
    "step7": "Channel Selection",
    "step8": "Decomposition Results",
    "step9": "CoVISI Pre-Filter",
    "step10": "Multi-Grid Configuration",
    "step11": "MUEdit Manual Cleaning",
    "step12": "CoVISI Post-Validation",
    "step13": "Final Results",
}


def _get_log_path(workfolder: str = None) -> str | None:
    """Return the absolute path to the process log file, or None if no workfolder is set."""
    folder = workfolder or global_state.workfolder
    if not folder:
        return None
    return os.path.join(folder, LOG_FILENAME)


def _read_raw(log_path: str) -> dict:
    """Read and parse the JSON log file; return an empty structure on any failure."""
    if not os.path.exists(log_path):
        return {"version": "1.0", "steps": {}}
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not read process log (%s): %s", log_path, e)
        return {"version": "1.0", "steps": {}}


def write_step_status(step_key: str, status: str, metadata: dict = None) -> None:
    """Write or update a step's status entry in the process log.

    Args:
        step_key:  Wizard step identifier, e.g. ``"step5"``.
        status:    ``"completed"`` or ``"skipped"``.
        metadata:  Optional dict with extra data (e.g. selected file paths).
    """
    log_path = _get_log_path()
    if not log_path:
        logger.debug("Cannot write process log: workfolder not set")
        return

    log = _read_raw(log_path)

    log.setdefault("version", "1.0")
    log.setdefault("workfolder", global_state.workfolder)
    log.setdefault("created", datetime.now().isoformat())
    log["last_updated"] = datetime.now().isoformat()

    step_entry: dict = {
        "name": STEP_NAMES.get(step_key, step_key),
        "status": status,
        "timestamp": datetime.now().isoformat(),
    }
    if metadata:
        step_entry["metadata"] = metadata

    log.setdefault("steps", {})[step_key] = step_entry

    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        logger.debug("Process log updated: %s = %s", step_key, status)
    except Exception as e:
        logger.warning("Could not write process log (%s): %s", log_path, e)


def read_process_log(workfolder: str = None) -> dict:
    """Read the process log for *workfolder* (or ``global_state.workfolder``).

    Returns:
        Parsed log dict.  The ``"steps"`` key maps step keys to their entries.
        Returns an empty ``{"steps": {}}`` dict when the log file is absent or unreadable.
    """
    log_path = _get_log_path(workfolder)
    if not log_path:
        return {"steps": {}}
    return _read_raw(log_path)


def get_step_status(step_key: str, workfolder: str = None) -> str | None:
    """Return the recorded status for *step_key*, or ``None`` if not found.

    Possible return values: ``"completed"``, ``"skipped"``, or ``None``.
    """
    log = read_process_log(workfolder)
    return log.get("steps", {}).get(step_key, {}).get("status")


def write_manual_cleaning_tool(tool: str) -> None:
    """Write the chosen manual cleaning tool to the process log root.

    Args:
        tool: ``"muedit"`` or ``"scd_edition"``.
    """
    log_path = _get_log_path()
    if not log_path:
        logger.debug("Cannot write manual_cleaning_tool: workfolder not set")
        return

    log = _read_raw(log_path)
    log.setdefault("version", "1.0")
    log.setdefault("workfolder", global_state.workfolder)
    log.setdefault("created", datetime.now().isoformat())
    log["last_updated"] = datetime.now().isoformat()
    log["manual_cleaning_tool"] = tool

    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        logger.debug("manual_cleaning_tool set to: %s", tool)
    except Exception as e:
        logger.warning("Could not write manual_cleaning_tool (%s): %s", log_path, e)


def read_manual_cleaning_tool(workfolder: str = None) -> str:
    """Return the manual cleaning tool for this workfolder.

    Returns the stored ``manual_cleaning_tool`` value if present.  When the
    field is absent, auto-detection is performed:

    1. ``decomposition_muedit/`` contains ``*_muedit.mat`` files → ``"muedit"``
    2. ``decomposition_covisi_filtered/`` contains ``*_covisi_filtered.pkl`` → ``"scd_edition"``
    3. Fallback → ``"muedit"``
    """
    import glob as _glob

    log = read_process_log(workfolder)
    stored = log.get("manual_cleaning_tool")
    if stored:
        return stored

    folder = workfolder or global_state.workfolder
    if not folder:
        return "muedit"

    muedit_dir = os.path.join(folder, FolderNames.DECOMPOSITION_MUEDIT.value)
    if os.path.isdir(muedit_dir) and _glob.glob(os.path.join(muedit_dir, "*_muedit.mat")):
        return "muedit"

    covisi_filtered_dir = os.path.join(folder, FolderNames.DECOMPOSITION_COVISI_FILTERED.value)
    if os.path.isdir(covisi_filtered_dir) and _glob.glob(
        os.path.join(covisi_filtered_dir, "*_covisi_filtered.pkl")
    ):
        return "scd_edition"

    return "muedit"
