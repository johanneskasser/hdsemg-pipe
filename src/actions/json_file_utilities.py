import json

def concatenate_grid_and_channel_info(channel_selection_filepath, associated_grids_filepath):
    """
    Loads the channel selection and associated grids JSON files,
    and returns a dictionary that combines the two data sources.

    The returned dictionary contains:
      - association_name and timestamp from the associated grids file.
      - A list of grid entries with file name, file path, dimensions,
        and combined grid info (if available).
      - The reference signals and the combined EMG grid information.
      - Channel selection information (e.g., which channels are selected).

    :param channel_selection_filepath: Path to the channel selection JSON file.
    :param associated_grids_filepath: Path to the associated grids JSON file.
    :return: A dictionary with the concatenated information.
    """
    # Load the associated grids JSON file
    with open(associated_grids_filepath, 'r') as f:
        grids_data = json.load(f)

    # Load the channel selection JSON file
    with open(channel_selection_filepath, 'r') as f:
        channel_data = json.load(f)

    # Create a dictionary to hold the concatenated info.
    concatenated_info = {}

    # Basic info from associated grids file.
    concatenated_info["association_name"] = grids_data.get("association_name", "")
    concatenated_info["timestamp"] = grids_data.get("timestamp", "")

    # Process each grid from the "grids" list.
    grids_list = []
    for grid in grids_data.get("grids", []):
        grid_entry = {
            "file_name": grid.get("file_name", ""),
            "file_path": grid.get("file_path", ""),
            "rows": grid.get("rows"),
            "cols": grid.get("cols"),
            "emg_count": grid.get("emg_count"),
            "ref_count": grid.get("ref_count"),
            "ied_mm": grid.get("ied_mm"),
            "electrodes": grid.get("electrodes")
        }
        # Create a dimensions string to help with matching.
        dims = f"{grid.get('rows')}x{grid.get('cols')}"
        grid_entry["dimensions"] = dims

        # Look for matching combined grid info by dimensions.
        combined_info = grids_data.get("combined_grid_info", {})
        if dims in combined_info:
            grid_entry["combined_info"] = combined_info[dims]
        else:
            grid_entry["combined_info"] = {}

        grids_list.append(grid_entry)
    concatenated_info["grids"] = grids_list

    # Also includes additional combined grid info if available.
    combined_info = grids_data.get("combined_grid_info", {})
    concatenated_info["reference_signals"] = combined_info.get("reference_signals", [])
    concatenated_info["combined_emg_grid"] = combined_info.get("combined_emg_grid", {})

    # Process channel selection information.
    channel_selection = {
        "filename": channel_data.get("filename", "")
    }
    # Assuming the channel selection JSON holds its grid info in a "grids" list.
    if "grids" in channel_data and len(channel_data["grids"]) > 0:
        channel_selection["grid"] = channel_data["grids"][0]
    else:
        channel_selection["grid"] = {}

    concatenated_info["channel_selection"] = channel_selection

    return concatenated_info