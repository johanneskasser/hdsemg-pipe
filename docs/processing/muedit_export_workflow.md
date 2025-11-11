# MUEdit Export Workflow

The MUEdit Export Workflow provides an automated pipeline for converting manually cleaned motor unit decomposition results back to OpenHD-EMG JSON format for final analysis and visualization.

## Overview

After manually cleaning decomposition results in MUEdit, the application automatically exports the edited files to a standardized OpenHD-EMG JSON format in the `decomposition_results/` folder.

**Workflow Summary:**
```
Original JSON → MUEdit MAT → Manual Cleaning → Edited MAT → Auto-Export → Cleaned JSON
```

## Folder Structure

The export workflow uses the following folders:

- **`decomposition_auto/`** - Contains original decomposition results and MUEdit files
  - `*.json` - Original OpenHD-EMG decomposition results
  - `*_muedit.mat` - Files exported for manual cleaning in MUEdit
  - `*_edited.mat` (or similar) - Files saved after manual cleaning

- **`decomposition_results/`** - Contains final cleaned results (**NEW**)
  - `*.json` - Cleaned decomposition results in OpenHD-EMG format
  - Ready for visualization in OpenHD-EMG
  - Used by "Show Decomposition Results" button

## Automatic Export Process

### Trigger Conditions

The export process is triggered automatically when:

1. An edited MUEdit file is detected in `decomposition_auto/`
2. The file watcher detects changes every 2 seconds
3. The file has not already been exported

### Export Logic

**File Detection:**
```python
# Checks for edited files
for base_name in self.muedit_files:
    # Find original JSON
    # Find edited MAT file (flexible naming)
    # Create export task
```

**Export Execution:**
- Runs in background thread (`MUEditExportWorker`)
- Does not block the UI
- Processes multiple files sequentially
- Emits progress signals for UI updates

### File Naming Convention

The export process uses flexible file naming to detect edited files:

**Input Files:**
- Original: `filename.json` (in `decomposition_auto/`)
- MUEdit export: `filename_muedit.mat` (in `decomposition_auto/`)
- Edited: `filename_*.mat` (in `decomposition_auto/`, any .mat file containing base name)

**Output File:**
- Exported: `filename.json` (in `decomposition_results/`)

**Example:**
```
decomposition_auto/
├── recording1.json                    (original)
├── recording1_muedit.mat              (for editing)
└── recording1_edited.mat              (after manual cleaning)
    ↓ Auto-Export
decomposition_results/
└── recording1.json                    (cleaned, ready for analysis)
```

## Export Implementation

### Data Conversion

The export function `apply_muedit_edits_to_json()` performs the following conversions:

**1. Pulse Trains (IPTS)**
- Extracted from `edition.Pulsetrainclean` in edited MAT file
- Converted to pandas DataFrame (time × nMU)
- Normalized values preserved

**2. Discharge Times (MUPULSES)**
- Extracted from `edition.Distimeclean` (nested cell array)
- Converted from 1-based (MATLAB) to 0-based (Python) indexing
- Stored as list of numpy int32 arrays

**3. Binary Firing Matrix**
- Generated from MUPULSES
- Shape: (n_samples × nMU)
- Binary values: 1 = spike, 0 = no spike

**4. Accuracy (SIL Values)**
- Extracted from `edition.silval`
- Stored as pandas DataFrame
- Represents signal-to-interference-level for each motor unit

**5. Metadata**
- `FILENAME`: Path to edited MAT file
- `NUMBER_OF_MUS`: Number of motor units
- All other fields from original JSON preserved

### Technical Details

**HDF5/MATLAB v7.3 Support:**
```python
import h5py

# Read MATLAB v7.3 file
with h5py.File(mat_edited_path, 'r') as f:
    edit = f['edition']
    pulsetrain_cells = _cell_row_read(f, edit['Pulsetrainclean'])
    disc_nested = _cell_row_read(f, edit['Distimeclean'])
    silval = _cell_row_read(f, edit['silval'])
```

**Cell Array Reading:**
- Custom `_cell_row_read()` function handles MATLAB cell arrays
- Validates HDF5 object references
- Converts to Python lists/arrays

**Output Format:**
- OpenHD-EMG JSON format
- Compression level: 4
- Compatible with OpenHD-EMG GUI
- Preserves all original metadata

## Auto-Delete Synchronization

The workflow includes automatic cleanup to maintain consistency between edited and exported files.

### Delete Sync Logic

When an edited MAT file is deleted (manually or during workflow):

1. **Detection:** File watcher checks `decomposition_results/` folder
2. **Comparison:** Compares `exported_files_on_disk` with `self.edited_files`
3. **Cleanup:** Removes exported JSON if source edited file no longer exists

**Example:**
```python
# If edited file deleted
decomposition_auto/recording1_edited.mat  (❌ deleted)

# Auto-delete sync removes exported file
decomposition_results/recording1.json     (🗑️ auto-deleted)
```

### Benefits

- **Consistency:** Exported files always match edited source files
- **Cleanup:** No orphaned files in results folder
- **Flexibility:** Users can re-edit files without manual cleanup

## Progress Tracking

### Three-Stage Status

The UI tracks files through three stages:

1. **⏳ Pending** - Exported to MUEdit, not yet edited
   - File: `*_muedit.mat` exists
   - No edited version found

2. **✅ Edited** - Manually cleaned in MUEdit
   - File: `*_edited.mat` (or similar) exists
   - Ready for export

3. **📦 Exported** - Converted to OpenHD-EMG format
   - File: `*.json` exists in `decomposition_results/`
   - Ready for visualization

### Progress Bar

```
Manual Cleaning Workflow: 3/5 exported (60%)
[██████████████████████░░░░░░░░] 60%
```

**Progress Calculation:**
- Based on exported files (final stage)
- Formula: `(exported_count / total_muedit_files) × 100`
- Updates in real-time as files are exported

### File Status Display

```
File Status:
📦 file1 (exported)     ← Blue (completed)
📦 file2 (exported)     ← Blue (completed)
✅ file3 (edited)       ← Green (exporting...)
⏳ file4 (pending)      ← Gray (needs editing)
⏳ file5 (pending)      ← Gray (needs editing)
```

## Show Decomposition Results Button

The "Show Decomposition Results" button is dynamically enabled based on exported files.

### Button States

**Disabled (Initial State):**
- No exported files in `decomposition_results/`
- Tooltip: "No exported results found. Please complete manual cleaning workflow first."

**Enabled (After Export):**
- At least one file exported successfully
- Opens OpenHD-EMG with cleaned results
- Tooltip: "Open OpenHD-EMG to view cleaned decomposition results from decomposition_results folder"

### Button Logic

```python
# Enable when files exported
if len(self.exported_files) > 0:
    self.btn_show_results.setEnabled(True)

# Disable when no files
if len(self.exported_files) == 0:
    self.btn_show_results.setEnabled(False)
```

**Real-time Updates:**
- Button enabled immediately after first successful export
- Button disabled if all exported files are deleted
- No manual refresh needed

### OpenHD-EMG Launch

When the button is clicked:

1. **Validation:**
   - Checks `decomposition_results/` folder exists
   - Verifies at least one `.json` file present
   - Displays warning if no files found

2. **Launch:**
   - Uses current Python interpreter: `sys.executable`
   - Command: `python -m openhdemg.gui.openhdemg_gui`
   - Opens in the `decomposition_results/` folder

3. **Loading State:**
   - Button shows loading animation
   - Callback stops loading when OpenHD-EMG starts

## Error Handling

### Export Errors

**Common Issues:**

1. **Missing original JSON:**
   ```
   Could not find original JSON for filename, skipping export
   ```
   - **Cause:** Original JSON file moved or deleted
   - **Solution:** Ensure original JSON remains in `decomposition_auto/`

2. **Missing edited MAT file:**
   ```
   Could not find edited MAT file for filename, skipping export
   ```
   - **Cause:** Edited file not detected or has unexpected naming
   - **Solution:** Verify file saved correctly from MUEdit

3. **HDF5 Structure Error:**
   ```
   'edition' group not found in file.mat
   ```
   - **Cause:** MAT file not saved by MUEdit or wrong version
   - **Solution:** Re-save file in MUEdit, ensure devHP branch

4. **Missing required fields:**
   ```
   edition.Pulsetrainclean not found in edited MAT
   ```
   - **Cause:** MUEdit file structure incomplete
   - **Solution:** Check MUEdit version and save process

### UI Error Messages

**Export Failed:**
```python
self.warn(f"Failed to export {base_name}: {error_msg}")
```
- Displayed in status bar
- Logged with full traceback
- Other files continue processing

**No Exported Files:**
```python
self.warn("No exported JSON files found in decomposition_results folder.")
```
- Shown when "Show Results" clicked with empty folder
- Guides user to complete workflow first

## State Reconstruction

When opening an existing workfolder, the export workflow state is automatically reconstructed.

### Folder Creation

The `decomposition_results/` folder is **optional** for backwards compatibility:

```python
# In automatic_state_reconstruction.py
optional_folders = [FolderNames.DECOMPOSITION_RESULTS.value]

if subfolder in optional_folders:
    os.makedirs(subfolder_path, exist_ok=True)
    logger.info(f"Created optional subfolder: {subfolder_path}")
```

**Behavior:**
- Old workfolders without `decomposition_results/`: Folder auto-created
- New workfolders: Folder created during initial setup
- No errors if folder missing, just creates it

### State Detection

On reconstruction:

1. Scans `decomposition_auto/` for edited MAT files
2. Scans `decomposition_results/` for exported JSON files
3. Matches files by base name
4. Rebuilds `self.edited_files` and `self.exported_files` lists
5. Updates UI with correct progress state

## Performance Considerations

### Background Processing

**Worker Thread:**
- Export runs in `MUEditExportWorker` (QThread)
- UI remains responsive during export
- Multiple files processed sequentially
- Progress signals emitted for each file

**Batch Processing:**
```python
export_tasks = [
    (base_name, original_json, edited_mat, output_json),
    ...
]
worker = MUEditExportWorker(export_tasks)
```

### File Watching

**Update Frequency:**
- Checks for changes every 2 seconds
- Balances responsiveness vs. system load
- Auto-triggers export when edited files detected

**Optimization:**
```python
# Only export if not already running
if self.export_worker and self.export_worker.isRunning():
    return  # Skip if export in progress
```

## Best Practices

### During Manual Cleaning

1. **Save regularly** in MUEdit to trigger auto-export
2. **Keep instruction dialog open** to track progress
3. **Work sequentially** through files for better organization
4. **Don't rename files** manually to avoid detection issues

### After Export

1. **Verify exports** before deleting edited MAT files
2. **Check progress UI** shows all files as 📦 exported
3. **Use "Show Results" button** to validate in OpenHD-EMG
4. **Keep original JSON files** in `decomposition_auto/` (required for re-export)

### Troubleshooting

1. **If export doesn't trigger:**
   - Check file watcher is active (restart app if needed)
   - Verify edited file naming matches base name
   - Check logs for error messages

2. **If exported file missing:**
   - Check `decomposition_results/` folder permissions
   - Look for export errors in application logs
   - Verify edited MAT file has correct structure

3. **If "Show Results" button disabled:**
   - Ensure at least one file successfully exported
   - Check `decomposition_results/` folder has .json files
   - Wait for auto-export to complete (check progress bar)

## Example Workflow

### Complete Export Workflow Example

```
1. Start with decomposition results
   decomposition_auto/rec1.json

2. Export to MUEdit
   → Click "Export to MUEdit"
   → decomposition_auto/rec1_muedit.mat created
   → Status: ⏳ rec1 (pending)

3. Manual cleaning
   → Click "Open MUEdit"
   → Load rec1_muedit.mat
   → Clean motor units
   → Save in MUEdit
   → decomposition_auto/rec1_edited.mat created
   → Status: ✅ rec1 (edited)

4. Auto-export (background)
   → Export worker starts automatically
   → Converts rec1_edited.mat → rec1.json
   → decomposition_results/rec1.json created
   → Status: 📦 rec1 (exported)
   → "Show Decomposition Results" button enabled

5. View results
   → Click "Show Decomposition Results"
   → OpenHD-EMG opens with decomposition_results/ folder
   → Load rec1.json for analysis
   → Workflow complete!
```

## Technical Reference

### Files Modified

- `decomposition_export.py` - Export function implementation
- `muedit_export_worker.py` - Background worker thread
- `DecompositionStepWidget.py` - UI and workflow logic
- `FolderNames.py` - Added `DECOMPOSITION_RESULTS`
- `global_state.py` - Added `get_decomposition_results_path()`
- `automatic_state_reconstruction.py` - State reconstruction support

### Dependencies

- **h5py** - Reading MATLAB v7.3 (HDF5) files
- **openhdemg** - OpenHD-EMG library for JSON format
- **numpy** - Array operations
- **pandas** - DataFrame handling

### Configuration

No additional configuration required. The workflow uses existing settings:

- `OPENHDEMG_INSTALLED` - Checks if OpenHD-EMG available
- `MUEDIT_PATH` - MUEdit installation path (for manual cleaning)
- `WORKFOLDER_PATH` - Project workfolder

## See Also

- [Decomposition Results](decomposition_results.md) - Overview of decomposition results step
- [MUEdit Manual Cleaning](decomposition_results.md#manual-cleaning-workflow-muedit) - Manual cleaning workflow
- [OpenHD-EMG Integration](decomposition_results.md#result-visualization) - Visualization in OpenHD-EMG
