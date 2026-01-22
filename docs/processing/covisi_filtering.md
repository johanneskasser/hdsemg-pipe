# CoVISI Filtering

CoVISI (Coefficient of Variation of Interspike Interval) filtering provides automated quality assessment and filtering of motor units based on physiological plausibility. This feature helps identify and optionally remove non-physiological motor units before and after manual cleaning in MUedit.

## Introduction

### What is CoVISI?

The Coefficient of Variation of Interspike Interval (CoVISI) is a measure of firing regularity for motor units. It is calculated as:

```
CoVISI = (Standard Deviation of ISI / Mean ISI) x 100%
```

Where ISI (Interspike Interval) is the time between consecutive motor unit discharges.

### Why Use CoVISI for Quality Assessment?

Motor units exhibit characteristic firing patterns based on physiological constraints. Physiologically plausible motor units typically show:

- Regular firing patterns during sustained contractions
- Moderate variability in interspike intervals
- CoVISI values below 30%

Motor units with high CoVISI values (>30%) may indicate:

- Decomposition errors (false positive detections)
- Merged motor units
- Missed discharges creating artificial variability
- Non-physiological artifacts

### Literature Reference

The 30% CoVISI threshold is based on established literature:

> **Taleshi et al. (2025)**, *Journal of Applied Physiology* 138: 559-570
>
> CoVISI < 30% indicates physiologically plausible motor units.

## Workflow Position

CoVISI filtering is integrated at two points in the hdsemg-pipe workflow:

| Step | Name | Position | Purpose |
|------|------|----------|---------|
| **Step 9** | CoVISI Pre-Filtering | After Multi-Grid Configuration, before MUedit | Automated removal of non-physiological MUs before manual cleaning |
| **Step 11** | CoVISI Post-Validation | After MUedit cleaning, before Final Results | Quality assurance after manual cleaning |

```
Multi-Grid Configuration (Step 8)
         |
         v
CoVISI Pre-Filtering (Step 9)  <-- Optional automated filtering
         |
         v
MUedit Cleaning (Step 10)
         |
         v
CoVISI Post-Validation (Step 11)  <-- Quality assurance checkpoint
         |
         v
Final Results (Step 12)
```

## CoVISI Pre-Filtering (Step 9)

### Purpose

The pre-filtering step allows automated removal of motor units with high CoVISI values before manual cleaning in MUedit. This can:

- Reduce the number of motor units requiring manual review
- Remove clearly non-physiological decomposition artifacts
- Speed up the manual cleaning workflow

**Note:** Pre-filtering is optional. You can skip this step and proceed with all motor units to MUedit.

### User Interface

#### Analysis Method Selection

The pre-filtering step offers two analysis methods:

| Method | Description | Best For |
|--------|-------------|----------|
| **Auto (Rec/Derec)** | Uses recruitment and derecruitment phases automatically | Quick analysis, contractions without clear steady-state |
| **Manual (Steady-State)** | User specifies the steady-state phase boundaries | Trapezoidal contractions with a plateau phase |

##### Auto Mode (Recommended for most cases)

- Uses `event_="rec_derec"` in openhdemg
- Analyzes CoVISI based on firing patterns at recruitment and derecruitment
- No user input required beyond clicking "Analyze CoVISI"
- Fast and automated

##### Manual Mode (Steady-State)

- Uses `event_="rec_derec_steady"` in openhdemg
- User specifies **Start** and **End** times (in seconds) for the steady-state phase
- More accurate for trapezoidal contractions with a defined plateau
- CoVISI from steady-state is scientifically preferred for quality assessment

**When to use Manual Mode:**

- Trapezoidal contractions with a clear force plateau
- When you need the most accurate CoVISI values
- For research requiring steady-state CoVISI specifically
- When comparing to published literature using steady-state CoVISI

**Steady-State Time Selection:**

There are two ways to specify the steady-state region:

1. **Manual Entry**: Enter start and end times directly in the spinboxes
2. **Visual Selection**: Click "Select from Signal..." to open an interactive dialog

##### Visual Selection Dialog

The "Select from Signal..." button opens a dialog that displays the reference signal (force/torque path) from your recordings. This allows you to:

- **See the actual contraction profile**: Visualize the force trace from your MUedit MAT files
- **Select by dragging**: Click and drag on the plot to select the plateau region
- **Two-click selection**: Click once to set the start, click again to set the end
- **Fine-tune with spinboxes**: Adjust the selection precisely using time inputs
- **Multiple file overlay**: If multiple files exist, all reference signals are displayed for comparison

**Steady-State Time Selection Tips:**

- The application automatically suggests default values based on contraction duration
- Default: middle 60% of the contraction (20%-80% of duration)
- Adjust based on your specific force profile
- Ensure the steady-state region has stable force output
- Minimum recommended duration: 0.5 seconds

#### Analysis Controls

| Component | Description |
|-----------|-------------|
| **Analysis Method** | Radio buttons to select Auto or Manual mode |
| **Start/End Spinboxes** | Time inputs for steady-state boundaries (Manual mode only) |
| **Select from Signal** | Opens visual dialog to select steady-state from reference signal (Manual mode only) |
| **Analyze CoVISI** | Compute CoVISI values for all motor units in all decomposition files |
| **Threshold Spinner** | Adjust the CoVISI threshold (default: 30%, range: 5-100%) |
| **Preview Label** | Shows how many MUs will be filtered at the current threshold |

#### Results Table

The results table displays CoVISI analysis for all motor units:

| Column | Description |
|--------|-------------|
| **File** | Source decomposition file name |
| **MU Index** | Motor unit index (0-based) |
| **CoVISI (%)** | Computed CoVISI value |
| **Quality** | Quality category based on CoVISI |
| **Status** | Whether MU will be kept or filtered |

#### Color Coding

The CoVISI column uses color coding for quick visual assessment:

| Color | CoVISI Range | Quality | Interpretation |
|-------|--------------|---------|----------------|
| Green | <= 30% | Good | Physiologically plausible |
| Yellow | 30-50% | Marginal | Borderline, may need review |
| Red | > 50% | Poor | Likely non-physiological |

#### Quality Categories

Motor units are categorized based on their CoVISI values:

| Category | CoVISI Range | Description |
|----------|--------------|-------------|
| **Excellent** | <= 20% | Very regular firing, high confidence |
| **Good** | 20-30% | Regular firing, physiologically plausible |
| **Marginal** | 30-50% | Irregular firing, may be valid or artifact |
| **Poor** | > 50% | Highly irregular, likely non-physiological |

### Actions

#### Analyze CoVISI

1. Click **Analyze CoVISI** to compute CoVISI values
2. Wait for computation to complete (progress bar shows status)
3. Review results in the table
4. Adjust threshold if needed using the spinner
5. Preview shows how many MUs will be filtered

#### Apply Filter

Click **Apply Filter** to:

1. Create filtered JSON files (`*_covisi_filtered.json`) containing only MUs below threshold
2. Re-export filtered files to MUedit format (`*_covisi_filtered_muedit.mat`)
3. Save filtering report (`covisi_pre_filter_report.json`)
4. Proceed to the next step

#### Skip Filtering

Click **Skip Filtering** to:

1. Proceed with all motor units (no filtering applied)
2. Save a report indicating filtering was skipped
3. Continue to MUedit with original files

#### Export to CSV

Click **Export to CSV** to save analysis results:

- Opens a file dialog (default location: `analysis/` folder)
- Exports all table data including CoVISI values and quality categories
- Useful for external analysis or documentation

#### Expand Table

Click **Expand Table** to open results in a larger, resizable window for detailed review.

### Output Files

Files created in `decomposition_auto/` folder:

| File | Description |
|------|-------------|
| `*_covisi_filtered.json` | Filtered decomposition files (MUs below threshold only) |
| `*_covisi_filtered_muedit.mat` | MUedit export of filtered files |
| `covisi_pre_filter_report.json` | Filtering statistics and CoVISI values for all MUs |

## CoVISI Post-Validation (Step 11)

### Purpose

The post-validation step provides quality assurance after manual cleaning in MUedit by:

- Computing CoVISI for cleaned motor units
- Comparing pre-cleaning and post-cleaning values
- Showing improvement metrics from manual cleaning
- Warning about MUs still exceeding the threshold

### User Interface

#### Summary Panel

Displays overall validation statistics:

- Files validated
- Total MUs before/after cleaning
- Average CoVISI improvement

#### Warning Panel

Appears when motor units still exceed the threshold after cleaning:

- Shows count of failing MUs
- Explains available options
- Highlights in yellow for visibility

#### Results Table

Comparison table showing pre/post cleaning values:

| Column | Description |
|--------|-------------|
| **File** | Source file name |
| **MU Index** | Motor unit index |
| **Pre-CoVISI (%)** | CoVISI before MUedit cleaning |
| **Post-CoVISI (%)** | CoVISI after MUedit cleaning |
| **Improvement** | Percentage improvement (positive = better) |
| **Status** | Pass (below threshold) or Exceeds (above threshold) |

### Actions

#### Run Validation

Click **Run Validation** to:

1. Load edited MAT files from MUedit
2. Compute post-cleaning CoVISI values
3. Compare with pre-cleaning values
4. Display results and improvement metrics

#### Accept All & Continue

Click **Accept All & Continue** to:

1. Accept all motor units (including those exceeding threshold)
2. Save validation report with "accepted_all" action
3. Proceed to Final Results step

Use this when:
- All MUs are acceptable despite some high CoVISI values
- High CoVISI is expected for specific motor units
- You've manually verified the quality

#### Filter Failing MUs

Click **Filter Failing MUs** to:

1. Mark MUs exceeding threshold for exclusion
2. Save report with list of MUs to exclude
3. Proceed to Final Results (excluded MUs will be filtered during final conversion)

Use this when:
- Some MUs still show non-physiological behavior after cleaning
- You want to automatically remove high-CoVISI units

#### Return to MUedit

Click **Return to MUedit** to:

1. Go back to the MUedit cleaning step
2. Allow further manual cleaning of problematic MUs
3. Re-run validation after additional cleaning

Use this when:
- Some MUs need additional manual cleaning
- Cleaning wasn't thorough enough initially

### Output File

| File | Location | Description |
|------|----------|-------------|
| `covisi_post_validation_report.json` | `decomposition_auto/` | Validation results including comparisons and action taken |

## CSV Export

Both pre-filtering and post-validation steps support exporting results to CSV files.

### Export Location

Files are saved to the `{workfolder}/analysis/` folder by default. The folder is created automatically if it doesn't exist.

### Pre-Filter Export Format

| Column | Description |
|--------|-------------|
| File | Decomposition file name |
| MU Index | Motor unit index (0-based) |
| CoVISI (%) | Computed CoVISI value |
| Quality | Quality category (Excellent/Good/Marginal/Poor) |
| Status | Keep or Filter |
| Threshold (%) | Applied threshold value |

### Post-Validation Export Format

| Column | Description |
|--------|-------------|
| File | Source file name |
| MU Index | Motor unit index |
| Pre-CoVISI (%) | CoVISI before cleaning |
| Post-CoVISI (%) | CoVISI after cleaning |
| Improvement (%) | Percentage improvement |
| Status | Pass or Exceeds |
| Threshold (%) | Applied threshold value |

## Technical Notes

### CoVISI Computation

The application uses openhdemg's `compute_covisi()` function with different parameters depending on the selected analysis method:

#### Auto Mode (Rec/Derec)

```python
covisi_df = emg.compute_covisi(
    emgfile=emgfile,
    n_firings_RecDerec=4,
    event_="rec_derec",
    start_steady=0,  # Dummy values, not used
    end_steady=1,
)
```

Key parameters:

- **`event_="rec_derec"`**: Uses recruitment/derecruitment periods only
- **`n_firings_RecDerec=4`**: Number of firings at recruitment/derecruitment to consider
- No user interaction required

#### Manual Mode (Steady-State)

```python
covisi_df = emg.compute_covisi(
    emgfile=emgfile,
    n_firings_RecDerec=4,
    event_="rec_derec_steady",
    start_steady=start_samples,  # User-specified start time (in samples)
    end_steady=end_samples,      # User-specified end time (in samples)
)
```

Key parameters:

- **`event_="rec_derec_steady"`**: Includes steady-state phase analysis
- **`start_steady` / `end_steady`**: Boundaries of steady-state region (converted from seconds to samples internally)
- Returns additional `COVisi_steady` column

#### Which CoVISI Value is Used for Filtering?

- **`covisi_all`** is always used for filtering decisions
- This represents CoVISI over the entire contraction
- Even in Manual mode, `covisi_all` is used (not `covisi_steady`) to ensure consistency
- The steady-state analysis provides additional insight but doesn't change the filtering logic

### Direct Computation from Discharge Times

For edited MAT files without full emgfile structure, CoVISI is computed directly:

```python
# Compute ISI (in samples)
isi = np.diff(discharge_times)

# Compute CoVISI = (std / mean) * 100
mean_isi = np.mean(isi)
std_isi = np.std(isi)
covisi = (std_isi / mean_isi) * 100.0
```

### Threshold Configuration

- **Default threshold**: 30% (based on literature)
- **Adjustable range**: 5% to 100%
- **Step size**: 5%

The threshold can be adjusted in real-time during pre-filtering to see how many MUs would be affected.

### Dependencies

- **openhdemg**: Required for CoVISI computation
- **h5py**: Required for reading MUedit MAT files (HDF5/MATLAB v7.3 format)
- **numpy/pandas**: Data processing

## Best Practices

### Pre-Filtering

1. **Run analysis first**: Always analyze CoVISI before deciding to filter
2. **Review the distribution**: Check if most MUs are below threshold
3. **Adjust threshold carefully**: Lowering threshold removes more MUs
4. **Consider skipping**: If most MUs are good, manual cleaning may be sufficient
5. **Document decisions**: Export CSV for records

### Post-Validation

1. **Always validate**: Run validation after MUedit cleaning to assess improvement
2. **Check improvement metrics**: Good cleaning should show positive improvement
3. **Investigate failures**: MUs still exceeding threshold may need more cleaning
4. **Accept thoughtfully**: High CoVISI isn't always bad (some MUs naturally have higher variability)

### General Guidelines

- CoVISI is a guideline, not an absolute rule
- Some legitimate motor units may have higher CoVISI
- Combine CoVISI assessment with visual inspection in MUedit
- Document your filtering decisions for reproducibility

## Troubleshooting

### Common Issues

1. **"openhdemg library not available"**
   - Ensure openhdemg is installed in your Python environment
   - Check the virtual environment path in settings

2. **No decomposition files found**
   - Verify the decomposition step completed successfully
   - Check that JSON files exist in `decomposition_auto/` folder

3. **Computation fails for specific files**
   - File may have no motor units
   - File structure may be incompatible
   - Check application logs for details

4. **All MUs filtered out**
   - Threshold may be too strict
   - Decomposition quality may be poor
   - Consider re-running decomposition with different parameters

### Validation Issues

1. **No edited files found**
   - Ensure MUedit cleaning was completed and files saved
   - Check for `*_edited.mat` files in `decomposition_auto/`

2. **Cannot match edited to original files**
   - File naming may have changed
   - Check that base names match between JSON and MAT files

3. **CoVISI increased after cleaning**
   - Cleaning may have removed stabilizing discharges
   - Review the specific MUs in MUedit
   - Consider if the cleaning approach was appropriate

## See Also

- [Decomposition Results](decomposition_results.md) - Overview of decomposition workflow
- [MUEdit Export Workflow](muedit_export_workflow.md) - Manual cleaning in MUedit
- [openhdemg Documentation](https://www.giacomovalli.com/openhdemg/) - Library documentation
