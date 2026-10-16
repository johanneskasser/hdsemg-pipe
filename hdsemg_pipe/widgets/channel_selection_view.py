"""Read-only overview of a channel-selection run (Step 7).

A summary band (kept / discarded / pending), a filter bar and one row per file.
Each row shows, per grid, a strip with one tick per channel: kept channels in
green, channels dropped in hdsemg-select in red.

Styling note: the wizard's content card sets ``QFrame { padding; border }``, which
cascades into every QFrame subclass (QLabel, QTableWidget, ...). Everything here
therefore sets ``border/padding/background`` explicitly via ``_label`` / object names.
"""
import os
from typing import List, Optional

from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFontMetrics, QPainter
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from hdsemg_pipe.actions.channel_selection_summary import (
    DISCARDED, KEPT, PENDING, FileSummary, GridSummary,
)
from hdsemg_pipe.ui_elements.theme import BorderRadius, Colors, Fonts, Spacing

STATUS_COLOR = {KEPT: Colors.GREEN_600, DISCARDED: Colors.RED_500, PENDING: Colors.GRAY_400}


def _label(text: str = "", size: str = Fonts.SIZE_BASE, color: str = Colors.TEXT_PRIMARY,
           weight: str = Fonts.WEIGHT_NORMAL) -> QLabel:
    """QLabel that opts out of the parent card's QFrame border/padding."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"QLabel {{ color: {color}; font-size: {size}; font-weight: {weight};"
        " border: none; padding: 0; background: transparent; }"
    )
    return lbl


class _ElidedLabel(QLabel):
    """Single-line label that elides in the middle instead of forcing the row wider."""

    def __init__(self, text: str, size: str, weight: str, color: str):
        super().__init__()
        self._full = text
        self._color = color
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setStyleSheet(
            f"QLabel {{ color: {color}; font-size: {size}; font-weight: {weight};"
            " border: none; padding: 0; background: transparent; }"
        )

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QColor(self._color))
        text = QFontMetrics(self.font()).elidedText(self._full, Qt.ElideMiddle, self.width())
        painter.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, text)


class _SegmentBar(QWidget):
    """Thin proportional bar: kept / discarded / pending."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self._parts = []

    def set_counts(self, kept: int, discarded: int, pending: int):
        self._parts = [(kept, Colors.GREEN_500), (discarded, Colors.RED_500), (pending, Colors.GRAY_300)]
        self.update()

    def paintEvent(self, _event):
        total = sum(n for n, _ in self._parts)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(Colors.GRAY_200))
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
        if not total:
            return
        x = 0.0
        w = self.width()
        for n, color in self._parts:
            if not n:
                continue
            seg = w * n / total
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(x, 0, max(seg - 1, 2), self.height()), 3, 3)
            x += seg


class _ChannelStrip(QWidget):
    """One tick per channel; dropped channels are red and taller."""

    def __init__(self, grid: GridSummary):
        super().__init__()
        self._grid = grid
        self.setFixedHeight(18)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if grid.excluded_channels:
            self.setToolTip("Dropped channels: " + ", ".join(map(str, grid.excluded_channels)))

    def paintEvent(self, _event):
        g = self._grid
        n = g.n_total
        if n <= 0:
            return
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        dropped = set(g.excluded_channels)
        gap = 1.0 if self.width() / n >= 3 else 0.0
        tick_w = max(self.width() / n - gap, 1.0)
        h = self.height()
        for i in range(n):
            is_dropped = (i + 1) in dropped
            painter.setBrush(QColor(Colors.RED_500 if is_dropped else Colors.GREEN_500))
            top = 0 if is_dropped else 4
            painter.drawRect(QRectF(i * (tick_w + gap), top, tick_w, h - top - (0 if is_dropped else 4)))


def _grid_title(g: GridSummary) -> str:
    dims = f"{g.rows}×{g.columns}" if g.rows and g.columns else g.grid_key
    ied = f" · {g.ied_mm:g} mm" if isinstance(g.ied_mm, (int, float)) else ""
    return f"{dims}{ied}"


class _FileRow(QFrame):
    edit_requested = pyqtSignal(str)

    def __init__(self, f: FileSummary, display_name: str):
        super().__init__()
        self.summary = f
        self.setObjectName("fileRow")
        self.setStyleSheet(
            f"QFrame#fileRow {{ background: {Colors.BG_PRIMARY}; border: none; padding: 0;"
            f" border-bottom: 1px solid {Colors.BORDER_MUTED}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        row.setSpacing(Spacing.LG)

        dot = QFrame()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"QFrame {{ background: {STATUS_COLOR[f.status]}; border: none; padding: 0; border-radius: 5px; }}"
        )
        row.addWidget(dot, 0, Qt.AlignVCenter)

        # Left: name + one-line facts
        left = QVBoxLayout()
        left.setSpacing(2)
        name = _ElidedLabel(display_name, Fonts.SIZE_BASE, Fonts.WEIGHT_SEMIBOLD, Colors.TEXT_PRIMARY)
        name.setToolTip(f.name)
        left.addWidget(name)
        left.addWidget(_label(self._facts(f), Fonts.SIZE_SM, Colors.TEXT_SECONDARY))
        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setStyleSheet("background: transparent; border: none; padding: 0;")
        left_host.setMinimumWidth(240)
        row.addWidget(left_host, 5, Qt.AlignVCenter)

        # Middle: one strip per grid
        grids = QVBoxLayout()
        grids.setSpacing(Spacing.XS)
        for g in f.grids:
            line = QHBoxLayout()
            line.setSpacing(Spacing.SM)
            title = _label(_grid_title(g), Fonts.SIZE_SM, Colors.TEXT_SECONDARY)
            title.setMinimumWidth(96)
            line.addWidget(title)
            line.addWidget(_ChannelStrip(g), 1)
            count = _label(f"{g.n_selected}/{g.n_total}", Fonts.SIZE_SM,
                           Colors.RED_600 if g.n_dropped else Colors.TEXT_SECONDARY,
                           Fonts.WEIGHT_MEDIUM)
            count.setMinimumWidth(48)
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            line.addWidget(count)
            grids.addLayout(line)
        if not f.grids:
            msg = "Not processed yet" if f.status == PENDING else "No sidecar JSON found"
            grids.addWidget(_label(msg, Fonts.SIZE_SM, Colors.TEXT_MUTED))
        grids_host = QWidget()
        grids_host.setLayout(grids)
        grids_host.setStyleSheet("background: transparent; border: none; padding: 0;")
        row.addWidget(grids_host, 6, Qt.AlignVCenter)

        # Right: edit action (kept files only)
        if f.status == KEPT and f.path:
            btn = QPushButton("Edit")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip("Re-open this file in hdsemg-select")
            btn.setStyleSheet(
                f"QPushButton {{ color: {Colors.BLUE_700}; background: {Colors.BG_PRIMARY};"
                f" border: 1px solid {Colors.BORDER_DEFAULT}; border-radius: {BorderRadius.MD};"
                f" padding: 4px 14px; font-size: {Fonts.SIZE_SM}; font-weight: {Fonts.WEIGHT_MEDIUM}; }}"
                f"QPushButton:hover {{ background: {Colors.BLUE_50}; border-color: {Colors.BLUE_500}; }}"
                f"QPushButton:disabled {{ color: {Colors.GRAY_400}; background: {Colors.BG_SECONDARY}; }}"
            )
            btn.clicked.connect(lambda: self.edit_requested.emit(f.path))
            self.edit_button = btn
            row.addWidget(btn, 0, Qt.AlignVCenter)

    @staticmethod
    def _facts(f: FileSummary) -> str:
        if f.status == DISCARDED:
            return f"Discarded — {f.reason}" if f.reason else "Discarded"
        if f.status == PENDING:
            return "Pending"
        if not f.grids:
            return "Kept"
        sel = sum(g.n_selected for g in f.grids)
        tot = sum(g.n_total for g in f.grids)
        grids = "1 grid" if len(f.grids) == 1 else f"{len(f.grids)} grids"
        return f"{grids} · {sel} of {tot} channels kept"


def _common_prefix(names: List[str]) -> str:
    """Longest shared prefix of the file stems, cut back to an underscore boundary."""
    if len(names) < 2:
        return ""
    stems = [n[:-4] if n.lower().endswith(".mat") else n for n in names]
    prefix = os.path.commonprefix(stems)
    cut = prefix.rfind("_")
    return prefix[:cut + 1] if cut > 0 else ""


_FILTERS = [("All", None), ("Kept", KEPT), ("Discarded", DISCARDED), ("Pending", PENDING)]


class ChannelSelectionSummaryView(QWidget):
    """Summary band + filter bar + scrolling file list."""

    edit_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[_FileRow] = []
        self._status_filter: Optional[str] = None
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.LG)

        root.addWidget(self._build_band())
        root.addLayout(self._build_filter_bar())

        self._list_host = QWidget()
        self._list_host.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)

        self._empty = _label("No files match this filter.", Fonts.SIZE_BASE, Colors.TEXT_MUTED)
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setContentsMargins(0, Spacing.XXL, 0, Spacing.XXL)
        self._empty.setVisible(False)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._list_host)
        scroll.setMinimumHeight(300)
        scroll.setMaximumHeight(560)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {Colors.BG_PRIMARY}; border: 1px solid {Colors.BORDER_DEFAULT};"
            f" border-radius: {BorderRadius.LG}; padding: 0; }}"
        )
        self._scroll = scroll
        root.addWidget(scroll)
        root.addWidget(self._empty)

    # -- construction ----------------------------------------------------------

    def _build_band(self) -> QWidget:
        band = QFrame()
        band.setObjectName("band")
        band.setStyleSheet(
            f"QFrame#band {{ background: {Colors.BG_SECONDARY}; border: 1px solid {Colors.BORDER_MUTED};"
            f" border-radius: {BorderRadius.LG}; padding: 0; }}"
        )
        outer = QVBoxLayout(band)
        outer.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        outer.setSpacing(Spacing.MD)

        figures = QHBoxLayout()
        figures.setSpacing(Spacing.XXXL)
        self._fig = {}
        for key, word, color in ((KEPT, "kept", Colors.GREEN_700), (DISCARDED, "discarded", Colors.RED_600),
                                 (PENDING, "pending", Colors.GRAY_500)):
            col = QVBoxLayout()
            col.setSpacing(0)
            num = _label("0", "26px", color, Fonts.WEIGHT_SEMIBOLD)
            col.addWidget(num)
            col.addWidget(_label(word, Fonts.SIZE_SM, Colors.TEXT_SECONDARY))
            host = QWidget()
            host.setLayout(col)
            host.setStyleSheet("background: transparent; border: none; padding: 0;")
            figures.addWidget(host)
            self._fig[key] = num
        figures.addStretch(1)
        self._channels_label = _label("", Fonts.SIZE_SM, Colors.TEXT_SECONDARY)
        self._channels_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        figures.addWidget(self._channels_label, 0, Qt.AlignBottom)
        outer.addLayout(figures)

        self._bar = _SegmentBar()
        outer.addWidget(self._bar)
        return band

    def _build_filter_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(Spacing.XS)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._filter_buttons = {}
        for text, status in _FILTERS:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(status is None)
            b.setStyleSheet(
                f"QPushButton {{ color: {Colors.TEXT_SECONDARY}; background: transparent; border: 1px solid transparent;"
                f" border-radius: 14px; padding: 4px 14px; font-size: {Fonts.SIZE_SM}; }}"
                f"QPushButton:hover {{ background: {Colors.BG_TERTIARY}; }}"
                f"QPushButton:checked {{ color: {Colors.BLUE_700}; background: {Colors.BLUE_50};"
                f" border-color: {Colors.BLUE_100}; font-weight: {Fonts.WEIGHT_SEMIBOLD}; }}"
            )
            b.clicked.connect(lambda _=False, s=status: self._set_status_filter(s))
            self._group.addButton(b)
            self._filter_buttons[status] = b
            bar.addWidget(b)
        bar.addSpacing(Spacing.LG)
        self._prefix_label = _label("", Fonts.SIZE_SM, Colors.TEXT_MUTED)
        bar.addWidget(self._prefix_label)
        bar.addStretch(1)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by file name")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(240)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {Colors.BG_PRIMARY}; color: {Colors.TEXT_PRIMARY};"
            f" border: 1px solid {Colors.BORDER_DEFAULT}; border-radius: {BorderRadius.MD};"
            f" padding: 5px 10px; font-size: {Fonts.SIZE_SM}; }}"
            f"QLineEdit:focus {{ border-color: {Colors.BLUE_500}; }}"
        )
        self._search.textChanged.connect(lambda _t: self._apply_filter())
        bar.addWidget(self._search)
        return bar

    # -- public ----------------------------------------------------------------

    def set_summaries(self, summaries: List[FileSummary]):
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        prefix = _common_prefix([f.name for f in summaries])
        self._prefix_label.setText(f"All files start with {prefix}" if prefix else "")
        for f in summaries:
            stem = f.name[:-4] if f.name.lower().endswith(".mat") else f.name
            row = _FileRow(f, stem[len(prefix):] or stem)
            row.edit_requested.connect(self.edit_requested)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._rows.append(row)

        counts = {s: sum(1 for f in summaries if f.status == s) for s in (KEPT, DISCARDED, PENDING)}
        for key, num in self._fig.items():
            num.setText(str(counts[key]))
        self._bar.set_counts(counts[KEPT], counts[DISCARDED], counts[PENDING])
        sel = sum(g.n_selected for f in summaries if f.status == KEPT for g in f.grids)
        tot = sum(g.n_total for f in summaries if f.status == KEPT for g in f.grids)
        dropped = tot - sel
        self._channels_label.setText(
            f"{sel} of {tot} channels kept in {counts[KEPT]} files"
            + (f" · {dropped} dropped" if dropped else "") if tot else ""
        )
        self._apply_filter()

    def set_editing(self, editing: bool):
        for row in self._rows:
            btn = getattr(row, "edit_button", None)
            if btn is not None:
                btn.setEnabled(not editing)

    # -- filtering -------------------------------------------------------------

    def _set_status_filter(self, status: Optional[str]):
        self._status_filter = status
        self._apply_filter()

    def _apply_filter(self):
        needle = self._search.text().strip().lower()
        shown = 0
        for row in self._rows:
            f = row.summary
            ok = (self._status_filter is None or f.status == self._status_filter) and needle in f.name.lower()
            row.setVisible(ok)
            shown += ok
        self._empty.setVisible(bool(self._rows) and shown == 0)
        self._scroll.setVisible(shown > 0 or not self._rows)
