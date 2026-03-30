"""
HD-sEMG Motor Unit Study - Database Connector

Central Python module for all database interactions.
Used by notebooks (01_export_to_db.ipynb) and analysis scripts.

Usage:
    from db_connector import DatabaseConnection

    db = DatabaseConnection("./mu_study.db")
    db.insert_subject({'subject_id': 'S01', 'age': 25, ...})
    session_id = db.insert_session({'subject_id': 'S01', 'session_date': '20260202', ...})
    db.close()
"""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd


class DatabaseConnection:
    """
    Manages SQLite database connections and CRUD operations for the MU study.

    The database stores data for all subjects in a normalized schema:
        subjects -> sessions -> recordings -> motor_units
        tracking_clusters <-> mu_tracking <-> motor_units

    Args:
        db_path: Path to the .db file (created if it doesn't exist)
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self):
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.commit()

    def init_schema(self, schema_dir: Optional[str] = None):
        """
        Initialize the database schema from SQL files.

        Runs 001_initial_schema.sql and 002_views.sql in order.
        Safe to call on an existing DB (uses IF NOT EXISTS).

        Args:
            schema_dir: Path to directory containing schema SQL files.
                        Defaults to db_setup/schema/ relative to this file.
        """
        if schema_dir is None:
            schema_dir = Path(__file__).parent / "schema"
        else:
            schema_dir = Path(schema_dir)

        schema_files = [
            schema_dir / "001_initial_schema.sql",
            schema_dir / "002_views.sql",
        ]

        for sql_file in schema_files:
            if not sql_file.exists():
                raise FileNotFoundError(f"Schema file not found: {sql_file}")
            sql = sql_file.read_text(encoding="utf-8")
            self._conn.executescript(sql)

        self._conn.commit()
        print(f"✓ Schema initialized in {self.db_path}")

    # =========================================================================
    # INSERT operations
    # =========================================================================

    def insert_subject(self, data: Dict) -> str:
        """
        Insert or update a subject. Safe to call multiple times (upsert).

        Args:
            data: Dict with keys matching subjects table columns.
                  Required: 'subject_id'

        Returns:
            subject_id
        """
        sql = """
            INSERT INTO subjects (
                subject_id, age, sex, height_m, body_mass_kg,
                body_fat_pct, muscle_mass_pct,
                leg_muscle_mass_right_kg, leg_muscle_mass_left_kg,
                dominant_leg, first_training_mode, notes
            ) VALUES (
                :subject_id, :age, :sex, :height_m, :body_mass_kg,
                :body_fat_pct, :muscle_mass_pct,
                :leg_muscle_mass_right_kg, :leg_muscle_mass_left_kg,
                :dominant_leg, :first_training_mode, :notes
            )
            ON CONFLICT(subject_id) DO UPDATE SET
                age = excluded.age,
                sex = excluded.sex,
                height_m = excluded.height_m,
                body_mass_kg = excluded.body_mass_kg,
                body_fat_pct = excluded.body_fat_pct,
                muscle_mass_pct = excluded.muscle_mass_pct,
                leg_muscle_mass_right_kg = excluded.leg_muscle_mass_right_kg,
                leg_muscle_mass_left_kg = excluded.leg_muscle_mass_left_kg,
                dominant_leg = excluded.dominant_leg,
                first_training_mode = excluded.first_training_mode,
                notes = excluded.notes
        """
        defaults = {
            "subject_id": None, "age": None, "sex": None,
            "height_m": None, "body_mass_kg": None,
            "body_fat_pct": None, "muscle_mass_pct": None,
            "leg_muscle_mass_right_kg": None, "leg_muscle_mass_left_kg": None,
            "dominant_leg": None, "first_training_mode": None, "notes": None,
        }
        defaults.update(data)
        self._conn.execute(sql, defaults)
        self._conn.commit()
        return data["subject_id"]

    def insert_session(self, data: Dict) -> int:
        """
        Insert or update a session.

        Args:
            data: Dict with keys matching sessions table columns.
                  Required: 'subject_id', 'session_date'

        Returns:
            session_id (int)
        """
        sql = """
            INSERT INTO sessions (
                subject_id, session_date, mvc_pre_nm, mvc_post_nm,
                borg_cr10_post_con, borg_cr10_post_exz, doms_score_pre
            ) VALUES (
                :subject_id, :session_date, :mvc_pre_nm, :mvc_post_nm,
                :borg_cr10_post_con, :borg_cr10_post_exz, :doms_score_pre
            )
            ON CONFLICT(subject_id, session_date) DO UPDATE SET
                mvc_pre_nm = excluded.mvc_pre_nm,
                mvc_post_nm = excluded.mvc_post_nm,
                borg_cr10_post_con = excluded.borg_cr10_post_con,
                borg_cr10_post_exz = excluded.borg_cr10_post_exz,
                doms_score_pre = excluded.doms_score_pre
        """
        defaults = {
            "subject_id": None, "session_date": None,
            "mvc_pre_nm": None, "mvc_post_nm": None,
            "borg_cr10_post_con": None, "borg_cr10_post_exz": None,
            "doms_score_pre": None,
        }
        defaults.update(data)
        self._conn.execute(sql, defaults)
        self._conn.commit()

        cursor = self._conn.execute(
            "SELECT session_id FROM sessions WHERE subject_id = ? AND session_date = ?",
            (data["subject_id"], data["session_date"])
        )
        return cursor.fetchone()["session_id"]

    def insert_recording(self, data: Dict) -> int:
        """
        Insert or update a recording.

        Args:
            data: Dict with keys matching recordings table columns.
                  Required: 'session_id', 'block_number', 'task_type', 'muscle'

        Returns:
            recording_id (int)
        """
        sql = """
            INSERT INTO recordings (
                session_id, block_number, block_label, training_mode_before,
                task_type, muscle,
                n_mus_total, n_mus_after_qc, n_mus_after_cleaning,
                n_mus_after_duplicate_removal,
                cst_plateau_mean_pps, cst_plateau_sd_pps,
                emg_rms_uv, emg_mdf_hz, emg_mnf_hz,
                spatial_entropy, barycenter_x, barycenter_y,
                ft_rmse_pct_mvc, ft_r2, ft_mean_force_pct_mvc,
                rms_noise_mean_uv, rms_noise_sd_uv, n_dead_channels
            ) VALUES (
                :session_id, :block_number, :block_label, :training_mode_before,
                :task_type, :muscle,
                :n_mus_total, :n_mus_after_qc, :n_mus_after_cleaning,
                :n_mus_after_duplicate_removal,
                :cst_plateau_mean_pps, :cst_plateau_sd_pps,
                :emg_rms_uv, :emg_mdf_hz, :emg_mnf_hz,
                :spatial_entropy, :barycenter_x, :barycenter_y,
                :ft_rmse_pct_mvc, :ft_r2, :ft_mean_force_pct_mvc,
                :rms_noise_mean_uv, :rms_noise_sd_uv, :n_dead_channels
            )
            ON CONFLICT(session_id, block_number, task_type, muscle) DO UPDATE SET
                block_label = excluded.block_label,
                training_mode_before = excluded.training_mode_before,
                n_mus_total = excluded.n_mus_total
        """
        cols = [
            "session_id", "block_number", "block_label", "training_mode_before",
            "task_type", "muscle",
            "n_mus_total", "n_mus_after_qc", "n_mus_after_cleaning",
            "n_mus_after_duplicate_removal",
            "cst_plateau_mean_pps", "cst_plateau_sd_pps",
            "emg_rms_uv", "emg_mdf_hz", "emg_mnf_hz",
            "spatial_entropy", "barycenter_x", "barycenter_y",
            "ft_rmse_pct_mvc", "ft_r2", "ft_mean_force_pct_mvc",
            "rms_noise_mean_uv", "rms_noise_sd_uv", "n_dead_channels",
        ]
        defaults = {c: None for c in cols}
        defaults.update(data)
        self._conn.execute(sql, defaults)
        self._conn.commit()

        cursor = self._conn.execute(
            """SELECT recording_id FROM recordings
               WHERE session_id = ? AND block_number = ? AND task_type = ? AND muscle = ?""",
            (data["session_id"], data["block_number"], data["task_type"], data["muscle"])
        )
        return cursor.fetchone()["recording_id"]

    def insert_motor_unit(self, data: Dict) -> int:
        """
        Insert or update a motor unit.

        Args:
            data: Dict with keys matching motor_units table columns.
                  Required: 'recording_id', 'mu_idx'

        Returns:
            mu_id (int)
        """
        sql = """
            INSERT INTO motor_units (
                recording_id, mu_idx,
                sil, cov_isi_pct, n_spikes,
                is_duplicate, manually_cleaned, qc_passed,
                mean_dr_plateau_hz, peak_dr_hz, dr_at_rec_hz, dr_at_derec_hz,
                rt_pct_mvc, drt_pct_mvc, cov_isi_plateau_pct, n_spikes_plateau,
                mean_dr_pyramid_hz, peak_dr_pyramid_hz,
                rt_pct_pyramid_mvc, drt_pct_pyramid_mvc,
                delta_f_hz, delta_f_pair_mu, brace_slope,
                mucv_ms
            ) VALUES (
                :recording_id, :mu_idx,
                :sil, :cov_isi_pct, :n_spikes,
                :is_duplicate, :manually_cleaned, :qc_passed,
                :mean_dr_plateau_hz, :peak_dr_hz, :dr_at_rec_hz, :dr_at_derec_hz,
                :rt_pct_mvc, :drt_pct_mvc, :cov_isi_plateau_pct, :n_spikes_plateau,
                :mean_dr_pyramid_hz, :peak_dr_pyramid_hz,
                :rt_pct_pyramid_mvc, :drt_pct_pyramid_mvc,
                :delta_f_hz, :delta_f_pair_mu, :brace_slope,
                :mucv_ms
            )
            ON CONFLICT(recording_id, mu_idx) DO UPDATE SET
                sil = excluded.sil,
                cov_isi_pct = excluded.cov_isi_pct,
                n_spikes = excluded.n_spikes,
                is_duplicate = excluded.is_duplicate,
                manually_cleaned = excluded.manually_cleaned,
                qc_passed = excluded.qc_passed,
                mean_dr_plateau_hz = excluded.mean_dr_plateau_hz,
                peak_dr_hz = excluded.peak_dr_hz,
                dr_at_rec_hz = excluded.dr_at_rec_hz,
                dr_at_derec_hz = excluded.dr_at_derec_hz,
                rt_pct_mvc = excluded.rt_pct_mvc,
                drt_pct_mvc = excluded.drt_pct_mvc,
                cov_isi_plateau_pct = excluded.cov_isi_plateau_pct,
                n_spikes_plateau = excluded.n_spikes_plateau,
                mean_dr_pyramid_hz = excluded.mean_dr_pyramid_hz,
                peak_dr_pyramid_hz = excluded.peak_dr_pyramid_hz,
                rt_pct_pyramid_mvc = excluded.rt_pct_pyramid_mvc,
                drt_pct_pyramid_mvc = excluded.drt_pct_pyramid_mvc,
                delta_f_hz = excluded.delta_f_hz,
                delta_f_pair_mu = excluded.delta_f_pair_mu,
                brace_slope = excluded.brace_slope,
                mucv_ms = excluded.mucv_ms
        """
        cols = [
            "recording_id", "mu_idx",
            "sil", "cov_isi_pct", "n_spikes",
            "is_duplicate", "manually_cleaned", "qc_passed",
            "mean_dr_plateau_hz", "peak_dr_hz", "dr_at_rec_hz", "dr_at_derec_hz",
            "rt_pct_mvc", "drt_pct_mvc", "cov_isi_plateau_pct", "n_spikes_plateau",
            "mean_dr_pyramid_hz", "peak_dr_pyramid_hz",
            "rt_pct_pyramid_mvc", "drt_pct_pyramid_mvc",
            "delta_f_hz", "delta_f_pair_mu", "brace_slope",
            "mucv_ms",
        ]
        defaults = {c: None for c in cols}
        defaults["is_duplicate"] = False
        defaults["manually_cleaned"] = True
        defaults["qc_passed"] = True
        defaults.update(data)
        self._conn.execute(sql, defaults)
        self._conn.commit()

        cursor = self._conn.execute(
            "SELECT mu_id FROM motor_units WHERE recording_id = ? AND mu_idx = ?",
            (data["recording_id"], data["mu_idx"])
        )
        return cursor.fetchone()["mu_id"]

    def insert_tracking_cluster(self, data: Dict) -> int:
        """
        Insert a tracking cluster and return its cluster_id.

        Args:
            data: Dict with 'session_id', 'muscle', 'task_type', 'tracking_scope'

        Returns:
            cluster_id (int)
        """
        sql = """
            INSERT INTO tracking_clusters (session_id, muscle, task_type, tracking_scope)
            VALUES (:session_id, :muscle, :task_type, :tracking_scope)
        """
        cursor = self._conn.execute(sql, data)
        self._conn.commit()
        return cursor.lastrowid

    def insert_mu_tracking(self, mu_id: int, cluster_id: int, tracking_xcc: Optional[float] = None):
        """
        Link a motor unit to a tracking cluster.

        Args:
            mu_id: motor_units.mu_id
            cluster_id: tracking_clusters.cluster_id
            tracking_xcc: Cross-correlation value
        """
        sql = """
            INSERT OR IGNORE INTO mu_tracking (mu_id, cluster_id, tracking_xcc)
            VALUES (?, ?, ?)
        """
        self._conn.execute(sql, (mu_id, cluster_id, tracking_xcc))
        self._conn.commit()

    # =========================================================================
    # UPDATE operations
    # =========================================================================

    def update_qc_flags(self, sil_threshold: float = 0.85, cov_isi_threshold: float = 30.0):
        """
        Set qc_passed = FALSE for MUs below SIL or above CoV ISI threshold.

        Args:
            sil_threshold: Minimum SIL value (default 0.85)
            cov_isi_threshold: Maximum CoV ISI in % (default 30.0)
        """
        sql = """
            UPDATE motor_units SET qc_passed = FALSE
            WHERE (sil IS NOT NULL AND sil < ?)
               OR (cov_isi_pct IS NOT NULL AND cov_isi_pct > ?)
        """
        cursor = self._conn.execute(sql, (sil_threshold, cov_isi_threshold))
        self._conn.commit()
        print(f"✓ QC flags updated: {cursor.rowcount} MUs marked as qc_passed=FALSE")

    def update_recording_metrics(self, recording_id: int, data: Dict):
        """
        Update pool counts and derived metrics for a recording.

        Args:
            recording_id: recordings.recording_id
            data: Dict with column-value pairs to update
        """
        if not data:
            return
        set_clause = ", ".join(f"{col} = :{col}" for col in data)
        sql = f"UPDATE recordings SET {set_clause} WHERE recording_id = :recording_id"
        data["recording_id"] = recording_id
        self._conn.execute(sql, data)
        self._conn.commit()

    # =========================================================================
    # READ operations (returns pandas DataFrames)
    # =========================================================================

    def query(self, sql: str, params: Optional[list] = None) -> pd.DataFrame:
        """
        Execute raw SQL and return result as DataFrame.

        Args:
            sql: SQL query string
            params: Optional parameter list for parameterized queries

        Returns:
            pandas DataFrame
        """
        if params is None:
            params = []
        return pd.read_sql_query(sql, self._conn, params=params)

    def get_mu_full(self) -> pd.DataFrame:
        """Return v_mu_full view - all MUs with all metadata (all subjects)."""
        return self.query("SELECT * FROM v_mu_full")

    def get_mu_tracked(self, scope: str = "4_block") -> pd.DataFrame:
        """
        Return tracked MUs for a given scope.

        Args:
            scope: '4_block' or '6_block'

        Returns:
            DataFrame from v_mu_tracked_4block or v_mu_tracked_6block
        """
        if scope == "4_block":
            return self.query("SELECT * FROM v_mu_tracked_4block")
        elif scope == "6_block":
            return self.query("SELECT * FROM v_mu_tracked_6block")
        else:
            raise ValueError(f"Unknown scope: {scope}. Use '4_block' or '6_block'.")

    def get_recording_summary(self) -> pd.DataFrame:
        """Return v_recording_summary - all recordings with subject metadata."""
        return self.query("SELECT * FROM v_recording_summary")

    def export_for_glmm(self, task_type: str = "Trapezoid") -> pd.DataFrame:
        """
        Export clean DataFrame for GLMM analysis (statsmodels mixedlm).

        Args:
            task_type: 'Trapezoid' or 'Pyramid'

        Returns:
            DataFrame with key columns for GLMM (no duplicates, qc_passed only)
        """
        sql = """
            SELECT
                s.subject_id, s.first_training_mode,
                r.block_number, r.block_label, r.training_mode_before,
                r.task_type, r.muscle,
                mu.mu_id, mu.mu_idx, mu.sil, mu.cov_isi_pct,
                mu.mean_dr_plateau_hz, mu.rt_pct_mvc, mu.drt_pct_mvc,
                mu.cov_isi_plateau_pct, mu.delta_f_hz, mu.brace_slope
            FROM motor_units mu
            JOIN recordings r ON mu.recording_id = r.recording_id
            JOIN sessions sess ON r.session_id = sess.session_id
            JOIN subjects s ON sess.subject_id = s.subject_id
            WHERE mu.qc_passed = TRUE
              AND mu.is_duplicate = FALSE
              AND r.task_type = ?
            ORDER BY s.subject_id, r.block_number, r.muscle, mu.mu_idx
        """
        return self.query(sql, [task_type])

    def get_subjects(self) -> pd.DataFrame:
        """Return all subjects."""
        return self.query("SELECT * FROM subjects")

    def get_sessions(self, subject_id: Optional[str] = None) -> pd.DataFrame:
        """Return sessions, optionally filtered by subject."""
        if subject_id:
            return self.query("SELECT * FROM sessions WHERE subject_id = ?", [subject_id])
        return self.query("SELECT * FROM sessions")

    def get_recording_id(self, session_id: int, block_number: int,
                         task_type: str, muscle: str) -> Optional[int]:
        """Look up recording_id by natural key."""
        sql = """SELECT recording_id FROM recordings
                 WHERE session_id = ? AND block_number = ? AND task_type = ? AND muscle = ?"""
        df = self.query(sql, [session_id, block_number, task_type, muscle])
        if len(df) == 0:
            return None
        return int(df.iloc[0]["recording_id"])

    def get_mu_ids_for_recording(self, recording_id: int) -> pd.DataFrame:
        """Return mu_id and mu_idx for all MUs in a recording."""
        return self.query(
            "SELECT mu_id, mu_idx FROM motor_units WHERE recording_id = ?",
            [recording_id]
        )

    # =========================================================================
    # Utility
    # =========================================================================

    def validate(self, subject_id: Optional[str] = None) -> None:
        """
        Print a validation summary.

        Args:
            subject_id: If given, show stats only for that subject.
        """
        filter_clause = f"WHERE s.subject_id = '{subject_id}'" if subject_id else ""

        df = self.query(f"""
            SELECT
                s.subject_id,
                r.block_label,
                r.task_type,
                r.muscle,
                COUNT(mu.mu_id) AS n_mus,
                SUM(CASE WHEN mu.qc_passed = 1 THEN 1 ELSE 0 END) AS n_qc_passed,
                SUM(CASE WHEN mu.is_duplicate = 1 THEN 1 ELSE 0 END) AS n_duplicates
            FROM motor_units mu
            JOIN recordings r ON mu.recording_id = r.recording_id
            JOIN sessions sess ON r.session_id = sess.session_id
            JOIN subjects s ON sess.subject_id = s.subject_id
            {filter_clause}
            GROUP BY s.subject_id, r.block_label, r.task_type, r.muscle
            ORDER BY s.subject_id, r.block_label, r.task_type, r.muscle
        """)

        total = self.query(f"""
            SELECT COUNT(*) AS total_mus FROM motor_units mu
            JOIN recordings r ON mu.recording_id = r.recording_id
            JOIN sessions sess ON r.session_id = sess.session_id
            JOIN subjects s ON sess.subject_id = s.subject_id
            {filter_clause}
        """).iloc[0]["total_mus"]

        label = f"Subject {subject_id}" if subject_id else "All subjects"
        print(f"\n{'='*60}")
        print(f"DB Validation: {label}")
        print(f"{'='*60}")
        print(f"Total MUs in DB: {total}")
        print(f"\nBreakdown by block/task/muscle:")
        print(df.to_string(index=False))
        print(f"{'='*60}\n")

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self):
        return f"DatabaseConnection(db_path='{self.db_path}')"
