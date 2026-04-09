# hdsemg_pipe/widgets/wizard/MUQualityReviewWizardWidget.py
"""Step 9 — MU Quality Review.

Left panel: file list grouped by recording session (>=1 per group required).
Right panel: threshold bar + horizontal split of plot canvas (~65%) and MU
             reliability table (~35%) + footer counter + Proceed button.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False

try:
    import openhdemg.library as emg
    from openhdemg.library import plot, tools
    _OPENHDEMG_AVAILABLE = True
except ImportError:
    _OPENHDEMG_AVAILABLE = False

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.actions.decomposition_file import DecompositionFile, ReliabilityThresholds
from hdsemg_pipe.actions.file_grouping import get_group_key, shorten_group_labels
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, Styles
from hdsemg_pipe.widgets.WizardStepWidget import WizardStepWidget


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class _ReliabilityWorker(QThread):
    finished = pyqtSignal(object)   # pd.DataFrame
    error = pyqtSignal(str)

    def __init__(self, dec_file: DecompositionFile, thresholds: ReliabilityThresholds):
        super().__init__()
        self._dec_file = dec_file
        self._thresholds = thresholds

    def run(self):
        try:
            df = self._dec_file.compute_reliability(self._thresholds)
            self.finished.emit(df)
        except Exception as exc:
            self.error.emit(str(exc))


class _STAWorker(QThread):
    finished = pyqtSignal(object)   # sta result dict or None
    error = pyqtSignal(str)

    _GRID_CODES = ["GR08MM1305", "GR04MM1305", "GR10MM0808"]

    def __init__(self, emgfile: dict):
        super().__init__()
        self._emgfile = emgfile

    def run(self):
        if not _OPENHDEMG_AVAILABLE:
            self.finished.emit(None)
            return
        try:
            ef = self._emgfile
            sorted_ef = None
            for code in self._GRID_CODES:
                try:
                    sorted_ef = tools.sort_rawemg(
                        ef, code=code, orientation=0, dividebycolumns=True
                    )
                    break
                except Exception:
                    continue
            if sorted_ef is None:
                sorted_ef = ef
            sta_result = emg.sta(
                sorted_ef, sorted_ef["MUPULSES"], sorted_ef["FSAMP"]
            )
            self.finished.emit(sta_result)
        except Exception as exc:
            logger.warning("_STAWorker: STA failed: %s", exc)
            self.finished.emit(None)


class _ProceedWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        kept_files: List[str],
        thresholds: ReliabilityThresholds,
        overrides: Dict[str, Dict[str, str]],
        source_dir: Path,
        dest_dir: Path,
        manifest_path: Path,
    ):
        super().__init__()
        self._kept_files = kept_files
        self._thresholds = thresholds
        self._overrides = overrides
        self._source_dir = source_dir
        self._dest_dir = dest_dir
        self._manifest_path = manifest_path

    def run(self):
        try:
            self._dest_dir.mkdir(parents=True, exist_ok=True)
            total = len(self._kept_files)

            for i, filename in enumerate(self._kept_files):
                self.progress.emit(i + 1, total)
                src_path = self._source_dir / filename
                if not src_path.exists():
                    logger.warning("Source file not found: %s", src_path)
                    continue

                dec = DecompositionFile.load(src_path)
                file_overrides_raw = self._overrides.get(filename, {})
                # JSON files are single-port; use port_idx=0
                file_overrides = {
                    (0, int(k)): v for k, v in file_overrides_raw.items()
                }
                filtered = dec.filter_mus_by_reliability(self._thresholds, file_overrides)

                stem = src_path.stem
                if not stem.endswith("_covisi_filtered"):
                    out_stem = stem + "_covisi_filtered"
                else:
                    out_stem = stem
                out_path = self._dest_dir / (out_stem + src_path.suffix)
                filtered.save(out_path)

            # Write manifest
            manifest = {
                "version": 1,
                "thresholds": self._thresholds.to_dict(),
                "kept_files": self._kept_files,
                "mu_overrides": self._overrides,
            }
            self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._manifest_path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)

            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# File list items
# ---------------------------------------------------------------------------

class _GroupHeader(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-weight: bold; color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        layout.addWidget(lbl)
        layout.addStretch()
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        layout.addWidget(self.counter_label)

    def set_counter(self, selected: int, total: int):
        color = Colors.GREEN_600 if selected >= 1 else Colors.RED_600
        self.counter_label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: bold;"
        )
        self.counter_label.setText(f"{selected}/{total}")


class _FileListItem(QWidget):
    toggled = pyqtSignal(str, bool)
    selected = pyqtSignal(str)

    def __init__(self, filepath: str, label: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._is_selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.SM, Spacing.XS)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(
            lambda checked: self.toggled.emit(filepath, checked)
        )
        layout.addWidget(self.checkbox)

        self.name_label = QLabel(label)
        self.name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(self.name_label)
        layout.addStretch()

        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self.selected.emit(self.filepath)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        bg = Colors.BLUE_100 if selected else "transparent"
        self.setStyleSheet(f"background-color: {bg}; border-radius: 4px;")

    def set_force_checked(self, force: bool):
        """Disable checkbox when this is the last checked file in the group."""
        self.checkbox.setEnabled(not force)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class MUQualityReviewWizardWidget(WizardStepWidget):
    """Step 9 — MU Quality Review."""

    def __init__(self, parent=None):
        super().__init__(
            step_index=9,
            step_name="MU Quality Review",
            description=(
                "Review and filter motor units based on SIL, PNR, and CoVISI "
                "reliability metrics. Select files to forward, inspect plots, "
                "and override per-MU decisions before proceeding."
            ),
            parent=parent,
        )

        self._thresholds = ReliabilityThresholds()
        self._reliability_cache: Dict[str, object] = {}
        self._emgfile_cache: Dict[str, Optional[dict]] = {}
        self._overrides: Dict[str, Dict[str, str]] = {}
        self._checked: Dict[str, bool] = {}
        self._groups: Dict[str, List[str]] = {}
        self._items: Dict[str, _FileListItem] = {}
        self._group_headers: Dict[str, _GroupHeader] = {}
        self._current_file: Optional[str] = None
        self._sta_cache: Dict[str, object] = {}
        self._worker: Optional[QThread] = None

        self._build_ui()

    # -- UI construction -------------------------------------------------------

    def _build_ui(self):
        container = QFrame()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QHBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        outer_splitter = QSplitter(Qt.Horizontal)
        root.addWidget(outer_splitter)

        # ---- Left panel: file list ----
        left = QWidget()
        left.setFixedWidth(240)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        left_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._file_list_widget = QWidget()
        self._file_list_layout = QVBoxLayout(self._file_list_widget)
        self._file_list_layout.setContentsMargins(0, 0, 0, 0)
        self._file_list_layout.setSpacing(2)
        self._file_list_layout.addStretch()
        scroll.setWidget(self._file_list_widget)
        left_layout.addWidget(scroll)
        outer_splitter.addWidget(left)

        # ---- Right panel ----
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        right_layout.setSpacing(Spacing.SM)

        # Threshold bar
        threshold_bar = QFrame()
        threshold_bar.setStyleSheet(Styles.card())
        tb_layout = QHBoxLayout(threshold_bar)
        tb_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

        self._sil_check = QCheckBox("SIL >=")
        self._sil_check.setChecked(True)
        self._sil_spin = QDoubleSpinBox()
        self._sil_spin.setRange(0.0, 1.0)
        self._sil_spin.setSingleStep(0.05)
        self._sil_spin.setDecimals(3)
        self._sil_spin.setValue(0.9)

        self._pnr_check = QCheckBox("PNR >=")
        self._pnr_check.setChecked(True)
        self._pnr_spin = QDoubleSpinBox()
        self._pnr_spin.setRange(0.0, 100.0)
        self._pnr_spin.setSingleStep(1.0)
        self._pnr_spin.setDecimals(1)
        self._pnr_spin.setValue(30.0)
        self._pnr_spin.setSuffix(" dB")

        self._covisi_check = QCheckBox("CoVISI <=")
        self._covisi_check.setChecked(True)
        self._covisi_spin = QDoubleSpinBox()
        self._covisi_spin.setRange(0.0, 100.0)
        self._covisi_spin.setSingleStep(1.0)
        self._covisi_spin.setDecimals(1)
        self._covisi_spin.setValue(30.0)
        self._covisi_spin.setSuffix(" %")

        for w in [
            self._sil_check, self._sil_spin,
            self._pnr_check, self._pnr_spin,
            self._covisi_check, self._covisi_spin,
        ]:
            tb_layout.addWidget(w)
        tb_layout.addStretch()
        right_layout.addWidget(threshold_bar)

        # Content splitter: plot | table
        content_splitter = QSplitter(Qt.Horizontal)

        # Plot panel
        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(Spacing.XS)

        self._plot_dropdown = QComboBox()
        self._plot_dropdown.addItems(
            ["Discharge Rate (IDR)", "Discharge Times", "MUAPs"]
        )
        plot_layout.addWidget(self._plot_dropdown)

        self._canvas_container = QWidget()
        self._canvas_layout = QVBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)

        if _MATPLOTLIB_AVAILABLE:
            self._figure = Figure(figsize=(8, 5), tight_layout=True)
            self._canvas = FigureCanvasQTAgg(self._figure)
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._canvas_layout.addWidget(self._canvas)
        else:
            self._canvas_layout.addWidget(QLabel("matplotlib unavailable"))

        plot_layout.addWidget(self._canvas_container)
        content_splitter.addWidget(plot_panel)

        # MU table panel
        table_panel = QWidget()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._mu_table = QTableWidget()
        self._mu_table.setColumnCount(7)
        self._mu_table.setHorizontalHeaderLabels(
            ["#", "SIL", "PNR (dB)", "CoVISI (%)", "DR (pps)", "Spikes", "Decision"]
        )
        self._mu_table.horizontalHeader().setStretchLastSection(True)
        self._mu_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._mu_table.setSelectionMode(QTableWidget.NoSelection)
        table_layout.addWidget(self._mu_table)
        content_splitter.addWidget(table_panel)

        content_splitter.setSizes([650, 350])
        right_layout.addWidget(content_splitter, stretch=1)

        # Footer
        self._footer_label = QLabel()
        self._footer_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        right_layout.addWidget(self._footer_label)

        # Proceed button
        self._proceed_btn = QPushButton("Proceed")
        self._proceed_btn.setStyleSheet(Styles.button_primary())
        self._proceed_btn.setEnabled(False)
        self._proceed_btn.clicked.connect(self._on_proceed)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._proceed_btn)
        right_layout.addLayout(btn_row)

        outer_splitter.addWidget(right)
        outer_splitter.setSizes([240, 760])

        # Connect threshold controls
        for w in [self._sil_check, self._pnr_check, self._covisi_check]:
            w.toggled.connect(self._on_threshold_changed)
        for w in [self._sil_spin, self._pnr_spin, self._covisi_spin]:
            w.valueChanged.connect(self._on_threshold_changed)

        self._plot_dropdown.currentIndexChanged.connect(self._on_plot_type_changed)

        self.content_layout.addWidget(container)

    # -- WizardStepWidget hook -------------------------------------------------

    def check(self):
        """Populate file list from decomposition_results folder."""
        if not global_state.is_widget_completed("step8"):
            return
        source_dir = Path(global_state.get_decomposition_results_path())
        if not source_dir.exists():
            return
        files = sorted(
            str(p) for p in source_dir.iterdir() if p.suffix.lower() == ".json"
        )
        if files:
            self._populate_file_list(files)

    # -- Public API ------------------------------------------------------------

    def restore_from_manifest(self, manifest: dict):
        """Restore widget state from a previously saved manifest."""
        thresholds_data = manifest.get("thresholds", {})
        self._thresholds = ReliabilityThresholds.from_dict(thresholds_data)

        for w in [
            self._sil_check, self._sil_spin, self._pnr_check,
            self._pnr_spin, self._covisi_check, self._covisi_spin,
        ]:
            w.blockSignals(True)
        self._sil_check.setChecked(self._thresholds.sil_enabled)
        self._sil_spin.setValue(self._thresholds.sil_min)
        self._pnr_check.setChecked(self._thresholds.pnr_enabled)
        self._pnr_spin.setValue(self._thresholds.pnr_min)
        self._covisi_check.setChecked(self._thresholds.covisi_enabled)
        self._covisi_spin.setValue(self._thresholds.covisi_max)
        for w in [
            self._sil_check, self._sil_spin, self._pnr_check,
            self._pnr_spin, self._covisi_check, self._covisi_spin,
        ]:
            w.blockSignals(False)

        self._overrides = manifest.get("mu_overrides", {})
        kept_files = set(manifest.get("kept_files", []))

        for filepath, item in self._items.items():
            basename = Path(filepath).name
            should_check = basename in kept_files
            item.checkbox.blockSignals(True)
            item.checkbox.setChecked(should_check)
            item.checkbox.blockSignals(False)
            self._checked[filepath] = should_check

        self._update_group_headers()
        self._update_proceed_button()

    # -- Private helpers -------------------------------------------------------

    def _populate_file_list(self, filepaths: List[str]):
        # Clear existing widgets (keep stretch at end)
        while self._file_list_layout.count() > 1:
            item = self._file_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._items.clear()
        self._group_headers.clear()
        self._groups.clear()
        self._checked.clear()

        for fp in filepaths:
            key = get_group_key(os.path.basename(fp))
            self._groups.setdefault(key, []).append(fp)

        labels = shorten_group_labels(list(self._groups.keys()))

        insert_pos = 0
        for key, fps in self._groups.items():
            header = _GroupHeader(labels.get(key, key))
            self._group_headers[key] = header
            self._file_list_layout.insertWidget(insert_pos, header)
            insert_pos += 1
            for fp in fps:
                item = _FileListItem(fp, Path(fp).name)
                item.toggled.connect(self._on_file_toggled)
                item.selected.connect(self._on_file_selected)
                self._items[fp] = item
                self._checked[fp] = True
                self._file_list_layout.insertWidget(insert_pos, item)
                insert_pos += 1

        self._update_group_headers()
        self._enforce_last_in_group()
        self._update_proceed_button()

        if filepaths:
            self._on_file_selected(filepaths[0])

    def _on_file_toggled(self, filepath: str, checked: bool):
        self._checked[filepath] = checked
        self._update_group_headers()
        self._enforce_last_in_group()
        self._update_proceed_button()
        self._update_footer()

    def _enforce_last_in_group(self):
        for fps in self._groups.values():
            checked_fps = [fp for fp in fps if self._checked.get(fp, True)]
            for fp in fps:
                item = self._items.get(fp)
                if item:
                    item.set_force_checked(
                        len(checked_fps) == 1 and fp in checked_fps
                    )

    def _on_file_selected(self, filepath: str):
        if self._current_file:
            old = self._items.get(self._current_file)
            if old:
                old.set_selected(False)
        self._current_file = filepath
        item = self._items.get(filepath)
        if item:
            item.set_selected(True)
        self._load_file_data(filepath)

    def _load_file_data(self, filepath: str):
        if filepath in self._reliability_cache:
            self._refresh_mu_table(filepath)
            self._refresh_plot(filepath)
            return
        try:
            dec = DecompositionFile.load(Path(filepath))
        except Exception as exc:
            logger.warning("Could not load %s: %s", filepath, exc)
            return
        self._emgfile_cache[filepath] = dec.get_emgfile_for_plotting()
        worker = _ReliabilityWorker(dec, self._thresholds)
        worker.finished.connect(
            lambda df, fp=filepath: self._on_reliability_loaded(fp, df)
        )
        worker.error.connect(
            lambda err: logger.warning("Reliability worker error: %s", err)
        )
        self._worker = worker
        worker.start()

    def _on_reliability_loaded(self, filepath: str, df):
        self._reliability_cache[filepath] = df
        if filepath == self._current_file:
            self._refresh_mu_table(filepath)
            self._refresh_plot(filepath)
        self._update_footer()

    def _refresh_mu_table(self, filepath: str):
        import math
        df = self._reliability_cache.get(filepath)
        if df is None or len(df) == 0:
            self._mu_table.setRowCount(0)
            return

        file_overrides = self._overrides.get(filepath, {})
        thresholds = self._build_thresholds()

        self._mu_table.setRowCount(len(df))
        for row_idx, (_, row) in enumerate(df.iterrows()):
            mu = int(row["mu_index"])
            sil = float(row["sil"])
            pnr = float(row["pnr"])
            covisi = float(row["covisi"])
            decision = file_overrides.get(str(mu), "Auto")

            is_reliable = thresholds.is_reliable(sil, pnr, covisi)
            keep = is_reliable or decision == "Keep"
            if decision == "Filter":
                keep = False

            bg_color = QColor(Colors.GREEN_100) if keep else QColor(Colors.RED_100)

            def _make_item(val, fmt):
                if isinstance(val, float) and math.isnan(val):
                    text = "N/A"
                else:
                    text = fmt.format(val)
                item = QTableWidgetItem(text)
                item.setBackground(bg_color)
                return item

            self._mu_table.setItem(row_idx, 0, _make_item(mu, "{}"))
            self._mu_table.setItem(row_idx, 1, _make_item(sil, "{:.3f}"))
            self._mu_table.setItem(row_idx, 2, _make_item(pnr, "{:.1f}"))
            self._mu_table.setItem(row_idx, 3, _make_item(covisi, "{:.1f}"))
            self._mu_table.setItem(row_idx, 4, _make_item(float(row["dr_mean"]), "{:.1f}"))
            self._mu_table.setItem(row_idx, 5, _make_item(float(row["n_spikes"]), "{:.0f}"))

            combo = QComboBox()
            combo.addItems(["Auto", "Keep", "Filter"])
            combo.setCurrentText(decision)
            combo.currentTextChanged.connect(
                lambda text, mu_=mu, fp=filepath: self._on_decision_changed(fp, mu_, text)
            )
            self._mu_table.setCellWidget(row_idx, 6, combo)

    def _on_decision_changed(self, filepath: str, mu_idx: int, decision: str):
        self._overrides.setdefault(filepath, {})[str(mu_idx)] = decision
        if filepath == self._current_file:
            self._refresh_mu_table(filepath)
        self._update_footer()

    def _refresh_plot(self, filepath: str):
        if not _MATPLOTLIB_AVAILABLE or not _OPENHDEMG_AVAILABLE:
            return
        emgfile = self._emgfile_cache.get(filepath)
        if emgfile is None:
            return
        plot_type = self._plot_dropdown.currentText()
        if plot_type == "MUAPs":
            self._load_muaps_plot(filepath, emgfile)
            return
        self._figure.clear()
        try:
            if plot_type == "Discharge Rate (IDR)":
                fig = plot.plot_idr(emgfile, munumber="all", showimmediately=False)
            else:
                fig = plot.plot_mupulses(emgfile, linewidths=0.8, showimmediately=False)
            self._replace_canvas_figure(fig)
        except Exception as exc:
            ax = self._figure.add_subplot(111)
            ax.text(
                0.5, 0.5, f"Plot error:\n{exc}",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=9, color="red",
            )
        self._canvas.draw()

    def _replace_canvas_figure(self, fig):
        """Copy axes content from openhdemg figure into self._figure."""
        self._figure.clear()
        if fig is None:
            return
        for src_ax in fig.get_axes():
            dst_ax = self._figure.add_subplot(111)
            for line in src_ax.get_lines():
                dst_ax.plot(
                    line.get_xdata(), line.get_ydata(),
                    color=line.get_color(),
                    linewidth=line.get_linewidth(),
                )
            dst_ax.set_xlabel(src_ax.get_xlabel())
            dst_ax.set_ylabel(src_ax.get_ylabel())
            dst_ax.set_title(src_ax.get_title())
        plt.close(fig)

    def _load_muaps_plot(self, filepath: str, emgfile: dict):
        if filepath in self._sta_cache:
            self._draw_muaps(self._sta_cache[filepath])
            return
        worker = _STAWorker(emgfile)
        worker.finished.connect(
            lambda sta, fp=filepath: self._on_sta_done(fp, sta)
        )
        worker.error.connect(
            lambda err: logger.warning("STA worker error: %s", err)
        )
        self._worker = worker
        worker.start()

    def _on_sta_done(self, filepath: str, sta_result):
        self._sta_cache[filepath] = sta_result
        if filepath == self._current_file:
            self._draw_muaps(sta_result)

    def _draw_muaps(self, sta_result):
        self._figure.clear()
        if sta_result is None or not _OPENHDEMG_AVAILABLE:
            ax = self._figure.add_subplot(111)
            ax.text(
                0.5, 0.5, "MUAPs unavailable",
                ha="center", va="center", transform=ax.transAxes,
            )
            self._canvas.draw()
            return
        try:
            fig = plot.plot_muaps(sta_result, showimmediately=False)
            self._replace_canvas_figure(fig)
        except Exception as exc:
            ax = self._figure.add_subplot(111)
            ax.text(
                0.5, 0.5, f"MUAPs error:\n{exc}",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=9, color="red",
            )
        self._canvas.draw()

    def _on_plot_type_changed(self):
        if self._current_file:
            self._refresh_plot(self._current_file)

    def _on_threshold_changed(self):
        self._thresholds = self._build_thresholds()
        self._reliability_cache.clear()
        if self._current_file:
            self._load_file_data(self._current_file)
        self._update_footer()

    def _build_thresholds(self) -> ReliabilityThresholds:
        return ReliabilityThresholds(
            sil_min=self._sil_spin.value(),
            pnr_min=self._pnr_spin.value(),
            covisi_max=self._covisi_spin.value(),
            sil_enabled=self._sil_check.isChecked(),
            pnr_enabled=self._pnr_check.isChecked(),
            covisi_enabled=self._covisi_check.isChecked(),
        )

    def _update_group_headers(self):
        for key, fps in self._groups.items():
            header = self._group_headers.get(key)
            if header:
                checked = sum(1 for fp in fps if self._checked.get(fp, True))
                header.set_counter(checked, len(fps))

    def _update_proceed_button(self):
        all_ok = all(
            any(self._checked.get(fp, True) for fp in fps)
            for fps in self._groups.values()
        )
        self._proceed_btn.setEnabled(all_ok and bool(self._groups))

    def _update_footer(self):
        import math
        total_mus = 0
        filtered_mus = 0
        thresholds = self._build_thresholds()
        for fp, checked in self._checked.items():
            if not checked:
                continue
            df = self._reliability_cache.get(fp)
            if df is None:
                continue
            file_overrides = self._overrides.get(fp, {})
            for _, row in df.iterrows():
                mu = int(row["mu_index"])
                total_mus += 1
                decision = file_overrides.get(str(mu), "Auto")
                sil = float(row["sil"])
                pnr = float(row["pnr"])
                covisi = float(row["covisi"])
                is_reliable = thresholds.is_reliable(sil, pnr, covisi)
                if decision == "Filter" or (decision == "Auto" and not is_reliable):
                    filtered_mus += 1
        self._footer_label.setText(
            f"{filtered_mus} of {total_mus} total MUs filtered"
        )

    def _on_proceed(self):
        unvisited = [
            fp for fp in self._checked
            if self._checked[fp] and fp not in self._reliability_cache
        ]
        if unvisited:
            reply = QMessageBox.question(
                self,
                "Unvisited files",
                f"{len(unvisited)} file(s) have not been reviewed.\n"
                "They will be processed with Auto decisions using current thresholds.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        kept_files = [
            Path(fp).name
            for fp, checked in self._checked.items()
            if checked
        ]
        source_dir = Path(global_state.get_decomposition_results_path())
        dest_dir = Path(global_state.get_decomposition_covisi_filtered_path())
        manifest_path = Path(global_state.get_analysis_path()) / "mu_quality_selection.json"

        self._proceed_btn.setEnabled(False)
        worker = _ProceedWorker(
            kept_files=kept_files,
            thresholds=self._build_thresholds(),
            overrides=self._overrides,
            source_dir=source_dir,
            dest_dir=dest_dir,
            manifest_path=manifest_path,
        )
        worker.finished.connect(self._on_proceed_done)
        worker.error.connect(self._on_proceed_error)
        self._worker = worker
        worker.start()

    def _on_proceed_done(self):
        global_state.complete_widget("step9")
        self._proceed_btn.setEnabled(True)

    def _on_proceed_error(self, error: str):
        QMessageBox.critical(self, "Proceed failed", error)
        self._proceed_btn.setEnabled(True)
