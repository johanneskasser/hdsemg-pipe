# Decomposition Results

The Decomposition Results step allows you to map decomposition results to their corresponding channel selection files and visualize the results using the OpenHD-EMG application.

## Overview

This step provides two main functions:
1. Mapping decomposition results to channel selection files
2. Visualizing the results in OpenHD-EMG

## Interface Components

### Main Buttons

- **Apply Mapping**: Opens a dialog to create mappings between decomposition and channel selection files
- **Show Decomposition Results**: Launches OpenHD-EMG to visualize the processed results

### File Watcher

The system automatically monitors the decomposition folder for:
- `.json` files
- `.pkl` files

When new files are detected, the "Apply Mapping" button becomes enabled.

## Mapping Process

### Opening the Mapping Dialog

The mapping dialog provides a user-friendly interface to create 1:1 mappings between:
- Decomposition result files (`.json`, `.pkl`)
- Channel selection files (`.mat`)

![Mapping Dialog](../img/decomposition/mapping_dialog.png)

### Dialog Components

- **Left List**: Shows available decomposition files
- **Right List**: Shows available channel selection files
- **Add Mapping Button**: Creates a mapping between selected files
- **Mapping Table**: Displays current mappings
- **OK/Cancel Buttons**: Confirm or discard mappings

### Creating Mappings

1. Select a decomposition file from the left list
2. Select a corresponding channel selection file from the right list
3. Click "Add Mapping" to create the association
4. The mapping appears in the table below
5. Repeat for all required files
6. Click OK to save mappings

### Validation Rules

- Each decomposition file can only be mapped once
- Each channel selection file can only be mapped once
- Both files must be selected to create a mapping
- Existing mappings are preserved and can be extended

## File Processing

### Automatic Processing

When mappings are confirmed:
1. Each decomposition file is processed with its corresponding channel selection
2. The system updates metadata in the result files
3. Progress is tracked and displayed

### File Types

The system handles different file formats:
- `.pkl` files: Updated using `update_extras_in_pickle_file`
- `.json` files: Updated using `update_extras_in_json_file`

### Error Handling

The system provides feedback for common issues:
- Missing files
- Processing errors
- Invalid mappings
- File access problems

## Result Visualization

### OpenHD-EMG Integration

To view results:
1. Click "Show Decomposition Results"
2. The system launches OpenHD-EMG application
3. Results are automatically loaded
4. The button shows a loading animation during startup

### Requirements

- OpenHD-EMG virtual environment must be configured in Settings
- The path must be valid and accessible
- Python environment must include required dependencies

## Configuration

### Required Settings

In the application settings:
```
Settings > OpenHD-EMG Virtual Environment Path
```

### File Paths

The system uses several important paths:
- Decomposition results folder
- Channel selection folder
- OpenHD-EMG virtual environment

## Best Practices

1. **Before Processing**
   - Ensure all decomposition results are available
   - Verify channel selection files are in place
   - Check OpenHD-EMG configuration

2. **During Mapping**
   - Create mappings systematically
   - Verify mappings before confirming
   - Monitor processing progress

3. **Viewing Results**
   - Wait for processing to complete
   - Ensure OpenHD-EMG launches successfully
   - Check for any error messages

## Troubleshooting

### Common Issues

1. **Missing Files**
   - Verify decomposition results are in the correct folder
   - Check channel selection files are available
   - Ensure file permissions are correct

2. **OpenHD-EMG Issues**
   - Verify virtual environment path
   - Check Python dependencies
   - Monitor application logs

3. **Processing Errors**
   - Check file format compatibility
   - Verify file contents
   - Review error messages in application logs

### Error Messages

Common error messages and solutions:

- "OpenHD-EMG virtual environment path is not set"
  - Configure the path in Settings
  - Verify the environment exists

- "The decomposition folder does not exist"
  - Check folder structure
  - Verify workspace configuration
  - Ensure previous steps completed successfully

## Next Steps

After completing this step:
1. Verify all mappings are processed
2. Check results in OpenHD-EMG
3. Export or save final results as needed
