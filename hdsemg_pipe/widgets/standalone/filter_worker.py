# hdsemg_pipe/widgets/standalone/filter_worker.py
"""Background worker for the standalone MU Quality Review filter operation."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

from PyQt5.QtCore import QThread, pyqtSignal

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.decomposition_file import DecompositionFile, ReliabilityThresholds
from hdsemg_pipe.widgets.standalone.output_options_dialog import FilterOutputConfig


class StandaloneFilterWorker(QThread):
    """Filter MUs and write output according to the chosen FilterOutputConfig.

    Adapted from _ProceedWorker in MUQualityReviewWizardWidget, but with three
    configurable output modes (in_place, archive, custom) instead of a fixed
    destination directory.
    """

    progress = pyqtSignal(int, int)  # (current, total)
    finished = pyqtSignal(int)       # n_files_written
    error = pyqtSignal(str)

    def __init__(
        self,
        kept_files: List[str],
        all_files: List[str],
        thresholds: ReliabilityThresholds,
        overrides: Dict[str, Dict[str, str]],
        config: FilterOutputConfig,
    ) -> None:
        super().__init__()
        self._kept_files = kept_files
        self._all_files = all_files
        self._thresholds = thresholds
        self._overrides = overrides
        self._config = config

    # ------------------------------------------------------------------

    def run(self) -> None:  # noqa: C901
        try:
            cfg = self._config
            cfg.output_dir.mkdir(parents=True, exist_ok=True)

            if cfg.mode == "archive":
                self._archive_originals(cfg)
                load_dir = cfg.backup_dir
                write_dir = cfg.output_dir
            elif cfg.mode == "in_place":
                load_dir = cfg.source_dir
                write_dir = cfg.source_dir / "_mu_review_tmp"
                write_dir.mkdir(parents=True, exist_ok=True)
            else:  # custom
                if cfg.backup_dir:
                    self._copy_originals(cfg.source_dir, cfg.backup_dir)
                load_dir = cfg.source_dir
                write_dir = cfg.output_dir

            total = len(self._kept_files)
            n_written = 0

            for i, filename in enumerate(self._kept_files):
                self.progress.emit(i + 1, total)
                src_json = load_dir / filename
                if not src_json.exists():
                    logger.warning("StandaloneFilterWorker: source not found: %s", src_json)
                    continue

                # Derive keep_mu_indices from JSON reliability
                dec_json = DecompositionFile.load(src_json)
                file_overrides_raw = self._overrides.get(filename, {})
                file_overrides = {(0, int(k)): v for k, v in file_overrides_raw.items()}

                rel_df = dec_json.compute_reliability(self._thresholds)
                keep_mu_indices: set = set()
                for _, row in rel_df.iterrows():
                    mu = int(row["mu_index"])
                    key = (0, mu)
                    decision = file_overrides.get(key, "Auto")
                    if decision == "Keep":
                        keep_mu_indices.add(mu)
                    elif decision == "Filter":
                        pass
                    elif bool(row["is_reliable"]):
                        keep_mu_indices.add(mu)

                stem = src_json.stem
                # In standalone mode we keep the original stem (no _covisi_filtered suffix)
                out_stem = stem

                # --- 1. Filter and save JSON ---
                filtered_json = dec_json.filter_mus_by_reliability(
                    self._thresholds, file_overrides
                )
                out_json = write_dir / (out_stem + ".json")
                filtered_json.save(out_json)
                n_written += 1

                # --- 2. Filter sibling PKL (if selected) ---
                if "pkl" in cfg.process_siblings:
                    src_pkl = load_dir / (stem + ".pkl")
                    if src_pkl.exists():
                        try:
                            dec_pkl = DecompositionFile.load(src_pkl)
                            dec_pkl._pkl_keep_indices = {0: keep_mu_indices}
                            out_pkl = write_dir / (out_stem + ".pkl")
                            dec_pkl.save(out_pkl)
                            n_written += 1
                        except Exception as exc:
                            logger.warning("PKL filter failed for %s: %s", src_pkl.name, exc)

                # --- 3. Filter sibling MAT (if selected) ---
                if "mat" in cfg.process_siblings:
                    src_mat = load_dir / (stem + "_muedit.mat")
                    if src_mat.exists():
                        try:
                            dec_mat = DecompositionFile.load(src_mat)
                            out_mat = write_dir / (out_stem + "_muedit.mat")
                            dec_mat._filter_mat_pulsetrain_by_indices(keep_mu_indices, out_mat)
                            n_written += 1
                        except Exception as exc:
                            logger.warning("MAT filter failed for %s: %s", src_mat.name, exc)

            # --- In-place: swap temp files into source dir ---
            if cfg.mode == "in_place":
                self._apply_inplace_swap(
                    write_dir, cfg.source_dir, self._kept_files, self._all_files
                )
                n_written_final = n_written
            else:
                n_written_final = n_written

            # --- Write manifest ---
            manifest_path = (cfg.output_dir if cfg.mode != "in_place" else cfg.source_dir) / "mu_quality_review_manifest.json"
            manifest = {
                "version": 1,
                "thresholds": self._thresholds.to_dict(),
                "kept_files": self._kept_files,
                "mu_overrides": self._overrides,
                "mode": cfg.mode,
            }
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)

            self.finished.emit(n_written_final)

        except Exception as exc:
            self.error.emit(str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _archive_originals(self, cfg: FilterOutputConfig) -> None:
        """Move JSON + selected sibling files to the backup directory."""
        cfg.backup_dir.mkdir(parents=True, exist_ok=True)
        for filename in self._all_files:
            for src in self._sibling_paths(cfg.source_dir, filename, cfg.process_siblings):
                if src.exists():
                    shutil.move(str(src), str(cfg.backup_dir / src.name))

    def _copy_originals(self, source_dir: Path, backup_dir: Path) -> None:
        """Copy JSON + selected sibling files to the backup directory."""
        backup_dir.mkdir(parents=True, exist_ok=True)
        for filename in self._all_files:
            for src in self._sibling_paths(source_dir, filename, self._config.process_siblings):
                if src.exists():
                    shutil.copy2(str(src), str(backup_dir / src.name))

    def _apply_inplace_swap(
        self,
        tmp_dir: Path,
        source_dir: Path,
        kept_files: List[str],
        all_files: List[str],
    ) -> None:
        """Move filtered files from tmp to source; delete unchecked originals."""
        # Delete originals for unchecked files (JSON always; siblings if selected)
        kept_set = set(kept_files)
        for filename in all_files:
            if filename not in kept_set:
                for p in self._sibling_paths(source_dir, filename, self._config.process_siblings):
                    if p.exists():
                        p.unlink()
                        logger.debug("In-place: deleted %s", p.name)

        # Move filtered output from tmp into source dir
        for item in tmp_dir.iterdir():
            dest = source_dir / item.name
            if dest.exists():
                dest.unlink()
            shutil.move(str(item), str(dest))

        # Clean up temp dir
        try:
            tmp_dir.rmdir()
        except OSError:
            pass

    @staticmethod
    def _sibling_paths(base_dir: Path, json_filename: str, process_siblings: frozenset) -> list:
        """Return paths for JSON + selected sibling types."""
        stem = Path(json_filename).stem
        paths = [base_dir / json_filename]
        if "pkl" in process_siblings:
            paths.append(base_dir / (stem + ".pkl"))
        if "mat" in process_siblings:
            paths.append(base_dir / (stem + "_muedit.mat"))
        return paths
