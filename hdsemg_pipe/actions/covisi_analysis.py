"""
CoVISI (Coefficient of Variation of Interspike Interval) analysis and filtering.

This module provides functions for computing CoVISI values for motor units
and filtering out non-physiological MUs based on CoVISI thresholds.

Literature standard: CoVISI < 30% indicates physiologically plausible motor units.
Reference: Taleshi et al. (2025), J Appl Physiol 138: 559-570
"""

import copy
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

import h5py
import numpy as np
import pandas as pd
import scipy.io as sio

from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, BorderRadius, Fonts, Styles

try:
    import openhdemg.library as emg

    OPENHDEMG_AVAILABLE = True
except ImportError:
    OPENHDEMG_AVAILABLE = False
    logger.warning(
        "openhdemg library not available. CoVISI analysis will be limited."
    )

# Default CoVISI threshold per literature (Taleshi et al., 2025)
DEFAULT_COVISI_THRESHOLD = 30.0

# Analysis method options
COVISI_METHOD_AUTO = "auto"  # Uses rec_derec (automatic, no user interaction)
COVISI_METHOD_STEADY = "steady"  # Uses steady-state phase (requires time range)


def compute_covisi_for_all_mus(
    emgfile: dict,
    n_firings_rec_derec: int = 4,
    method: str = COVISI_METHOD_AUTO,
    start_steady: Optional[float] = None,
    end_steady: Optional[float] = None,
) -> pd.DataFrame:
    """
    Compute CoVISI for all motor units in an emgfile.

    Supports two methods:
    - "auto": Uses event_="rec_derec" for automatic computation without
      interactive steady-state selection. Best for quick analysis.
    - "steady": Uses event_="rec_derec_steady" with user-specified steady-state
      boundaries. More accurate for trapezoidal contractions with a plateau.

    Parameters
    ----------
    emgfile : dict
        The openhdemg emgfile dictionary containing IPTS, MUPULSES, etc.
    n_firings_rec_derec : int, default 4
        Number of firings at recruitment/derecruitment to consider.
    method : str, default "auto"
        Analysis method: "auto" (rec/derec only) or "steady" (includes steady-state).
    start_steady : float, optional
        Start time of steady-state phase in seconds. Required if method="steady".
    end_steady : float, optional
        End time of steady-state phase in seconds. Required if method="steady".

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - mu_index: Motor unit index (0-based)
        - covisi_rec: CoVISI at recruitment (if available)
        - covisi_derec: CoVISI at derecruitment (if available)
        - covisi_steady: CoVISI during steady-state (if method="steady")
        - covisi_all: CoVISI for entire contraction (always available)

    Raises
    ------
    RuntimeError
        If openhdemg is not available.
    ValueError
        If emgfile has no motor units or if steady-state bounds are invalid.
    """
    if not OPENHDEMG_AVAILABLE:
        raise RuntimeError(
            "openhdemg library is required for CoVISI computation"
        )

    n_mus = emgfile.get("NUMBER_OF_MUS", 0)
    if n_mus == 0:
        # Check IPTS shape as fallback
        ipts = emgfile.get("IPTS")
        if ipts is not None and hasattr(ipts, "shape"):
            n_mus = ipts.shape[1] if len(ipts.shape) > 1 else 0

    if n_mus == 0:
        raise ValueError("emgfile contains no motor units")

    # Get sampling frequency for time-to-sample conversion
    fsamp = emgfile.get("FSAMP", 2048)

    # Determine event type and steady-state parameters
    if method == COVISI_METHOD_STEADY:
        if start_steady is None or end_steady is None:
            raise ValueError(
                "start_steady and end_steady are required for method='steady'"
            )
        if start_steady >= end_steady:
            raise ValueError(
                f"start_steady ({start_steady}) must be less than end_steady ({end_steady})"
            )

        # Convert time (seconds) to samples
        start_steady_samples = int(start_steady * fsamp)
        end_steady_samples = int(end_steady * fsamp)

        event_type = "rec_derec_steady"
        logger.info(
            f"Computing CoVISI with steady-state: {start_steady:.2f}s - {end_steady:.2f}s "
            f"(samples {start_steady_samples} - {end_steady_samples})"
        )
    else:
        # Auto mode: use rec_derec only
        event_type = "rec_derec"
        start_steady_samples = 0  # Dummy values, not used
        end_steady_samples = 1
        logger.info("Computing CoVISI with auto mode (rec/derec only)")

    # Compute CoVISI using openhdemg
    try:
        covisi_df = emg.compute_covisi(
            emgfile=emgfile,
            n_firings_RecDerec=n_firings_rec_derec,
            event_=event_type,
            start_steady=start_steady_samples,
            end_steady=end_steady_samples,
        )
    except Exception as e:
        logger.error(f"Failed to compute CoVISI: {e}")
        raise

    # Add MU index column
    covisi_df = covisi_df.reset_index(drop=True)
    covisi_df.insert(0, "mu_index", range(len(covisi_df)))

    # Rename columns for consistency
    rename_map = {
        "COVisi_rec": "covisi_rec",
        "COVisi_derec": "covisi_derec",
        "COVisi_all": "covisi_all",
    }
    if method == COVISI_METHOD_STEADY:
        rename_map["COVisi_steady"] = "covisi_steady"

    covisi_df = covisi_df.rename(columns=rename_map)

    return covisi_df


def get_contraction_duration(emgfile: dict) -> float:
    """
    Get the total duration of the contraction in seconds.

    Parameters
    ----------
    emgfile : dict
        The openhdemg emgfile dictionary.

    Returns
    -------
    float
        Duration in seconds.
    """
    fsamp = emgfile.get("FSAMP", 2048)
    ref_signal = emgfile.get("REF_SIGNAL")

    if ref_signal is not None:
        if hasattr(ref_signal, "__len__"):
            n_samples = len(ref_signal)
        else:
            n_samples = ref_signal.shape[0] if hasattr(ref_signal, "shape") else 0
    else:
        # Fall back to EMG signal length
        emg_signal = emgfile.get("RAW_SIGNAL")
        if emg_signal is not None and hasattr(emg_signal, "shape"):
            n_samples = emg_signal.shape[0]
        else:
            n_samples = 0

    return n_samples / fsamp if n_samples > 0 else 0.0


def get_ref_signal_for_plotting(emgfile: dict) -> tuple:
    """
    Extract the reference signal (force/torque) for plotting.

    Parameters
    ----------
    emgfile : dict
        The openhdemg emgfile dictionary.

    Returns
    -------
    tuple
        (time_array, signal_array) where time is in seconds.
        Returns (None, None) if no reference signal is available.
    """
    fsamp = emgfile.get("FSAMP", 2048)
    ref_signal = emgfile.get("REF_SIGNAL")

    if ref_signal is None:
        return None, None

    # Convert to numpy array
    if hasattr(ref_signal, "values"):
        signal = ref_signal.values.flatten()
    else:
        signal = np.asarray(ref_signal).flatten()

    # Create time array
    time = np.arange(len(signal)) / fsamp

    return time, signal


def filter_mus_by_covisi(
    emgfile: dict,
    threshold: float = DEFAULT_COVISI_THRESHOLD,
    n_firings_rec_derec: int = 4,
    method: str = COVISI_METHOD_AUTO,
    start_steady: Optional[float] = None,
    end_steady: Optional[float] = None,
    use_steady_for_filter: bool = False,
    manual_overrides: Optional[dict] = None,
) -> tuple[dict, pd.DataFrame]:
    """
    Filter motor units based on CoVISI threshold.

    Removes motor units with CoVISI > threshold from the emgfile.

    Parameters
    ----------
    emgfile : dict
        The openhdemg emgfile dictionary.
    threshold : float, default 30.0
        CoVISI threshold in percent. MUs with CoVISI > threshold are removed.
    n_firings_rec_derec : int, default 4
        Number of firings at recruitment/derecruitment for CoVISI calculation.
    method : str, default "auto"
        Analysis method: "auto" or "steady".
    start_steady : float, optional
        Start time of steady-state in seconds (required if method="steady").
    end_steady : float, optional
        End time of steady-state in seconds (required if method="steady").
    use_steady_for_filter : bool, default False
        If True and method="steady", use covisi_steady for filtering instead of covisi_all.
    manual_overrides : dict, optional
        Dictionary mapping MU index (int) to decision ("Keep" or "Filter").
        Manual overrides take precedence over threshold-based decisions.

    Returns
    -------
    tuple[dict, pd.DataFrame]
        - filtered_emgfile: New emgfile dict with filtered MUs
        - report_df: DataFrame with filtering results containing:
          - mu_index: Original MU index
          - covisi_all: CoVISI value (or covisi_steady if use_steady_for_filter)
          - status: "kept" or "removed"
          - manual_override: Whether this MU was manually overridden
    """
    manual_overrides = manual_overrides or {}

    # Compute CoVISI for all MUs
    covisi_df = compute_covisi_for_all_mus(
        emgfile,
        n_firings_rec_derec=n_firings_rec_derec,
        method=method,
        start_steady=start_steady,
        end_steady=end_steady,
    )

    # Determine which column to use for filtering
    if use_steady_for_filter and method == COVISI_METHOD_STEADY and "covisi_steady" in covisi_df.columns:
        filter_column = "covisi_steady"
        logger.info("Using steady-state CoVISI for filtering")
    else:
        filter_column = "covisi_all"

    # Determine which MUs to keep, considering manual overrides
    kept_indices = []
    removed_indices = []
    statuses = []
    manual_override_flags = []

    for _, row in covisi_df.iterrows():
        mu_index = int(row["mu_index"])
        covisi_val = row[filter_column]

        # Check for manual override
        if mu_index in manual_overrides:
            override = manual_overrides[mu_index]
            if override == "Keep":
                kept_indices.append(mu_index)
                statuses.append("kept")
            else:  # "Filter"
                removed_indices.append(mu_index)
                statuses.append("removed")
            manual_override_flags.append(True)
            logger.debug(f"MU {mu_index}: Manual override -> {override}")
        else:
            # Use threshold-based decision
            if covisi_val <= threshold:
                kept_indices.append(mu_index)
                statuses.append("kept")
            else:
                removed_indices.append(mu_index)
                statuses.append("removed")
            manual_override_flags.append(False)

    # Create filtering report
    covisi_df["status"] = statuses
    covisi_df["manual_override"] = manual_override_flags
    report_df = covisi_df.copy()

    manual_count = sum(manual_override_flags)
    logger.info(
        f"CoVISI filtering: {len(kept_indices)} MUs kept, "
        f"{len(removed_indices)} MUs removed (threshold={threshold}%, "
        f"{manual_count} manual overrides)"
    )

    if len(kept_indices) == 0:
        logger.warning("All motor units were filtered out!")

    # Create filtered emgfile
    filtered_emgfile = _remove_mus_from_emgfile(emgfile, removed_indices)

    return filtered_emgfile, report_df


def _remove_mus_from_emgfile(emgfile: dict, mu_indices_to_remove: list) -> dict:
    """
    Remove specified motor units from an emgfile dictionary.

    Parameters
    ----------
    emgfile : dict
        The original openhdemg emgfile dictionary.
    mu_indices_to_remove : list
        List of MU indices (0-based) to remove.

    Returns
    -------
    dict
        New emgfile dict with specified MUs removed.
    """
    if not mu_indices_to_remove:
        return copy.deepcopy(emgfile)

    filtered = copy.deepcopy(emgfile)
    n_original = emgfile.get("NUMBER_OF_MUS", 0)

    # Determine indices to keep
    indices_to_keep = [
        i for i in range(n_original) if i not in mu_indices_to_remove
    ]

    # Filter IPTS (DataFrame: time x nMU)
    if "IPTS" in filtered and filtered["IPTS"] is not None:
        ipts = filtered["IPTS"]
        if isinstance(ipts, pd.DataFrame):
            # Select columns by position
            filtered["IPTS"] = ipts.iloc[:, indices_to_keep].reset_index(
                drop=True
            )
            # Rename columns to sequential integers
            filtered["IPTS"].columns = range(len(indices_to_keep))

    # Filter MUPULSES (list of arrays)
    if "MUPULSES" in filtered and filtered["MUPULSES"] is not None:
        filtered["MUPULSES"] = [
            filtered["MUPULSES"][i] for i in indices_to_keep
        ]

    # Filter BINARY_MUS_FIRING (DataFrame: time x nMU)
    if (
        "BINARY_MUS_FIRING" in filtered
        and filtered["BINARY_MUS_FIRING"] is not None
    ):
        binary = filtered["BINARY_MUS_FIRING"]
        if isinstance(binary, pd.DataFrame):
            filtered["BINARY_MUS_FIRING"] = binary.iloc[
                :, indices_to_keep
            ].reset_index(drop=True)
            filtered["BINARY_MUS_FIRING"].columns = range(len(indices_to_keep))

    # Filter ACCURACY if present (DataFrame with one row per MU)
    if "ACCURACY" in filtered and filtered["ACCURACY"] is not None:
        accuracy = filtered["ACCURACY"]
        if isinstance(accuracy, pd.DataFrame) and len(accuracy) == n_original:
            filtered["ACCURACY"] = accuracy.iloc[indices_to_keep].reset_index(
                drop=True
            )

    # Update NUMBER_OF_MUS
    filtered["NUMBER_OF_MUS"] = len(indices_to_keep)

    return filtered


def apply_covisi_filter_to_json(
    json_path: str,
    output_path: str,
    threshold: float = DEFAULT_COVISI_THRESHOLD,
    n_firings_rec_derec: int = 4,
    manual_overrides: Optional[dict] = None,
) -> dict:
    """
    Load a JSON file, apply CoVISI filtering, and save the filtered result.

    Parameters
    ----------
    json_path : str
        Path to the input openhdemg JSON file.
    output_path : str
        Path where the filtered JSON will be saved.
    threshold : float, default 30.0
        CoVISI threshold in percent.
    n_firings_rec_derec : int, default 4
        Number of firings at recruitment/derecruitment for CoVISI calculation.
    manual_overrides : dict, optional
        Dictionary mapping MU index (int) to decision ("Keep" or "Filter").
        Manual overrides take precedence over threshold-based decisions.

    Returns
    -------
    dict
        Filtering statistics containing:
        - original_mu_count: Number of MUs before filtering
        - filtered_mu_count: Number of MUs after filtering
        - removed_count: Number of MUs removed
        - threshold_used: The CoVISI threshold used
        - removed_mu_indices: List of removed MU indices
        - covisi_values: Dict mapping MU index to CoVISI value
        - manual_overrides_applied: Number of manual overrides applied
    """
    if not OPENHDEMG_AVAILABLE:
        raise RuntimeError(
            "openhdemg library is required for CoVISI filtering"
        )

    manual_overrides = manual_overrides or {}

    # Load JSON
    logger.info(f"Loading JSON for CoVISI filtering: {json_path}")
    emgfile = emg.emg_from_json(str(json_path))

    original_count = emgfile.get("NUMBER_OF_MUS", 0)

    # Apply filtering with manual overrides
    filtered_emgfile, report_df = filter_mus_by_covisi(
        emgfile,
        threshold=threshold,
        n_firings_rec_derec=n_firings_rec_derec,
        manual_overrides=manual_overrides,
    )

    filtered_count = filtered_emgfile.get("NUMBER_OF_MUS", 0)

    # Save filtered JSON
    logger.info(f"Saving filtered JSON to: {output_path}")
    emg.save_json_emgfile(filtered_emgfile, str(output_path), compresslevel=4)

    # Build statistics
    removed_mask = report_df["status"] == "removed"
    stats = {
        "original_mu_count": original_count,
        "filtered_mu_count": filtered_count,
        "removed_count": original_count - filtered_count,
        "threshold_used": threshold,
        "removed_mu_indices": report_df.loc[removed_mask, "mu_index"].tolist(),
        "covisi_values": dict(
            zip(report_df["mu_index"], report_df["covisi_all"])
        ),
        "manual_overrides_applied": len(manual_overrides),
    }

    return stats


def compute_covisi_from_discharge_times(
    discharge_times: list,
    fsamp: float,
) -> list[float]:
    """
    Compute CoVISI directly from discharge times (for edited MAT files).

    This is used for post-validation when we need to compute CoVISI
    from MUedit-edited data without a full emgfile structure.

    Parameters
    ----------
    discharge_times : list
        List of arrays, each containing discharge times (sample indices)
        for one motor unit.
    fsamp : float
        Sampling frequency in Hz.

    Returns
    -------
    list[float]
        CoVISI values (in percent) for each motor unit.
    """
    covisi_values = []

    for mu_discharges in discharge_times:
        if mu_discharges is None or len(mu_discharges) < 2:
            # Not enough spikes to compute ISI
            covisi_values.append(np.nan)
            continue

        # Convert to numpy array and sort
        discharges = np.asarray(mu_discharges).flatten()
        discharges = np.sort(discharges)

        # Compute ISI (in samples)
        isi = np.diff(discharges)

        if len(isi) < 2:
            covisi_values.append(np.nan)
            continue

        # Compute CoVISI = (std / mean) * 100
        mean_isi = np.mean(isi)
        std_isi = np.std(isi)

        if mean_isi > 0:
            covisi = (std_isi / mean_isi) * 100.0
        else:
            covisi = np.nan

        covisi_values.append(covisi)

    return covisi_values


def compute_covisi_from_muedit_mat(
    mat_path: str,
    fsamp: float,
) -> pd.DataFrame:
    """
    Compute CoVISI from an MUedit-edited MAT file.

    Extracts cleaned discharge times from the MAT file and computes
    CoVISI for each motor unit.

    Parameters
    ----------
    mat_path : str
        Path to the MUedit-edited MAT file (*_edited.mat).
    fsamp : float
        Sampling frequency in Hz.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - mu_index: Motor unit index (0-based)
        - covisi_all: CoVISI value for the entire contraction
    """
    discharge_times = []

    try:
        with h5py.File(mat_path, "r") as f:
            # Navigate to cleaned discharge times
            if "edition" not in f:
                raise ValueError(f"No 'edition' group found in {mat_path}")

            edition = f["edition"]

            if "Distimeclean" not in edition:
                raise ValueError(
                    f"No 'Distimeclean' found in edition group of {mat_path}"
                )

            distimeclean = edition["Distimeclean"]

            # Handle different array structures
            # MUedit stores as (ngrids x nMU) cell array of references
            if distimeclean.ndim == 2:
                n_grids, n_mus = distimeclean.shape
                for mu_idx in range(n_mus):
                    # Get discharge times for this MU (from first grid)
                    ref = distimeclean[0, mu_idx]
                    if isinstance(ref, h5py.Reference):
                        data = np.array(f[ref]).flatten()
                    else:
                        data = np.array(ref).flatten()

                    # Convert from 1-based MATLAB to 0-based Python
                    if len(data) > 0:
                        data = data - 1

                    discharge_times.append(data)
            else:
                # Single grid case
                for mu_idx in range(len(distimeclean)):
                    ref = distimeclean[mu_idx]
                    if isinstance(ref, h5py.Reference):
                        data = np.array(f[ref]).flatten()
                    else:
                        data = np.array(ref).flatten()

                    if len(data) > 0:
                        data = data - 1

                    discharge_times.append(data)

    except Exception as e:
        logger.error(f"Failed to read discharge times from {mat_path}: {e}")
        raise

    # Compute CoVISI from discharge times
    covisi_values = compute_covisi_from_discharge_times(discharge_times, fsamp)

    # Create DataFrame
    result_df = pd.DataFrame(
        {
            "mu_index": range(len(covisi_values)),
            "covisi_all": covisi_values,
        }
    )

    return result_df


def compare_pre_post_covisi(
    pre_covisi_df: pd.DataFrame,
    post_covisi_df: pd.DataFrame,
) -> dict:
    """
    Compare CoVISI values before and after MUedit cleaning.

    Parameters
    ----------
    pre_covisi_df : pd.DataFrame
        CoVISI DataFrame before cleaning (from compute_covisi_for_all_mus).
    post_covisi_df : pd.DataFrame
        CoVISI DataFrame after cleaning (from compute_covisi_from_muedit_mat).

    Returns
    -------
    dict
        Comparison report containing:
        - pre_mu_count: Number of MUs before cleaning
        - post_mu_count: Number of MUs after cleaning
        - mus_removed: Number of MUs removed during cleaning
        - avg_covisi_pre: Average CoVISI before cleaning
        - avg_covisi_post: Average CoVISI after cleaning
        - avg_improvement_percent: Average improvement in CoVISI
        - mus_exceeding_threshold: List of MU indices still > 30%
        - comparison_details: List of per-MU comparison dicts
    """
    pre_count = len(pre_covisi_df)
    post_count = len(post_covisi_df)

    # Calculate averages (excluding NaN)
    avg_pre = pre_covisi_df["covisi_all"].mean()
    avg_post = post_covisi_df["covisi_all"].mean()

    # Identify MUs exceeding threshold after cleaning
    exceeding_mask = post_covisi_df["covisi_all"] > DEFAULT_COVISI_THRESHOLD
    exceeding_indices = post_covisi_df.loc[exceeding_mask, "mu_index"].tolist()

    # Build per-MU comparison (assumes indices align after cleaning)
    comparison_details = []
    n_compare = min(pre_count, post_count)

    for i in range(n_compare):
        pre_val = pre_covisi_df.loc[i, "covisi_all"]
        post_val = post_covisi_df.loc[i, "covisi_all"]

        if pd.notna(pre_val) and pd.notna(post_val) and pre_val > 0:
            improvement = ((pre_val - post_val) / pre_val) * 100
        else:
            improvement = np.nan

        comparison_details.append(
            {
                "mu_index": i,
                "covisi_pre": pre_val,
                "covisi_post": post_val,
                "improvement_percent": improvement,
                "exceeds_threshold": post_val > DEFAULT_COVISI_THRESHOLD
                if pd.notna(post_val)
                else False,
            }
        )

    # Calculate average improvement
    improvements = [
        d["improvement_percent"]
        for d in comparison_details
        if pd.notna(d["improvement_percent"])
    ]
    avg_improvement = np.mean(improvements) if improvements else np.nan

    report = {
        "pre_mu_count": pre_count,
        "post_mu_count": post_count,
        "mus_removed": pre_count - post_count,
        "avg_covisi_pre": float(avg_pre) if pd.notna(avg_pre) else None,
        "avg_covisi_post": float(avg_post) if pd.notna(avg_post) else None,
        "avg_improvement_percent": float(avg_improvement)
        if pd.notna(avg_improvement)
        else None,
        "mus_exceeding_threshold": exceeding_indices,
        "threshold_used": DEFAULT_COVISI_THRESHOLD,
        "comparison_details": comparison_details,
    }

    return report


def save_covisi_report(
    report: dict,
    output_path: str,
    report_type: str = "pre_filter",
) -> None:
    """
    Save a CoVISI filtering/validation report to JSON.

    Parameters
    ----------
    report : dict
        The report dictionary to save.
    output_path : str
        Path where the report will be saved.
    report_type : str, default "pre_filter"
        Type of report: "pre_filter" or "post_validation".
    """
    report_with_metadata = {
        "report_type": report_type,
        "timestamp": datetime.now().isoformat(),
        "covisi_threshold": DEFAULT_COVISI_THRESHOLD,
        **report,
    }

    with open(output_path, "w") as f:
        json.dump(report_with_metadata, f, indent=2, default=str)

    logger.info(f"Saved CoVISI {report_type} report to: {output_path}")


def load_covisi_report(report_path: str) -> dict:
    """
    Load a CoVISI report from JSON.

    Parameters
    ----------
    report_path : str
        Path to the report JSON file.

    Returns
    -------
    dict
        The loaded report dictionary.
    """
    with open(report_path, "r") as f:
        return json.load(f)


def get_covisi_quality_category(covisi_value: float) -> str:
    """
    Categorize a CoVISI value into a quality category.

    Parameters
    ----------
    covisi_value : float
        The CoVISI value in percent.

    Returns
    -------
    str
        Quality category: "excellent", "good", "marginal", or "poor".
    """
    if pd.isna(covisi_value):
        return "unknown"
    elif covisi_value <= 20:
        return "excellent"
    elif covisi_value <= 30:
        return "good"
    elif covisi_value <= 50:
        return "marginal"
    else:
        return "poor"


def load_reference_signal_from_muedit_mat(mat_path: str) -> Tuple[Optional[np.ndarray], Optional[float]]:
    """
    Load the reference signal (path/target) from an MUedit MAT file.

    Parameters
    ----------
    mat_path : str
        Path to the MUedit MAT file.

    Returns
    -------
    tuple
        (signal, sampling_frequency) or (None, None) if not found.
    """
    try:
        # Try to load with scipy.io first (older MAT format)
        try:
            mat_data = sio.loadmat(mat_path, squeeze_me=True, struct_as_record=False)
            signal_struct = mat_data.get('signal')
            if signal_struct is not None:
                # Get path signal (performed path)
                path_signal = getattr(signal_struct, 'path', None)
                fsamp = getattr(signal_struct, 'fsamp', 2048)

                if path_signal is not None:
                    signal = np.asarray(path_signal).flatten()
                    return signal, float(fsamp)

        except NotImplementedError:
            # MATLAB v7.3 file, use h5py
            pass

        # Load with h5py for HDF5/v7.3 format
        with h5py.File(mat_path, 'r') as f:
            if 'signal' not in f:
                logger.warning(f"No 'signal' group in {mat_path}")
                return None, None

            signal_group = f['signal']

            # Get sampling frequency
            fsamp = 2048.0
            if 'fsamp' in signal_group:
                fsamp_data = signal_group['fsamp'][()]
                fsamp = float(np.squeeze(fsamp_data))

            # Get path signal
            if 'path' in signal_group:
                path_data = signal_group['path'][()]
                signal = np.asarray(path_data).flatten()
                return signal, fsamp

            # Fallback to target signal
            if 'target' in signal_group:
                target_data = signal_group['target'][()]
                signal = np.asarray(target_data).flatten()
                return signal, fsamp

        return None, None

    except Exception as e:
        logger.error(f"Failed to load reference signal from {mat_path}: {e}")
        return None, None


class SteadyStateSelectionDialog(QtWidgets.QDialog):
    """
    Dialog for interactive selection of the steady-state phase.

    Displays the reference signal (force/torque path) from MUedit MAT files
    and allows the user to select the steady-state plateau region by dragging
    or two-click selection.
    """

    def __init__(self, mat_files: List[str], parent=None):
        """
        Initialize the dialog.

        Parameters
        ----------
        mat_files : list
            List of paths to MUedit MAT files containing reference signals.
        parent : QWidget, optional
            Parent widget.
        """
        super().__init__(parent)
        logger.info(f"Initializing Steady-State Selection Dialog for {len(mat_files)} file(s)")

        self.mat_files = mat_files
        self.signal_data: dict = {}  # filename -> (time, signal)
        self.sampling_frequency = 2048.0

        # Selection state
        self.selected_region: Optional[Tuple[float, float]] = None
        self.span_selector = None
        self.selection_lines = []
        self.first_click_pos = None

        # Result values
        self.start_steady = None
        self.end_steady = None

        self.load_signals()
        self.init_ui()

    def load_signals(self):
        """Load reference signals from all MAT files."""
        self.signal_data.clear()

        for mat_path in self.mat_files:
            try:
                signal, fsamp = load_reference_signal_from_muedit_mat(mat_path)
                if signal is not None:
                    filename = os.path.basename(mat_path)
                    self.sampling_frequency = fsamp

                    # Create time array
                    time = np.arange(len(signal)) / fsamp
                    self.signal_data[filename] = (time, signal)
                    logger.debug(f"Loaded reference signal from {filename}: {len(signal)} samples")
            except Exception as e:
                logger.error(f"Failed to load {mat_path}: {e}")

        logger.info(f"Loaded {len(self.signal_data)} reference signal(s)")

    def init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("Select Steady-State Phase")
        self.resize(1200, 700)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG_SECONDARY};
            }}
        """)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        main_layout.setSpacing(Spacing.LG)

        # Header
        header = QtWidgets.QLabel("Select Steady-State Phase")
        header.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_XXL};
                font-weight: {Fonts.WEIGHT_BOLD};
            }}
        """)

        instruction = QtWidgets.QLabel(
            "Drag to select the plateau region of your contraction. "
            "This region will be used for steady-state CoVISI analysis."
        )
        instruction.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
            }}
        """)
        instruction.setWordWrap(True)

        main_layout.addWidget(header)
        main_layout.addWidget(instruction)

        # ROI info and action buttons
        self._create_action_panel(main_layout)

        # Selection panel with plot
        self._create_selection_panel(main_layout)

    def _create_selection_panel(self, parent_layout):
        """Create the signal selection panel with matplotlib plot."""
        panel = QtWidgets.QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.LG};
            }}
        """)

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)

        # Matplotlib figure
        self.figure = Figure(figsize=(12, 5), facecolor=Colors.BG_PRIMARY)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(Colors.BG_PRIMARY)

        # Navigation toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet(f"""
            QToolBar {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px;
            }}
        """)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        parent_layout.addWidget(panel)

        # Initialize plot
        self._update_plot()

    def _create_action_panel(self, parent_layout):
        """Create the ROI info and action buttons panel."""
        panel = QtWidgets.QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
            }}
        """)

        layout = QtWidgets.QHBoxLayout(panel)
        layout.setSpacing(Spacing.LG)

        # Spinbox style
        spinbox_style = f"""
            QDoubleSpinBox {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_SM};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                background-color: {Colors.GRAY_100};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
                min-width: 100px;
            }}
            QDoubleSpinBox:focus {{
                border: 1px solid {Colors.BLUE_600};
            }}
        """

        label_style = f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_SM};
            }}
        """

        # Start time input
        start_label = QtWidgets.QLabel("Start:")
        start_label.setStyleSheet(label_style)
        layout.addWidget(start_label)

        self.start_spin = QtWidgets.QDoubleSpinBox()
        self.start_spin.setDecimals(2)
        self.start_spin.setSuffix(" s")
        self.start_spin.setRange(0, 10000)
        self.start_spin.setSingleStep(0.5)
        self.start_spin.setStyleSheet(spinbox_style)
        self.start_spin.valueChanged.connect(self._on_time_input_changed)
        layout.addWidget(self.start_spin)

        layout.addSpacing(Spacing.MD)

        # End time input
        end_label = QtWidgets.QLabel("End:")
        end_label.setStyleSheet(label_style)
        layout.addWidget(end_label)

        self.end_spin = QtWidgets.QDoubleSpinBox()
        self.end_spin.setDecimals(2)
        self.end_spin.setSuffix(" s")
        self.end_spin.setRange(0, 10000)
        self.end_spin.setSingleStep(0.5)
        self.end_spin.setStyleSheet(spinbox_style)
        self.end_spin.valueChanged.connect(self._on_time_input_changed)
        layout.addWidget(self.end_spin)

        layout.addSpacing(Spacing.MD)

        # Duration label
        self.duration_label = QtWidgets.QLabel("Duration: --")
        self.duration_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_SM};
                font-weight: {Fonts.WEIGHT_MEDIUM};
                background-color: {Colors.GRAY_100};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                padding: {Spacing.XS}px {Spacing.SM}px;
            }}
        """)
        layout.addWidget(self.duration_label)

        layout.addStretch()

        # Reset button
        btn_reset = QtWidgets.QPushButton("Reset Selection")
        btn_reset.setStyleSheet(Styles.button_secondary())
        btn_reset.clicked.connect(self.reset_selection)
        layout.addWidget(btn_reset)

        # Confirm button
        self.btn_confirm = QtWidgets.QPushButton("Confirm Selection")
        self.btn_confirm.setStyleSheet(Styles.button_primary())
        self.btn_confirm.clicked.connect(self.confirm_selection)
        self.btn_confirm.setEnabled(False)
        layout.addWidget(self.btn_confirm)

        # Cancel button
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.setStyleSheet(Styles.button_secondary())
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

        parent_layout.addWidget(panel)

    def _update_plot(self):
        """Update the selection plot with overlaid reference signals."""
        self.ax.clear()
        self.ax.set_facecolor(Colors.BG_PRIMARY)

        if not self.signal_data:
            self.ax.text(0.5, 0.5, "No reference signals found in MAT files",
                         ha='center', va='center', transform=self.ax.transAxes,
                         fontsize=12, color=Colors.TEXT_SECONDARY)
            self.canvas.draw_idle()
            return

        # Get max duration for setting default steady-state suggestion
        max_duration = 0.0

        # Plot all reference signals (normalized for overlay)
        colors = ['#2563eb', '#059669', '#dc2626', '#7c3aed', '#ea580c']
        for idx, (filename, (time, signal)) in enumerate(self.signal_data.items()):
            color = colors[idx % len(colors)]
            max_duration = max(max_duration, time[-1])

            # Normalize to [0, 1] for visualization
            signal_min, signal_max = signal.min(), signal.max()
            if signal_max != signal_min:
                signal_norm = (signal - signal_min) / (signal_max - signal_min)
            else:
                signal_norm = signal

            self.ax.plot(time, signal_norm, color=color, alpha=0.7, linewidth=1.2,
                         label=filename.replace('_muedit.mat', ''))

        # Academic-style formatting
        self.ax.set_xlabel("Time (s)", fontsize=11, fontfamily='sans-serif')
        self.ax.set_ylabel("Normalized Force (a.u.)", fontsize=11, fontfamily='sans-serif')
        self.ax.set_title("Reference Signal (Force/Torque Path)", fontsize=12,
                          fontweight='bold', fontfamily='sans-serif')
        self.ax.grid(True, alpha=0.3, linestyle='--', color='gray')
        self.ax.tick_params(labelsize=10)

        # Legend
        if len(self.signal_data) <= 6:
            self.ax.legend(loc='upper right', fontsize=9, framealpha=0.9)
        else:
            self.ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5),
                           fontsize=8, framealpha=0.9)
            self.figure.subplots_adjust(right=0.80)

        # Set default steady-state suggestion (middle 60% of signal)
        if max_duration > 0 and self.selected_region is None:
            suggested_start = max_duration * 0.2
            suggested_end = max_duration * 0.8
            self.start_spin.setMaximum(max_duration)
            self.end_spin.setMaximum(max_duration)
            self.start_spin.setValue(round(suggested_start, 1))
            self.end_spin.setValue(round(suggested_end, 1))

        # Setup span selector
        self.span_selector = SpanSelector(
            self.ax,
            self._on_span_select,
            'horizontal',
            useblit=True,
            props=dict(alpha=0.3, facecolor=Colors.BLUE_500),
            interactive=True,
            drag_from_anywhere=True
        )

        # Connect click event for two-click selection
        self.canvas.mpl_connect('button_press_event', self._on_click)

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _on_span_select(self, xmin, xmax):
        """Handle span selection (drag mode)."""
        self.first_click_pos = None
        self.selected_region = (xmin, xmax)
        self._update_roi_display()
        self._draw_selection_lines()
        self.btn_confirm.setEnabled(True)
        logger.debug(f"Region selected: {xmin:.3f} - {xmax:.3f} s")

    def _on_click(self, event):
        """Handle click events for two-click selection."""
        if event.inaxes != self.ax or event.button != 1:
            return
        if self.toolbar.mode != '':
            return

        x_pos = event.xdata

        if self.first_click_pos is None:
            self.first_click_pos = x_pos
            self._draw_selection_lines()
        else:
            second_pos = x_pos
            start = min(self.first_click_pos, second_pos)
            end = max(self.first_click_pos, second_pos)
            self.selected_region = (start, end)
            self.first_click_pos = None

            # Update SpanSelector to show the selection
            if self.span_selector is not None:
                self.span_selector.extents = (start, end)

            self._update_roi_display()
            self._draw_selection_lines()
            self.btn_confirm.setEnabled(True)

    def _update_roi_display(self):
        """Update the ROI info spinboxes."""
        if self.selected_region:
            start, end = self.selected_region
            duration = end - start

            # Block signals to avoid recursion when updating from code
            self.start_spin.blockSignals(True)
            self.end_spin.blockSignals(True)

            self.start_spin.setValue(start)
            self.end_spin.setValue(end)
            self.duration_label.setText(f"Duration: {duration:.2f} s")

            self.start_spin.blockSignals(False)
            self.end_spin.blockSignals(False)

    def _on_time_input_changed(self):
        """Handle manual time input changes."""
        start = self.start_spin.value()
        end = self.end_spin.value()

        # Validate: end must be after start
        if end <= start:
            return

        # Update selected region
        self.selected_region = (start, end)

        # Update duration label
        duration = end - start
        self.duration_label.setText(f"Duration: {duration:.2f} s")

        # Update the SpanSelector to match the new values
        if self.span_selector is not None:
            self.span_selector.extents = (start, end)

        # Update visualization
        self._draw_selection_lines()
        self.btn_confirm.setEnabled(True)

    def _draw_selection_lines(self):
        """Draw selection visualization."""
        # Remove old lines
        for line in self.selection_lines:
            try:
                line.remove()
            except Exception:
                pass
        self.selection_lines.clear()

        # Draw first click indicator if in two-click mode
        if self.first_click_pos is not None:
            line = self.ax.axvline(self.first_click_pos, color=Colors.BLUE_600,
                                   linestyle='--', linewidth=2)
            self.selection_lines.append(line)

        self.canvas.draw_idle()

    def reset_selection(self):
        """Reset the selection."""
        self.selected_region = None
        self.first_click_pos = None

        # Remove selection lines
        for line in self.selection_lines:
            try:
                line.remove()
            except Exception:
                pass
        self.selection_lines.clear()

        # Reset SpanSelector
        if self.span_selector is not None:
            self.span_selector.extents = (0, 0)

        # Reset spinboxes to default suggestion
        max_duration = 0.0
        for time, _ in self.signal_data.values():
            max_duration = max(max_duration, time[-1])

        if max_duration > 0:
            self.start_spin.blockSignals(True)
            self.end_spin.blockSignals(True)
            self.start_spin.setValue(round(max_duration * 0.2, 1))
            self.end_spin.setValue(round(max_duration * 0.8, 1))
            self.start_spin.blockSignals(False)
            self.end_spin.blockSignals(False)

        self.duration_label.setText("Duration: --")
        self.btn_confirm.setEnabled(False)

        self.canvas.draw_idle()
        logger.info("Selection reset")

    def confirm_selection(self):
        """Confirm the selection and close the dialog."""
        start = self.start_spin.value()
        end = self.end_spin.value()

        if end <= start:
            QtWidgets.QMessageBox.warning(
                self, "Invalid Selection",
                "End time must be greater than start time."
            )
            return

        if end - start < 0.5:
            QtWidgets.QMessageBox.warning(
                self, "Selection Too Short",
                "Please select at least 0.5 seconds for steady-state analysis."
            )
            return

        self.start_steady = start
        self.end_steady = end

        logger.info(f"Steady-state selection confirmed: {start:.2f}s - {end:.2f}s")
        self.accept()

    def get_selection(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get the selected steady-state boundaries.

        Returns
        -------
        tuple
            (start_steady, end_steady) in seconds, or (None, None) if not selected.
        """
        return self.start_steady, self.end_steady
