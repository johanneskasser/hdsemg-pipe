# Database Export (SQLite)

After completing the HD-sEMG processing pipeline, the **DB Export Notebook** writes all motor unit properties into a central SQLite database (`mu_study.db`). All subjects share one database, enabling cross-subject SQL queries and GLMM analysis without manually concatenating CSV files.

## Architecture Overview

```
hdsemg-pipe pipeline (per subject)
        │
        ▼
hdsemg_analysis.ipynb        ← exploratory plots, QC visualizations
01_export_to_db.ipynb        ← NO plots, writes to mu_study.db
        │
        ▼
    mu_study.db (SQLite)     ← one file for ALL subjects
        │
        ▼
02_analyze_from_db.ipynb     ← cross-subject stats, GLMM, figures
DBeaver                      ← SQL browser for the database
```

Both notebooks are **automatically generated** into your workfolder when you click **"Export Analysis Notebook"** in Step 12.

---

## Database Schema

The database has **6 tables** arranged in a hierarchy:

```
subjects (1) ──> sessions (n) ──> recordings (n) ──> motor_units (n)

tracking_clusters (1) ──> mu_tracking (n) <── motor_units (1)
```

### Table: `subjects`

One row per participant. Stores anthropometrics and **randomization order** (`first_training_mode`).

| Column | Type | Description |
|--------|------|-------------|
| `subject_id` | TEXT PK | `'S01'`, `'S02'`, … |
| `age` | INTEGER | |
| `sex` | TEXT | `'M'` or `'F'` |
| `height_m`, `body_mass_kg` | REAL | |
| `body_fat_pct`, `muscle_mass_pct` | REAL | |
| `leg_muscle_mass_right_kg`, `_left_kg` | REAL | |
| `dominant_leg` | TEXT | `'R'` or `'L'` |
| `first_training_mode` | TEXT | **`'CON'` or `'EXZ'`** – randomization key |
| `notes` | TEXT | |

### Table: `sessions`

One row per measurement day.

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | INTEGER PK | Auto-increment |
| `subject_id` | TEXT FK | → `subjects` |
| `session_date` | TEXT | `'YYYYMMDD'` |
| `mvc_pre_nm`, `mvc_post_nm` | REAL | Max voluntary contraction (Nm) |
| `borg_cr10_post_con`, `borg_cr10_post_exz` | REAL | RPE after each intervention |
| `doms_score_pre` | INTEGER | |

### Table: `recordings`

One row per recording (Block × Task × Muscle). Replaces `recording_level_master.csv`.

| Column | Type | Description |
|--------|------|-------------|
| `recording_id` | INTEGER PK | Auto-increment |
| `session_id` | INTEGER FK | → `sessions` |
| `block_number` | INTEGER | 1 – 6 |
| `block_label` | TEXT | `'Baseline'`, `'Pre_Intervention'`, … |
| `training_mode_before` | TEXT | **`'none'`, `'CON'`, `'EXZ'`, `'washout'`** |
| `task_type` | TEXT | `'Trapezoid'` or `'Pyramid'` |
| `muscle` | TEXT | `'VL'` or `'VM'` |
| `n_mus_total` … `n_mus_after_duplicate_removal` | INTEGER | Pool counts |
| `cst_plateau_mean_pps`, `_sd_pps` | REAL | Cumulative spike train in plateau |
| `emg_rms_uv`, `emg_mdf_hz`, `emg_mnf_hz` | REAL | Global EMG metrics |
| `spatial_entropy`, `barycenter_x`, `_y` | REAL | Spatial features |
| `ft_rmse_pct_mvc`, `ft_r2`, `ft_mean_force_pct_mvc` | REAL | Force tracking |
| `rms_noise_mean_uv`, `_sd_uv`, `n_dead_channels` | REAL / INTEGER | Signal quality |

### Table: `motor_units`

One row per MU per recording. Replaces `mu_level_master.csv`.

| Column | Type | Description |
|--------|------|-------------|
| `mu_id` | INTEGER PK | Auto-increment |
| `recording_id` | INTEGER FK | → `recordings` |
| `mu_idx` | INTEGER | MU index within the recording |
| `sil` | REAL | Silhouette Index |
| `cov_isi_pct` | REAL | CoV ISI over full contraction (%) |
| `n_spikes` | INTEGER | |
| `is_duplicate` | BOOLEAN | Within-recording duplicate flag |
| `manually_cleaned` | BOOLEAN | Always `TRUE` (after MUedit) |
| `qc_passed` | BOOLEAN | Set by QC cell (SIL + CoV ISI thresholds) |
| **Trapezoid plateau** (NULL for Pyramid) | | |
| `mean_dr_plateau_hz` | REAL | Mean DR in plateau only |
| `peak_dr_hz`, `dr_at_rec_hz`, `dr_at_derec_hz` | REAL | |
| `rt_pct_mvc`, `drt_pct_mvc` | REAL | Recruitment / derecruitment (%MVC) |
| `cov_isi_plateau_pct`, `n_spikes_plateau` | REAL / INTEGER | Plateau-specific CoV ISI |
| **Pyramid** (NULL for Trapezoid) | | |
| `mean_dr_pyramid_hz`, `peak_dr_pyramid_hz` | REAL | |
| `rt_pct_pyramid_mvc`, `drt_pct_pyramid_mvc` | REAL | |
| `delta_f_hz` | REAL | Delta F (persistent inward currents) |
| `delta_f_pair_mu` | TEXT | e.g. `'anchor_MU3_test_MU7'` |
| `brace_slope` | REAL | Brace method slope |
| `mucv_ms` | REAL | Motor unit conduction velocity |

### Tables: `tracking_clusters` + `mu_tracking`

MU identity across blocks.

```sql
-- tracking_clusters: one row per cluster (group of matched MUs)
tracking_scope: '4_block'  -- blocks 2,3,4,5
               '6_block'  -- all 6 blocks

-- mu_tracking: junction table  motor_units <-> tracking_clusters
tracking_xcc: cross-correlation value of the match
```

---

## SQL Views

Six predefined views simplify analysis:

| View | Description |
|------|-------------|
| `v_mu_full` | All MUs with all metadata (master DataFrame) |
| `v_mu_tracked_4block` | Only 4-block tracked MUs |
| `v_mu_tracked_6block` | Only 6-block tracked MUs |
| `v_recording_summary` | Recordings with subject metadata |
| `v_tracking_summary` | Cluster counts per subject / scope |
| `v_mu_crossover` | Post-training MUs for CON vs EXZ comparison |

---

## Quickstart

### Step 1: Initialize the Database

Run once before adding the first subject:

```bash
python db_setup/init_db.py --db-path /path/to/mu_study.db --verify
```

Expected output:

```
✓ Schema initialized in mu_study.db
✓ Table: subjects
✓ Table: sessions
...
✓ All tables and views created successfully.
```

The `--verify` flag checks that all 6 tables and 6 views were created.

### Step 2: Export the Notebook

In hdsemg-pipe, complete the pipeline and click **"Export Analysis Notebook"** in Step 12.
This generates `01_export_to_db.ipynb` in your workfolder.

### Step 3: Run 01_export_to_db.ipynb

Open the notebook in Jupyter:

```bash
cd /path/to/workfolder
jupyter notebook 01_export_to_db.ipynb
```

**Edit Cell 2 (Config)** for each subject:

```python
SUBJECT_ID = "S01"           # Change per subject
SESSION_DATE = "20260202"    # YYYYMMDD
FIRST_TRAINING_MODE = "CON"  # From your randomization list
DB_PATH = WORKFOLDER.parent / "mu_study.db"  # Adjust if needed
```

Then run all cells. The notebook:

1. Connects to `mu_study.db` (creates it if missing)
2. Inserts or updates the subject and session
3. Parses the protocol file and maps files to blocks
4. Loops over all recordings → inserts MUs into DB
5. Runs plateau selection (reads `plateau_markers.json` or interactive)
6. Sets QC flags (SIL < 0.85 or CoV ISI > 30%)
7. Detects within-recording duplicates
8. Runs 4-block and 6-block MU tracking
9. Updates recording-level pool counts and CST metrics
10. Prints a validation summary

### Step 4: Repeat for Each Subject

Run `01_export_to_db.ipynb` in each subject's workfolder. All data accumulates in the same `mu_study.db`.

```
S01/workfolder/01_export_to_db.ipynb  →  mu_study.db (S01 added)
S02/workfolder/01_export_to_db.ipynb  →  mu_study.db (S02 added)
S03/workfolder/01_export_to_db.ipynb  →  mu_study.db (S03 added)
```

### Step 5: Analyze

```python
from db_connector import DatabaseConnection

db = DatabaseConnection("mu_study.db")
df_mu = db.get_mu_full()        # All MUs, all subjects
df_glmm = db.export_for_glmm("Trapezoid")
db.close()
```

---

## Connecting DBeaver

DBeaver (free) provides a visual SQL browser for the database.

1. Download [DBeaver Community](https://dbeaver.io)
2. **Database → New Database Connection → SQLite**
3. Set path to `mu_study.db`
4. Click **Test Connection → Finish**
5. In the navigator: expand **Tables** and **Views**
6. Right-click schema → **View Diagram** for ER diagram

Useful DBeaver queries:

```sql
-- Check what's in the DB
SELECT subject_id, COUNT(*) AS n_mus
FROM v_mu_full
GROUP BY subject_id;

-- CON vs EXZ: mean DR from plateau
SELECT training_mode_before, muscle,
       AVG(mean_dr_plateau_hz) AS mean_dr, COUNT(*) AS n
FROM v_mu_full
WHERE task_type = 'Trapezoid' AND qc_passed = 1 AND is_duplicate = 0
  AND training_mode_before IN ('CON','EXZ')
GROUP BY training_mode_before, muscle;
```

---

## Extending the Schema

### Adding a New Column

**1. Add the column to the SQL schema file:**

```sql
-- db_setup/schema/001_initial_schema.sql
CREATE TABLE IF NOT EXISTS motor_units (
    ...
    mucv_ms     REAL,
    my_new_col  REAL,   -- add here
    ...
);
```

**2. Add it to `db_connector.py` in `insert_motor_unit()`:**

```python
# In the INSERT statement, add to both the column list and VALUES list:
sql = """
    INSERT INTO motor_units (
        ..., mucv_ms, my_new_col
    ) VALUES (
        ..., :mucv_ms, :my_new_col
    )
    ON CONFLICT(recording_id, mu_idx) DO UPDATE SET
        ...
        my_new_col = excluded.my_new_col
"""

# Also add to the `cols` list to get a None default:
cols = [..., "mucv_ms", "my_new_col"]
```

**3. Update the view** (if the column should appear in `v_mu_full`):

```sql
-- db_setup/schema/002_views.sql
-- Add to the SELECT in v_mu_full:
mu.mucv_ms,
mu.my_new_col   -- add here
```

**4. Re-initialize** (safe – drops and recreates views, tables use IF NOT EXISTS):

```bash
# Drop and recreate views only (tables keep their data)
python -c "
from db_setup.db_connector import DatabaseConnection
db = DatabaseConnection('mu_study.db')
db._conn.executescript(open('db_setup/schema/002_views.sql').read())
db._conn.commit()
print('Views updated')
db.close()
"
```

!!! warning "Existing data"
    `CREATE TABLE IF NOT EXISTS` will not add new columns to an existing table.
    For existing databases with data, use `ALTER TABLE` instead:

    ```sql
    ALTER TABLE motor_units ADD COLUMN my_new_col REAL;
    ```

    Run this directly in DBeaver or via Python:

    ```python
    db._conn.execute("ALTER TABLE motor_units ADD COLUMN my_new_col REAL")
    db._conn.commit()
    ```

### Adding a New Table

**1. Add `CREATE TABLE` to `001_initial_schema.sql`**

**2. Add insert/read methods to `db_connector.py`**

**3. Add the table to `_verify_schema()` in `init_db.py`**

**4. Re-run** `init_db.py` (new table will be created; existing tables unchanged):

```bash
python db_setup/init_db.py --db-path mu_study.db --verify
```

### Adding a New View

**1. Add `CREATE VIEW IF NOT EXISTS` to `002_views.sql`**

**2. Drop and recreate views** (views are stateless – no data is lost):

```python
from db_setup.db_connector import DatabaseConnection

db = DatabaseConnection("mu_study.db")
# Drop the old view
db._conn.execute("DROP VIEW IF EXISTS v_my_new_view")
# Re-run the views SQL
sql = open("db_setup/schema/002_views.sql").read()
db._conn.executescript(sql)
db._conn.commit()
db.close()
```

---

## `db_connector.py` API Reference

### Class: `DatabaseConnection`

```python
from db_connector import DatabaseConnection

db = DatabaseConnection("mu_study.db")
```

#### Insert operations

| Method | Description |
|--------|-------------|
| `insert_subject(data)` | Upsert subject. Returns `subject_id`. |
| `insert_session(data)` | Upsert session. Returns `session_id`. |
| `insert_recording(data)` | Upsert recording. Returns `recording_id`. |
| `insert_motor_unit(data)` | Upsert MU. Returns `mu_id`. |
| `insert_tracking_cluster(data)` | Insert cluster. Returns `cluster_id`. |
| `insert_mu_tracking(mu_id, cluster_id, xcc)` | Link MU to cluster. |

All insert methods use **upsert** (`ON CONFLICT DO UPDATE`) – safe to re-run.

#### Update operations

| Method | Description |
|--------|-------------|
| `update_qc_flags(sil_threshold, cov_isi_threshold)` | Mark failed MUs as `qc_passed=FALSE`. |
| `update_recording_metrics(recording_id, data)` | Update pool counts, CST, force metrics. |

#### Read operations (return DataFrames)

| Method | Description |
|--------|-------------|
| `query(sql, params)` | Execute raw SQL → DataFrame. |
| `get_mu_full()` | Full `v_mu_full` view. |
| `get_mu_tracked(scope)` | `'4_block'` or `'6_block'` tracked MUs. |
| `get_recording_summary()` | `v_recording_summary` view. |
| `export_for_glmm(task_type)` | Clean DataFrame for `statsmodels.mixedlm`. |
| `get_subjects()` | All subjects. |
| `get_sessions(subject_id)` | Sessions, optionally filtered. |
| `get_mu_ids_for_recording(recording_id)` | `mu_id` + `mu_idx` for a recording. |
| `validate(subject_id)` | Print validation summary to console. |

#### Usage as context manager

```python
with DatabaseConnection("mu_study.db") as db:
    df = db.get_mu_full()
    # connection closed automatically
```

---

## Example Queries

See [db_setup/schema/003_example_queries.sql](../../db_setup/schema/003_example_queries.sql) for all 9 predefined queries.

```sql
-- Q1: Mean DR from trapezoid plateau, CON vs EXZ
SELECT r.training_mode_before,
       AVG(mu.mean_dr_plateau_hz) AS mean_dr_hz,
       COUNT(*) AS n_mus
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
WHERE r.task_type = 'Trapezoid'
  AND r.training_mode_before IN ('CON', 'EXZ')
  AND mu.qc_passed = TRUE AND mu.is_duplicate = FALSE
GROUP BY r.training_mode_before;

-- Q2: Washout effectiveness
SELECT r.block_label, AVG(mu.mean_dr_plateau_hz) AS mean_dr
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
WHERE r.block_label IN ('Pre_Intervention', 'Post_Washout')
GROUP BY r.block_label;

-- GLMM export via Python
df = db.export_for_glmm("Trapezoid")
import statsmodels.formula.api as smf
model = smf.mixedlm(
    "mean_dr_plateau_hz ~ training_mode_before * block_label + muscle",
    df, groups=df["subject_id"]
)
result = model.fit()
print(result.summary())
```

---

## File Structure

```
hdsemg-pipe/
├── db_setup/
│   ├── schema/
│   │   ├── 001_initial_schema.sql    # CREATE TABLE statements
│   │   ├── 002_views.sql             # 6 predefined views
│   │   └── 003_example_queries.sql   # 9 research queries
│   ├── db_connector.py               # DatabaseConnection class
│   ├── init_db.py                    # CLI init script
│   └── requirements.txt
│
└── {workfolder}/                     # Per-subject workfolder
    ├── 01_export_to_db.ipynb         # Generated by hdsemg-pipe
    ├── hdsemg_analysis.ipynb         # Full analysis notebook (unchanged)
    ├── workfolder_analysis_helper.py # Helper module
    └── plateau_markers.json          # Plateau definitions (saved after first run)

mu_study.db                           # Central database (all subjects)
```

---

## Troubleshooting

### `OperationalError: table already exists`

This should not occur since all SQL uses `IF NOT EXISTS`. If it does, check for manually created tables without this clause.

### Subject inserted twice with different `session_date`

The upsert key for `sessions` is `(subject_id, session_date)`. Two sessions on different dates are stored as two separate rows. This is correct behaviour for longitudinal studies.

### Tracking found 0 clusters

Possible causes:

- XCC threshold too strict – try lowering `XCC_TRACKING_THRESHOLD` from `0.8` to `0.7`
- Too few spikes per MU for reliable cross-correlation
- Block mapping incorrect – verify `block_number` assignment in the protocol cell

### `qc_passed = FALSE` for all MUs

Check SIL and CoV ISI values before applying thresholds:

```python
df_check = db.query("""
    SELECT AVG(sil) as mean_sil, AVG(cov_isi_pct) as mean_cov
    FROM motor_units mu
    JOIN recordings r ON mu.recording_id = r.recording_id
    JOIN sessions sess ON r.session_id = sess.session_id
    WHERE sess.subject_id = ?
""", [SUBJECT_ID])
print(df_check)
```

---

## Related Documentation

- [Analysis Notebook Export](analysis_notebook.md) – The `hdsemg_analysis.ipynb` notebook
- [CoVISI Filtering](covisi_filtering.md) – Quality filtering before export
- [MUEdit Export Workflow](muedit_export_workflow.md) – Manual cleaning step
- [Developer Guide](../developer.md)
