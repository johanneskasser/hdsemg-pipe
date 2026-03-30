"""
Duplicate Motor Unit Detection

This module implements duplicate MU detection based on MUEdit's remduplicatesbgrids.m algorithm.
Detects duplicate motor units within and between grids by comparing discharge times with
cross-correlation and jitter tolerance.

Author: hdsemg-pipe
Date: 2026-02-19
"""

import numpy as np
import pandas as pd
from scipy.signal import correlate
import copy
from typing import List, Dict, Tuple, Union, Optional
from pathlib import Path

from hdsemg_pipe._log.log_config import logger

try:
    import openhdemg.library as emg
    OPENHDEMG_AVAILABLE = True
except ImportError:
    OPENHDEMG_AVAILABLE = False
    logger.warning("openhdemg not available - duplicate detection will not work")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_discharge_times(emgfile: dict, mu_idx: int) -> np.ndarray:
    """
    Extract discharge times for a specific MU from an openhdemg emgfile.

    Args:
        emgfile: openhdemg emgfile dictionary
        mu_idx: Motor unit index (0-based)

    Returns:
        Sorted numpy array of discharge times (in seconds), with invalid values filtered

    Raises:
        ValueError: If no discharge times found in emgfile
    """
    discharge_times = None

    # Try MUPULSES first (preferred)
    if 'MUPULSES' in emgfile:
        mupulses = emgfile['MUPULSES']
        if isinstance(mupulses, pd.DataFrame):
            discharge_times = mupulses.iloc[mu_idx].values
        elif isinstance(mupulses, list):
            discharge_times = np.array(mupulses[mu_idx])
        else:
            discharge_times = np.array(mupulses)

    # Fallback to IPTS
    elif 'IPTS' in emgfile:
        ipts = emgfile['IPTS']
        if isinstance(ipts, pd.DataFrame):
            discharge_times = ipts.iloc[mu_idx].values
        elif isinstance(ipts, list):
            discharge_times = np.array(ipts[mu_idx])
        else:
            discharge_times = np.array(ipts)

    else:
        raise ValueError("No discharge times found in emgfile (no MUPULSES or IPTS)")

    # Ensure numpy array
    if not isinstance(discharge_times, np.ndarray):
        discharge_times = np.array(discharge_times)

    # Filter out NaN and negative values
    discharge_times = discharge_times[~np.isnan(discharge_times)]
    discharge_times = discharge_times[discharge_times >= 0]

    # Return sorted
    return np.sort(discharge_times)


def compute_cov_isi(discharge_times: np.ndarray) -> float:
    """
    Compute coefficient of variation of interspike intervals (CoV ISI).

    The CoV ISI is a measure of firing regularity. Lower values indicate more regular firing.
    MUs with lowest CoV ISI are considered highest quality and selected as survivors.

    Args:
        discharge_times: Array of discharge times (in seconds), sorted

    Returns:
        CoV ISI as percentage (std/mean * 100), or np.inf if < 2 discharges
    """
    if len(discharge_times) < 2:
        return np.inf  # Cannot compute ISI

    # Ensure sorted
    discharge_times = np.sort(discharge_times)

    # Compute interspike intervals
    isi = np.diff(discharge_times)

    # CoV = (std / mean) * 100
    mean_isi = np.mean(isi)
    if mean_isi == 0:
        return np.inf

    cov = (np.std(isi) / mean_isi) * 100
    return cov


# ============================================================================
# SIGNAL PROCESSING FUNCTIONS
# ============================================================================

def apply_jitter_broadening(
    discharge_times: np.ndarray,
    jitter: float,
    fsamp: float,
    emg_length: int
) -> np.ndarray:
    """
    Create binary spike train with jitter tolerance ("broadening").

    For each discharge time t, creates spikes at [t-jitter, ..., t, ..., t+jitter]
    to account for small timing variations.

    Args:
        discharge_times: Array of discharge times (in seconds)
        jitter: Time tolerance in seconds (e.g., 0.05 = 50ms)
        fsamp: Sampling frequency in Hz
        emg_length: Length of EMG signal in samples

    Returns:
        Binary spike train (1D numpy array of shape (emg_length,))
    """
    # Convert jitter from seconds to samples
    jitter_samples = int(np.round(jitter * fsamp))

    # Initialize binary spike train
    binary_spikes = np.zeros(emg_length, dtype=np.int8)

    # Convert discharge times to sample indices
    discharge_samples = np.round(discharge_times * fsamp).astype(int)

    # For each discharge, set spikes in [t-jitter, t+jitter] window
    for t in discharge_samples:
        # Determine window bounds
        start_idx = max(0, t - jitter_samples)
        end_idx = min(emg_length, t + jitter_samples + 1)

        # Set all samples in window to 1
        binary_spikes[start_idx:end_idx] = 1

    return binary_spikes


def compute_xcorr_lag(
    binary_firing1: np.ndarray,
    binary_firing2: np.ndarray,
    maxlag: int
) -> Tuple[int, float]:
    """
    Find optimal time lag between two binary spike trains using cross-correlation.

    Args:
        binary_firing1: First binary spike train (reference)
        binary_firing2: Second binary spike train (to be shifted)
        maxlag: Maximum lag to consider in samples

    Returns:
        Tuple of (best_lag, normalized_correlation)
        - best_lag: Lag that maximizes correlation (in samples, can be negative)
        - normalized_correlation: Correlation value normalized by signal length
    """
    # Compute cross-correlation (mode='same' centers the correlation)
    # Output length equals len(binary_firing2) (first argument)
    xcorr = correlate(binary_firing2, binary_firing1, mode='same')

    # Create lag vector based on xcorr length to guarantee alignment.
    # np.arange(n) - n//2 is safe for both even and odd lengths;
    # the -n//2 shorthand is wrong for odd n due to Python floor division.
    n_xcorr = len(xcorr)
    n = len(binary_firing1)  # kept for normalization
    lags = np.arange(n_xcorr) - n_xcorr // 2

    # Restrict to maxlag window
    valid_idx = np.abs(lags) <= maxlag
    xcorr_valid = xcorr[valid_idx]
    lags_valid = lags[valid_idx]

    # Find lag with maximum correlation
    max_idx = np.argmax(xcorr_valid)
    best_lag = lags_valid[max_idx]
    max_corr = xcorr_valid[max_idx]

    # Normalize correlation by signal length
    norm_corr = max_corr / n

    return best_lag, norm_corr


def compute_overlap_score(
    discharge_times1: np.ndarray,
    discharge_times2: np.ndarray,
    maxlag: int,
    jitter: float,
    fsamp: float,
    emg_length: int
) -> Tuple[float, int]:
    """
    Compute overlap percentage between two MUs' discharge times.

    This implements the core duplicate detection logic from MUEdit:
    1. Create jittered binary spike trains
    2. Find optimal lag via cross-correlation
    3. Apply lag correction if correlation > 0.2 (MUEdit threshold)
    4. Compute overlap as shared spikes / max(spikes1, spikes2)

    Args:
        discharge_times1: First MU's discharge times (seconds)
        discharge_times2: Second MU's discharge times (seconds)
        maxlag: Maximum lag for cross-correlation (samples)
        jitter: Jitter tolerance (seconds)
        fsamp: Sampling frequency (Hz)
        emg_length: EMG signal length (samples)

    Returns:
        Tuple of (overlap_score, lag_applied)
        - overlap_score: Fraction of shared discharges (0.0 to 1.0)
        - lag_applied: Lag that was applied in samples (0 if no lag correction)
    """
    # Step 1: Create jittered binary spike trains
    binary1 = apply_jitter_broadening(discharge_times1, jitter, fsamp, emg_length)
    binary2 = apply_jitter_broadening(discharge_times2, jitter, fsamp, emg_length)

    # Step 2: Find optimal lag
    lag, xcorr = compute_xcorr_lag(binary1, binary2, maxlag)

    # Step 3: Apply lag correction if correlation significant
    lag_applied = 0
    if xcorr > 0.2:  # MUEdit threshold
        # Shift discharge times by lag
        discharge_times2_shifted = discharge_times2 + (lag / fsamp)
        lag_applied = lag

        # Recompute broadened spike train after shift
        binary2 = apply_jitter_broadening(discharge_times2_shifted, jitter, fsamp, emg_length)

    # Step 4: Compute overlap
    # Overlap = count of shared spikes / max(spikes1, spikes2)
    overlap_samples = np.sum(binary1 & binary2)

    # Normalize by max number of discharges (not broadened samples)
    max_discharges = max(len(discharge_times1), len(discharge_times2))

    if max_discharges == 0:
        return 0.0, lag_applied

    overlap_score = overlap_samples / max_discharges

    return overlap_score, lag_applied


# ============================================================================
# DETECTION FUNCTIONS
# ============================================================================

def select_survivor(
    duplicate_mus: List[Tuple[int, int]],
    emgfile_list: List[dict]
) -> Tuple[Tuple[int, int], Dict[Tuple[int, int], float]]:
    """
    Select which MU to keep in a duplicate group (lowest CoV ISI).

    Args:
        duplicate_mus: List of (file_idx, mu_idx) tuples in duplicate group
        emgfile_list: List of openhdemg emgfiles

    Returns:
        Tuple of (survivor, cov_dict)
        - survivor: (file_idx, mu_idx) of MU with lowest CoV ISI
        - cov_dict: Dictionary mapping (file_idx, mu_idx) to CoV ISI value
    """
    cov_values = {}

    for file_idx, mu_idx in duplicate_mus:
        emgfile = emgfile_list[file_idx]
        discharge_times = get_discharge_times(emgfile, mu_idx)
        cov = compute_cov_isi(discharge_times)
        cov_values[(file_idx, mu_idx)] = cov

    # Select MU with lowest CoV ISI (most regular firing)
    survivor = min(cov_values.keys(), key=lambda k: cov_values[k])

    return survivor, cov_values


def detect_duplicates_in_group(
    emgfile_list: List[dict],
    maxlag: int = 512,
    jitter: float = 0.05,
    tol: float = 0.8,
    fsamp: Optional[float] = None
) -> dict:
    """
    Main entry point: detect duplicate MUs within a group of emgfiles.

    Implements the MUEdit duplicate detection algorithm:
    1. Build pairwise overlap matrix for all MUs
    2. Mark pairs with overlap >= tol as duplicates
    3. Group duplicates using connected components
    4. For each duplicate group, select survivor (lowest CoV ISI)

    Args:
        emgfile_list: List of openhdemg emgfile dictionaries
        maxlag: Maximum lag for cross-correlation (samples)
        jitter: Jitter tolerance (seconds)
        tol: Overlap threshold (0.8 = 80% overlap required for duplicate)
        fsamp: Sampling frequency (Hz), auto-detected if None

    Returns:
        Dictionary with structure:
        {
            'duplicate_groups': [
                {
                    'mus': [(file_idx, mu_idx), ...],
                    'survivor': (file_idx, mu_idx),
                    'overlap_scores': [[score, ...], ...],  # Pairwise matrix
                    'cov_isi_values': {(file_idx, mu_idx): cov, ...},
                    'reason': 'Lowest CoV ISI'
                },
                ...
            ],
            'all_mus': [(file_idx, mu_idx), ...],  # All MUs in group
            'unique_mus': [(file_idx, mu_idx), ...]  # MUs not in any duplicate group
        }
    """
    # Auto-detect sampling frequency from first file
    if fsamp is None:
        fsamp = emgfile_list[0].get('FSAMP', 2048.0)
        logger.info(f"Auto-detected sampling frequency: {fsamp} Hz")

    # Get EMG length from first file
    emg_length = emgfile_list[0].get('EMG_LENGTH', 0)
    if emg_length == 0:
        # Fallback: infer from REF_SIGNAL
        if 'REF_SIGNAL' in emgfile_list[0]:
            emg_length = len(emgfile_list[0]['REF_SIGNAL'])
        else:
            raise ValueError("Cannot determine EMG_LENGTH from emgfile")

    # Build list of all MUs in the group
    all_mus = []
    for file_idx, emgfile in enumerate(emgfile_list):
        n_mus = emgfile.get('NUMBER_OF_MUS', 0)
        for mu_idx in range(n_mus):
            all_mus.append((file_idx, mu_idx))

    n_total_mus = len(all_mus)
    logger.info(f"Detecting duplicates among {n_total_mus} MUs in {len(emgfile_list)} files")

    if n_total_mus == 0:
        logger.warning("No MUs found in group")
        return {
            'duplicate_groups': [],
            'all_mus': [],
            'unique_mus': []
        }

    # Step 1: Build pairwise overlap matrix
    overlap_matrix = np.zeros((n_total_mus, n_total_mus))

    for i in range(n_total_mus):
        file_idx1, mu_idx1 = all_mus[i]
        discharge_times1 = get_discharge_times(emgfile_list[file_idx1], mu_idx1)

        for j in range(i, n_total_mus):  # Only compute upper triangle
            if i == j:
                overlap_matrix[i, j] = 1.0  # Self-overlap is 100%
            else:
                file_idx2, mu_idx2 = all_mus[j]
                discharge_times2 = get_discharge_times(emgfile_list[file_idx2], mu_idx2)

                overlap_score, _ = compute_overlap_score(
                    discharge_times1, discharge_times2,
                    maxlag, jitter, fsamp, emg_length
                )

                overlap_matrix[i, j] = overlap_score
                overlap_matrix[j, i] = overlap_score  # Symmetric

    # Step 2: Find duplicate pairs (overlap >= tol)
    duplicate_adjacency = overlap_matrix >= tol

    # Step 3: Group duplicates using connected components
    # (Simple iterative grouping - not the most efficient but works)
    visited = set()
    duplicate_groups = []

    for i in range(n_total_mus):
        if i in visited:
            continue

        # Find all MUs connected to this one
        connected = set([i])
        to_visit = [i]

        while to_visit:
            current = to_visit.pop()
            visited.add(current)

            # Find neighbors (duplicates)
            neighbors = np.where(duplicate_adjacency[current])[0]
            for neighbor in neighbors:
                if neighbor not in visited and neighbor not in connected:
                    connected.add(neighbor)
                    to_visit.append(neighbor)

        # Only consider groups with more than 1 MU as duplicates
        if len(connected) > 1:
            duplicate_group_mus = [all_mus[idx] for idx in connected]

            # Step 4: Select survivor
            survivor, cov_values = select_survivor(duplicate_group_mus, emgfile_list)

            # Extract overlap scores for this group
            group_indices = list(connected)
            group_overlap_scores = overlap_matrix[np.ix_(group_indices, group_indices)].tolist()

            duplicate_groups.append({
                'mus': duplicate_group_mus,
                'survivor': survivor,
                'overlap_scores': group_overlap_scores,
                'cov_isi_values': cov_values,
                'reason': 'Lowest CoV ISI'
            })

    # Find unique MUs (not in any duplicate group)
    mus_in_duplicates = set()
    for group in duplicate_groups:
        mus_in_duplicates.update(group['mus'])

    unique_mus = [mu for mu in all_mus if mu not in mus_in_duplicates]

    logger.info(f"Found {len(duplicate_groups)} duplicate groups, {len(unique_mus)} unique MUs")

    return {
        'duplicate_groups': duplicate_groups,
        'all_mus': all_mus,
        'unique_mus': unique_mus
    }


# ============================================================================
# FILTERING FUNCTIONS
# ============================================================================

def filter_mus_from_emgfile(emgfile: dict, keep_indices: List[int]) -> dict:
    """
    Remove specific MUs from an emgfile (keeps only specified indices).

    Similar to CoVISI filtering logic - filters IPTS, MUPULSES, BINARY_MUS_FIRING, ACCURACY.

    Args:
        emgfile: openhdemg emgfile dictionary
        keep_indices: List of MU indices to keep (0-based)

    Returns:
        New emgfile dictionary with filtered MUs
    """
    filtered = copy.deepcopy(emgfile)

    if len(keep_indices) == 0:
        # All MUs removed
        logger.warning("All MUs filtered out - creating empty structure")
        filtered['IPTS'] = pd.DataFrame() if isinstance(emgfile.get('IPTS'), pd.DataFrame) else []
        filtered['MUPULSES'] = []
        filtered['BINARY_MUS_FIRING'] = pd.DataFrame()
        filtered['ACCURACY'] = pd.DataFrame()
        filtered['NUMBER_OF_MUS'] = 0
        return filtered

    # Filter IPTS
    if 'IPTS' in emgfile:
        if isinstance(emgfile['IPTS'], pd.DataFrame):
            filtered['IPTS'] = emgfile['IPTS'].iloc[keep_indices].reset_index(drop=True)
        elif isinstance(emgfile['IPTS'], list):
            filtered['IPTS'] = [emgfile['IPTS'][i] for i in keep_indices]

    # Filter MUPULSES
    if 'MUPULSES' in emgfile:
        if isinstance(emgfile['MUPULSES'], pd.DataFrame):
            filtered['MUPULSES'] = emgfile['MUPULSES'].iloc[keep_indices].reset_index(drop=True)
        elif isinstance(emgfile['MUPULSES'], list):
            filtered['MUPULSES'] = [emgfile['MUPULSES'][i] for i in keep_indices]

    # Filter BINARY_MUS_FIRING (columns are MUs)
    if 'BINARY_MUS_FIRING' in emgfile and isinstance(emgfile['BINARY_MUS_FIRING'], pd.DataFrame):
        filtered['BINARY_MUS_FIRING'] = emgfile['BINARY_MUS_FIRING'].iloc[:, keep_indices]

    # Filter ACCURACY
    if 'ACCURACY' in emgfile and isinstance(emgfile['ACCURACY'], pd.DataFrame):
        if len(emgfile['ACCURACY']) > 0:
            filtered['ACCURACY'] = emgfile['ACCURACY'].iloc[keep_indices].reset_index(drop=True)

    # Update NUMBER_OF_MUS
    filtered['NUMBER_OF_MUS'] = len(keep_indices)

    return filtered


def remove_duplicates_from_emgfiles(
    emgfile_list: List[dict],
    duplicate_groups: List[dict]
) -> List[dict]:
    """
    Create new emgfiles with duplicates removed.

    Args:
        emgfile_list: List of original emgfiles
        duplicate_groups: List of duplicate group dicts from detect_duplicates_in_group()

    Returns:
        List of cleaned emgfiles (same length as input, with duplicates filtered out)
    """
    # Collect all MUs to remove (not survivors)
    mus_to_remove = set()
    for group in duplicate_groups:
        for mu in group['mus']:
            if mu != group['survivor']:
                mus_to_remove.add(mu)

    logger.info(f"Removing {len(mus_to_remove)} duplicate MUs")

    # Create cleaned emgfiles
    cleaned_emgfiles = []
    for file_idx, emgfile in enumerate(emgfile_list):
        # Find MUs to keep in this file
        n_mus = emgfile['NUMBER_OF_MUS']
        keep_indices = [
            mu_idx for mu_idx in range(n_mus)
            if (file_idx, mu_idx) not in mus_to_remove
        ]

        if len(keep_indices) == n_mus:
            # No MUs removed from this file
            logger.debug(f"File {file_idx}: No duplicates removed")
            cleaned_emgfiles.append(copy.deepcopy(emgfile))
        else:
            # Filter MUs
            logger.info(f"File {file_idx}: Removing {n_mus - len(keep_indices)} MUs (keeping {len(keep_indices)})")
            cleaned = filter_mus_from_emgfile(emgfile, keep_indices)
            cleaned_emgfiles.append(cleaned)

    return cleaned_emgfiles


def save_cleaned_jsons(
    cleaned_emgfiles: List[dict],
    original_paths: List[Union[str, Path]],
    output_folder: Union[str, Path],
    suffix: str = '_duplicates_removed'
) -> List[Path]:
    """
    Save cleaned emgfiles to JSON format.

    Args:
        cleaned_emgfiles: List of cleaned emgfile dictionaries
        original_paths: List of original file paths (for naming)
        output_folder: Output folder path
        suffix: Suffix to append to filenames (default: '_duplicates_removed')

    Returns:
        List of output file paths
    """
    if not OPENHDEMG_AVAILABLE:
        raise ImportError("openhdemg is required for saving JSON files")

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    output_paths = []

    for emgfile, original_path in zip(cleaned_emgfiles, original_paths):
        stem = Path(original_path).stem
        output_path = output_folder / f"{stem}{suffix}.json"

        # Save using openhdemg
        emg.save_json_emgfile(emgfile, str(output_path))
        logger.info(f"Saved cleaned file: {output_path.name}")
        output_paths.append(output_path)

    return output_paths
