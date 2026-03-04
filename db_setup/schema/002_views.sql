-- ============================================================================
-- HD-sEMG Motor Unit Study - Database Views
-- ============================================================================
-- Predefined flat views for analysis notebooks and DBeaver inspection
-- Run after 001_initial_schema.sql
-- ============================================================================

-- ============================================================================
-- v_mu_full: Master view - all MUs with all metadata (replaces mu_level_master.csv)
-- JOIN: motor_units -> recordings -> sessions -> subjects
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_mu_full AS
SELECT
    -- Subject
    s.subject_id,
    s.age,
    s.sex,
    s.height_m,
    s.body_mass_kg,
    s.first_training_mode,
    s.dominant_leg,
    -- Session
    sess.session_id,
    sess.session_date,
    sess.session_type,
    sess.mvc_pre_nm,
    sess.mvc_post_nm,
    sess.borg_cr10_post_con,
    sess.borg_cr10_post_exz,
    sess.doms_score_pre,
    -- Contrex setup
    sess.contrex_sitzwinkel_deg,
    sess.contrex_sitzboden_laenge_mm,
    sess.contrex_lever_height_mm,
    sess.contrex_lever_seat_position_mm,
    -- Electrode grids
    sess.vm_grid_64_type,
    sess.vm_grid_64_orientation,
    sess.vm_grid_32_type,
    sess.vm_grid_32_orientation,
    sess.vl_grid_64_type,
    sess.vl_grid_64_orientation,
    sess.vl_grid_32_type,
    sess.vl_grid_32_orientation,
    -- Recording
    r.recording_id,
    r.block_number,
    r.block_label,
    r.training_mode_before,
    r.task_type,
    r.muscle,
    r.n_mus_total,
    r.n_mus_after_qc,
    r.n_mus_after_cleaning,
    r.n_mus_after_duplicate_removal,
    r.cst_plateau_mean_pps,
    r.cst_plateau_sd_pps,
    r.emg_rms_uv,
    r.emg_mdf_hz,
    r.emg_mnf_hz,
    r.ft_rmse_pct_mvc,
    r.ft_r2,
    r.ft_mean_force_pct_mvc,
    -- Motor unit
    mu.mu_id,
    mu.mu_idx,
    mu.sil,
    mu.cov_isi_pct,
    mu.n_spikes,
    mu.is_duplicate,
    mu.manually_cleaned,
    mu.qc_passed,
    -- Trapezoid plateau
    mu.mean_dr_plateau_hz,
    mu.peak_dr_hz,
    mu.dr_at_rec_hz,
    mu.dr_at_derec_hz,
    mu.rt_pct_mvc,
    mu.drt_pct_mvc,
    mu.cov_isi_plateau_pct,
    mu.n_spikes_plateau,
    -- Pyramid
    mu.mean_dr_pyramid_hz,
    mu.peak_dr_pyramid_hz,
    mu.rt_pct_pyramid_mvc,
    mu.drt_pct_pyramid_mvc,
    mu.delta_f_hz,
    mu.delta_f_pair_mu,
    mu.brace_slope,
    -- MUCV
    mu.mucv_ms
FROM motor_units mu
JOIN recordings r   ON mu.recording_id = r.recording_id
JOIN sessions sess  ON r.session_id = sess.session_id
JOIN subjects s     ON sess.subject_id = s.subject_id;

-- ============================================================================
-- v_mu_tracked_4block: Only MUs tracked across 4 blocks (2,3,4,5)
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_mu_tracked_4block AS
SELECT
    vf.*,
    mt.cluster_id,
    mt.tracking_xcc
FROM v_mu_full vf
JOIN mu_tracking mt          ON vf.mu_id = mt.mu_id
JOIN tracking_clusters tc    ON mt.cluster_id = tc.cluster_id
WHERE tc.tracking_scope = '4_block';

-- ============================================================================
-- v_mu_tracked_6block: Only MUs tracked across all 6 blocks
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_mu_tracked_6block AS
SELECT
    vf.*,
    mt.cluster_id,
    mt.tracking_xcc
FROM v_mu_full vf
JOIN mu_tracking mt          ON vf.mu_id = mt.mu_id
JOIN tracking_clusters tc    ON mt.cluster_id = tc.cluster_id
WHERE tc.tracking_scope = '6_block';

-- ============================================================================
-- v_recording_summary: Flat view of all recordings with subject metadata
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_recording_summary AS
SELECT
    s.subject_id,
    s.first_training_mode,
    sess.session_date,
    r.*
FROM recordings r
JOIN sessions sess  ON r.session_id = sess.session_id
JOIN subjects s     ON sess.subject_id = s.subject_id;

-- ============================================================================
-- v_tracking_summary: How many MUs per cluster, per subject, per scope
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_tracking_summary AS
SELECT
    s.subject_id,
    tc.tracking_scope,
    tc.muscle,
    tc.task_type,
    tc.cluster_id,
    COUNT(mt.mu_id) AS n_mus_in_cluster
FROM tracking_clusters tc
JOIN mu_tracking mt     ON tc.cluster_id = mt.cluster_id
JOIN sessions sess      ON tc.session_id = sess.session_id
JOIN subjects s         ON sess.subject_id = s.subject_id
GROUP BY s.subject_id, tc.tracking_scope, tc.muscle, tc.task_type, tc.cluster_id;

-- ============================================================================
-- v_mu_crossover: Crossover comparison - POST-training MUs with their condition
-- Key view for CON vs EXZ effects (regardless of randomization order)
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_mu_crossover AS
SELECT
    s.subject_id,
    s.first_training_mode,
    sess.session_date,
    sess.doms_score_pre,
    r.training_mode_before AS training_type,
    r.block_number,
    r.block_label,
    r.muscle,
    r.task_type,
    -- Grid configuration for this muscle (64-ch and 32-ch)
    CASE r.muscle
        WHEN 'VM' THEN sess.vm_grid_64_type
        WHEN 'VL' THEN sess.vl_grid_64_type
    END AS grid_64_type,
    CASE r.muscle
        WHEN 'VM' THEN sess.vm_grid_64_orientation
        WHEN 'VL' THEN sess.vl_grid_64_orientation
    END AS grid_64_orientation,
    CASE r.muscle
        WHEN 'VM' THEN sess.vm_grid_32_type
        WHEN 'VL' THEN sess.vl_grid_32_type
    END AS grid_32_type,
    CASE r.muscle
        WHEN 'VM' THEN sess.vm_grid_32_orientation
        WHEN 'VL' THEN sess.vl_grid_32_orientation
    END AS grid_32_orientation,
    mu.mu_id,
    mu.mu_idx,
    mu.sil,
    mu.cov_isi_pct,
    mu.qc_passed,
    mu.is_duplicate,
    mu.mean_dr_plateau_hz,
    mu.rt_pct_mvc,
    mu.cov_isi_plateau_pct,
    mu.delta_f_hz,
    mu.brace_slope
FROM motor_units mu
JOIN recordings r   ON mu.recording_id = r.recording_id
JOIN sessions sess  ON r.session_id = sess.session_id
JOIN subjects s     ON sess.subject_id = s.subject_id
WHERE r.training_mode_before IN ('CON', 'EXZ');
