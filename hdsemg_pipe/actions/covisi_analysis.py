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
from typing import Optional

import h5py
import numpy as np
import pandas as pd

from hdsemg_pipe._log.log_config import logger

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


def compute_covisi_for_all_mus(
    emgfile: dict,
    n_firings_rec_derec: int = 4,
) -> pd.DataFrame:
    """
    Compute CoVISI for all motor units in an emgfile.

    Uses openhdemg's compute_covisi() with event_="rec_derec" to avoid
    interactive steady-state selection.

    Parameters
    ----------
    emgfile : dict
        The openhdemg emgfile dictionary containing IPTS, MUPULSES, etc.
    n_firings_rec_derec : int, default 4
        Number of firings at recruitment/derecruitment to consider.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - mu_index: Motor unit index (0-based)
        - covisi_rec: CoVISI at recruitment
        - covisi_derec: CoVISI at derecruitment
        - covisi_all: CoVISI for entire contraction (used for filtering)

    Raises
    ------
    RuntimeError
        If openhdemg is not available.
    ValueError
        If emgfile has no motor units.
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

    # Compute CoVISI using openhdemg
    # event_="rec_derec" avoids interactive steady-state selection
    try:
        covisi_df = emg.compute_covisi(
            emgfile=emgfile,
            n_firings_RecDerec=n_firings_rec_derec,
            event_="rec_derec",
            start_steady=0,  # Dummy values, not used with event_="rec_derec"
            end_steady=1,
        )
    except Exception as e:
        logger.error(f"Failed to compute CoVISI: {e}")
        raise

    # Add MU index column
    covisi_df = covisi_df.reset_index(drop=True)
    covisi_df.insert(0, "mu_index", range(len(covisi_df)))

    # Rename columns for consistency
    covisi_df = covisi_df.rename(
        columns={
            "COVisi_rec": "covisi_rec",
            "COVisi_derec": "covisi_derec",
            "COVisi_all": "covisi_all",
        }
    )

    return covisi_df


def filter_mus_by_covisi(
    emgfile: dict,
    threshold: float = DEFAULT_COVISI_THRESHOLD,
    n_firings_rec_derec: int = 4,
) -> tuple[dict, pd.DataFrame]:
    """
    Filter motor units based on CoVISI threshold.

    Removes motor units with CoVISI_all > threshold from the emgfile.

    Parameters
    ----------
    emgfile : dict
        The openhdemg emgfile dictionary.
    threshold : float, default 30.0
        CoVISI threshold in percent. MUs with CoVISI > threshold are removed.
    n_firings_rec_derec : int, default 4
        Number of firings at recruitment/derecruitment for CoVISI calculation.

    Returns
    -------
    tuple[dict, pd.DataFrame]
        - filtered_emgfile: New emgfile dict with filtered MUs
        - report_df: DataFrame with filtering results containing:
          - mu_index: Original MU index
          - covisi_all: CoVISI value
          - status: "kept" or "removed"
    """
    # Compute CoVISI for all MUs
    covisi_df = compute_covisi_for_all_mus(
        emgfile, n_firings_rec_derec=n_firings_rec_derec
    )

    # Determine which MUs to keep
    kept_mask = covisi_df["covisi_all"] <= threshold
    kept_indices = covisi_df.loc[kept_mask, "mu_index"].tolist()
    removed_indices = covisi_df.loc[~kept_mask, "mu_index"].tolist()

    # Create filtering report
    covisi_df["status"] = np.where(kept_mask, "kept", "removed")
    report_df = covisi_df.copy()

    logger.info(
        f"CoVISI filtering: {len(kept_indices)} MUs kept, "
        f"{len(removed_indices)} MUs removed (threshold={threshold}%)"
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
    """
    if not OPENHDEMG_AVAILABLE:
        raise RuntimeError(
            "openhdemg library is required for CoVISI filtering"
        )

    # Load JSON
    logger.info(f"Loading JSON for CoVISI filtering: {json_path}")
    emgfile = emg.emg_from_json(str(json_path))

    original_count = emgfile.get("NUMBER_OF_MUS", 0)

    # Apply filtering
    filtered_emgfile, report_df = filter_mus_by_covisi(
        emgfile,
        threshold=threshold,
        n_firings_rec_derec=n_firings_rec_derec,
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
