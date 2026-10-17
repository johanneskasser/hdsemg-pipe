# Workflow

Opening a file or folder creates a working directory named after it, inside the work folder you chose in the settings. Each step reads from the previous step's folder and writes to its own.

| Step | What happens | Optional | Output |
|---|---|---|---|
| 1 | Open files | | `00_original_files` |
| 2 | Grid association | yes | `01_associated_grids` |
| 3 | Line noise removal | yes | `02_line_noise_cleaned` |
| 4 | RMS quality analysis | yes | `07_analysis` |
| 5 | File quality selection | yes | `07_analysis` |
| 6 | Crop to region of interest | yes | `03_cropped_signal` |
| 7 | Channel selection | | `04_channelselection` |
| 8 | Decomposition results | | `05_decomposition_auto` |
| 9 | MU quality review | | `05.1_decomposition_covisi_filtered` |
| 10 | Remove duplicate MUs | yes | `05.2_decomposition_removed_duplicates` |
| 11 | Manual cleaning | | `05.3_decomposition_muedit` or `05.3_decomposition_scd_edition` |
| 12 | CoVISI post-validation | | report next to the cleaned files |
| 13 | Final results | | `06_decomposition_results` |

See [the steps](steps.md) for details.

## Skipping

Optional steps can be skipped. The app asks for a short reason and stores it in a `.skip_marker.json` in that step's folder, so you can still tell later why a folder is empty.

## Picking up where you stopped

Choose **Open Existing Workfolder** in the menu, or use the folder button. The app looks at what is on disk, marks the finished steps and jumps to the first open one. Progress is also written to `hdsemg-pipe-process.log` in the root of the working directory. Heavy views, such as the motor unit review, only load once you open their step.
