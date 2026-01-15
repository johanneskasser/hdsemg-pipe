import OTBiolabInterface as otb
import OTBiolabClasses as otbClasses
import numpy as np

# Matplotlib OO + Qt canvas (binding-agnostic)
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

# Qt binding shim (PySide6/PySide2/PyQt5)
def _import_qt():
    try:
        from PySide6 import QtWidgets, QtCore, QtGui
        return QtWidgets, QtCore, QtGui, "PySide6"
    except Exception:
        pass
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        return QtWidgets, QtCore, QtGui, "PySide2"
    except Exception:
        pass
    from PyQt5 import QtWidgets, QtCore, QtGui
    return QtWidgets, QtCore, QtGui, "PyQt5"

QtWidgets, QtCore, QtGui, _QT_BINDING = _import_qt()

''' DESCRIPTION 
This script reads RMS-processed tracks, then paginates and visualizes channel quality per selection. It shows 8 channels/rows (change via CHANNELS_PER_PAGE) over 8 columns per window (change via COLS_PER_PAGE) by default,
colors each line by mean (µV) using quality classes (green/blue/orange/magenta/red), shades matching transparent bands,
keeps each row at 0–30 µV. Adjust the V_TO_UV conversion factor if needed.
'''

''' CATEGORY
Amplitude
'''
############################################## PARAMETERS #########################################################
CHANNELS_PER_PAGE = 8         # rows per column
COLS_PER_PAGE = 8             # number of columns side-by-side
V_TO_UV = 1000000           # convert to µV (use 1000 if your RMS are in mV)
###################################################################################################################

############################################# LOADING DATA ########################################################
tracks = otb.LoadDataFromPythonFolder()
###################################################################################################################

############################################## HELPERS ############################################################
def show_error_popup(msg: str, title: str = "Error"):
    """Editable, modal error window (Qt preferred, Tk fallback)."""
    try:
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        dlg = QtWidgets.QDialog(); dlg.setWindowTitle(title); dlg.setModal(True); dlg.resize(900, 500)
        lay = QtWidgets.QVBoxLayout(dlg)
        txt = QtWidgets.QTextEdit(dlg); txt.setAcceptRichText(False); txt.setPlainText(str(msg))
        txt.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)); lay.addWidget(txt)
        row = QtWidgets.QHBoxLayout(); btn_copy = QtWidgets.QPushButton("Copy"); btn_save = QtWidgets.QPushButton("Save…"); btn_close = QtWidgets.QPushButton("Close")
        row.addStretch(1); row.addWidget(btn_copy); row.addWidget(btn_save); row.addWidget(btn_close); lay.addLayout(row)
        btn_copy.clicked.connect(lambda: app.clipboard().setText(txt.toPlainText()))
        def _save():
            fn, _ = QtWidgets.QFileDialog.getSaveFileName(dlg, "Save Error Text", "error.txt", "Text Files (*.txt);;All Files (*)")
            if fn:
                try:
                    with open(fn, "w", encoding="utf-8") as f: f.write(txt.toPlainText())
                except Exception as e:
                    QtWidgets.QMessageBox.critical(dlg, "Save Failed", str(e))
        btn_save.clicked.connect(_save); btn_close.clicked.connect(dlg.accept)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+A"), dlg, activated=lambda: txt.selectAll())
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+C"), dlg, activated=lambda: app.clipboard().setText(txt.toPlainText()))
        QtWidgets.QShortcut(QtGui.QKeySequence("Meta+A"), dlg, activated=lambda: txt.selectAll())
        QtWidgets.QShortcut(QtGui.QKeySequence("Meta+C"), dlg, activated=lambda: app.clipboard().setText(txt.toPlainText()))
        dlg.show(); dlg.raise_(); dlg.activateWindow(); dlg.exec_(); return
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.title(title); root.geometry("900x500"); root.attributes("-topmost", True)
        frm = tk.Frame(root); frm.pack(fill="both", expand=True, padx=6, pady=6)
        txt = tk.Text(frm, wrap="none", undo=True); txt.insert("1.0", str(msg)); txt.configure(font=("Courier New", 10)); txt.pack(side="left", fill="both", expand=True)
        yscroll = tk.Scrollbar(frm, command=txt.yview); yscroll.pack(side="right", fill="y"); txt.config(yscrollcommand=yscroll.set)
        btn_frame = tk.Frame(root); btn_frame.pack(fill="x", padx=6, pady=(0,6))
        def _copy(): root.clipboard_clear(); root.clipboard_append(txt.get("1.0","end-1c"))
        def _save():
            fn = filedialog.asksaveasfilename(title="Save Error Text", defaultextension=".txt", filetypes=[("Text Files","*.txt"),("All Files","*.*")])
            if fn: open(fn,"w",encoding="utf-8").write(txt.get("1.0","end-1c"))
        tk.Button(btn_frame, text="Copy", command=_copy).pack(side="right", padx=4)
        tk.Button(btn_frame, text="Save…", command=_save).pack(side="right", padx=4)
        tk.Button(btn_frame, text="Close", command=root.destroy).pack(side="right", padx=4)
        root.bind("<Control-a>", lambda e: (txt.tag_add("sel","1.0","end"), "break"))
        root.bind("<Command-a>", lambda e: (txt.tag_add("sel","1.0","end"), "break"))
        root.bind("<Control-c>", lambda e: (_copy(), "break"))
        root.bind("<Command-c>", lambda e: (_copy(), "break"))
        root.mainloop(); return
    except Exception:
        pass
    print(f"[ERROR] {title}: {msg}")

def _classify_color(mean_uv: float) -> str:
    if mean_uv <= 5:   return "black"    # excellent
    if mean_uv <= 10:  return "blue"     # good
    if mean_uv <= 15:  return "orange"   # ok
    if mean_uv <= 20:  return "magenta"  # troubled
    return "red"                          # bad

def _draw_quality_bands(ax):
    bands = [
        (0, 5,   "green",   "≤5 µV: excellent"),
        (5, 10,  "lightblue",    "5–10 µV: good"),
        (10, 15, "orange",  "10–15 µV: ok"),
        (15, 20, "magenta", "15–20 µV: troubled"),
        (20, 30, "red",     "≥20 µV: bad"),
    ]
    for low, high, color, _ in bands:
        ax.axhspan(low, high, alpha=0.08, facecolor=color, edgecolor=None)

LEGEND_HANDLES = [
    Patch(facecolor="red",     alpha=0.15, label="≥20 µV: bad"),
    Patch(facecolor="magenta", alpha=0.15, label="15–20 µV: troubled"),
    Patch(facecolor="orange",  alpha=0.15, label="10–15 µV: ok"),
    Patch(facecolor="lightblue",    alpha=0.15, label="5–10 µV: good"),
    Patch(facecolor="green",   alpha=0.15, label="≤5 µV: excellent"),
]

def _new_page_figure(rows: int, cols: int):
    """Create a Figure with a grid (rows x cols). Share x within each column."""
    fig = Figure(figsize=(12.5, max(2.2, rows * 1.05)))  # a touch wider for column spacing + legend
    axes = [[None for _ in range(cols)] for _ in range(rows)]
    for c in range(cols):
        for r in range(rows):
            if r == 0:
                ax = fig.add_subplot(rows, cols, r*cols + c + 1)
            else:
                ax = fig.add_subplot(rows, cols, r*cols + c + 1, sharex=axes[0][c])
            axes[r][c] = ax
    # Add more horizontal space between columns; keep room for legend on the right
    fig.subplots_adjust(hspace=0.005, wspace=0.25, right=0.80, top=0.90)
    return fig, axes  # 2D list [row][col]

def _show_page_qt(fig: Figure, window_title: str):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = QtWidgets.QDialog()
    dialog.setWindowTitle(window_title)
    dialog.setModal(True)
    layout = QtWidgets.QVBoxLayout(dialog)
    canvas = FigureCanvas(fig)
    layout.addWidget(canvas)
    dialog.showMaximized()
    canvas.draw()
    dialog.exec_()

############################################## PLOTTING (grid pages) ##############################################
for t_idx, track in enumerate(tracks):
    for s_idx, section in enumerate(track.sections):
        channels = section.channels
        n_ch = len(channels)
        if n_ch == 0:
            continue

        # ---- Section-wide stats over ALL channels ----
        try:
            all_means = []
            for ch in channels:
                vals_uv_all = np.asarray(ch.data, dtype=float) * V_TO_UV
                all_means.append(float(np.nanmean(vals_uv_all)) if vals_uv_all.size else 0.0)
            all_means_arr = np.asarray(all_means, dtype=float)
            sec_mu  = float(np.nanmean(all_means_arr)) if all_means_arr.size else 0.0
            sec_sd  = float(np.nanstd(all_means_arr, ddof=1)) if all_means_arr.size > 1 else 0.0
            sec_min = float(np.nanmin(all_means_arr)) if all_means_arr.size else 0.0
            sec_max = float(np.nanmax(all_means_arr)) if all_means_arr.size else 0.0
            sec_n_good     = int(np.sum(all_means_arr < 10))
            sec_n_maybe    = int(np.sum((all_means_arr >= 10) & (all_means_arr < 15)))
            sec_n_intermed = int(np.sum((all_means_arr >= 15) & (all_means_arr < 20)))
            sec_n_notacc   = int(np.sum(all_means_arr >= 20))
            stats_txt_global = (
                f"Overall channel stats: μ={sec_mu:.1f} µV, σ={sec_sd:.1f} µV, "
                f"min={sec_min:.1f} µV, max={sec_max:.1f} µV\n"
                f"Counts: good Ch. ≤10 µV: {sec_n_good}, ok Ch. 10-15 µV : {sec_n_maybe}, troubled Ch. 15-20 µV: {sec_n_intermed}, bad Ch. ≥20 µV: {sec_n_notacc}"
            )
        except Exception:
            import traceback
            show_error_popup("While computing global stats:\n\n" + "".join(traceback.format_exc()),
                             title=f"Stats error (Track {t_idx+1}, Section {s_idx+1})")
            stats_txt_global = "Overall channel stats: n/a"

        # ---- Pagination over grid capacity ----
        PER_PAGE = CHANNELS_PER_PAGE * COLS_PER_PAGE
        for page_start in range(0, n_ch, PER_PAGE):
            page_end = min(page_start + PER_PAGE, n_ch)
            subset = channels[page_start:page_end]
            count = len(subset)

            try:
                # Precompute arrays and means
                ch_vals = []
                ch_means = []
                for ch in subset:
                    vals_uv = np.asarray(ch.data, dtype=float) * V_TO_UV
                    ch_vals.append(vals_uv)
                    ch_means.append(float(np.nanmean(vals_uv)) if vals_uv.size else 0.0)

                # Figure & axes grid
                fig, axes_grid = _new_page_figure(CHANNELS_PER_PAGE, COLS_PER_PAGE)

                # Legend on the right
                fig.legend(handles=LEGEND_HANDLES, loc="center left",
                           bbox_to_anchor=(0.82, 0.5), frameon=False)

                # Map each channel in this page to (row, col)
                for idx_within_page in range(PER_PAGE):
                    r = idx_within_page % CHANNELS_PER_PAGE     # fill down rows first
                    c = idx_within_page // CHANNELS_PER_PAGE     # then across columns
                    ax = axes_grid[r][c]

                    global_idx = page_start + idx_within_page
                    if idx_within_page >= count:
                        ax.set_visible(False)
                        continue

                    vals_uv = ch_vals[idx_within_page]
                    mean_uv = ch_means[idx_within_page]
                    ch_number = global_idx + 1
                    x = np.arange(len(vals_uv))

                    _draw_quality_bands(ax)
                    ax.plot(x, vals_uv, linewidth=1.25, color=_classify_color(mean_uv))

                    # Cosmetics
                    ax.set_ylim(0, 30)
                    ax.set_yticks(np.arange(0, 30, 5))  # 0..25 (no 30 label)

                    # Show y tick labels only on the leftmost column
                    if c == 0:
                        ax.tick_params(axis="y", which="both", labelleft=True)
                    else:
                        ax.tick_params(axis="y", which="both", labelleft=False)

                    # Top-left channel label (keep axes joined)
                    ax.text(0.01, 0.98, f"Ch. {ch_number}",
                            transform=ax.transAxes, ha="left", va="top", fontsize=9)

                    ax.grid(True, which="both", axis="y", alpha=0.2, linestyle="--")

                    # Mean annotation at right
                    ax.text(0.995, 0.5, f"{mean_uv:.1f} µV",
                            transform=ax.transAxes, ha="right", va="center",
                            fontsize=8, color=_classify_color(mean_uv))

                    # Only bottom row in each column gets an x-label
                    if r == CHANNELS_PER_PAGE - 1:
                        ax.set_xlabel("Samples (epoch index)")

                # Page/Title
                page_num = page_start // PER_PAGE + 1
                total_pages = (n_ch + PER_PAGE - 1) // PER_PAGE
                fig.suptitle(
                    f"RMS Quality (µV) — {track.title} — Section {s_idx+1} — "
                    f"Channels {page_start+1}-{page_end} of {n_ch} (Page {page_num}/{total_pages})\n"
                    f"{stats_txt_global}",
                    y=0.96, fontsize=11
                )

                # Show page (Qt dialog, fullscreen/maximized)
                _show_page_qt(fig, window_title=f"{track.title} — Section {s_idx+1} — Page {page_num}/{total_pages}")

            except Exception:
                import traceback
                tb = "".join(traceback.format_exc())
                show_error_popup(tb, title=f"Plot error (Track {t_idx+1}, Section {s_idx+1})")

############################################ WRITE DATA ###########################################################
otb.WriteDataInPythonFolder(tracks)
###################################################################################################################
