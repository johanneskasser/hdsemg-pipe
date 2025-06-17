import os
import sys

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox
)

from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import Settings
from hdsemg_pipe.config.config_manager import config
from hdsemg_pipe.settings.tabs.installer import InstallThread


def is_packaged():
    return getattr(sys, 'frozen', False)


def is_openhdemg_installed():
    return config.get(Settings.OPENHDEMG_INSTALLED, False)


def init(parent):
    """
    Initialize the OpenHD-EMG settings tab.

    Args:
        parent (QWidget): The parent widget.

    Returns:
        QWidget: The initialized settings tab widget.
    """
    layout = QVBoxLayout()

    # Information label
    info_label = QLabel(
        "openhdemg is an open-source project to analyse HD-EMG recordings [<a href=\"https://doi.org/10.1016/j.jelekin.2023.102850\">Valli et al. 2024</a>].<br>"
        "The openhdemg package is required to complete the decomposition pipline and proceed.<br>"
        "If you have not installed it yet, please click the button below to install it.<br>"
    )
    info_label.setOpenExternalLinks(True)
    layout.addWidget(info_label)

    status_layout = QHBoxLayout()
    status_label = QLabel()
    status_layout.addWidget(status_label)
    install_button = QPushButton('Install openhdemg')
    install_button.setVisible(False)
    status_layout.addWidget(install_button)
    progress_bar = QProgressBar()
    progress_bar.setVisible(False)
    status_layout.addWidget(progress_bar)
    layout.addLayout(status_layout)

    def update_status():
        if is_openhdemg_installed():
            status_label.setText('openhdemg is <b style="color:green">installed</b>.')
            install_button.setVisible(False)
            progress_bar.setVisible(False)
        else:
            status_label.setText('openhdemg is <b style="color:red">not installed</b>.')
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
            status_label.setText(
                'openhdemg <b style="color:green">installed successfully</b>.'
            )
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
            status_label.setText(
                f'Installation failed: <span style="color:red">{msg}</span>'
            )
        update_status()  # still safe – we’re back on the GUI thread

    install_button.clicked.connect(on_install_clicked)
    update_status()
    return layout
