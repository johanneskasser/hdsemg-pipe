"""Functions for exporting decomposition outputs between different formats."""

import json
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


def extract_grid_metadata_from_extras(extras_field):
    """
    Extract grid metadata from the EXTRAS field of an OpenHD-EMG JSON file.

    The EXTRAS field can contain structured grid information from the grid association
    and channel selection steps. This function parses that information to extract
    grid count and per-grid metadata.

    Args:
        extras_field: The EXTRAS field from OpenHD-EMG (pandas Series or DataFrame)

    Returns:
        dict: Dictionary containing:
            - 'ngrid': Number of grids (int)
            - 'grids': List of grid dictionaries, each containing:
                - 'gridname': Grid identifier (str)
                - 'muscle': Muscle name (str)
                - 'rows': Number of rows (int)
                - 'cols': Number of columns (int)
                - 'ied_mm': Inter-electrode distance in mm (float)
                - 'emg_count': Number of EMG channels (int)
                - 'file_name': Original file name (str)

    Example:
        >>> extras = pd.Series(['{"grids": [{"file_name": "grid1.mat", ...}]}'])
        >>> metadata = extract_grid_metadata_from_extras(extras)
        >>> metadata['ngrid']
        1
    """
    grid_metadata = {
        'ngrid': 1,
        'grids': [{
            'gridname': 'GR1',
            'muscle': 'Unknown',
            'rows': 8,
            'cols': 8,
            'ied_mm': 8.0,
            'emg_count': 64,
            'file_name': 'unknown'
        }]
    }

    try:
        # Try to get the first entry from EXTRAS
        if isinstance(extras_field, pd.Series):
            extras_str = str(extras_field.iloc[0])
        elif isinstance(extras_field, pd.DataFrame):
            extras_str = str(extras_field.loc[0.0])
        else:
            extras_str = str(extras_field)

        # Try to parse as JSON
        try:
            extras_dict = json.loads(extras_str)
        except json.JSONDecodeError:
            # Fallback: try old string parsing method for backward compatibility
            logger.warning("EXTRAS field is not valid JSON, using fallback string parsing")
            gridname = extras_str.split(" - ")[-1].split(' ')[0].replace('HD', 'GR')
            muscle = extras_str.split(" - ")[0][1:].strip() if extras_str.startswith('[') else extras_str.split(" - ")[0].strip()
            grid_metadata['grids'][0]['gridname'] = gridname
            grid_metadata['grids'][0]['muscle'] = muscle
            return grid_metadata

        # Extract grids list from the parsed JSON
        if 'grids' in extras_dict and len(extras_dict['grids']) > 0:
            grids_list = []
            for idx, grid in enumerate(extras_dict['grids']):
                # Extract grid name from file_name (e.g., "GR08MM0808.mat" -> "GR08MM0808")
                file_name = grid.get('file_name', f'grid{idx+1}')
                gridname = file_name.replace('.mat', '').replace('HD', 'GR')

                # Try to get muscle name from combined_info or use default
                combined_info = grid.get('combined_info', {})
                muscle = combined_info.get('muscle', grid.get('muscle', f'Muscle{idx+1}'))

                grid_info = {
                    'gridname': gridname,
                    'muscle': muscle,
                    'rows': grid.get('rows', 8),
                    'cols': grid.get('cols', 8),
                    'ied_mm': float(grid.get('ied_mm', 8.0)),
                    'emg_count': grid.get('emg_count', 64),
                    'file_name': file_name
                }
                grids_list.append(grid_info)

            grid_metadata['ngrid'] = len(grids_list)
            grid_metadata['grids'] = grids_list
            logger.info(f"Detected {len(grids_list)} grid(s) from EXTRAS field")
        else:
            logger.warning("No 'grids' list found in EXTRAS, using single grid default")

    except Exception as e:
        logger.warning(f"Could not fully parse EXTRAS field: {e}. Using defaults.")

    return grid_metadata


def export_to_muedit_mat(json_load_filepath, ngrid=None):
    """
    Export OpenHD-EMG JSON decomposition results to MUEdit MAT format.

    This function converts decomposition results from OpenHD-EMG JSON format into
    a MATLAB .mat file that can be opened in MUEdit for manual cleaning of motor units.
    Supports both single-grid and multi-grid recordings. For multi-grid data, all grids
    are exported in a single MAT file to enable MUEdit's cross-grid duplicate detection.

    Args:
        json_load_filepath (str or Path): Path to the OpenHD-EMG JSON file.
        ngrid (int, optional): Number of electrode grids. If None (default), the number
            of grids is auto-detected from the EXTRAS field. Explicit values override
            auto-detection.

    Returns:
        str: Path to the created MUEdit MAT file, or None if export failed.

    Raises:
        ImportError: If openhdemg library is not available.
        FileNotFoundError: If the JSON file doesn't exist.
        ValueError: If the JSON file has invalid structure.

    Example:
        >>> # Single-grid export (auto-detected)
        >>> export_to_muedit_mat('decomposition_result.json')
        'decomposition_result_muedit.mat'

        >>> # Multi-grid export (auto-detected from EXTRAS field)
        >>> export_to_muedit_mat('multi_grid_result.json')
        'multi_grid_result_multigrid_muedit.mat'
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

        # Extract grid metadata from EXTRAS field
        grid_metadata = extract_grid_metadata_from_extras(json_from_openhdemg["EXTRAS"])

        # Override with explicit ngrid if provided, otherwise use detected value
        if ngrid is not None:
            grid_metadata['ngrid'] = ngrid
            logger.info(f"Using explicitly provided ngrid={ngrid}")
        else:
            ngrid = grid_metadata['ngrid']

        # Determine output path based on grid count
        if ngrid > 1:
            mat_save_filepath = str(json_path).replace(".json", "_multigrid_muedit.mat")
            logger.info(f"Multi-grid export: {ngrid} grids detected")
        else:
            mat_save_filepath = str(json_path).replace(".json", "_muedit.mat")
            logger.info("Single-grid export")

        # Extract dimensions
        nMU = json_from_openhdemg["IPTS"].shape[1]
        nCH = json_from_openhdemg["RAW_SIGNAL"].shape[1]

        logger.debug(f"Converting file with {nMU} motor units and {nCH} channels across {ngrid} grid(s)")

        # Allocate MUEdit structure
        dict_for_muedit = allocate_muedit_file_structure()

        # Populate signal data
        dict_for_muedit["signal"]["data"] = np.transpose(json_from_openhdemg["RAW_SIGNAL"].to_numpy())
        dict_for_muedit["signal"]["fsamp"] = json_from_openhdemg["FSAMP"]
        dict_for_muedit["signal"]["nChan"] = nCH
        dict_for_muedit["signal"]["ngrid"] = ngrid

        # Build grid name and muscle arrays
        gridnames = [grid['gridname'] for grid in grid_metadata['grids'][:ngrid]]
        muscles = [grid['muscle'] for grid in grid_metadata['grids'][:ngrid]]

        dict_for_muedit["signal"]["gridname"] = np.array([gridnames], dtype=object)
        dict_for_muedit["signal"]["muscle"] = np.array([muscles], dtype=object)

        # Build Pulsetrain (1 x ngrid cell array)
        # NOTE: Current implementation assigns all MUs to the first grid
        # For true multi-grid support, decomposition would need to track which MUs belong to which grid
        pulsetrain_cell = np.empty((1, ngrid), dtype=object)
        ipts = json_from_openhdemg["IPTS"].to_numpy(dtype=np.float64, copy=True).T
        pulsetrain_cell[0, 0] = ipts / ipts.max()  # Normalize for MUEdit

        # Fill remaining grids with empty arrays
        for grid_idx in range(1, ngrid):
            pulsetrain_cell[0, grid_idx] = np.empty((0, ipts.shape[1]), dtype=np.float64)

        dict_for_muedit["signal"]["Pulsetrain"] = pulsetrain_cell

        # Build Dischargetimes (ngrid x nMU MATLAB cell)
        # NOTE: All MUs assigned to first grid, other grids have no MUs
        discharges_cell = np.empty((ngrid, nMU), dtype=object)
        for mu in range(nMU):
            seq = json_from_openhdemg["MUPULSES"][mu] + 1  # +1 for 1-indexed MATLAB
            arr = np.asarray(seq, dtype=np.float64).reshape(1, -1)
            discharges_cell[0, mu] = arr

        # Fill other grids with empty arrays
        for grid_idx in range(1, ngrid):
            for mu in range(nMU):
                discharges_cell[grid_idx, mu] = np.empty((1, 0), dtype=np.float64)

        dict_for_muedit["signal"]["Dischargetimes"] = discharges_cell

        # Build IED array (1 x ngrid)
        ied_array = np.array([grid['ied_mm'] for grid in grid_metadata['grids'][:ngrid]])
        dict_for_muedit['signal']['IED'] = ied_array

        # Set reference signals (global, not per-grid)
        dict_for_muedit['signal']['target'] = np.transpose(json_from_openhdemg["REF_SIGNAL"])
        dict_for_muedit['signal']['path'] = np.transpose(json_from_openhdemg["REF_SIGNAL"])

        # Set emgtype (1 x ngrid, all surface EMG = 1)
        dict_for_muedit['signal']['emgtype'] = np.ones((1, ngrid))

        # Build EMGmask (1 x ngrid MATLAB cell)
        # For multi-grid, calculate channels per grid
        bad_channel_bool = np.empty((1, ngrid), dtype=object)

        if ngrid == 1:
            # Single grid: use all channels
            bad_channel_bool[0, 0] = np.asarray(np.zeros((nCH, 1)))
        else:
            # Multi-grid: distribute channels based on grid metadata
            channel_offset = 0
            for grid_idx in range(ngrid):
                grid_ch_count = grid_metadata['grids'][grid_idx]['emg_count']
                # Ensure we don't exceed total channel count
                if channel_offset + grid_ch_count <= nCH:
                    bad_channel_bool[0, grid_idx] = np.asarray(np.zeros((grid_ch_count, 1)))
                    channel_offset += grid_ch_count
                else:
                    # Fallback: use remaining channels
                    remaining = nCH - channel_offset
                    bad_channel_bool[0, grid_idx] = np.asarray(np.zeros((remaining, 1)))
                    logger.warning(f"Grid {grid_idx}: Expected {grid_ch_count} channels but only {remaining} remaining")
                    break

        dict_for_muedit['signal']['EMGmask'] = bad_channel_bool

        # Build coordinates (1 x ngrid cell array)
        # Each cell contains [nChannels x 2] array of (row, col) 1-based indices
        coordinates_cell = np.empty((1, ngrid), dtype=object)

        if ngrid == 1:
            # Single grid: create coordinate matrix
            rows = grid_metadata['grids'][0]['rows']
            cols = grid_metadata['grids'][0]['cols']
            coords = np.zeros((rows * cols, 2))
            idx = 0
            for r in range(1, rows + 1):  # 1-based indexing for MATLAB
                for c in range(1, cols + 1):
                    if idx < nCH:
                        coords[idx] = [r, c]
                        idx += 1
            coordinates_cell[0, 0] = coords[:nCH]  # Truncate to actual channel count
        else:
            # Multi-grid: create coordinate matrix for each grid
            channel_offset = 0
            for grid_idx in range(ngrid):
                rows = grid_metadata['grids'][grid_idx]['rows']
                cols = grid_metadata['grids'][grid_idx]['cols']
                grid_ch_count = grid_metadata['grids'][grid_idx]['emg_count']

                coords = np.zeros((grid_ch_count, 2))
                idx = 0
                for r in range(1, rows + 1):  # 1-based indexing for MATLAB
                    for c in range(1, cols + 1):
                        if idx < grid_ch_count:
                            coords[idx] = [r, c]
                            idx += 1
                coordinates_cell[0, grid_idx] = coords
                channel_offset += grid_ch_count

        dict_for_muedit['signal']['coordinates'] = coordinates_cell

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

    Checks for both single-grid (_muedit.mat) and multi-grid (_multigrid_muedit.mat)
    file variants.

    Args:
        json_filepath (str or Path): Path to the JSON file.

    Returns:
        bool: True if any corresponding MUEdit file exists, False otherwise.
    """
    json_path = Path(json_filepath)
    muedit_path_single = json_path.parent / json_path.name.replace(".json", "_muedit.mat")
    muedit_path_multi = json_path.parent / json_path.name.replace(".json", "_multigrid_muedit.mat")
    return muedit_path_single.exists() or muedit_path_multi.exists()


def get_muedit_filepath(json_filepath, multi_grid=False):
    """
    Get the expected MUEdit MAT filepath for a given JSON file.

    Args:
        json_filepath (str or Path): Path to the JSON file.
        multi_grid (bool, optional): If True, returns the multi-grid filename variant.
            Defaults to False.

    Returns:
        str: Expected path to the MUEdit MAT file.

    Example:
        >>> get_muedit_filepath('result.json', multi_grid=False)
        'result_muedit.mat'
        >>> get_muedit_filepath('result.json', multi_grid=True)
        'result_multigrid_muedit.mat'
    """
    if multi_grid:
        return str(json_filepath).replace(".json", "_multigrid_muedit.mat")
    else:
        return str(json_filepath).replace(".json", "_muedit.mat")


def export_multi_grid_to_muedit(json_filepaths, group_name, output_dir=None):
    """
    Export multiple OpenHD-EMG JSON files as a single multi-grid MUEdit MAT file.

    This function combines decomposition results from multiple grids (recorded from
    the same muscle with common motor units) into a single MUEdit MAT file. This
    enables MUEdit's cross-grid duplicate detection and common input analysis.

    Args:
        json_filepaths (list): List of paths to OpenHD-EMG JSON files (one per grid)
        group_name (str): Name for this multi-grid group (used in output filename)
        output_dir (str or Path, optional): Output directory. If None, uses the
            directory of the first JSON file.

    Returns:
        str: Path to the created multi-grid MUEdit MAT file, or None if export failed.

    Raises:
        ImportError: If openhdemg library is not available.
        FileNotFoundError: If any JSON file doesn't exist.
        ValueError: If JSON files have incompatible structure (different sampling rates, etc.)

    Example:
        >>> export_multi_grid_to_muedit(
        ...     ['biceps_grid1.json', 'biceps_grid2.json'],
        ...     'Biceps'
        ... )
        'Biceps_multigrid_muedit.mat'
    """
    if not OPENHDEMG_AVAILABLE:
        raise ImportError("openhdemg library is required for this function")

    if not json_filepaths:
        raise ValueError("No JSON files provided")

    json_paths = [Path(f) for f in json_filepaths]
    ngrid = len(json_paths)

    logger.info(f"Combining {ngrid} JSON files into multi-grid MUEdit format for group '{group_name}'...")

    # Verify all files exist
    for json_path in json_paths:
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")

    try:
        # Load all JSON files
        json_data_list = []
        grid_metadata_list = []

        for json_path in json_paths:
            logger.debug(f"Loading {json_path.name}...")
            json_data = emg.emg_from_json(str(json_path))
            json_data_list.append(json_data)

            # Extract grid metadata
            grid_meta = extract_grid_metadata_from_extras(json_data["EXTRAS"])
            grid_metadata_list.append(grid_meta['grids'][0])  # Each file has one grid

        # Validate compatibility
        fsamp_ref = json_data_list[0]["FSAMP"]
        n_samples_ref = json_data_list[0]["RAW_SIGNAL"].shape[0]

        for idx, json_data in enumerate(json_data_list[1:], start=1):
            if json_data["FSAMP"] != fsamp_ref:
                raise ValueError(f"Incompatible sampling rates: Grid 0 has {fsamp_ref} Hz, "
                               f"Grid {idx} has {json_data['FSAMP']} Hz")

            if json_data["RAW_SIGNAL"].shape[0] != n_samples_ref:
                raise ValueError(f"Incompatible signal lengths: Grid 0 has {n_samples_ref} samples, "
                               f"Grid {idx} has {json_data['RAW_SIGNAL'].shape[0]} samples")

        logger.info(f"All grids compatible: {fsamp_ref} Hz, {n_samples_ref} samples")

        # Determine output path
        if output_dir is None:
            output_dir = json_paths[0].parent
        else:
            output_dir = Path(output_dir)

        # Create sanitized filename from group name
        safe_group_name = "".join(c for c in group_name if c.isalnum() or c in (' ', '_', '-')).strip()
        safe_group_name = safe_group_name.replace(' ', '_')
        mat_save_filepath = output_dir / f"{safe_group_name}_multigrid_muedit.mat"

        # Allocate MUEdit structure
        dict_for_muedit = allocate_muedit_file_structure()

        # Concatenate signal data from all grids
        all_signals = []
        total_channels = 0

        for idx, json_data in enumerate(json_data_list):
            signal = json_data["RAW_SIGNAL"].to_numpy()
            all_signals.append(signal.T)  # Transpose to (channels x samples)
            total_channels += signal.shape[1]
            logger.debug(f"Grid {idx}: {signal.shape[1]} channels")

        concatenated_signal = np.vstack(all_signals)  # Stack vertically: (total_channels x samples)

        # Populate basic signal data
        dict_for_muedit["signal"]["data"] = concatenated_signal
        dict_for_muedit["signal"]["fsamp"] = fsamp_ref
        dict_for_muedit["signal"]["nChan"] = total_channels
        dict_for_muedit["signal"]["ngrid"] = ngrid

        # Build grid names and muscle arrays
        gridnames = [grid['gridname'] for grid in grid_metadata_list]
        muscles = [grid['muscle'] for grid in grid_metadata_list]

        dict_for_muedit["signal"]["gridname"] = np.array([gridnames], dtype=object)
        dict_for_muedit["signal"]["muscle"] = np.array([muscles], dtype=object)

        # Build Pulsetrain (1 x ngrid cell array)
        # Each cell contains the pulse trains for MUs in that grid
        pulsetrain_cell = np.empty((1, ngrid), dtype=object)

        max_mu_count = 0  # Track maximum MU count across all grids for Dischargetimes

        for grid_idx, json_data in enumerate(json_data_list):
            ipts = json_data["IPTS"].to_numpy(dtype=np.float64, copy=True).T  # (nMU x time)
            if ipts.size > 0:
                pulsetrain_cell[0, grid_idx] = ipts / ipts.max()  # Normalize
            else:
                pulsetrain_cell[0, grid_idx] = np.empty((0, n_samples_ref), dtype=np.float64)

            mu_count = json_data["IPTS"].shape[1]
            max_mu_count = max(max_mu_count, mu_count)
            logger.debug(f"Grid {grid_idx}: {mu_count} motor units")

        dict_for_muedit["signal"]["Pulsetrain"] = pulsetrain_cell

        # Build Dischargetimes (ngrid x maxMU cell array)
        # Each grid gets a row, each MU gets a column
        discharges_cell = np.empty((ngrid, max_mu_count), dtype=object)

        for grid_idx, json_data in enumerate(json_data_list):
            n_mu_in_grid = json_data["IPTS"].shape[1]

            for mu_idx in range(max_mu_count):
                if mu_idx < n_mu_in_grid:
                    # This MU exists in this grid
                    seq = json_data["MUPULSES"][mu_idx] + 1  # +1 for 1-indexed MATLAB
                    arr = np.asarray(seq, dtype=np.float64).reshape(1, -1)
                    discharges_cell[grid_idx, mu_idx] = arr
                else:
                    # This MU doesn't exist in this grid (padding)
                    discharges_cell[grid_idx, mu_idx] = np.empty((1, 0), dtype=np.float64)

        dict_for_muedit["signal"]["Dischargetimes"] = discharges_cell

        # Build IED array (1 x ngrid)
        ied_array = np.array([grid['ied_mm'] for grid in grid_metadata_list])
        dict_for_muedit['signal']['IED'] = ied_array

        # Set reference signals
        # Use first grid's reference signal (assuming all grids recorded same task)
        dict_for_muedit['signal']['target'] = np.transpose(json_data_list[0]["REF_SIGNAL"])
        dict_for_muedit['signal']['path'] = np.transpose(json_data_list[0]["REF_SIGNAL"])

        # Set emgtype (1 x ngrid, all surface EMG = 1)
        dict_for_muedit['signal']['emgtype'] = np.ones((1, ngrid))

        # Build EMGmask (1 x ngrid cell array)
        bad_channel_bool = np.empty((1, ngrid), dtype=object)

        for grid_idx, grid_meta in enumerate(grid_metadata_list):
            grid_ch_count = grid_meta['emg_count']
            bad_channel_bool[0, grid_idx] = np.asarray(np.zeros((grid_ch_count, 1)))

        dict_for_muedit['signal']['EMGmask'] = bad_channel_bool

        # Build coordinates (1 x ngrid cell array)
        coordinates_cell = np.empty((1, ngrid), dtype=object)

        for grid_idx, grid_meta in enumerate(grid_metadata_list):
            rows = grid_meta['rows']
            cols = grid_meta['cols']
            grid_ch_count = grid_meta['emg_count']

            coords = np.zeros((grid_ch_count, 2))
            idx = 0
            for r in range(1, rows + 1):  # 1-based indexing for MATLAB
                for c in range(1, cols + 1):
                    if idx < grid_ch_count:
                        coords[idx] = [r, c]
                        idx += 1

            coordinates_cell[0, grid_idx] = coords

        dict_for_muedit['signal']['coordinates'] = coordinates_cell

        # Set parameters
        dict_for_muedit['parameters']['pathname'] = str(output_dir)
        dict_for_muedit['parameters']['filename'] = f"{group_name} (multi-grid, {ngrid} grids)"

        # Save to MAT file
        sio.savemat(str(mat_save_filepath), dict_for_muedit, do_compression=True, long_field_names=True)

        logger.info(f"Successfully created multi-grid MUEdit file: {mat_save_filepath.name}")
        logger.info(f"  - {ngrid} grids combined")
        logger.info(f"  - {total_channels} total channels")
        logger.info(f"  - {max_mu_count} max motor units per grid")

        return str(mat_save_filepath)

    except Exception as e:
        logger.error(f"Failed to create multi-grid MUEdit file for group '{group_name}': {str(e)}")
        raise ValueError(f"Multi-grid export failed: {str(e)}") from e


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
