from PyQt5.QtCore import QThread, pyqtSignal
import subprocess, sys, logging

class InstallThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, package_name, parent=None):
        super().__init__(parent)
        self.pkg = package_name

    def run(self):
        logging.info(f"Installing {self.pkg}…")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", self.pkg],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        ok = (result.returncode == 0)
        if ok:
            logging.info(f"Successfully installed {self.pkg}")
        else:
            logging.error(f"Failed to install {self.pkg}: {result.stderr.strip()}")
        self.finished.emit(ok,
            result.stdout if ok else result.stderr.strip())
