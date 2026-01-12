import os
import sys

from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox, QFrame

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.settings.tabs.installer import InstallThread


def is_packaged():
    return getattr(sys, 'frozen', False)


def is_hdsemg_select_installed():
    return config.get(Settings.HDSEMG_SELECT_INSTALLED, False)


def init(parent):
    """Initialize the Channel Selection settings tab."""
    layout = QVBoxLayout()
    layout.setSpacing(10)
    layout.setContentsMargins(0, 0, 0, 0)

    # Header section
    header = QLabel("Channel Selection App")
    layout.addWidget(header)

    # Info section
    info_frame = QFrame()
    info_frame.setFrameShape(QFrame.StyledPanel)
    info_layout = QVBoxLayout(info_frame)
    info_layout.setSpacing(8)

    info_label = QLabel(
        '<b>What is hdsemg-select?</b><br>'
        'The <b>hdsemg-select</b> package provides advanced algorithms for automatic channel selection '
        'in HD-sEMG recordings. It helps identify the most relevant electrode channels for further analysis.'
    )
    info_label.setWordWrap(True)
    info_layout.addWidget(info_label)

    learn_more = QLabel(
        'Learn more: <a href="https://github.com/johanneskasser/hdsemg-select">GitHub Repository</a>'
    )
    learn_more.setOpenExternalLinks(True)
    info_layout.addWidget(learn_more)

    layout.addWidget(info_frame)

    # Status section
    status_frame = QFrame()
    status_frame.setFrameShape(QFrame.StyledPanel)
    status_frame_layout = QVBoxLayout(status_frame)
    status_frame_layout.setSpacing(10)

    status_header = QLabel("Installation Status")
    status_frame_layout.addWidget(status_header)

    status_layout = QHBoxLayout()
    status_layout.setSpacing(10)
    status_label = QLabel()
    status_layout.addWidget(status_label)
    status_layout.addStretch()

    install_button = QPushButton('Install hdsemg-select')
    install_button.setVisible(False)
    status_layout.addWidget(install_button)

    progress_bar = QProgressBar()
    progress_bar.setVisible(False)
    status_layout.addWidget(progress_bar)

    status_frame_layout.addLayout(status_layout)
    layout.addWidget(status_frame)

    layout.addStretch()

    def update_status():
        if is_hdsemg_select_installed():
            status_label.setText('✓ <span style="color: green;">Installed</span>')
            install_button.setVisible(False)
            progress_bar.setVisible(False)
        else:
            status_label.setText('✕ <span style="color: red;">Not Installed</span>')
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

        thread = InstallThread("hdsemg-select", parent=parent)
        parent._installer_thread = thread  # Store the thread in the parent to keep it alive
        thread.finished.connect(handle_result)
        thread.finished.connect(lambda *_: thread.deleteLater())
        thread.start()

    def handle_result(success, msg):
        progress_bar.setVisible(False)
        install_button.setEnabled(True)
        if success:
            config.set(Settings.HDSEMG_SELECT_INSTALLED, True)
            status_label.setText('✓ <span style="color: green;">Installation Successful</span>')
            dlg = QMessageBox(parent)
            dlg.setIcon(QMessageBox.Information)
            dlg.setWindowTitle("Installation Successful - Application restart required")
            dlg.setText("The package <b>hdsemg-select</b> has been installed successfully.\n"
                        "Please restart the application for the changes to take effect.")
            restart_btn = dlg.addButton("Restart Now", QMessageBox.AcceptRole)
            dlg.addButton("Restart Later", QMessageBox.RejectRole)
            dlg.exec_()
            if dlg.clickedButton() == restart_btn:
                logger.info("Restarting application after hdsemg-select installation (User Choice).")
                os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            config.set(Settings.HDSEMG_SELECT_INSTALLED, False)
            status_label.setText(f'✕ <span style="color: red;">Installation failed: {msg}</span>')
        update_status()  # still safe – we're back on the GUI thread

    install_button.clicked.connect(on_install_clicked)
    update_status()
    return layout
