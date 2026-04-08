# MU Quality Review — Design Spec

**Issue:** [#129](https://github.com/johanneskasser/hdsemg-pipe/issues/129)  
**Date:** 2026-04-08  
**Branch:** `129-feature-mu-quality-review`  
**Status:** Approved, ready for implementation

---

## Problem

Step 9 (CoVISI Pre-Filter) uses only CoVISI as a quality criterion. SIL (Silhouette score) and PNR (Pulse-to-Noise Ratio) are equally important. There is also no post-decomposition step where the user can visually inspect MU plots and decide which files and MUs to forward.

---

## Solution

Replace `CoVISIPreFilterWizardWidget` (step 9) with `MUQualityReviewWizardWidget` — a new widget that:

- Lets the user select which files to forward (≥1 per group)
- Shows openhdemg plots (IDR, Discharge Times, MUAPs) for the selected file
- Shows a per-MU table with SIL / PNR / CoVISI scores and pass/fail indicators
- Lets the user toggle each metric on/off and adjust thresholds globally
- Lets the user override per-MU decisions (Keep / Filter / Auto)
- Writes filtered files to `decomposition_covisi_filtered/` on Proceed

Defaults: SIL ≥ 0.9, PNR ≥ 30 dB, CoVISI ≤ 30%. A MU is filtered if **any enabled** criterion fails (OR logic) unless overridden.

---

## Architecture

### Files to create

| File | Purpose |
|---|---|
| `hdsemg_pipe/actions/file_grouping.py` | Shared `get_group_key()` + `shorten_group_labels()` extracted from `FileQualitySelectionWizardWidget` |
| `hdsemg_pipe/widgets/wizard/MUQualityReviewWizardWidget.py` | New step 9 widget |

### Files to modify

| File | Change |
|---|---|
| `hdsemg_pipe/actions/decomposition_file.py` | Add `ReliabilityThresholds` dataclass, `compute_reliability()`, `filter_mus_by_reliability()`, `get_emgfile_for_plotting()` |
| `hdsemg_pipe/widgets/wizard/FileQualitySelectionWizardWidget.py` | Replace local `_get_group_key` / `_shorten_group_labels` with imports from `file_grouping.py` |
| `hdsemg_pipe/widgets/wizard/CoVISIPostValidationWizardWidget.py` | Add SIL + PNR columns to validation table |
| `hdsemg_pipe/main.py` | Swap `CoVISIPreFilterWizardWidget` → `MUQualityReviewWizardWidget` as step 9 |
| `hdsemg_pipe/controller/automatic_state_reconstruction.py` | Replace `_covisi_pre_filter()` with `_mu_quality_review()` that restores state from manifest |

### Files to retire

| File | Action |
|---|---|
| `hdsemg_pipe/widgets/wizard/CoVISIPreFilterWizardWidget.py` | Delete — fully replaced |

### Output contract (unchanged)

Step 9 continues to write to `decomposition_covisi_filtered/` (folder key `DECOMPOSITION_COVISI_FILTERED`). All downstream steps (10–13), MUedit, scd-edition, and state reconstruction keep working without changes to their folder lookups.

New addition: `mu_quality_selection.json` written to `analysis/` alongside the existing CoVISI report.

---

## `DecompositionFile` Extensions (`decomposition_file.py`)

### `ReliabilityThresholds` dataclass

```python
@dataclass
class ReliabilityThresholds:
    sil_min: float = 0.9
    pnr_min: float = 30.0
    covisi_max: float = 30.0
    sil_enabled: bool = True
    pnr_enabled: bool = True
    covisi_enabled: bool = True
```

Serialises to/from dict for manifest storage.

### `compute_reliability(thresholds: ReliabilityThresholds) -> pd.DataFrame`

Columns: `mu_index`, `port_index`, `sil`, `pnr`, `covisi`, `dr_mean`, `n_spikes`, `is_reliable`

- **JSON backend:** calls `emg.compute_sil(ipts[mu], mupulses[mu])` and `emg.compute_pnr(ipts[mu], mupulses[mu], fsamp)` per MU. Delegates CoVISI to the existing `_compute_covisi_json()`. `is_reliable` is computed against the passed thresholds with OR logic.
- **PKL backend:** same computation using the reconstructed `ipts_df` per port. Falls back to `nan` if IPTS is empty.
- **MAT backend:** returns empty DataFrame (MAT files only appear post-MUedit).
- `dr_mean` = `n_spikes / contraction_duration_s`. `n_spikes` = `len(mupulses[mu])`.

### `filter_mus_by_reliability(thresholds: ReliabilityThresholds, overrides: dict) -> DecompositionFile`

Same immutable pattern as `filter_mus_by_covisi`:
- `overrides`: `dict[(port_index, mu_index) → "Keep" | "Filter"]`
- A MU is removed if any enabled threshold fails AND no "Keep" override is set
- Returns a new `DecompositionFile` instance

### `get_emgfile_for_plotting() -> dict | None`

Returns the openhdemg emgfile dict (JSON backend) or a reconstructed one (PKL backend via `_pkl_to_emgfile_dict`) sorted with `tools.sort_mus()`. Used by the widget to feed `plot_idr`, `plot_mupulses`, and `sta` + `plot_muaps`. Returns `None` for MAT backend or when openhdemg is unavailable.

---

## `file_grouping.py`

Extracted verbatim from `FileQualitySelectionWizardWidget`:

```python
def get_group_key(filename: str) -> str: ...
def shorten_group_labels(group_keys: list[str]) -> dict[str, str]: ...
```

`FileQualitySelectionWizardWidget` switches its local `_get_group_key` / `_shorten_group_labels` to import these.

---

## `MUQualityReviewWizardWidget` Layout & Behaviour

### Layout

```
┌──────────────┬─────────────────────────────────────────────────────────────┐
│  LEFT PANEL  │  MAIN PANEL                                                 │
│  (file list) │                                                              │
│              │  ┌── Threshold bar ───────────────────────────────────────┐ │
│  [group hdr] │  │ ☑ SIL ≥ [0.90]  ☑ PNR ≥ [30] dB  ☑ CoVISI ≤ [30] % │ │
│  ☑ file_a   │  └───────────────────────────────────────────────────────┘ │
│  ☑ file_b   │                                                              │
│  ☐ file_c   │  ┌── Plot canvas (~65%) ──────┬── MU table (~35%) ────────┐ │
│              │  │                            │ # │SIL│PNR│CoVISI│Dec.   │ │
│  [group hdr] │  │  [IDR ▼]                  │ 0 │ ✓ │ ✓ │  ✓   │Auto▼ │ │
│  ☑ file_d   │  │                            │ 1 │ ✗ │ ✓ │  ✗   │Auto▼ │ │
│              │  │  matplotlib FigureCanvas   │ 2 │ ✓ │ ✗ │  ✓   │Keep▼ │ │
│              │  │                            │ 3 │ ✓ │ ✓ │  ✓   │Auto▼ │ │
│              │  └────────────────────────────┴──────────────────────────┘ │
│              │                                                              │
│              │  Footer: 2 of 18 MUs filtered · 37 of 412 total            │
├──────────────┴─────────────────────────────────────────────────────────────┤
│  [Proceed]  (enabled when ≥1 file per group selected)                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### File list (left panel)

- Groups via `file_grouping.get_group_key()` + `shorten_group_labels()`
- Same `_GroupHeader` + `_FileListItem` pattern as `FileQualitySelectionWizardWidget`
- Minimum 1 file per group must remain checked; if a group has exactly 1 file its checkbox is disabled
- Clicking a file row loads reliability data and plots into the main panel (lazy — computed on first click, cached)

### Threshold bar

- One `QCheckBox` toggle + `QDoubleSpinBox` per metric (SIL, PNR, CoVISI)
- Thresholds are **global** — changing any value immediately recolours the MU table for the currently displayed file and updates the footer counters for all files

### Plot panel (dominant ~65% width)

- Dropdown: `Discharge Rate (IDR)` / `Discharge Times` / `MUAPs`
- IDR → `plot.plot_idr(emgfile, munumber="all")`
- Discharge Times → `plot.plot_mupulses(emgfile, linewidths=0.8)`
- MUAPs → `sta()` (in a `QThread` worker with spinner) then `plot.plot_muaps()`
- Plots are rendered into an embedded `FigureCanvas`; switching the dropdown replaces the figure

### MU table (~35% width)

- Columns: `#`, `SIL`, `PNR`, `CoVISI`, `DR (pps)`, `Spikes`, `Decision`
- Row tint: pass = `Colors.GREEN_100`, fail = `Colors.RED_100`
- Per-cell chip: metric value + small coloured dot (green/red)
- Decision combo per row: `Auto / Keep / Filter`
- Table updates in real-time on any threshold or toggle change

### Proceed button

- Enabled when ≥1 file per group is checked
- If the user clicks Proceed without having visited all files, a confirmation dialog warns that unvisited files will use Auto decisions with current thresholds
- On confirm: `QThread` worker iterates kept files, calls `DecompositionFile.filter_mus_by_reliability(thresholds, overrides).save(dest)` for JSON/PKL, then calls `apply_covisi_filter_to_json` (or equivalent from `decomposition_export.py`) to write the corresponding MAT sibling; writes `mu_quality_selection.json`; marks step 9 complete
- The widget stores per-file overrides as `{str(mu_index): decision}` (JSON-serialisable). When passing to `filter_mus_by_reliability`, these are reconstructed as `{(0, int(k)): v}` for single-port JSON files and `{(port_idx, int(k)): v}` for PKL files

---

## Manifest Format (`analysis/mu_quality_selection.json`)

```json
{
  "version": 1,
  "thresholds": {
    "sil_min": 0.9,
    "pnr_min": 30.0,
    "covisi_max": 30.0,
    "sil_enabled": true,
    "pnr_enabled": true,
    "covisi_enabled": true
  },
  "kept_files": ["file_a.json", "file_b.json"],
  "mu_overrides": {
    "file_a.json": {"2": "Keep", "5": "Filter"},
    "file_b.json": {}
  }
}
```

`kept_files` stores basenames only. `mu_overrides` uses stringified `mu_index` keys (JSON requirement).

---

## State Reconstruction

`_covisi_pre_filter()` in `automatic_state_reconstruction.py` is replaced by `_mu_quality_review()`:

1. If `decomposition_covisi_filtered/` is empty → skip step 9
2. Look for `analysis/mu_quality_selection.json`
3. **Manifest found:** restore `kept_files` checkboxes + `mu_overrides` + `thresholds` into the widget; mark step 9 complete
4. **Manifest absent** (workfolder from old CoVISI pre-filter): mark step 9 complete with empty overrides — backward compatible

---

## `CoVISIPostValidationWizardWidget` Extension

Existing columns: `File`, `MU`, `CoVISI`, `Status`  
New columns: `File`, `MU`, `SIL`, `PNR`, `CoVISI`, `Status`

- SIL and PNR computed via `DecompositionFile.compute_reliability()` on the post-cleaning MAT files
- Pass/fail colouring per cell; thresholds are fixed defaults (display only, not user-configurable in post-validation)
- If openhdemg is unavailable or IPTS is absent from the MAT, SIL/PNR show `N/A`

---

## Verification Checklist

- [ ] Workfolder with 12 decomposed files → keep 5 → filtered folder has exactly 5 JSON+MAT+PKL triples
- [ ] Threshold change → MU table recolours immediately, footer counters update
- [ ] Per-MU override (Keep/Filter) → counter updates
- [ ] Plot dropdown: IDR, Discharge Times, MUAPs all render
- [ ] MUAPs STA computation runs in worker thread (UI stays responsive)
- [ ] ≥1 file per group enforced (last file in group cannot be unchecked)
- [ ] Proceed with unvisited files → confirmation dialog shown
- [ ] Apply filter → downstream steps operate on kept files only
- [ ] MUedit launch → only kept files visible
- [ ] scd-edition launch → only kept files and kept MUs visible
- [ ] Post-Validation shows SIL + PNR columns
- [ ] Reopen workfolder → reconstruction restores kept_files + overrides + thresholds
- [ ] Old workfolder (no manifest) → step 9 marked complete, no crash
