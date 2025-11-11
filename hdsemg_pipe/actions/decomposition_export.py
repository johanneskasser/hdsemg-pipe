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


def _is_valid_ref(ref):
    """
    Check if an HDF5 reference is valid (non-null).

    Args:
        ref: HDF5 reference object

    Returns:
        bool: True if reference is valid, False otherwise
    """
    import h5py as _h5py
    return isinstance(ref, _h5py.Reference) and bool(ref)


def _cell_row_read(f, ds):
    """
    Read a MATLAB 1xN (or Nx1) cell array dataset into a Python list of arrays.
    Assumes v7.3 (HDF5). Elements are object references.

    Args:
        f: Open h5py.File object
        ds: HDF5 dataset containing cell array

    Returns:
        list: List of numpy arrays or None for empty cells
    """
    obj = ds[()]
    if obj.ndim != 2:
        raise ValueError(f"Expected 2-D cell array, got {obj.ndim}D.")

    # Normalize to a row
    if obj.shape[0] == 1:
        refs = [obj[0, j] for j in range(obj.shape[1])]
    elif obj.shape[1] == 1:
        refs = [obj[i, 0] for i in range(obj.shape[0])]
    else:
        # Still handle as row-major
        refs = [obj[0, j] for j in range(obj.shape[1])]

    out = []
    for r in refs:
        if _is_valid_ref(r):
            arr = np.array(f[r])
            out.append(arr)
        else:
            out.append(None)
    return out


def apply_muedit_edits_to_json(json_in_path, mat_edited_path, json_out_path):
    """
    Update an OpenHD-EMG JSON with MU edits made in a MUEdit-exported MAT file (v7.3/HDF5).

    This function reads the edited motor unit data from a MUEdit MAT file and updates
    the original OpenHD-EMG JSON with the cleaned results.

    Fields updated in the output JSON:
      - 'IPTS': Pulse trains from signal.Pulsetrain (saved as DataFrame, shape time x nMU)
      - 'MUPULSES': Discharge times from signal.Dischargetimes (converted 1-based -> 0-based)
      - 'BINARY_MUS_FIRING': Binary firing matrix derived from MUPULSES
      - 'ACCURACY': SIL values from edition.silval
      - 'NUMBER_OF_MUS': Number of motor units
      - 'FILENAME': Path to the edited MAT file

    Args:
        json_in_path (str or Path): Path to the original OpenHD-EMG JSON file
        mat_edited_path (str or Path): Path to the edited MUEdit MAT file (v7.3 format)
        json_out_path (str or Path): Path where the updated JSON should be saved

    Raises:
        ImportError: If openhdemg or h5py libraries are not available
        KeyError: If required fields are not found in the MAT file
        ValueError: If data structure validation fails

    Example:
        >>> apply_muedit_edits_to_json(
        ...     'original.json',
        ...     'edited_muedit.mat',
        ...     'cleaned_result.json'
        ... )
        Updated JSON written to: cleaned_result.json
    """
    if not OPENHDEMG_AVAILABLE:
        raise ImportError("openhdemg library is required for this function")

    try:
        import h5py
    except ImportError:
        raise ImportError("h5py library is required for reading MATLAB v7.3 files (pip install h5py)")

    json_in_path = Path(json_in_path)
    mat_edited_path = Path(mat_edited_path)
    json_out_path = Path(json_out_path)

    logger.info(f"Converting edited MUEdit file to OpenHD-EMG format...")
    logger.debug(f"Input JSON: {json_in_path.name}")
    logger.debug(f"Edited MAT: {mat_edited_path.name}")
    logger.debug(f"Output JSON: {json_out_path.name}")

    # Load original OpenHD-EMG JSON
    json_dict = emg.emg_from_json(str(json_in_path))

    # Read edited MUEdit MAT (v7.3) using h5py
    with h5py.File(str(mat_edited_path), 'r') as f:
        if 'edition' not in f:
            raise KeyError(f"'edition' group not found in {mat_edited_path.name}. "
                          "The MAT file may not be a valid MUEdit edited file.")
        edit = f['edition']

        # SIL: 1 x ngrid cell, each double
        if 'silval' not in edit:
            raise KeyError("edition.silval not found in edited MAT.")
        silval = _cell_row_read(f, edit['silval'])

        # Pulsetrain: 1 x ngrid cell; each cell: (nMU_g x n_samples)
        if 'Pulsetrainclean' not in edit:
            raise KeyError("edition.Pulsetrainclean not found in edited MAT.")
        pulsetrain_cells = _cell_row_read(f, edit['Pulsetrainclean'])

        # Dischargetimes: ngrid x maxMU cell; each cell: (1 x nDischarges) or (nDischarges,)
        top = edit['Distimeclean'][()]           # object array, shape (1,1)
        inner_ref = top.flat[0]                  # the only reference
        inner_cell_ds = f[inner_ref]             # dataset: the 1×nMU cell

        # Now read that inner row cell into a Python list of arrays (length = nMU)
        disc_nested = _cell_row_read(f, inner_cell_ds)

    # JSON expects IPTS as DataFrame (time x nMU)
    IPTS_df = pd.DataFrame(pulsetrain_cells[0])

    # Build MUPULSES (0-based) from Dischargetimes
    MUPULSES_list = []
    for mu_timing in disc_nested:
        MUPULSES_list.append(np.squeeze(np.asarray(mu_timing, dtype='int32')) - 1)

    # Update the edited fields in the new JSON
    json_dict['IPTS'] = IPTS_df
    json_dict['MUPULSES'] = MUPULSES_list

    # Create binary firing matrix
    nMU = min(IPTS_df.shape)
    spikeMat = np.zeros((nMU, max(IPTS_df.shape)))
    for i in range(nMU):
        spikeMat[i, MUPULSES_list[i]] = 1
    json_dict['BINARY_MUS_FIRING'] = pd.DataFrame(spikeMat.T)
    json_dict['FILENAME'] = str(mat_edited_path)
    json_dict['ACCURACY'] = pd.DataFrame(np.squeeze(np.array(silval)))
    json_dict['NUMBER_OF_MUS'] = nMU

    # Save updated JSON in OpenHD-EMG format
    emg.save_json_emgfile(json_dict, str(json_out_path), compresslevel=4)
    logger.info(f"Successfully converted to OpenHD-EMG format: {json_out_path.name}")

    return str(json_out_path)
