"""
MUEdit Configuration Settings Tab.

This tab allows users to configure MUEdit integration settings including:
- Launch method (AUTO, MATLAB Engine, MATLAB CLI, Standalone)
- Automated vs Manual workflow mode
- MUEdit installation path
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QGroupBox, QRadioButton, QCheckBox,
    QMessageBox, QFrame
)
from PyQt5.QtCore import Qt

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import Settings, MUEditLaunchMethod
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.ui_elements.theme import Styles, Colors, Spacing, BorderRadius


def init(parent):
    """
    Initialize the MUEdit settings tab.

    Args:
        parent (QWidget): The parent widget.

    Returns:
        QVBoxLayout: The initialized settings tab layout.
    """
    layout = QVBoxLayout()
    layout.setSpacing(Spacing.LG)

    # Header section
    header_label = QLabel(
        "<h2>MUEdit Configuration</h2>"
        "Configure MUEdit for manual cleaning of motor unit decomposition results."
    )
    header_label.setWordWrap(True)
    header_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; padding-bottom: 10px;")
    layout.addWidget(header_label)

    # Info section
    info_frame = QFrame()
    info_frame.setStyleSheet(f"""
        QFrame {{
            background-color: {Colors.BLUE_50};
            border: 1px solid {Colors.BLUE_500};
            border-radius: {BorderRadius.MD};
            padding: {Spacing.MD}px;
        }}
    """)
    info_layout = QVBoxLayout(info_frame)
    info_text = QLabel(
        "<b>About MUEdit:</b><br>"
        "MUEdit is a MATLAB-based tool for manual cleaning and quality control of "
        "motor unit decomposition results. It provides visual inspection and editing capabilities.<br><br>"
        "<b>Repository:</b> <a href='https://github.com/haripen/MUedit/tree/devHP'>MUEdit on GitHub</a>"
    )
    info_text.setOpenExternalLinks(True)
    info_text.setWordWrap(True)
    info_text.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
    info_layout.addWidget(info_text)
    layout.addWidget(info_frame)

    # ========== MUEdit Path Configuration ==========
    path_group = QGroupBox("MUEdit Installation Path")
    path_group.setStyleSheet(f"""
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            margin-top: 10px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }}
    """)
    path_layout = QVBoxLayout()

    path_desc = QLabel(
        "Specify the folder containing MUEdit MATLAB files (e.g., MUedit_exported.m).<br>"
        "This path will be added to MATLAB's search path when launching MUEdit."
    )
    path_desc.setWordWrap(True)
    path_desc.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-weight: normal; font-size: 12px;")
    path_layout.addWidget(path_desc)

    path_input_layout = QHBoxLayout()
    path_input = QLineEdit()
    path_input.setPlaceholderText("Path to MUEdit folder (optional)")
    path_input.setStyleSheet(Styles.input_field())

    # Load current path
    current_path = config.get(Settings.MUEDIT_PATH)
    if current_path:
        path_input.setText(current_path)

    browse_button = QPushButton("Browse...")
    browse_button.setStyleSheet(Styles.button_secondary())

    def browse_path():
        folder = QFileDialog.getExistingDirectory(
            parent,
            "Select MUEdit Installation Folder",
            path_input.text() or os.path.expanduser("~")
        )
        if folder:
            path_input.setText(folder)
            config.set(Settings.MUEDIT_PATH, folder)
            logger.info(f"MUEdit path set to: {folder}")
            QMessageBox.information(parent, "Path Saved", f"MUEdit path saved:\n{folder}")

    browse_button.clicked.connect(browse_path)

    path_input_layout.addWidget(path_input, stretch=1)
    path_input_layout.addWidget(browse_button)
    path_layout.addLayout(path_input_layout)

    # Save path on text change
    def save_path():
        path = path_input.text().strip()
        if path:
            config.set(Settings.MUEDIT_PATH, path)
            logger.info(f"MUEdit path updated: {path}")

    path_input.editingFinished.connect(save_path)

    path_group.setLayout(path_layout)
    layout.addWidget(path_group)

    # ========== Launch Method Configuration ==========
    launch_group = QGroupBox("Launch Method")
    launch_group.setStyleSheet(f"""
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            margin-top: 10px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }}
    """)
    launch_layout = QVBoxLayout()

    launch_desc = QLabel(
        "Select how MUEdit should be launched. 'AUTO' tries all available methods automatically."
    )
    launch_desc.setWordWrap(True)
    launch_desc.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-weight: normal; font-size: 12px;")
    launch_layout.addWidget(launch_desc)

    # Radio buttons for launch method
    radio_auto = QRadioButton("AUTO - Automatic detection (recommended)")
    radio_matlab_engine = QRadioButton("MATLAB Engine API - Reuse existing MATLAB session")
    radio_matlab_cli = QRadioButton("MATLAB CLI - Start new MATLAB process")
    radio_standalone = QRadioButton("Standalone - Run MUEdit as executable")

    # Style radio buttons
    radio_style = f"QRadioButton {{ color: {Colors.TEXT_PRIMARY}; font-weight: normal; }}"
    radio_auto.setStyleSheet(radio_style)
    radio_matlab_engine.setStyleSheet(radio_style)
    radio_matlab_cli.setStyleSheet(radio_style)
    radio_standalone.setStyleSheet(radio_style)

    # Load current setting
    current_method = config.get(Settings.MUEDIT_LAUNCH_METHOD)
    if current_method == MUEditLaunchMethod.MATLAB_ENGINE.value:
        radio_matlab_engine.setChecked(True)
    elif current_method == MUEditLaunchMethod.MATLAB_CLI.value:
        radio_matlab_cli.setChecked(True)
    elif current_method == MUEditLaunchMethod.STANDALONE.value:
        radio_standalone.setChecked(True)
    else:
        radio_auto.setChecked(True)  # Default

    def update_launch_method():
        if radio_auto.isChecked():
            method = MUEditLaunchMethod.AUTO.value
        elif radio_matlab_engine.isChecked():
            method = MUEditLaunchMethod.MATLAB_ENGINE.value
        elif radio_matlab_cli.isChecked():
            method = MUEditLaunchMethod.MATLAB_CLI.value
        else:
            method = MUEditLaunchMethod.STANDALONE.value

        config.set(Settings.MUEDIT_LAUNCH_METHOD, method)
        logger.info(f"MUEdit launch method set to: {method}")

    radio_auto.toggled.connect(update_launch_method)
    radio_matlab_engine.toggled.connect(update_launch_method)
    radio_matlab_cli.toggled.connect(update_launch_method)
    radio_standalone.toggled.connect(update_launch_method)

    launch_layout.addWidget(radio_auto)
    launch_layout.addWidget(radio_matlab_engine)
    launch_layout.addWidget(radio_matlab_cli)
    launch_layout.addWidget(radio_standalone)

    # Method descriptions
    method_info = QLabel(
        "<b>Method Details:</b><br>"
        "• <b>AUTO:</b> Tries MATLAB Engine → MATLAB CLI → Standalone<br>"
        "• <b>MATLAB Engine:</b> Best option - can reuse existing MATLAB sessions (requires <code>pip install matlabengine</code>)<br>"
        "• <b>MATLAB CLI:</b> Starts new MATLAB process (requires MATLAB in PATH)<br>"
        "• <b>Standalone:</b> Assumes MUEdit is compiled as standalone executable"
    )
    method_info.setWordWrap(True)
    method_info.setStyleSheet(f"""
        QLabel {{
            color: {Colors.TEXT_MUTED};
            font-weight: normal;
            font-size: 11px;
            padding: 10px;
            background-color: {Colors.BG_SECONDARY};
            border-radius: {BorderRadius.SM};
            margin-top: 10px;
        }}
    """)
    launch_layout.addWidget(method_info)

    launch_group.setLayout(launch_layout)
    layout.addWidget(launch_group)

    # ========== Workflow Information ==========
    workflow_info = QFrame()
    workflow_info.setStyleSheet(f"""
        QFrame {{
            background-color: {Colors.BLUE_50};
            border: 1px solid {Colors.BLUE_500};
            border-radius: {BorderRadius.MD};
            padding: {Spacing.MD}px;
        }}
    """)
    workflow_info_layout = QVBoxLayout(workflow_info)

    workflow_title = QLabel("<b>Manual Workflow</b>")
    workflow_title.setStyleSheet(f"color: {Colors.BLUE_700}; font-size: 14px;")
    workflow_info_layout.addWidget(workflow_title)

    workflow_text = QLabel(
        "When you click 'Open MUEdit', the application will:<br>"
        "• Launch MUEdit GUI for manual inspection and editing<br>"
        "• Show an instruction dialog with the next file to process<br>"
        "• Provide a copyable file path for easy loading in MUEdit<br>"
        "• Automatically detect when you save edited files<br>"
        "• Update progress tracking in real-time<br>"
        "• Guide you through processing all files sequentially"
    )
    workflow_text.setWordWrap(True)
    workflow_text.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px;")
    workflow_info_layout.addWidget(workflow_text)

    layout.addWidget(workflow_info)

    # ========== Help Section ==========
    help_frame = QFrame()
    help_frame.setStyleSheet(f"""
        QFrame {{
            background-color: {Colors.GRAY_50};
            border: 1px solid {Colors.BORDER_MUTED};
            border-radius: {BorderRadius.MD};
            padding: {Spacing.MD}px;
        }}
    """)
    help_layout = QVBoxLayout(help_frame)

    help_title = QLabel("<b>Need Help?</b>")
    help_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
    help_layout.addWidget(help_title)

    help_text = QLabel(
        "• Recommended: Install MATLAB Engine for best performance: <code>pip install matlabengine</code><br>"
        "• Ensure MUEdit files are accessible in the specified path<br>"
        "• Check MATLAB is installed and in PATH if using CLI mode<br>"
        "• The app monitors the folder and updates progress when edited files are saved<br>"
        "• Visit <a href='https://github.com/haripen/MUedit/tree/devHP'>MUEdit GitHub</a> for installation instructions"
    )
    help_text.setOpenExternalLinks(True)
    help_text.setWordWrap(True)
    help_text.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
    help_layout.addWidget(help_text)

    layout.addWidget(help_frame)

    # Add stretch to push everything to top
    layout.addStretch()

    return layout
