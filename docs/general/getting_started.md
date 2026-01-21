# Getting Started with hdsemg-pipe

This guide will help you get started with the hdsemg-pipe application and walk you through the basic workflow for processing HD-sEMG data.

## Installation

Before you begin, make sure you have installed hdsemg-pipe and its dependencies as described in the [Installation Guide](../installation.md).

## Initial Setup

1. Launch hdsemg-pipe
2. Configure the application settings (Settings -> Preferences):
   - Set the work folder path where your data will be processed
   - Configure the Channel Selection App path
   - Set the openhdemg virtual environment path
   
See [Application Settings](application_settings.md) for detailed configuration instructions.

## Basic Workflow

The hdsemg-pipe application guides you through twelve main steps to process your HD-sEMG data:

### 1. Open Files
- Click on the "Open File" button
- Select your `.otb`, `.otb+`, `.otb4`, or `.mat` file(s)
- The application will automatically create a workspace structure
- Files are automatically preprocessed (DC offset correction)

[Learn more about Opening Data](../processing/opening_data.md)

### 2. Grid Association
- Select grids from your loaded files
- Combine multiple grids if needed
- Name your grid associations
- Save the configuration

[Learn more about Grid Association](../processing/grid_association.md)

### 3. Line Noise Removal

- Remove powerline interference (50/60 Hz)
- Choose from multiple filtering methods
- Process all files with visual progress

[Learn more about Line Noise Removal](../processing/line_noise_removal.md)

### 4. RMS Quality Analysis

- Analyze baseline noise levels across recordings
- Select a quiet region for RMS calculation
- Review quality statistics and visualizations
- Identify recordings with poor signal quality

[Learn more about RMS Quality Analysis](../processing/rms_quality_analysis.md)

### 5. Define Region of Interest (ROI)
- Visualize your signals
- Select the time range of interest
- Apply the selection to all files
- Review the cropped data

[Learn more about ROI Definition](../processing/crop_to_roi.md)

### 6. Channel Selection
- Launch the external channel selection application
- Process each file to select valid channels
- Monitor the progress
- Verify the results

[Learn more about Channel Selection](../processing/channel_selection.md)

### 7. Decomposition Results
- Map decomposition results to channel selections
- Review the mappings

[Learn more about Decomposition Results](../processing/decomposition_results.md)

### 8. Multi-Grid Configuration

- Configure settings for multi-grid analysis
- Set up decomposition parameters

### 9. CoVISI Pre-Filtering

- Analyze motor unit quality using CoVISI (Coefficient of Variation of Interspike Interval)
- Optionally filter out non-physiological motor units (CoVISI > 30%)
- Review quality categories and export analysis to CSV

[Learn more about CoVISI Filtering](../processing/covisi_filtering.md)

### 10. MUEdit Cleaning

- Clean and refine motor unit decomposition results
- Export data for MUEdit processing

[Learn more about MUEdit Export](../processing/muedit_export_workflow.md)

### 11. CoVISI Post-Validation

- Validate motor unit quality after MUedit manual cleaning
- Compare pre/post cleaning CoVISI values
- Review improvement metrics and handle MUs still exceeding threshold

[Learn more about CoVISI Filtering](../processing/covisi_filtering.md)

### 12. Final Results

- Review all processed data
- Launch openhdemg to visualize results
- Export final analysis

## Workspace Structure

The application automatically creates and manages the following folder structure:

{! folder_structure.md !}

Each folder serves a specific purpose in the processing pipeline:

- `original_files/`: Contains your imported and preprocessed data
- `associated_grids/`: Stores grid association configurations
- `line_noise_cleaned/`: Contains signals after line noise removal
- `analysis/`: Stores RMS quality analysis reports and figures
- `cropped_signal/`: Contains the ROI-defined data segments
- `channelselection/`: Stores the results of channel selection
- `decomposition_auto/`: Contains automatic decomposition outputs
- `decomposition_results/`: Contains final decomposition results

## Progress Tracking

The [Dashboard](dashboard.md) provides visual feedback on your progress:
- Completed steps are marked with a check icon
- Current step is highlighted
- Upcoming steps are shown but may be disabled until prerequisites are met

## Resume where you left off
If you close the application or need to pause your work, since the application saves a file during each step, we have implemented a feature where you can
resume your work by reopening a hdsemg-pipe workfolder. The application automatically detects the last completed step and allows you to continue from there.
To do that, you have two options:
1. **Click on the **Folder Button** next to the Folder Stucture display, which will open a file explorer where you can select your old workfolder.
2. **Settings -> Open Existing Workfolder**: This will open a dialog where you can select your old workfolder.

Now the application will look for all expected folders in the selected path and reconstruct the folder state based on the files in the specific subfolders. 
This allows you to continue processing without losing any progress.


## Common Issues

1. **File Loading Problems**
   - Verify file format compatibility
   - Check file permissions
   - Ensure sufficient disk space

2. **External Application Errors**
   - Verify paths in settings
   - Check application compatibility
   - Review connection settings

3. **Processing Delays**
   - Large files may take longer to process
   - Multiple files increase processing time
   - Consider available system resources

## Getting Help

If you encounter issues:
1. Check the detailed documentation for each step
2. Set logging level to DEBUG in settings
3. Open an issue on [GitHub](https://github.com/johanneskasser/hdsemg-pipe/issues) with:
   - Detailed description of the problem
   - Steps to reproduce
   - Application logs
   - System information
