# Analysis notebooks

Step 13, the **Export Analysis Notebook**, generates three files in the working directory's root:

- `workfolder_analysis_helper.py`, a small helper module
- `hdsemg_analysis.ipynb`, plots and summaries of the cleaned units
- `01_export_to_db.ipynb`, which writes the units into a SQLite database

You need `nbformat` for the export and `openhdemg` to run the notebooks.

## One database for all subjects

Create the database once:

```bash
python db_setup/init_db.py --db-path mu_study.db --verify
```

Then run `01_export_to_db.ipynb` in each subject's working directory. Everything lands in the same file, in the tables `subjects`, `sessions`, `recordings`, `motor_units`, `tracking_clusters` and `mu_tracking`, plus a few views. Open it with any SQLite client, or query it from Python or R for cross-subject statistics. The schema lives in `db_setup/schema`.
