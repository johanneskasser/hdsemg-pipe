"""
Tracking Error Thresholds Dialog

Lets the user view and edit the quality tier boundaries (excellent / good / ok /
troubled) for the currently selected tracking-error metric.  Changes are saved
immediately to ``config`` so the parent widget can repaint live.
"""

from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QDoubleSpinBox, QFrame, QWidget,
)

from hdsemg_pipe.actions.tracking_error_metrics import (
    DEFAULT_THRESHOLDS, TIER_ORDER, TIER_DISPLAY,
)
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.ui_elements.theme import (
    BorderRadius, Colors, Fonts, Spacing, Styles,
)


class TrackingErrorThresholdsDialog(QDialog):
    """Modal dialog for editing quality tier thresholds for a given metric.

    The dialog reads the current thresholds from ``config`` (falling back to
    ``DEFAULT_THRESHOLDS`` when none are stored), shows four ``QDoubleSpinBox``
    rows (excellent / good / ok / troubled), and writes changes back to
    ``config`` on "Save".  A "Reset to defaults" button restores per-metric
    factory values without closing the dialog.

    Usage::

        dlg = TrackingErrorThresholdsDialog("NRMSE", parent=self)
        dlg.exec_()
        # config already updated – caller can repaint immediately
    """

    def __init__(self, metric_name: str, parent=None):
        super().__init__(parent)
        self._metric_name = metric_name
        self.setWindowTitle(f"Quality Thresholds — {metric_name}")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_PRIMARY}; }}")
        self._spinboxes: Dict[str, QDoubleSpinBox] = {}
        self._build_ui()
        self._load_current_thresholds()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        root.setSpacing(Spacing.LG)

        # Header
        header = QLabel(
            f"Set score boundaries for <b>{self._metric_name}</b>.<br>"
            "<small style='color:gray;'>Files with a score ≥ Excellent threshold are "
            "rated Excellent; ≥ Good → Good; etc.</small>"
        )
        header.setTextFormat(Qt.RichText)
        header.setWordWrap(True)
        header.setStyleSheet(
            f"QLabel {{ color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_SM}; }}"
        )
        root.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {Colors.BORDER_MUTED};")
        root.addWidget(sep)

        # Tier rows
        tier_colors = {
            "excellent": Colors.GREEN_500,
            "good": Colors.BLUE_500,
            "ok": Colors.YELLOW_500,
            "troubled": Colors.ORANGE_500,
        }
        form = QWidget()
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(Spacing.SM)

        for tier in TIER_ORDER:
            row = QHBoxLayout()
            row.setSpacing(Spacing.MD)

            dot = QLabel("●")
            dot.setFixedWidth(14)
            dot.setStyleSheet(
                f"color: {tier_colors[tier]}; font-size: 14px;"
                f"background: transparent; border: none;"
            )
            row.addWidget(dot)

            lbl = QLabel(TIER_DISPLAY[tier])
            lbl.setFixedWidth(80)
            lbl.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.SIZE_SM};"
                f"font-weight: {Fonts.WEIGHT_MEDIUM}; background: transparent; border: none;"
            )
            row.addWidget(lbl)

            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setSuffix("  %")
            spin.setFixedWidth(110)
            spin.setStyleSheet(f"""
                QDoubleSpinBox {{
                    background-color: {Colors.BG_SECONDARY};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.BORDER_DEFAULT};
                    border-radius: {BorderRadius.SM};
                    padding: 4px 6px;
                    font-size: {Fonts.SIZE_SM};
                }}
                QDoubleSpinBox:focus {{
                    border-color: {Colors.BLUE_500};
                }}
            """)
            row.addWidget(spin)
            row.addStretch()

            hint = QLabel("(min score for this tier)")
            hint.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS};"
                f"background: transparent; border: none;"
            )
            row.addWidget(hint)

            self._spinboxes[tier] = spin
            form_layout.addLayout(row)

        root.addWidget(form)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color: {Colors.BORDER_MUTED};")
        root.addWidget(sep2)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.SM)

        reset_btn = QPushButton("Reset to defaults")
        reset_btn.setStyleSheet(Styles.button_secondary())
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(Styles.button_secondary())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(Styles.button_primary())
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _get_stored_thresholds(self) -> Dict[str, float]:
        """Return the stored thresholds for the current metric, or defaults."""
        all_thresholds = config.get(Settings.TRACKING_ERROR_THRESHOLDS, {})
        if isinstance(all_thresholds, dict) and self._metric_name in all_thresholds:
            stored = all_thresholds[self._metric_name]
            # Merge with defaults to cover any missing tier keys
            defaults = DEFAULT_THRESHOLDS.get(self._metric_name, {})
            return {tier: stored.get(tier, defaults.get(tier, 60.0)) for tier in TIER_ORDER}
        return dict(DEFAULT_THRESHOLDS.get(self._metric_name, {}))

    def _load_current_thresholds(self):
        thresholds = self._get_stored_thresholds()
        for tier, spin in self._spinboxes.items():
            spin.setValue(thresholds.get(tier, 60.0))

    def _write_thresholds_to_config(self, thresholds: Dict[str, float]):
        all_thresholds = config.get(Settings.TRACKING_ERROR_THRESHOLDS, {})
        if not isinstance(all_thresholds, dict):
            all_thresholds = {}
        all_thresholds[self._metric_name] = thresholds
        config.set(Settings.TRACKING_ERROR_THRESHOLDS, all_thresholds)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_save(self):
        thresholds = {tier: self._spinboxes[tier].value() for tier in TIER_ORDER}
        self._write_thresholds_to_config(thresholds)
        self.accept()

    def _on_reset(self):
        defaults = DEFAULT_THRESHOLDS.get(self._metric_name, {})
        for tier, spin in self._spinboxes.items():
            spin.setValue(defaults.get(tier, 60.0))
        # Write resets immediately so live repaint works if caller polls config
        self._write_thresholds_to_config(dict(defaults))
