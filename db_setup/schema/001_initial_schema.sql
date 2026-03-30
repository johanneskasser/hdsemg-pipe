-- ============================================================================
-- HD-sEMG Motor Unit Study Database Schema
-- ============================================================================
-- 6 tables for crossover study design (CON vs EXZ)
-- Run via: python db_setup/init_db.py --db-path mu_study.db
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ============================================================================
-- subjects: One row per participant (anthropometrics, randomization)
-- ============================================================================
CREATE TABLE IF NOT EXISTS subjects (
    subject_id              TEXT PRIMARY KEY,           -- 'S01', 'S02', ...
    age                     INTEGER,
    sex                     TEXT CHECK(sex IN ('M', 'F')),
    height_m                REAL,
    body_mass_kg            REAL,
    body_fat_pct            REAL,
    muscle_mass_pct         REAL,
    leg_muscle_mass_right_kg REAL,
    leg_muscle_mass_left_kg  REAL,
    dominant_leg            TEXT CHECK(dominant_leg IN ('R', 'L')),
    first_training_mode     TEXT CHECK(first_training_mode IN ('CON', 'EXZ')),  -- randomization
    notes                   TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- sessions: One row per measurement day
-- ============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id              TEXT NOT NULL REFERENCES subjects(subject_id),
    session_date            TEXT NOT NULL,              -- 'YYYYMMDD'
    session_type            TEXT,                       -- e.g. 'Day 2 - Intervention'
    mvc_pre_nm              REAL,
    mvc_post_nm             REAL,
    borg_cr10_post_con      REAL,
    borg_cr10_post_exz      REAL,
    doms_score_pre          INTEGER,
    -- Contrex isokinetic dynamometer setup (from arrival_setup, use_from_ref fields)
    contrex_sitzwinkel_deg          REAL,               -- seat angle (degrees)
    contrex_sitzboden_laenge_mm     REAL,               -- seat depth (mm)
    contrex_lever_height_mm         REAL,               -- lever arm height (mm)
    contrex_lever_seat_position_mm  REAL,               -- lever arm seat position (mm)
    -- Electrode grid configuration (set once per session in arrival_setup)
    -- 64-channel grids (HD04MM1305 or HD08MM1305, 5×13 layout)
    vm_grid_64_type         TEXT,                       -- e.g. 'HD08MM1305'
    vm_grid_64_orientation  INTEGER CHECK(vm_grid_64_orientation IN (0, 180)),
    vl_grid_64_type         TEXT,
    vl_grid_64_orientation  INTEGER CHECK(vl_grid_64_orientation IN (0, 180)),
    -- 32-channel grids (HD10MM0804 or HD05MM0804, 4×8 layout)
    vm_grid_32_type         TEXT,                       -- e.g. 'HD10MM0804'
    vm_grid_32_orientation  INTEGER CHECK(vm_grid_32_orientation IN (0, 180)),
    vl_grid_32_type         TEXT,
    vl_grid_32_orientation  INTEGER CHECK(vl_grid_32_orientation IN (0, 180)),
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subject_id, session_date)
);

-- ============================================================================
-- recordings: One row per recording (Block x Task x Muscle)
-- Replaces recording_level_master.csv
-- ============================================================================
CREATE TABLE IF NOT EXISTS recordings (
    recording_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL REFERENCES sessions(session_id),
    block_number            INTEGER NOT NULL CHECK(block_number BETWEEN 1 AND 6),
    block_label             TEXT NOT NULL,              -- 'Baseline', 'Pre_Intervention', etc.
    training_mode_before    TEXT CHECK(training_mode_before IN ('none', 'CON', 'EXZ', 'washout')),
    task_type               TEXT NOT NULL CHECK(task_type IN ('Trapezoid', 'Pyramid')),
    muscle                  TEXT NOT NULL CHECK(muscle IN ('VL', 'VM')),
    -- MU Pool counts
    n_mus_total             INTEGER,
    n_mus_after_qc          INTEGER,
    n_mus_after_cleaning    INTEGER,
    n_mus_after_duplicate_removal INTEGER,
    -- Neural Drive (Trapezoid only)
    cst_plateau_mean_pps    REAL,
    cst_plateau_sd_pps      REAL,
    -- Global EMG
    emg_rms_uv              REAL,
    emg_mdf_hz              REAL,
    emg_mnf_hz              REAL,
    -- Spatial features
    spatial_entropy         REAL,
    barycenter_x            REAL,
    barycenter_y            REAL,
    -- Force tracking performance
    ft_rmse_pct_mvc         REAL,
    ft_r2                   REAL,
    ft_mean_force_pct_mvc   REAL,
    -- Signal quality
    rms_noise_mean_uv       REAL,
    rms_noise_sd_uv         REAL,
    n_dead_channels         INTEGER,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, block_number, task_type, muscle)
);

-- ============================================================================
-- motor_units: One row per MU per recording
-- Replaces mu_level_master.csv
-- ============================================================================
CREATE TABLE IF NOT EXISTS motor_units (
    mu_id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id            INTEGER NOT NULL REFERENCES recordings(recording_id),
    mu_idx                  INTEGER NOT NULL,           -- index within the recording
    -- Quality metrics
    sil                     REAL,                      -- Silhouette Index
    cov_isi_pct             REAL,                      -- Coefficient of Variation of ISI (%)
    n_spikes                INTEGER,
    is_duplicate            BOOLEAN DEFAULT FALSE,
    manually_cleaned        BOOLEAN DEFAULT TRUE,
    qc_passed               BOOLEAN DEFAULT TRUE,
    -- Trapezoid plateau metrics (NULL for Pyramid recordings)
    mean_dr_plateau_hz      REAL,                      -- Mean discharge rate in plateau
    peak_dr_hz              REAL,                      -- Peak discharge rate
    dr_at_rec_hz            REAL,                      -- DR at recruitment
    dr_at_derec_hz          REAL,                      -- DR at derecruitment
    rt_pct_mvc              REAL,                      -- Recruitment threshold (%MVC)
    drt_pct_mvc             REAL,                      -- Derecruitment threshold (%MVC)
    cov_isi_plateau_pct     REAL,                      -- CoV ISI in plateau window only
    n_spikes_plateau        INTEGER,                   -- Spike count in plateau
    -- Pyramid metrics (NULL for Trapezoid recordings)
    mean_dr_pyramid_hz      REAL,
    peak_dr_pyramid_hz      REAL,
    rt_pct_pyramid_mvc      REAL,
    drt_pct_pyramid_mvc     REAL,
    delta_f_hz              REAL,                      -- Delta F (persistent inward currents)
    delta_f_pair_mu         TEXT,                      -- e.g. 'anchor_MU3_test_MU7'
    brace_slope             REAL,                      -- Brace method slope
    -- Motor unit conduction velocity
    mucv_ms                 REAL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(recording_id, mu_idx)
);

-- ============================================================================
-- tracking_clusters: Groups of MUs tracked across blocks
-- ============================================================================
CREATE TABLE IF NOT EXISTS tracking_clusters (
    cluster_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL REFERENCES sessions(session_id),
    muscle                  TEXT NOT NULL,
    task_type               TEXT NOT NULL,
    tracking_scope          TEXT NOT NULL CHECK(tracking_scope IN ('4_block', '6_block')),
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- mu_tracking: Junction table - links MUs to tracking clusters (n:m)
-- ============================================================================
CREATE TABLE IF NOT EXISTS mu_tracking (
    mu_id                   INTEGER NOT NULL REFERENCES motor_units(mu_id),
    cluster_id              INTEGER NOT NULL REFERENCES tracking_clusters(cluster_id),
    tracking_xcc            REAL,                      -- Cross-correlation value
    PRIMARY KEY(mu_id, cluster_id)
);
