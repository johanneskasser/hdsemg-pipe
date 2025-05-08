import traceback
import platform

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QApplication, QStyle, QPushButton

from _log.log_config import logger


def exception_hook(exc_type, exc_value, exc_traceback):
    """
    Custom exception hook to handle uncaught exceptions.
    """
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.error("Uncaught exception: %s", tb)

    dlg = QMessageBox()
    dlg.setWindowTitle("Unexpected Error")
    dlg.setTextFormat(Qt.RichText)
    dlg.setText(
        "An unexpected error occurred.<br>Please report this issue to the developers <a href='https://github.com/johanneskasser/hdsemg-pipe/issues'>here</a> and append the detailed log report below.")
    dlg.setTextInteractionFlags(Qt.TextBrowserInteraction)
    informative_text = _build_detailed_text(exc_value, exc_traceback, exc_type)
    #dlg.setInformativeText(informative_text)
    dlg.setDetailedText(informative_text)
    dlg.setIcon(QMessageBox.Critical)

    copy_informative_text_button = QPushButton(QApplication.style().standardIcon(QStyle.SP_FileDialogDetailedView),
                                               "Copy Informative Text")
    dlg.addButton(copy_informative_text_button, QMessageBox.ActionRole)
    copy_informative_text_button.setAutoDefault(False)
    copy_informative_text_button.setDefault(False)
    copy_informative_text_button.clicked.connect(lambda: QApplication.clipboard().setText(informative_text))
    dlg.setStandardButtons(QMessageBox.Ok)
    dlg.exec_()

def _build_detailed_text(exec_value, tb, exc_type):
    """
    Build an informative text for the error message box.
    """
    exec_value_str = ""
    # Append host machine information
    host_info = f"==== Host Information ====\nSystem: {platform.system()}\nNode: {platform.node()}\nRelease: {platform.release()}\nVersion: {platform.version()}\nMachine: {platform.machine()}\nProcessor: {platform.processor()}\n"
    exec_value_str += host_info

    exec_value_str += "\n\n==== Error ====\n"
    if isinstance(exec_value, str):
        exec_value_str += exec_value
    elif hasattr(exec_value, 'message'):
        exec_value_str += exec_value.message
    else:
        exec_value_str += str(exec_value)

    exec_value_str += "\n\n==== Traceback ====\n"
    # Append the traceback information
    if tb:
        tb_str = "".join(traceback.format_exception(exc_type, exec_value, tb))
        exec_value_str += tb_str
    else:
        exec_value_str += "No traceback available."

    exec_value_str += "\n\n==== Last 50 Logs ====\n"
    # Append the last 50 lines of the log file
    try:
        with open("hdsemg-select.log", "r") as log_file:
            lines = log_file.readlines()
            last_50_lines = "".join(lines[-50:])
            exec_value_str += last_50_lines
    except FileNotFoundError:
        exec_value_str += "Log file not found."

    return exec_value_str