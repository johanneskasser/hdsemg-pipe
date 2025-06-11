# Crop to Region of Interest (ROI)

The Crop to ROI step allows you to select a specific time segment of your recordings for further analysis. This is particularly useful when you want to focus on specific events or movements within your recording.

![Define ROI Dialog](../img/define_roi.png)

## Overview

In this step, you can:
1. Visualize reference and force channels from your recordings
2. Select a specific time range using interactive sliders
3. Save the cropped data for all selected files

## Interface Components

### Signal Selection Panel

For each loaded grid, the dialog shows a group box containing:
- Reference signal checkboxes
- Force channel checkboxes (if available)
- EMG channel checkbox (if no reference signals are available)

Signal types are automatically detected and pre-selected based on the following rules:
- If force channels are detected (containing "requested path" or "performed path"), they are pre-selected
- If no force channels exist, the first reference channel is pre-selected
- If no reference channels exist, the first EMG channel is pre-selected

### Plot View

The main plot area shows:
- Selected signals from all grids
- Vertical threshold lines (red for start, green for end)
- Legend identifying each plotted signal

### Range Slider

Located at the bottom of the plot, allows you to:
- Set the start and end points of your ROI
- Interactively adjust the selection
- See immediate visual feedback through the threshold lines

## Controls

- **Checkboxes**: Toggle visibility of individual signals
- **Range Slider**: Define the ROI boundaries
- **OK Button**: Confirm selection and save cropped data
- **Cancel Button**: Close dialog without saving

## Data Processing

### Signal Detection

The system automatically processes the input files to identify:
1. Reference signals
2. Force channels
3. EMG channels

### Cropping Process

When you confirm your selection:
1. The selected time range is extracted from all channels
2. Data is resampled based on the original sampling frequency
3. Time vectors are adjusted to maintain temporal alignment
4. All metadata is preserved in the output files

## File Handling

### Input Files
- Original .mat files containing the full recording
- All selected files must have compatible sampling rates
- Files can contain multiple types of signals (EMG, force, reference)

### Output Files
- Cropped data is saved in .mat format
- Original file names are preserved
- Files are saved in the designated ROI output folder
- Original files remain unchanged

## Skip Option

If you don't need to crop your data, you can:
1. Click the "Skip" button
2. Files will be copied to the destination folder without modification
3. The step will be marked as complete

## Best Practices

1. **Signal Selection**
   - Select reference signals that clearly show your events of interest
   - Use force channels when available for better event identification
   - Verify signal alignment across all files

2. **ROI Selection**
   - Include a small buffer before and after your events of interest
   - Ensure all relevant activity is within the selected range
   - Check that the selection is appropriate for all loaded files

3. **Data Verification**
   - Verify that all signals are properly aligned
   - Check that the cropped data includes all necessary information
   - Confirm that the output files are saved in the correct location

## Troubleshooting

### Common Issues

1. **Missing Signals**
   - Verify file format and content
   - Check if reference channels are properly labeled
   - Ensure files are correctly loaded

2. **Visualization Problems**
   - Try selecting different reference channels
   - Verify signal scaling and normalization
   - Check for data corruption or missing values

3. **Saving Errors**
   - Verify write permissions in the destination folder
   - Ensure sufficient disk space
   - Check file naming conflicts

### Error Messages

Common error messages and their solutions:

- "No files selected for ROI definition"
  - Select input files before starting the ROI definition
  - Check if files were properly loaded in the previous step

- "Workfolder Basepath is not set"
  - Configure the workspace settings before proceeding
  - Set the workfolder path in the application settings
