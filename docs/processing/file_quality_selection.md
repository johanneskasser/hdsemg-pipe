# File Quality Selection

The File Quality Selection step lets you review signal quality for each recorded file and decide which files to carry forward into further analysis. It appears after RMS Quality Analysis and before Crop to Region of Interest.

## Overview

In this step you can:

1. Browse all line-noise-cleaned recordings in the left panel
2. View the required vs. performed force path for each file in the plot
3. Check two quality metrics per file: tracking deviation and RMS noise level
4. Include or exclude individual files using checkboxes
5. Confirm your selection to filter the pipeline, or skip to keep all files

## Interface Components

### Left Panel — File List

The scrollable list on the left shows every `.mat` file in the `line_noise_cleaned/` folder.

Each row contains:

- **Status dot (●)** — colour-coded quality indicator, updated when you click the file
- **Checkbox** — check to include the file, uncheck to exclude it
- **Filename** — truncated display; hover for the full path

**Grouping toggle (top-right of the panel header)**

When enabled (default), files that share the same base name and differ only by a trailing increment number are grouped together under a section header.

Example:
```
BLOCK 1 PYRAMID            2/3
  ● ☑ ..._Block1_Pyramid_1.mat
  ● ☑ ..._Block1_Pyramid_2.mat
  ● ☐ ..._Block1_Pyramid_3.mat
```

The counter in the header shows `selected / total` and is colour-coded:

| State | Colour |
|-------|--------|
| All selected | Green |
| Partial | Orange |
| None selected | Red |

Click **Group** to toggle grouping on or off.

**Select All / Deselect All** — bulk-check buttons pinned below the list.

---

### Right Panel — Signal Plot

The matplotlib plot shows the force signals for the currently selected file:

- **Blue dashed line** — Required (requested) path
- **Orange solid line** — Performed path
- Both signals are normalised to [0, 1] for visual comparison

If a signal is unavailable, a grey placeholder message is shown and a warning strip appears below the plot.

---

### Quality Metrics Row

Below the plot, two flat columns show per-file quality statistics:

#### Tracking Deviation (NRMSE)

A 0–100 % score measuring how closely the participant followed the required force path.
Computed as:

```
score = max(0, (1 - RMSE / range(required)) × 100 %)
```

A score of 100 % means perfect tracking.

| Score | Label | Colour |
|-------|-------|--------|
| 90–100 % | Excellent | Green |
| 80–90 % | Good | Blue |
| 70–80 % | OK | Amber |
| 60–70 % | Troubled | Orange |
| < 60 % | Bad | Red |

Shown as `—` if either signal is missing.

#### RMS Noise Quality

The mean ± standard deviation RMS noise level in µV, aggregated across all channels and grids for the file.
Read from `{workfolder}/analysis/rms_analysis_report.csv` (generated in the RMS Quality Analysis step).

| RMS (µV) | Label | Colour |
|----------|-------|--------|
| ≤ 5 | Excellent | Green |
| 5–10 | Good | Blue |
| 10–15 | OK | Amber |
| 15–20 | Troubled | Orange |
| > 20 | Bad | Red |

Shown as `—` if the RMS report CSV is not available.

---

### Buttons

| Button | Action |
|--------|--------|
| **Skip** | Mark step as skipped; all files pass through unchanged |
| **Confirm Selection (N/M files)** | Apply the selection and advance to the next step |

The confirm button label updates in real time to show how many files are selected.

---

## Workflow

### 1. Review each file

Click a filename in the left panel. The plot and quality metrics update automatically for the selected file.

### 2. Uncheck files to exclude

Uncheck the checkbox next to any file you want to remove from further analysis (e.g. poor tracking, high noise). Unchecked files are not deleted — they remain on disk but are excluded from all subsequent steps.

### 3. Confirm or skip

- **Confirm** — The selected files are written to `global_state.line_noise_cleaned_files` and a `file_quality_selection.json` record is saved. All subsequent steps (Crop to ROI, Channel Selection, …) operate only on the confirmed subset.
- **Skip** — All files pass through without filtering. No selection record is written.

---

## State Reconstruction

When you reopen an existing workfolder, the step is restored automatically:

- If `{workfolder}/analysis/file_quality_selection.json` exists, the saved selection is re-applied and the step is marked **completed**.
- If the file does not exist (step was skipped or not yet reached), the step is marked **skipped**.

The JSON file stores the full paths of included and excluded files:

```json
{
  "selected": ["/path/to/file_1.mat", "/path/to/file_2.mat"],
  "excluded": ["/path/to/file_3.mat"]
}
```

---

## Output

| Location | Description |
|----------|-------------|
| `{workfolder}/analysis/file_quality_selection.json` | Saved include/exclude lists for state reconstruction |
| `global_state.line_noise_cleaned_files` | In-memory list passed to subsequent steps |

The files on disk in `line_noise_cleaned/` are **never modified or deleted** by this step.

---

## Skip Option

Click **Skip** if you do not need per-file quality gating. All line-noise-cleaned files are forwarded to subsequent steps without filtering, identical to the behaviour before this step existed.

---

## Troubleshooting

### RMS values show "—"

The RMS report CSV is generated by the **RMS Quality Analysis** step (Step 4). If that step was skipped, the CSV does not exist and RMS values cannot be shown. Tracking deviation scores are still available.

### Plot shows "No path signals available"

The selected file does not contain a required or performed path signal. This typically happens when:

- The file was not recorded with a force-tracking protocol
- Grid configuration did not assign path indices

The file can still be included or excluded based on other criteria.

### Grouping does not match expected blocks

The grouping algorithm strips the trailing `_N` number from each filename stem. If your filenames use a different suffix convention, use the **Group** toggle to switch to flat (ungrouped) view.
