import traceback

from PyQt5.QtWidgets import QMessageBox

from _log.log_config import logger


def exception_hook(exc_type, exc_value, exc_traceback):
    """
    Custom exception hook to handle uncaught exceptions.
    """
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.error("Uncaught exception: %s", tb)

    dlg = QMessageBox()
    dlg.setWindowTitle("Unexpected Error")
    dlg.setText("An unexpected error occurred.")
    dlg.setInformativeText(str(exc_value))
    dlg.setDetailedText(tb)
    dlg.setIcon(QMessageBox.Critical)
    dlg.exec_()
