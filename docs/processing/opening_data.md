# Opening Data

The first step in the HD-sEMG signal processing pipeline is opening and importing your data files.

## Supported File Formats

The application currently supports the following file formats for HD-sEMG data:

- OTB (.otb) files - Output files from OT Bioelettronica devices
- JSON files - Previously processed and saved data from this application

## Using the File Open Dialog

1. Click on the "Open File" button in the first step of the pipeline
2. Navigate to your data file location
3. Select the file you want to process
4. Click "Open" to import the data

![Folder View](../img/folder_view.png)

## File Browser Features

The file browser provides several useful features:

- File type filtering to show only supported formats
- Preview of basic file information

## Data Import Process

When you open a file, the following operations are performed:

1. File format validation
2. Header information extraction
3. Raw data loading
4. Initial signal validation
5. Data structure preparation for processing
6. Mean value correction of the EMG signals (offset correction) 

### Mean Value Correction

The application automatically performs a mean value correction on the EMG signals. This step removes the DC offset from the signals, ensuring that they oscillate around zero. This is crucial for accurate signal analysis and visualization.
- The corrected signals are saved in the `original_files/` folder for further processing.
- The EMG signals are adjusted by substracting the mean value of the signal. 
- The reference signals are also adjusted by substracting the min value of the signal to ensure that they oscillate around zero.
- The meta information of each channel is then saved in a seperate JSON file, which includes the value bevor and after, and specifiying the type of correction applied ("mean" or "min"). This JSON file is saved in the `original_files/` folder as well under the same name as the original file, but with a `.json` extension.

## File Structure Requirements

### OTB Files
OTB files should contain:
- Proper header information
- Channel configuration data
- Raw EMG signals
- Sampling rate information

### JSON Files
JSON files should include:
- Complete signal data
- Processing history
- Channel configuration
- Grid association information (if previously defined)

## Error Handling

Common issues that might occur during file opening:

- **Invalid File Format**: Ensure your file is in a supported format
- **Corrupted Data**: The file might be damaged or incomplete
- **Missing Information**: Required metadata is not present in the file
- **Size Limitations**: Very large files might require additional processing time

## Data Preview

After successfully opening a file, you will see:

- Basic file information
- Number of available channels
- Recording duration
- Sampling rate
- Preview of signal quality

## Next Steps

Once your data is successfully loaded, you can proceed to:

1. [Associate electrode grids](grid_association.md)
2. [Define the Region of Interest](crop_to_roi.md)
3. [Select specific channels](channel_selection.md)
4. [Decompose the signals](decomposition_results.md)

## Troubleshooting

If you encounter issues while opening files:

1. Verify file format compatibility
2. Check file permissions
3. Ensure sufficient disk space
4. Look for error messages in the application log and change the log level to "Debug" (see [Settings](../general/application_settings.md) to change the log level)
5. Open a [GitHub issue](https://github.com/johanneskasser/hdsemg-pipe/issues)
