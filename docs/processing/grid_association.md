# Grid Association

The Grid Association dialog allows you to combine multiple electrode grids into a single virtual grid while maintaining the relationship between channels and their respective source files.

## Overview

In this step, you can:
1. Select grids from different files to combine
2. Name your grid association
3. Save multiple associations in one session
4. Review your saved associations

![Grid Association Dialog](../img/grid_association.png)

## Interface Components

### Available Grids List
- Displays all grids from loaded files
- Shows grid dimensions and reference channel count
- Format: `[rows]x[cols] Grid ([ref_count] refs) - [filename]`

### Selected Grids List
- Shows grids selected for combination
- Supports drag and drop for reordering
- Order matters for channel mapping

### Control Buttons
- `>>` button to add a grid to the selection
- `<<` button to remove a grid from selection
- `+` button to save current association and create another
- `Save & Close` button to save and exit

### Association Name
- Input field for naming your grid combination
- Names are sanitized for file system compatibility
- Timestamp is automatically added to prevent overwrites

## Validation Checks

The system performs several automatic checks:

1. **Time Vector Compatibility**
   - Ensures all selected grids have matching time vectors
   - Prevents combining recordings of different lengths

2. **Sampling Frequency**
   - Verifies all grids have the same sampling frequency
   - Essential for maintaining signal timing integrity

## Data Processing

### Channel Combination Process

1. **Grid Size Calculation**
   - Automatically determines optimal dimensions for the combined grid
   - Uses total EMG channel count to compute rows and columns
   - Aims for most square-like configuration

2. **Data Integration**
   - Combines EMG channels from all selected grids
   - Preserves reference signals from each source
   - Maintains channel descriptions with updated grid dimensions

### Metadata Handling

The association is saved in two formats:

1. **MAT File**
   - Contains the combined signal data
   - Includes updated channel descriptions
   - Preserves timing and sampling information
   - Stores grid configuration metadata

2. **JSON File**
   - Records association metadata
   - Stores original grid information
   - Contains file references and channel mappings
   - Includes timestamp and association name

## Output Format

#### Combined Grid MATLAB Data File (MAT)

The newly created `.mat` file will contain only one, combined grid. The structure will be the same as the original file stucture.

### Combined Grid Information (JSON)
```json
{
    "association_name": "your_association_name",
    "timestamp": "YYYY-MM-DD_HH-MM-SS",
    "grids": [
        {
            "file_name": "original_file.mat",
            "rows": 8,
            "cols": 8,
            "emg_count": 64,
            "ref_count": 2,
            "ied_mm": 10,
            "electrodes": {...}
        }
    ],
    "combined_grid_info": {
        "combined_emg_grid": {
            "rows": 16,
            "cols": 8
        },
        "reference_signals": [...]
    }
}
```
> After completing this step, these files will be saved in the `associated_grids/` folder within your working directory.

## Best Practices

1. **Grid Selection**
   - Ensure grids are from compatible recording sessions
   - Verify sampling rates match before combining
   - Consider the spatial relationship between grids

2. **Association Naming**
   - Use descriptive names for easy identification
   - Include relevant experimental conditions
   - Names will be sanitized automatically

3. **Data Management**
   - Associations are saved in the workspace
   - Both .mat and .json files are generated
   - Original files remain unchanged

## Troubleshooting

### Common Issues

1. **Validation Errors**
   - Check sampling frequencies match
   - Verify recording lengths are identical
   - Ensure all files are from the same experiment

2. **Saving Problems**
   - Verify association name is provided
   - Check workspace has write permissions
   - Ensure enough disk space is available

3. **Grid Size Issues**
   - Total channel count must be factorizable
   - System will optimize grid dimensions automatically
   - Consider recording setup when selecting grids

### Error Messages

- "Time vectors mismatch between selected grids"
  - Recordings have different lengths
  - Ensure all recordings cover the same time period

- "Sampling frequency mismatch between selected grids"
  - Different sampling rates detected
  - All grids must have identical sampling frequency
