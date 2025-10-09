# Line Noise Removal

The Line Noise Removal step allows you to remove powerline interference (50/60 Hz) and its harmonics from your HD-sEMG signals. This step is crucial for improving signal quality before further analysis.

## Overview

In this step, you can:
1. Choose from multiple line noise removal methods
2. Select the appropriate powerline frequency region (US/EU)
3. Process multiple files with visual progress tracking
4. Compare different filtering approaches

## Requirements

Before using the Line Noise Removal step:
- Files must have been processed through the Grid Association step
- The workspace must be properly initialized
- For MATLAB-based methods: MATLAB Engine for Python must be installed
- For CleanLine: MATLAB + EEGLAB + CleanLine plugin must be installed
- For Octave: Octave and oct2py must be installed

## Available Methods

### 1. MNE-Python: Notch Filter (FIR)
**Type:** Finite Impulse Response filter
**Speed:** ⚡⚡⚡ Very fast
**Quality:** ⭐⭐⭐ Good

Classic notch filter approach that creates narrow rejection bands at specified frequencies.

**Advantages:**
- Very fast and efficient
- Stable filtering (no phase shift with zero-phase)
- Simple to understand
- No external dependencies (only MNE-Python)

**Disadvantages:**
- Also removes frequencies near the target ("frequency hole")
- Not adaptive - uses fixed frequencies
- Can cause time-domain distortions

**Best for:** Fast processing when slight spectral distortions are acceptable.

### 2. MNE-Python: Spectrum Fit (Adaptive) ⭐ RECOMMENDED
**Type:** Adaptive spectrum fitting with sinusoidal regression
**Speed:** ⚡⚡ Medium
**Quality:** ⭐⭐⭐⭐⭐ Excellent

Adaptively estimates and removes sinusoidal components using sliding windows. Similar approach to CleanLine.

**Advantages:**
- Adaptive - adjusts to time-varying interference
- Minimal distortion of adjacent frequencies
- Narrower removal than classical notch filters
- No external dependencies (only MNE-Python)
- Similar quality to CleanLine without MATLAB

**Disadvantages:**
- Slower than simple notch filter
- More computationally intensive for long signals

**Best for:** High-quality signal processing with minimal distortion. This is the **recommended default method** for most users.

### 3. MATLAB CleanLine (EEGLAB Plugin) 🏆 GOLD STANDARD
**Type:** Adaptive multi-taper regression with Thompson F-statistic
**Speed:** ⚡ Slow
**Quality:** ⭐⭐⭐⭐⭐ Excellent (Gold Standard)

The original CleanLine algorithm from EEGLAB. Uses multi-taper spectral analysis with statistical validation.

**Advantages:**
- **Gold standard** for adaptive line noise removal
- Statistical validation using Thompson F-test
- Excellent for time-varying line noise
- Well-tested in neuroscience community
- Can automatically detect line noise frequencies

**Disadvantages:**
- **Requires MATLAB license** (commercial)
- Requires CleanLine plugin installation in EEGLAB
- Slower due to Python-MATLAB communication
- Most computationally intensive method
- Higher memory usage

**Best for:** Users with MATLAB + EEGLAB setup who need the highest quality adaptive filtering.

**Installation Requirements:**
1. MATLAB (license required)
2. EEGLAB installed
3. CleanLine plugin installed in EEGLAB
4. MATLAB Engine for Python
5. EEGLAB in MATLAB path

### 4. MATLAB: IIR Notch Filter
**Type:** Infinite Impulse Response notch filter
**Speed:** ⚡⚡ Medium
**Quality:** ⭐⭐⭐⭐ Very good

Native MATLAB implementation using `iirnotch` and `filtfilt` functions.

**Advantages:**
- Native MATLAB implementation
- Very narrow-band filtering possible
- Well documented
- Compatible with MATLAB workflows

**Disadvantages:**
- **Requires MATLAB license** (commercial)
- Slower due to Python-MATLAB communication
- Not adaptive

**Best for:** Users with existing MATLAB license who prefer MATLAB-native implementations.

### 5. Octave: IIR Notch Filter (Free)
**Type:** Infinite Impulse Response notch filter via GNU Octave
**Speed:** ⚡ Slow
**Quality:** ⭐⭐⭐⭐ Very good

MATLAB-compatible filtering using free GNU Octave.

**Advantages:**
- **Free and Open Source**
- MATLAB-compatible syntax
- Similar results to MATLAB
- No license costs

**Disadvantages:**
- Octave and oct2py must be installed separately
- Slower due to Python-Octave communication
- ~95% MATLAB compatible (minor differences possible)
- Not adaptive

**Best for:** Users without MATLAB license who want MATLAB-like processing.

## Interface Components

### Method Display
- Shows currently selected method and region
- Example: `Method: ⭐ MNE Spectrum Fit | 60 Hz (US)`
- **Clickable** - opens detailed method information dialog
- Updates automatically when settings change

### Files Counter
- Shows current progress as "Files: processed/total"
- Updates in real-time during processing
- Example: "Files: 3/10"

### Progress Bar
- Visual progress indicator showing percentage complete
- Only appears during processing
- Automatically hidden after completion

### Action Buttons
- **"Methods Info"** - Opens detailed comparison of all methods
- **"Remove Noise"** - Starts processing with selected method

## Process Flow

1. **Initialization**
   - System checks for input files from Grid Association
   - Verifies selected method availability (MATLAB/Octave)
   - Updates method display
   - Enables/disables action button based on validation

2. **Processing Start**
   - User clicks "Remove Noise" button
   - Button shows loading animation
   - Progress bar appears
   - Files counter resets
   - Output directory is created

3. **File Processing**
   - Files are processed sequentially
   - Progress bar updates after each file
   - Files counter increments
   - Results saved to `line_noise_cleaned/` folder

4. **Completion**
   - Loading animation stops
   - Progress bar disappears
   - Final file count displayed
   - Step marked as complete
   - Success message shown

## Configuration

### Method Selection

Configure the line noise removal method in:
```
Settings > Preferences > Line Noise Removal > Line Noise Removal Method
```

Available options (depending on installed software):
- ⚡ MNE-Python: Notch Filter (FIR) - Fast
- ⭐ MNE-Python: Spectrum Fit (Adaptive) - **Recommended**
- 🏆 MATLAB: CleanLine (EEGLAB Plugin) - Gold Standard
- 🔬 MATLAB: IIR Notch Filter
- 🐙 Octave: IIR Notch Filter (Free)

### Region Selection

Configure your powerline frequency region in:
```
Settings > Preferences > Line Noise Removal > Power Line Frequency Region
```

Options:
- **🇺🇸 USA/North America (60 Hz)** - Removes 60, 120, 180, 240 Hz
- **🇪🇺 Europe/Asia (50 Hz)** - Removes 50, 100, 150, 200 Hz

### File Handling

**Input files:**
- Located in the `associated_grids/` directory
- Must be in .mat format
- Must contain valid EMG channel data

**Output files:**
- Saved in the `line_noise_cleaned/` directory
- Maintain original file names
- Contain the same structure with cleaned signal data

## Method Comparison

| Method | Speed | Quality | Cost | Adaptive | Dependencies |
|--------|-------|---------|------|----------|--------------|
| MNE Notch | ⚡⚡⚡ | ⭐⭐⭐ | Free | ✗ | MNE-Python |
| **MNE Spectrum Fit** | ⚡⚡ | ⭐⭐⭐⭐⭐ | Free | ✓ | MNE-Python |
| **MATLAB CleanLine** | ⚡ | ⭐⭐⭐⭐⭐ | MATLAB | ✓✓✓ | MATLAB + EEGLAB |
| MATLAB IIR | ⚡⚡ | ⭐⭐⭐⭐ | MATLAB | ✗ | MATLAB |
| Octave IIR | ⚡ | ⭐⭐⭐⭐ | Free | ✗ | Octave |

## Error Handling

### Common Issues

1. **Method Not Available**
   - Warning: "MATLAB is not available. Please install MATLAB Engine..."
   - Solution: Install required software or select a different method

2. **No Input Files**
   - Warning: "No files available for processing"
   - Solution: Ensure Grid Association step was completed successfully

3. **Processing Errors**
   - Error displayed in step status
   - Check application logs for details
   - Verify file integrity

### MATLAB/CleanLine Specific Issues

1. **EEGLAB Not Found**
   - Error: "EEGLAB might not be on MATLAB path"
   - Solution: Add EEGLAB to MATLAB path in startup.m

2. **CleanLine Not Installed**
   - Error: "CleanLine execution failed"
   - Solution: Install CleanLine plugin in EEGLAB

3. **MATLAB Engine Issues**
   - Error: "Failed to start MATLAB engine"
   - Solution: Reinstall MATLAB Engine for Python

## Best Practices

### Method Selection

1. **For most users:** Use **MNE Spectrum Fit** (default)
   - Excellent quality
   - Free and fast
   - No additional software needed

2. **For MATLAB users with EEGLAB:** Use **CleanLine**
   - Gold standard quality
   - Best for time-varying line noise
   - Requires MATLAB setup

3. **For quick testing:** Use **MNE Notch Filter**
   - Very fast
   - Good enough for initial exploration

### Before Processing

1. Verify method availability in settings
2. Check input file availability
3. Ensure sufficient disk space
4. Select correct powerline frequency region

### During Processing

1. Allow each file to process completely
2. Monitor progress bar and file counter
3. Don't close the application during processing
4. Watch for error messages in step status

### After Processing

1. Verify output files in `line_noise_cleaned/` folder
2. Check file counts match expected totals
3. Visually inspect a few cleaned signals (optional)
4. Proceed to next step only after completion

## Technical Details

### MNE Spectrum Fit Algorithm

The spectrum fit method uses a sophisticated approach:
1. **Segmentation:** Signal divided into overlapping windows
2. **Spectral Analysis:** FFT applied to each window
3. **Sinusoid Fitting:** Sinusoidal curves fitted to interference frequencies
4. **Subtraction:** Estimated interference subtracted from signal
5. **Smoothing:** Transitions between windows smoothed

### MATLAB CleanLine Algorithm

CleanLine uses multi-taper spectral analysis:
1. **Multi-Taper Estimation:** Uses Slepian sequences (DPSS) for robust spectral estimation
2. **Statistical Testing:** Thompson F-statistic tests significance of line noise
3. **Adaptive Fitting:** Fits sinusoids with time-varying amplitude and phase
4. **Regression:** Least-squares regression estimates interference parameters
5. **Removal:** Subtracts estimated interference while preserving signal

**Key CleanLine Parameters:**
- Window size: 4 seconds (default)
- Window overlap: 50% (default)
- Bandwidth: 2 Hz per frequency
- Significance level: p-value threshold
- Smoothing factor: 100

### Data Format

All methods:
- Preserve original data structure
- Maintain sampling frequency
- Keep all metadata
- Only modify signal data array

## Installation Guides

### MNE-Python (Already Installed)
```bash
pip install mne>=1.0.0
```

### MATLAB Engine for Python

**Installation Assistant (Recommended):**
1. Go to **Settings → Preferences → Line Noise Removal**
2. Scroll to **MATLAB Engine for Python** section
3. Click **Show Installation Instructions** button
4. Follow the displayed instructions (copy-paste ready commands)
5. Click "Copy Command" to copy the installation command
6. Run the command in MATLAB or Terminal/CMD
7. Restart application after installation

**Benefits:**
- Automatically detects your MATLAB installation path
- Provides correct commands for your system
- Works with all Python environments
- Simple copy-paste workflow

**Manual Installation (if you prefer):**

*Option 1 - In MATLAB:*
```matlab
cd(fullfile(matlabroot,'extern','engines','python'))
system('python setup.py install')
```

*Option 2 - In Terminal/CMD:*
```bash
cd <matlabroot>/extern/engines/python
python setup.py install
```

### MATLAB CleanLine (EEGLAB Plugin)
1. Install MATLAB (license required)
2. Install EEGLAB from [sccn.ucsd.edu](https://sccn.ucsd.edu/eeglab/download.php)
3. In EEGLAB: `File → Manage EEGLAB extensions → CleanLine`
4. Install MATLAB Engine (see above - use automatic installation)
5. Add EEGLAB to MATLAB path (in startup.m or manually)

### Octave
1. Install Octave from [octave.org](https://octave.org/download)
2. Install Python package:
```bash
pip install oct2py>=5.0.0
```

## Next Steps

After line noise removal is complete:
1. Verify the number of processed files matches your input
2. Check output directory for cleaned files
3. Proceed to [Crop to Region of Interest](crop_to_roi.md)

## Troubleshooting

If you encounter issues:

1. **Check Installation Status**
   - Open Settings → Preferences → Line Noise Removal
   - Verify installation status indicators

2. **Method-Specific Issues**
   - MATLAB/CleanLine: Check EEGLAB and CleanLine installation
   - Octave: Verify Octave installation with `octave --version`
   - All methods: Check application logs

3. **Performance Issues**
   - CleanLine and Octave methods are slower - this is normal
   - For faster processing, use MNE Spectrum Fit
   - Ensure sufficient RAM for large files

4. **Quality Issues**
   - Verify correct region selected (50 Hz vs 60 Hz)
   - Try different methods to compare results
   - Check if line noise is actually present (use Methods Info for guidance)

## References

- [MNE-Python Notch Filter Documentation](https://mne.tools/stable/generated/mne.filter.notch_filter.html)
- [CleanLine GitHub Repository](https://github.com/sccn/cleanline)
- [CleanLine EEGLAB Wiki](https://sccn.ucsd.edu/wiki/Cleanline)
- [Spectrum Interpolation Paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6456018/)
