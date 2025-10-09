"""
Settings tab for line noise removal configuration.
"""
import os
import sys
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QGroupBox, QPushButton, QProgressBar, QMessageBox
)
from PyQt5.QtCore import Qt

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import Settings, LineNoiseMethod, LineNoiseRegion
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.widgets.LineNoiseInfoDialog import LineNoiseInfoDialog
from hdsemg_pipe.settings.tabs.matlab_installer import MatlabEngineInstallThread


def init(parent):
    """Initialize the line noise removal settings tab."""
    main_layout = QVBoxLayout()

    # Info section
    info_label = QLabel(
        '<b>Line Noise Removal</b> removes powerline interference (50/60 Hz) and harmonics from EMG signals.<br>'
        'Multiple methods are available - see "Methods Info" for detailed comparison.'
    )
    info_label.setWordWrap(True)
    main_layout.addWidget(info_label)

    # Methods Info Button
    info_button = QPushButton("📖 Methods Info (Detailed Comparison)")
    info_button.clicked.connect(lambda: show_methods_info(parent))
    main_layout.addWidget(info_button)

    # Region selection
    region_group = QGroupBox("Power Line Frequency Region")
    region_layout = QVBoxLayout()

    region_label = QLabel("Select your region (determines line frequency):")
    region_layout.addWidget(region_label)

    region_combo = QComboBox()
    region_combo.addItem("🇺🇸 USA/North America (60 Hz)", LineNoiseRegion.US.value)
    region_combo.addItem("🇪🇺 Europe/Asia (50 Hz)", LineNoiseRegion.EU.value)
    region_layout.addWidget(region_combo)

    freq_info_label = QLabel()
    freq_info_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
    region_layout.addWidget(freq_info_label)

    # Set current region
    current_region = config.get(Settings.LINE_NOISE_REGION, LineNoiseRegion.US.value)
    index = region_combo.findData(current_region)
    if index >= 0:
        region_combo.setCurrentIndex(index)

    def update_freq_info(index):
        """Update frequency info label based on selected region."""
        region = region_combo.itemData(index)
        if region == LineNoiseRegion.EU.value:
            freq_info_label.setText("Frequencies: 50, 100, 150, 200 Hz")
        else:
            freq_info_label.setText("Frequencies: 60, 120, 180, 240 Hz")

    update_freq_info(region_combo.currentIndex())
    region_combo.currentIndexChanged.connect(update_freq_info)

    def on_region_changed(index):
        """Save region setting when changed."""
        region = region_combo.itemData(index)
        config.set(Settings.LINE_NOISE_REGION, region)
        logger.info(f"Line noise region changed to: {region}")

    region_combo.currentIndexChanged.connect(on_region_changed)

    region_group.setLayout(region_layout)
    main_layout.addWidget(region_group)

    # Method selection
    method_group = QGroupBox("Line Noise Removal Method")
    method_layout = QVBoxLayout()

    method_label = QLabel("Select the method for line noise removal:")
    method_layout.addWidget(method_label)

    method_combo = QComboBox()
    method_layout.addWidget(method_combo)

    method_info_label = QLabel()
    method_info_label.setWordWrap(True)
    method_info_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 5px;")
    method_layout.addWidget(method_info_label)

    # Availability status labels
    availability_layout = QVBoxLayout()
    availability_layout.setContentsMargins(10, 5, 10, 5)

    mne_status_label = QLabel()
    matlab_status_label = QLabel()
    octave_status_label = QLabel()

    availability_layout.addWidget(QLabel("<b>Installation Status:</b>"))
    availability_layout.addWidget(mne_status_label)
    availability_layout.addWidget(matlab_status_label)
    availability_layout.addWidget(octave_status_label)

    method_layout.addLayout(availability_layout)

    def update_availability_status():
        """Update installation status labels."""
        # MNE is always available (required dependency)
        mne_status_label.setText("✓ MNE-Python: <span style='color:green'>Available</span>")

        # MATLAB status
        matlab_available = config.get(Settings.MATLAB_INSTALLED, False)
        if matlab_available:
            matlab_status_label.setText("✓ MATLAB Engine: <span style='color:green'>Available</span>")
        else:
            matlab_status_label.setText("✗ MATLAB Engine: <span style='color:red'>Not available</span> "
                                       "(License required)")

        # Octave status
        octave_available = config.get(Settings.OCTAVE_INSTALLED, False)
        if octave_available:
            octave_status_label.setText("✓ Octave + oct2py: <span style='color:green'>Available</span>")
        else:
            octave_status_label.setText("✗ Octave + oct2py: <span style='color:red'>Not available</span> "
                                       "(Installation required)")

    def populate_method_combo():
        """Populate method combo box with available methods."""
        method_combo.clear()

        # Always add MNE methods (MNE is a required dependency)
        method_combo.addItem(
            "⚡ MNE-Python: Notch Filter (FIR) - Fast",
            LineNoiseMethod.MNE_NOTCH.value
        )
        method_combo.addItem(
            "⭐ MNE-Python: Spectrum Fit (Adaptive) - Recommended",
            LineNoiseMethod.MNE_SPECTRUM_FIT.value
        )

        # Add MATLAB methods if available
        matlab_available = config.get(Settings.MATLAB_INSTALLED, False)

        # CleanLine (gold standard)
        if matlab_available:
            method_combo.addItem(
                "🏆 MATLAB: CleanLine (EEGLAB Plugin) - Gold Standard",
                LineNoiseMethod.MATLAB_CLEANLINE.value
            )
        else:
            method_combo.addItem(
                "🏆 MATLAB: CleanLine (Not available)",
                LineNoiseMethod.MATLAB_CLEANLINE.value
            )
            model = method_combo.model()
            item = model.item(method_combo.count() - 1)
            item.setEnabled(False)

        # MATLAB IIR
        if matlab_available:
            method_combo.addItem(
                "🔬 MATLAB: IIR Notch Filter",
                LineNoiseMethod.MATLAB_IIR.value
            )
        else:
            method_combo.addItem(
                "🔬 MATLAB: IIR Notch Filter (Not available)",
                LineNoiseMethod.MATLAB_IIR.value
            )
            model = method_combo.model()
            item = model.item(method_combo.count() - 1)
            item.setEnabled(False)

        # Add Octave if available
        octave_available = config.get(Settings.OCTAVE_INSTALLED, False)
        if octave_available:
            method_combo.addItem(
                "🐙 Octave: IIR Notch Filter (Free)",
                LineNoiseMethod.OCTAVE.value
            )
        else:
            method_combo.addItem(
                "🐙 Octave: IIR Notch Filter (Not available)",
                LineNoiseMethod.OCTAVE.value
            )
            model = method_combo.model()
            item = model.item(method_combo.count() - 1)
            item.setEnabled(False)

        # Set current method
        current_method = config.get(Settings.LINE_NOISE_METHOD, LineNoiseMethod.MNE_SPECTRUM_FIT.value)
        index = method_combo.findData(current_method)
        if index >= 0:
            method_combo.setCurrentIndex(index)
        else:
            # Default to MNE Spectrum Fit
            index = method_combo.findData(LineNoiseMethod.MNE_SPECTRUM_FIT.value)
            if index >= 0:
                method_combo.setCurrentIndex(index)

    def update_method_info(index):
        """Update info label based on selected method."""
        method = method_combo.itemData(index)

        info_texts = {
            LineNoiseMethod.MNE_NOTCH.value:
                "FIR Notch Filter: Fast and stable. Removes frequencies in narrow bands. "
                "Good for most applications.",

            LineNoiseMethod.MNE_SPECTRUM_FIT.value:
                "Adaptive Spectrum Fitting: Best quality with minimal distortion. Similar to CleanLine. "
                "Recommended for high-quality analyses.",

            LineNoiseMethod.MATLAB_CLEANLINE.value:
                "MATLAB CleanLine: Gold standard adaptive line noise removal using EEGLAB plugin. "
                "Multi-taper with Thompson F-statistic. Requires MATLAB + EEGLAB + CleanLine plugin. "
                "Best for time-varying line noise.",

            LineNoiseMethod.MATLAB_IIR.value:
                "MATLAB IIR Notch: Native MATLAB implementation. Requires MATLAB license and Engine API. "
                "Good for MATLAB-based workflows.",

            LineNoiseMethod.OCTAVE.value:
                "Octave IIR Notch: MATLAB-compatible and free. Requires Octave installation. "
                "Alternative to MATLAB without license costs."
        }

        method_info_label.setText(info_texts.get(method, ""))

    def on_method_changed(index):
        """Save method setting when changed."""
        method = method_combo.itemData(index)
        config.set(Settings.LINE_NOISE_METHOD, method)
        logger.info(f"Line noise method changed to: {method}")
        update_method_info(index)

    # Initialize
    update_availability_status()
    populate_method_combo()
    update_method_info(method_combo.currentIndex())

    method_combo.currentIndexChanged.connect(on_method_changed)

    method_group.setLayout(method_layout)
    main_layout.addWidget(method_group)

    # MATLAB Engine Installation Section
    matlab_install_group = QGroupBox("MATLAB Engine for Python")
    matlab_install_layout = QVBoxLayout()

    matlab_info_label = QLabel(
        "The MATLAB Engine for Python is required for MATLAB-based methods. "
        "Click the button below to get installation instructions with the correct paths for your system."
    )
    matlab_info_label.setWordWrap(True)
    matlab_install_layout.addWidget(matlab_info_label)

    matlab_status_layout = QHBoxLayout()
    matlab_install_status_label = QLabel()
    matlab_status_layout.addWidget(matlab_install_status_label)

    matlab_install_button = QPushButton("Show Installation Instructions")
    matlab_install_button.setVisible(False)
    matlab_status_layout.addWidget(matlab_install_button)

    matlab_install_layout.addLayout(matlab_status_layout)

    def is_packaged():
        """Check if running as packaged application."""
        return getattr(sys, 'frozen', False)

    def update_matlab_install_status():
        """Update MATLAB Engine installation status display."""
        matlab_available = config.get(Settings.MATLAB_INSTALLED, False)

        if matlab_available:
            matlab_install_status_label.setText(
                'MATLAB Engine: <b style="color:green">Installed</b>'
            )
            matlab_install_button.setVisible(False)
        else:
            matlab_install_status_label.setText(
                'MATLAB Engine: <b style="color:red">Not installed</b>'
            )
            # Show button for installation instructions
            matlab_install_button.setVisible(True)

    def on_matlab_install_clicked():
        """Show installation instructions dialog."""
        from hdsemg_pipe.widgets.MatlabInstallDialog import MatlabInstallDialog

        # Show installation instructions dialog
        # The dialog will find MATLAB asynchronously
        dlg = MatlabInstallDialog(parent)
        dlg.exec_()

    matlab_install_button.clicked.connect(on_matlab_install_clicked)
    update_matlab_install_status()

    matlab_install_group.setLayout(matlab_install_layout)
    main_layout.addWidget(matlab_install_group)

    # Installation instructions
    install_group = QGroupBox("Manual Installation Instructions")
    install_layout = QVBoxLayout()

    install_text = QLabel(
        "<b>MATLAB Engine for Python:</b><br>"
        "• <b>Automatic:</b> Click 'Install MATLAB Engine' button above (requires MATLAB installed)<br>"
        "• <b>Manual Option 1 (In MATLAB):</b><br>"
        "&nbsp;&nbsp;<code>cd(fullfile(matlabroot,'extern','engines','python'))</code><br>"
        "&nbsp;&nbsp;<code>system('python setup.py install')</code><br>"
        "• <b>Manual Option 2 (In Terminal/CMD):</b><br>"
        "&nbsp;&nbsp;<code>cd &lt;matlabroot&gt;/extern/engines/python</code><br>"
        "&nbsp;&nbsp;<code>python setup.py install</code><br><br>"

        "<b>MATLAB CleanLine Plugin (Gold Standard):</b><br>"
        "1. Install MATLAB (license required)<br>"
        "2. Install EEGLAB from <a href='https://sccn.ucsd.edu/eeglab/download.php'>sccn.ucsd.edu</a><br>"
        "3. In EEGLAB: File → Manage EEGLAB extensions → CleanLine<br>"
        "4. Add EEGLAB to MATLAB path (in startup.m or manually)<br><br>"

        "<b>Octave (Free Alternative):</b><br>"
        "1. Install Octave from <a href='https://octave.org/download'>octave.org</a><br>"
        "2. In Terminal/CMD: <code>pip install oct2py</code><br><br>"

        "<small>⚠️ After any installation: Restart application for changes to take effect</small>"
    )
    install_text.setWordWrap(True)
    install_text.setOpenExternalLinks(True)
    install_layout.addWidget(install_text)

    install_group.setLayout(install_layout)
    main_layout.addWidget(install_group)

    # Add stretch to push everything to the top
    main_layout.addStretch()

    return main_layout


def show_methods_info(parent):
    """Show detailed methods information dialog."""
    dialog = LineNoiseInfoDialog(parent)
    dialog.exec_()
