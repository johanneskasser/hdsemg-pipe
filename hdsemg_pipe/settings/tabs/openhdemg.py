import os
import sys

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox, QFrame
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.settings.tabs.installer import InstallThread
from hdsemg_pipe.ui_elements.theme import Colors, Spacing, BorderRadius, Fonts, Styles


def is_packaged():
    return getattr(sys, 'frozen', False)


def is_openhdemg_installed():
    return config.get(Settings.OPENHDEMG_INSTALLED, False)


def init(parent):
    """Initialize the openhdemg settings tab with modern styling."""
    layout = QVBoxLayout()
    layout.setSpacing(Spacing.LG)
    layout.setContentsMargins(0, 0, 0, 0)

    # Header section
    header = QLabel("openhdemg Integration")
    header.setStyleSheet(f"""
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_XL};
            font-weight: {Fonts.WEIGHT_BOLD};
            margin-bottom: {Spacing.SM}px;
        }}
    """)
    layout.addWidget(header)

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
    info_layout.setSpacing(Spacing.SM)

    info_label = QLabel(
        '<b>What is openhdemg?</b><br>'
        'openhdemg is an open-source Python library for analyzing High-Density Electromyography (HD-EMG) '
        'recordings. It provides tools for motor unit decomposition, signal processing, and visualization.'
    )
    info_label.setWordWrap(True)
    info_label.setStyleSheet(f"""
        QLabel {{
            color: {Colors.BLUE_900};
            font-size: {Fonts.SIZE_BASE};
            background: transparent;
            border: none;
        }}
    """)
    info_layout.addWidget(info_label)

    citation = QLabel(
        '📄 Reference: <a href="https://doi.org/10.1016/j.jelekin.2023.102850" style="color: #2563eb;">Valli et al. (2024)</a>'
    )
    citation.setOpenExternalLinks(True)
    citation.setStyleSheet(f"""
        QLabel {{
            color: {Colors.BLUE_700};
            font-size: {Fonts.SIZE_SM};
            background: transparent;
            border: none;
        }}
    """)
    info_layout.addWidget(citation)

    requirement_note = QLabel(
        '⚠️ <b>Required:</b> This package is necessary to complete the decomposition pipeline.'
    )
    requirement_note.setStyleSheet(f"""
        QLabel {{
            color: {Colors.BLUE_900};
            font-size: {Fonts.SIZE_SM};
            font-weight: {Fonts.WEIGHT_MEDIUM};
            background: transparent;
            border: none;
            margin-top: {Spacing.SM}px;
        }}
    """)
    info_layout.addWidget(requirement_note)

    layout.addWidget(info_frame)

    # Status section
    status_frame = QFrame()
    status_frame.setStyleSheet(Styles.card())
    status_frame_layout = QVBoxLayout(status_frame)
    status_frame_layout.setSpacing(Spacing.MD)

    status_header = QLabel("Installation Status")
    status_header.setStyleSheet(f"""
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_LG};
            font-weight: {Fonts.WEIGHT_SEMIBOLD};
        }}
    """)
    status_frame_layout.addWidget(status_header)

    status_layout = QHBoxLayout()
    status_layout.setSpacing(Spacing.MD)
    status_label = QLabel()
    status_label.setStyleSheet(f"font-size: {Fonts.SIZE_BASE};")
    status_layout.addWidget(status_label)
    status_layout.addStretch()

    install_button = QPushButton('Install openhdemg')
    install_button.setStyleSheet(Styles.button_primary())
    install_button.setVisible(False)
    status_layout.addWidget(install_button)

    progress_bar = QProgressBar()
    progress_bar.setStyleSheet(Styles.progress_bar())
    progress_bar.setVisible(False)
    status_layout.addWidget(progress_bar)

    status_frame_layout.addLayout(status_layout)
    layout.addWidget(status_frame)

    layout.addStretch()

    def update_status():
        if is_openhdemg_installed():
            status_label.setText(f'✓ <span style="color: {Colors.GREEN_700}; font-weight: {Fonts.WEIGHT_SEMIBOLD};">Installed</span>')
            install_button.setVisible(False)
            progress_bar.setVisible(False)
        else:
            status_label.setText(f'✕ <span style="color: {Colors.RED_700}; font-weight: {Fonts.WEIGHT_SEMIBOLD};">Not Installed</span>')
            if not is_packaged():
                install_button.setVisible(True)
            else:
                install_button.setVisible(False)
            progress_bar.setVisible(False)

    def on_install_clicked():
        install_button.setEnabled(False)
        progress_bar.setVisible(True)
        progress_bar.setRange(0, 0)
        status_label.setText("Installing …")

        thread = InstallThread("openhdemg", parent=parent)
        parent._installer_thread = thread  # Store the thread in the parent to keep it alive
        thread.finished.connect(handle_result)
        thread.finished.connect(lambda *_: thread.deleteLater())
        thread.start()

    def handle_result(success, msg):
        progress_bar.setVisible(False)
        install_button.setEnabled(True)
        if success:
            config.set(Settings.OPENHDEMG_INSTALLED, True)
            status_label.setText(f'✓ <span style="color: {Colors.GREEN_700}; font-weight: {Fonts.WEIGHT_SEMIBOLD};">Installation Successful</span>')
            dlg = QMessageBox(parent)
            dlg.setIcon(QMessageBox.Information)
            dlg.setWindowTitle("Installation Successful - Application restart required")
            dlg.setText("The package <b>openhdemg</b> has been installed successfully.\n"
                        "Please restart the application for the changes to take effect.")
            restart_btn = dlg.addButton("Restart Now", QMessageBox.AcceptRole)
            dlg.addButton("Restart Later", QMessageBox.RejectRole)
            dlg.exec_()
            if dlg.clickedButton() == restart_btn:
                logger.info("Restarting application after openhdemg installation (User Choice).")
                os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            config.set(Settings.OPENHDEMG_INSTALLED, False)
            status_label.setText(f'✕ <span style="color: {Colors.RED_700};">Installation failed: {msg}</span>')
        update_status()  # still safe – we're back on the GUI thread

    install_button.clicked.connect(on_install_clicked)
    update_status()
    return layout
