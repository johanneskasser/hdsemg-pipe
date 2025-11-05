"""Functions for exporting decomposition outputs between different formats."""

import os
import numpy as np
import pandas as pd
import scipy.io as sio
from pathlib import Path

from hdsemg_pipe._log.log_config import logger

try:
    import openhdemg.library as emg
    OPENHDEMG_AVAILABLE = True
except ImportError:
    OPENHDEMG_AVAILABLE = False
    logger.warning("openhdemg library not available. Export functionality will be limited.")


def allocate_muedit_file_structure():
    """
    Minimal muedit structure: only 'signal' and 'parameters' with required fields.

    Returns
    -------
    dict
        {'signal': {required minimal keys for muedit}, 'parameters': {source file path and name info}}
    """
    signal = {
        # required
        'data': np.empty((0, 0), dtype=float),     # (nb_channels x samples)  -- EMG only
        'fsamp': float('nan'),
        'nChan': 0.0,
        'ngrid': 0.0,
        'gridname': np.empty((1, 0), dtype=object),    # 1 x ngrid cell row
        'muscle': np.empty((1, 0), dtype=object),      # 1 x ngrid cell row
        'Pulsetrain': np.empty((1, 0), dtype=object),  # 1 x ngrid cell row; each cell: (nbMU_i x time)
        'Dischargetimes': np.empty((0, 0), dtype=object),  # ngrid x maxMU
        'path': np.empty((0,), dtype=float),           # 1 x n_samples double: produced path
        'target': np.empty((0,), dtype=float),         # 1 x n_samples double: target path
        'coordinates': [],                             # 1 x ngrid cell; each cell: [n_grid_channels x 2] double (row, col) 1-based indices
        'IED': np.empty((0,), dtype=float),            # 1 x ngrid double: IED (mm)
        'EMGmask': [],                                 # 1 x ngrid cell; each cell: [n_grid_channels x 1] double (0=keep, 1=discard): select channels
        'emgtype': [],                                 # 1 x ngrid double; each entry 1 for surface EMG (per manual)
    }
    params = {
        'pathname': '',                # char
        'filename': '',                # char
    }

    return {'signal': signal, 'parameters': params}


def export_to_muedit_mat(json_load_filepath, ngrid=1):
    """
    Export OpenHD-EMG JSON decomposition results to MUEdit MAT format.

    This function converts decomposition results from OpenHD-EMG JSON format into
    a MATLAB .mat file that can be opened in MUEdit for manual cleaning of motor units.

    Args:
        json_load_filepath (str or Path): Path to the OpenHD-EMG JSON file.
        ngrid (int, optional): Number of electrode grids. Defaults to 1.

    Returns:
        str: Path to the created MUEdit MAT file, or None if export failed.

    Raises:
        ImportError: If openhdemg library is not available.
        FileNotFoundError: If the JSON file doesn't exist.
        ValueError: If the JSON file has invalid structure.

    Example:
        >>> export_to_muedit_mat('decomposition_result.json')
        'decomposition_result_muedit.mat'
    """
    if not OPENHDEMG_AVAILABLE:
        raise ImportError("openhdemg library is required for this function. "
                         "Please install it via Settings or pip install openhdemg")

    # Convert to Path object for easier handling
    json_path = Path(json_load_filepath)
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_load_filepath}")

    logger.info(f"Converting {json_path.name} to MUEdit format...")

    try:
        # Load OpenHD-EMG JSON file
        json_from_openhdemg = emg.emg_from_json(str(json_path))

        # Determine output path
        mat_save_filepath = str(json_path).replace(".json", "_muedit.mat")

        # Extract dimensions
        nMU = json_from_openhdemg["IPTS"].shape[1]
        nCH = json_from_openhdemg["RAW_SIGNAL"].shape[1]

        logger.debug(f"Converting file with {nMU} motor units and {nCH} channels")

        # Allocate MUEdit structure
        dict_for_muedit = allocate_muedit_file_structure()

        # Populate signal data
        dict_for_muedit["signal"]["data"] = np.transpose(json_from_openhdemg["RAW_SIGNAL"].to_numpy())
        dict_for_muedit["signal"]["fsamp"] = json_from_openhdemg["FSAMP"]
        dict_for_muedit["signal"]["nChan"] = nCH
        dict_for_muedit["signal"]["ngrid"] = ngrid  # Single grid at-a-time decomposition

        # Extract grid name and muscle from EXTRAS field
        try:
            extras_str = str(json_from_openhdemg["EXTRAS"].loc[0.0])
            gridname = extras_str.split(" - ")[-1].split(' ')[0].replace('HD', 'GR')
            muscle = extras_str.split(" - ")[0][1:].strip()
        except (KeyError, IndexError, AttributeError) as e:
            logger.warning(f"Could not extract gridname/muscle from EXTRAS: {e}. Using defaults.")
            gridname = "GR1"
            muscle = "Unknown"

        dict_for_muedit["signal"]["gridname"] = np.array([[gridname]], dtype=object)
        dict_for_muedit["signal"]["muscle"] = np.array([[muscle]], dtype=object)

        # Build Pulsetrain (1 x ngrid cell array)
        pulsetrain_cell = np.empty((1, ngrid), dtype=object)
        ipts = json_from_openhdemg["IPTS"].to_numpy(dtype=np.float64, copy=True).T
        pulsetrain_cell[0, 0] = ipts / ipts.max()  # Normalize for MUEdit
        dict_for_muedit["signal"]["Pulsetrain"] = pulsetrain_cell

        # Build Dischargetimes (ngrid x nMU MATLAB cell)
        discharges_cell = np.empty((ngrid, nMU), dtype=object)
        for mu in range(nMU):
            seq = json_from_openhdemg["MUPULSES"][mu] + 1  # +1 for 1-indexed MATLAB
            arr = np.asarray(seq, dtype=np.float64).reshape(1, -1)
            discharges_cell[0, mu] = arr
        dict_for_muedit["signal"]["Dischargetimes"] = discharges_cell

        # Set additional signal parameters
        dict_for_muedit['signal']['IED'] = json_from_openhdemg["IED"]
        dict_for_muedit['signal']['target'] = np.transpose(json_from_openhdemg["REF_SIGNAL"])
        dict_for_muedit['signal']['path'] = np.transpose(json_from_openhdemg["REF_SIGNAL"])
        dict_for_muedit['signal']['emgtype'] = np.ones((1, ngrid))

        # Build EMGmask (1 x ngrid MATLAB cell)
        # TODO: Extract bad channels from EXTRAS if available
        bad_channel_bool = np.empty((1, ngrid), dtype=object)
        bad_channel_bool[0, 0] = np.asarray(np.zeros((nCH, 1)))
        dict_for_muedit['signal']['EMGmask'] = bad_channel_bool

        # Set parameters
        dict_for_muedit['parameters']['pathname'] = str(json_path.parent)
        dict_for_muedit['parameters']['filename'] = str(json_path.name)

        # Save to MAT file
        sio.savemat(mat_save_filepath, dict_for_muedit, do_compression=True, long_field_names=True)
        logger.info(f"Successfully saved MUEdit file: {mat_save_filepath}")

        return mat_save_filepath

    except Exception as e:
        logger.error(f"Failed to export {json_path.name} to MUEdit format: {str(e)}")
        raise ValueError(f"Export failed: {str(e)}") from e


def is_muedit_file_exists(json_filepath):
    """
    Check if a MUEdit MAT file already exists for a given JSON file.

    Args:
        json_filepath (str or Path): Path to the JSON file.

    Returns:
        bool: True if the corresponding MUEdit file exists, False otherwise.
    """
    json_path = Path(json_filepath)
    muedit_path = json_path.parent / json_path.name.replace(".json", "_muedit.mat")
    return muedit_path.exists()


def get_muedit_filepath(json_filepath):
    """
    Get the expected MUEdit MAT filepath for a given JSON file.

    Args:
        json_filepath (str or Path): Path to the JSON file.

    Returns:
        str: Expected path to the MUEdit MAT file.
    """
    return str(json_filepath).replace(".json", "_muedit.mat")
