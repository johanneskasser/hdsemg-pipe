# Analysis Notebook Export

The Analysis Notebook Export feature provides a customized Jupyter notebook and helper module for continued analysis after completing the hdsemg-pipe workflow.

## Overview

After completing the full HD-sEMG processing pipeline and obtaining cleaned motor unit data, you can export a ready-to-use Jupyter notebook that:

- **Loads your cleaned data** using openhdemg
- **Summarizes the processing pipeline** with all completed steps
- **Provides example visualizations** of motor unit discharge patterns, firing rates, and action potentials
- **Includes analysis templates** for recruitment, firing rate statistics, and quality metrics
- **Serves as a boilerplate** for your custom analysis workflows

## Prerequisites

```bash
# Required for notebook export
pip install nbformat

# Recommended for visualization and analysis
pip install openhdemg
```

## How to Export

1. **Complete the Pipeline**: Process your data through all steps (1-12) until you reach **Step 12: Final Results**

2. **Convert MUEdit Files**: Click **"Convert to JSON"** to convert your edited MUEdit files to openhdemg JSON format

3. **Export Notebook**: Click **"Export Analysis Notebook"** button

4. **Files Created**: Two files will be generated in your workfolder root:
   - `workfolder_analysis_helper.py` - Python helper module (~250 lines)
   - `hdsemg_analysis.ipynb` - Jupyter notebook (20 cells)

## Generated Files

### Helper Module: `workfolder_analysis_helper.py`

A Python module providing convenient access to your pipeline data:

**Classes:**

- **`WorkfolderPaths`** - Easy access to all folder paths and file listings
  ```python
  paths = WorkfolderPaths("/path/to/workfolder")
  final_files = paths.list_final_json_files()
  ```

- **`MetadataReader`** - Read pipeline metadata (CoVISI reports, mappings, etc.)
  ```python
  reader = MetadataReader(paths)
  covisi_report = reader.get_covisi_pre_filter()
  ```

- **`PipelineSummary`** - Display processing steps and quality metrics
  ```python
  summary = PipelineSummary(paths, reader)
  summary.print_full_summary()
  ```

**Utility Functions:**

- `plot_pipeline_overview(summary)` - Visual overview of completed steps
- `plot_covisi_comparison(reader)` - Compare CoVISI values before/after cleaning

### Jupyter Notebook: `hdsemg_analysis.ipynb`

A 20-cell notebook structured as follows:

#### 1. Setup & Imports
- Standard libraries (numpy, pandas, matplotlib)
- Helper module import
- openhdemg integration (with fallback if not installed)
- Matplotlib configuration

#### 2. Pipeline Summary
- Lists all completed processing steps
- Shows file counts at each stage
- Displays quality metrics (RMS, CoVISI)

#### 3. Data Loading
- Loads all cleaned JSON files using openhdemg
- Displays file metadata (number of MUs, sampling frequency, duration)

#### 4. Motor Unit Visualizations

Four example visualizations included:

1. **Discharge Times (Rasterplot)** - Shows motor unit firing patterns over time
   ```python
   plot.plot_mupulses(emgfile=emgfile, linewidths=0.8)
   ```

2. **Instantaneous Discharge Rate** - Firing rate of each motor unit
   ```python
   plot.plot_idr(emgfile=emgfile, munumber="all")
   ```

3. **Motor Unit Action Potentials** - MUAP morphology comparison
   ```python
   plot.plot_muaps(emgfile=emgfile, munumber="all", channel=0)
   ```

4. **Reference Signal** - Force/activation context
   ```python
   plot.plot_refsig(emgfile=emgfile, ylabel="Force")
   ```

#### 5. Motor Unit Analysis

Four analysis examples included:

1. **Recruitment Analysis** - Recruitment order and timing
   - Extracts first spike time for each motor unit
   - Sorts motor units by recruitment time
   - Displays recruitment order

2. **Firing Rate Statistics** - Mean/peak firing rates per motor unit
   - Calculates inter-spike intervals (ISI)
   - Computes instantaneous firing rates
   - Shows mean and peak rates for each MU
   - Verifies CoVISI quality post-cleaning

3. **Motor Unit Properties** - Summary statistics
   - Number of spikes per motor unit
   - Active duration
   - Mean firing rate
   - Exports properties to `motor_unit_properties.csv`

4. **Quality Metrics** - SIL values and CoVISI comparison
   - Displays silhouette (SIL) scores
   - Compares CoVISI pre-filter and post-validation
   - Shows motor units filtered during processing

#### 6. Custom Analysis Section

Template section for your own analysis code with placeholder examples:
- Cross-correlations between motor units
- Coherence analysis with reference signal
- Custom recruitment pattern analysis
- Export to Excel/MATLAB formats

#### 7. Export Results

Example code for saving analysis outputs to files.

## Using the Notebook

### 1. Open in Jupyter

```bash
cd /path/to/your/workfolder
jupyter notebook hdsemg_analysis.ipynb
```

Or use Jupyter Lab:

```bash
jupyter lab hdsemg_analysis.ipynb
```

### 2. Run All Cells

In Jupyter, select **Cell → Run All** to execute the entire notebook.

### 3. Explore and Customize

- Modify visualization parameters (colors, titles, figure sizes)
- Add your own analysis code in the Custom Analysis section
- Export results to your preferred formats

## Example Workflow

### Basic Analysis

```python
# Cell 1: Imports and setup
from workfolder_analysis_helper import WorkfolderPaths, MetadataReader, PipelineSummary
import openhdemg.library as emg

# Cell 2: Initialize
paths = WorkfolderPaths(WORKFOLDER)
summary = PipelineSummary(paths, MetadataReader(paths))
summary.print_full_summary()

# Cell 3: Load data
final_files = paths.list_final_json_files()
emgfile = emg.emg_from_json(str(final_files[0]))

# Cell 4: Visualize
import openhdemg.plotemg as plot
plot.plot_mupulses(emgfile=emgfile)
```

### Advanced Analysis

```python
# Extract firing rates for all motor units
firing_rates = []
for mu_idx in range(emgfile['NUMBER_OF_MUS']):
    mupulses = emgfile['MUPULSES'][mu_idx]
    isi = np.diff(mupulses) / emgfile['FSAMP']
    mean_rate = np.mean(1.0 / isi)
    firing_rates.append(mean_rate)

# Plot distribution
plt.hist(firing_rates, bins=20)
plt.xlabel('Mean Firing Rate (Hz)')
plt.ylabel('Count')
plt.title('Distribution of Motor Unit Firing Rates')
plt.show()
```

## Helper Module API Reference

### WorkfolderPaths

```python
class WorkfolderPaths:
    def __init__(self, workfolder: str)

    # File listing methods
    def list_original_files() -> List[Path]
    def list_final_json_files() -> List[Path]
    def list_decomposition_files() -> List[Path]
    def list_analysis_files() -> Dict[str, List[Path]]

    # Metadata paths
    def get_metadata_files() -> Dict[str, Path]
```

### MetadataReader

```python
class MetadataReader:
    def __init__(self, paths: WorkfolderPaths)

    # Read metadata
    def get_decomposition_mapping() -> Optional[Dict]
    def get_multigrid_groupings() -> Optional[Dict]
    def get_covisi_pre_filter() -> Optional[Dict]
    def get_covisi_post_validation() -> Optional[Dict]
    def get_rms_quality_data(json_file: Path) -> Optional[Dict]

    # Check status
    def check_skip_marker(folder: Path) -> bool
```

### PipelineSummary

```python
class PipelineSummary:
    def __init__(self, paths: WorkfolderPaths, reader: MetadataReader)

    # Display methods
    def print_full_summary()
    def print_quality_metrics()

    # Data access
    def get_completed_steps() -> List[Tuple[int, str, str]]
    def get_processing_info() -> Dict
```

## Troubleshooting

### ImportError: No module named 'nbformat'

**Problem**: nbformat library not installed

**Solution**:
```bash
pip install nbformat
```

### ImportError: No module named 'openhdemg'

**Problem**: openhdemg library not installed

**Solution**:
```bash
pip install openhdemg
```

**Note**: The notebook will still run without openhdemg, but visualization cells will show warnings. You can perform manual analysis using pandas/numpy.

### FileNotFoundError: workfolder_analysis_helper.py

**Problem**: Helper module not found

**Solution**: Ensure you run Jupyter from the workfolder root directory where the helper module was exported:

```bash
cd /path/to/workfolder  # Must be in workfolder root
jupyter notebook hdsemg_analysis.ipynb
```

### ModuleNotFoundError: No module named 'workfolder_analysis_helper'

**Problem**: Python cannot find the helper module

**Solution**: The notebook automatically adds the workfolder to Python's path. If this fails, manually add:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from workfolder_analysis_helper import WorkfolderPaths
```

### Visualization plots not displaying

**Problem**: Matplotlib backend issue

**Solution**: Ensure the first code cell includes:

```python
%matplotlib inline
```

Or try switching backends:

```python
%matplotlib widget  # Interactive plots
```

### "No cleaned JSON files available"

**Problem**: Trying to export before converting MUEdit files

**Solution**: In Step 12, click **"Convert to JSON"** first, then **"Export Analysis Notebook"**.

## Tips and Best Practices

### 1. Version Control

Consider version-controlling your modified notebook:

```bash
git add hdsemg_analysis.ipynb
git commit -m "Add custom analysis for XYZ experiment"
```

### 2. Multiple Analyses

Create copies of the notebook for different analysis approaches:

```bash
cp hdsemg_analysis.ipynb hdsemg_analysis_recruitment.ipynb
cp hdsemg_analysis.ipynb hdsemg_analysis_coherence.ipynb
```

### 3. Export Results

Save analysis outputs for reproducibility:

```python
# Export figures
fig.savefig('motor_unit_discharge_times.png', dpi=300, bbox_inches='tight')

# Export data
df_properties.to_csv('motor_unit_properties.csv', index=False)
df_properties.to_excel('motor_unit_properties.xlsx', index=False)
```

### 4. Documentation

Add markdown cells to document your custom analysis:

```markdown
## Custom Analysis: Cross-Correlation

This section computes cross-correlations between motor unit pairs
to identify common synaptic input.

**Method**: Pearson correlation of smoothed discharge rates
**Reference**: De Luca et al. (2016)
```

### 5. Reusability

Extract reusable functions:

```python
def compute_recruitment_threshold(emgfile, mu_idx):
    """Compute recruitment threshold for a motor unit."""
    mupulses = emgfile['MUPULSES'][mu_idx]
    first_spike_sample = mupulses[0]
    ref_signal = emgfile['REF_SIGNAL']
    threshold = ref_signal.iloc[first_spike_sample, 0]
    return threshold
```

## Related Documentation

- [openhdemg Documentation](https://www.giacomovalli.com/openhdemg/)
- [CoVISI Filtering](covisi_filtering.md)
- [MUEdit Cleaning](muedit_cleaning.md)
- [Developer Guide](../developer.md)

## Example Gallery

### Example 1: Recruitment Threshold Analysis

```python
# Load data
emgfile = emg.emg_from_json('decomposition_cleaned.json')
ref_signal = emgfile['REF_SIGNAL'].values.flatten()

# Extract recruitment thresholds
thresholds = []
for mu_idx in range(emgfile['NUMBER_OF_MUS']):
    first_spike = emgfile['MUPULSES'][mu_idx][0]
    threshold = ref_signal[first_spike]
    thresholds.append(threshold)

# Plot
plt.scatter(range(len(thresholds)), thresholds)
plt.xlabel('Motor Unit Index')
plt.ylabel('Recruitment Threshold (% MVC)')
plt.title('Motor Unit Recruitment Thresholds')
plt.show()
```

### Example 2: Firing Rate During Contraction

```python
# Compute smoothed firing rate for all MUs
import scipy.signal as signal

fig, axes = plt.subplots(emgfile['NUMBER_OF_MUS'], 1, figsize=(12, 10), sharex=True)

for mu_idx in range(emgfile['NUMBER_OF_MUS']):
    # Get discharge times
    ipts = emgfile['IPTS'].iloc[:, mu_idx].values

    # Smooth
    window = signal.windows.gaussian(1000, std=200)
    smoothed = signal.convolve(ipts, window, mode='same') / window.sum()

    # Plot
    time = np.arange(len(smoothed)) / emgfile['FSAMP']
    axes[mu_idx].plot(time, smoothed * emgfile['FSAMP'])
    axes[mu_idx].set_ylabel(f'MU {mu_idx}\\n(Hz)')

axes[-1].set_xlabel('Time (s)')
plt.suptitle('Smoothed Firing Rates')
plt.tight_layout()
plt.show()
```

### Example 3: Export to MATLAB

```python
import scipy.io as sio

# Prepare data for MATLAB
matlab_data = {
    'FSAMP': emgfile['FSAMP'],
    'NUMBER_OF_MUS': emgfile['NUMBER_OF_MUS'],
    'MUPULSES': emgfile['MUPULSES'],
    'IPTS': emgfile['IPTS'].values,
    'REF_SIGNAL': emgfile['REF_SIGNAL'].values,
    'ACCURACY': emgfile['ACCURACY'].values
}

# Save
sio.savemat('emgfile_cleaned.mat', matlab_data)
print("✓ Exported to MATLAB format: emgfile_cleaned.mat")
```

## Feedback and Contributions

If you develop useful analysis templates or find issues with the generated notebook, please:

1. Open an issue: [GitHub Issues](https://github.com/johanneskasser/hdsemg-pipe/issues)
2. Submit improvements: [Pull Requests](https://github.com/johanneskasser/hdsemg-pipe/pulls)
3. Share your analysis workflows with the community

---

**Generated by hdsemg-pipe** | [Documentation Home](../index.md)
