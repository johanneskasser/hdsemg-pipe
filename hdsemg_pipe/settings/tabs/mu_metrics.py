"""Settings tab for MU quality metric computation backend."""

from PyQt5.QtWidgets import QVBoxLayout, QLabel, QComboBox, QGroupBox

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import MuMetricBackend, Settings
from hdsemg_pipe.config.config_manager import config


def init(parent):  # noqa: ARG001
    """Initialize the MU Metrics settings tab."""
    main_layout = QVBoxLayout()

    intro = QLabel(
        "<b>MU Quality Metric Computation</b><br>"
        "Choose the implementation used to compute SIL, PNR and CoVISI "
        "for all motor unit quality steps (Step 9 — MU Quality Review, "
        "Step 11 — CoVISI Post-Validation)."
    )
    intro.setWordWrap(True)
    main_layout.addWidget(intro)

    # Backend selection
    backend_group = QGroupBox("Metric Computation Backend")
    backend_layout = QVBoxLayout()

    combo = QComboBox()
    combo.addItem(
        "motor_unit_toolbox  (Scientific default — Negro 2016)",
        MuMetricBackend.MOTOR_UNIT_TOOLBOX.value,
    )
    combo.addItem(
        "openhdemg  (Per-MU implementation)",
        MuMetricBackend.OPENHDEMG.value,
    )
    backend_layout.addWidget(combo)

    # Description label updated on selection change
    desc_label = QLabel()
    desc_label.setWordWrap(True)
    desc_label.setStyleSheet("color: #555; font-style: italic; padding: 4px 0;")
    backend_layout.addWidget(desc_label)

    _DESCRIPTIONS = {
        MuMetricBackend.MOTOR_UNIT_TOOLBOX.value: (
            "Uses <b>motor_unit_toolbox</b> (Irene Mendez Guerra) — a validated, "
            "peer-reviewed implementation that processes all MUs in a single matrix "
            "call. CoVISI additionally filters physiologically implausible ISIs "
            "(&lt; 4 Hz / &gt; 50 Hz) per Negro (2016). Installed as part of scd-edition."
        ),
        MuMetricBackend.OPENHDEMG.value: (
            "Uses <b>openhdemg</b>'s built-in <code>compute_sil()</code> / "
            "<code>compute_pnr()</code> functions on a per-MU basis. CoVISI is "
            "computed from raw ISI std/mean without physiological filtering. "
            "Requires openhdemg to be installed."
        ),
    }

    def update_desc(index):
        key = combo.itemData(index)
        desc_label.setText(_DESCRIPTIONS.get(key, ""))

    # Availability status
    status_group = QGroupBox("Installation Status")
    status_layout = QVBoxLayout()

    try:
        from motor_unit_toolbox.props import get_silhouette_measure  # noqa: F401
        toolbox_ok = True
    except ImportError:
        toolbox_ok = False

    openhdemg_ok = config.get(Settings.OPENHDEMG_INSTALLED, False)

    toolbox_lbl = QLabel(
        "motor_unit_toolbox: "
        + ("<span style='color:green'>Available</span>" if toolbox_ok
           else "<span style='color:red'>Not installed</span>")
    )
    openhdemg_lbl = QLabel(
        "openhdemg: "
        + ("<span style='color:green'>Available</span>" if openhdemg_ok
           else "<span style='color:orange'>Not detected</span> "
                "(some metrics will return N/A)")
    )
    toolbox_lbl.setTextFormat(1)   # Qt.RichText
    openhdemg_lbl.setTextFormat(1)
    status_layout.addWidget(toolbox_lbl)
    status_layout.addWidget(openhdemg_lbl)
    status_group.setLayout(status_layout)

    # Wire combo
    current = config.get(
        Settings.MU_METRIC_BACKEND, MuMetricBackend.MOTOR_UNIT_TOOLBOX.value
    )
    idx = combo.findData(current)
    if idx >= 0:
        combo.setCurrentIndex(idx)

    def on_changed(index):
        value = combo.itemData(index)
        config.set(Settings.MU_METRIC_BACKEND, value)
        logger.info("MU metric backend changed to: %s", value)
        update_desc(index)

    combo.currentIndexChanged.connect(on_changed)
    update_desc(combo.currentIndex())

    backend_layout.addWidget(status_group)
    backend_group.setLayout(backend_layout)
    main_layout.addWidget(backend_group)

    note = QLabel(
        "<small>Changes take effect immediately for the next validation run. "
        "No restart required.</small>"
    )
    note.setWordWrap(True)
    note.setTextFormat(1)
    main_layout.addWidget(note)

    main_layout.addStretch()
    return main_layout
