-- ============================================================================
-- HD-sEMG Motor Unit Study - Example Queries
-- ============================================================================
-- These queries answer the key research questions from the crossover design.
-- Open in DBeaver or run via: python db_setup/db_connector.py --query <n>
-- ============================================================================

-- Q1: Mean discharge rate from trapezoid plateau after CON vs EXZ training
SELECT
    r.training_mode_before,
    AVG(mu.mean_dr_plateau_hz) AS mean_dr_hz,
    STDEV(mu.mean_dr_plateau_hz) AS sd_dr_hz,
    COUNT(*) AS n_mus
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
WHERE r.task_type = 'Trapezoid'
  AND r.training_mode_before IN ('CON', 'EXZ')
  AND mu.qc_passed = TRUE
  AND mu.is_duplicate = FALSE
GROUP BY r.training_mode_before;

-- Q2: Washout effectiveness (Pre_Intervention vs Post_Washout should be similar)
SELECT
    r.block_label,
    r.training_mode_before,
    AVG(mu.mean_dr_plateau_hz) AS mean_dr_hz,
    AVG(mu.rt_pct_mvc) AS mean_rt,
    COUNT(*) AS n_mus
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
WHERE r.task_type = 'Trapezoid'
  AND r.block_label IN ('Pre_Intervention', 'Post_Washout')
  AND mu.qc_passed = TRUE
GROUP BY r.block_label, r.training_mode_before;

-- Q3: PICs from pyramid tasks (Delta F and Brace method)
SELECT
    r.training_mode_before,
    AVG(mu.delta_f_hz) AS mean_delta_f,
    STDEV(mu.delta_f_hz) AS sd_delta_f,
    AVG(mu.brace_slope) AS mean_brace_slope,
    COUNT(*) AS n_mus
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
WHERE r.task_type = 'Pyramid'
  AND r.training_mode_before IN ('CON', 'EXZ')
  AND mu.qc_passed = TRUE
  AND mu.is_duplicate = FALSE
GROUP BY r.training_mode_before;

-- Q4: How many MUs tracked over 4 and 6 blocks per subject
SELECT
    s.subject_id,
    tc.tracking_scope,
    tc.muscle,
    tc.task_type,
    COUNT(DISTINCT tc.cluster_id) AS n_clusters
FROM tracking_clusters tc
JOIN sessions sess ON tc.session_id = sess.session_id
JOIN subjects s ON sess.subject_id = s.subject_id
GROUP BY s.subject_id, tc.tracking_scope, tc.muscle, tc.task_type;

-- Q5a: All MUs (no tracking filter)
SELECT
    r.training_mode_before,
    r.muscle,
    AVG(mu.mean_dr_plateau_hz) AS mean_dr_hz,
    COUNT(*) AS n_mus
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
WHERE r.task_type = 'Trapezoid'
  AND mu.qc_passed = TRUE
  AND mu.is_duplicate = FALSE
GROUP BY r.training_mode_before, r.muscle;

-- Q5b: Only 4-block tracked MUs
SELECT
    r.training_mode_before,
    r.muscle,
    AVG(mu.mean_dr_plateau_hz) AS mean_dr_hz,
    COUNT(*) AS n_mus
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
JOIN mu_tracking mt ON mu.mu_id = mt.mu_id
JOIN tracking_clusters tc ON mt.cluster_id = tc.cluster_id
WHERE r.task_type = 'Trapezoid'
  AND tc.tracking_scope = '4_block'
GROUP BY r.training_mode_before, r.muscle;

-- Q6: VM vs VL differences per training condition
SELECT
    r.muscle,
    r.training_mode_before,
    AVG(mu.mean_dr_plateau_hz) AS mean_dr_hz,
    AVG(mu.rt_pct_mvc) AS mean_rt,
    AVG(mu.cov_isi_plateau_pct) AS mean_cov_isi,
    COUNT(*) AS n_mus
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
WHERE r.task_type = 'Trapezoid'
  AND mu.qc_passed = TRUE
  AND mu.is_duplicate = FALSE
GROUP BY r.muscle, r.training_mode_before;

-- Q7: Duplicate MU counts per recording
SELECT
    s.subject_id,
    r.block_label,
    r.muscle,
    r.task_type,
    COUNT(*) FILTER (WHERE mu.is_duplicate = TRUE) AS n_duplicates,
    COUNT(*) FILTER (WHERE mu.is_duplicate = FALSE) AS n_unique
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
JOIN sessions sess ON r.session_id = sess.session_id
JOIN subjects s ON sess.subject_id = s.subject_id
GROUP BY s.subject_id, r.block_label, r.muscle, r.task_type;

-- Q8: Paired delta for tracked MUs (pre vs post per cluster)
SELECT
    tc.cluster_id,
    s.subject_id,
    r.training_mode_before,
    r.block_label,
    r.block_number,
    mu.mean_dr_plateau_hz,
    mu.rt_pct_mvc,
    mu.cov_isi_plateau_pct
FROM mu_tracking mt
JOIN motor_units mu ON mt.mu_id = mu.mu_id
JOIN recordings r ON mu.recording_id = r.recording_id
JOIN sessions sess ON r.session_id = sess.session_id
JOIN subjects s ON sess.subject_id = s.subject_id
JOIN tracking_clusters tc ON mt.cluster_id = tc.cluster_id
WHERE tc.tracking_scope = '4_block'
  AND r.task_type = 'Trapezoid'
ORDER BY tc.cluster_id, r.block_number;

-- GLMM-ready export (flat DataFrame for Python statsmodels)
SELECT
    s.subject_id,
    s.first_training_mode,
    r.block_number,
    r.block_label,
    r.training_mode_before,
    r.task_type,
    r.muscle,
    mu.mu_id,
    mu.mu_idx,
    mu.sil,
    mu.cov_isi_pct,
    mu.mean_dr_plateau_hz,
    mu.rt_pct_mvc,
    mu.drt_pct_mvc,
    mu.cov_isi_plateau_pct,
    mu.delta_f_hz,
    mu.brace_slope
FROM motor_units mu
JOIN recordings r ON mu.recording_id = r.recording_id
JOIN sessions sess ON r.session_id = sess.session_id
JOIN subjects s ON sess.subject_id = s.subject_id
WHERE mu.qc_passed = TRUE
  AND mu.is_duplicate = FALSE
ORDER BY s.subject_id, r.block_number, r.muscle, mu.mu_idx;
