# Settings

Access them via **Settings → Preferences**. Each topic has its own tab.

| Tab | What it controls |
|---|---|
| Channel Selection App | Installs and checks hdsemg-select |
| Work Folder | Where working directories are created |
| Line Noise Removal | 50 or 60 Hz and the filter method. Options that need MATLAB or Octave are greyed out when those are missing. |
| openhdemg | Path to the environment used for plots |
| MUEdit | MUedit folder and how it is launched |
| MU Metrics | Backend for SIL, PNR and CoVISI: `motor_unit_toolbox` (default) or `openhdemg` |
| Logging | Log level. Switch to DEBUG before you report a bug. |
| Updates | Update checks and forks |

## Update checks

On startup the app looks for new versions of scd-edition and MUedit (latest commit on GitHub) and openhdemg (PyPI). The check runs in the background, stays quiet when it fails, and tells you once per new version. To follow a fork instead, enter its URL and branch in the Updates tab; the change applies on the next start. The last seen commits are kept in `~/.hdsemg_pipe/update_cache.json`.
