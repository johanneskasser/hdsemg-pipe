"""
MATLAB Engine for Python installer.
"""
from PyQt5.QtCore import QThread, pyqtSignal
import subprocess
import sys
import os
import logging
import shutil
import tempfile


class MatlabEngineInstallThread(QThread):
    """Thread for installing MATLAB Engine for Python."""
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def find_matlab_engine_path(self):
        """Try to find the MATLAB Engine installation path.

        Returns:
            str or None: Path to the MATLAB Engine setup.py directory, or None if not found.
        """
        # Method 1: Try to find via MATLAB (if matlab.engine import fails)
        # We look for common MATLAB installation paths

        # First, try to get matlabroot via subprocess
        try:
            result = subprocess.run(
                ["matlab", "-batch", "disp(matlabroot)"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                matlabroot = result.stdout.strip()
                engine_path = os.path.join(matlabroot, "extern", "engines", "python")
                if os.path.exists(os.path.join(engine_path, "setup.py")):
                    return engine_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Method 2: Check common installation paths
        common_paths = []

        if sys.platform == "win32":
            # Windows common paths
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            for version in ["R2024b", "R2024a", "R2023b", "R2023a", "R2022b", "R2022a"]:
                common_paths.append(
                    os.path.join(program_files, "MATLAB", version, "extern", "engines", "python")
                )
        elif sys.platform == "darwin":
            # macOS common paths
            for version in ["R2024b", "R2024a", "R2023b", "R2023a", "R2022b", "R2022a"]:
                common_paths.append(
                    f"/Applications/MATLAB_{version}.app/extern/engines/python"
                )
        else:
            # Linux common paths
            for version in ["R2024b", "R2024a", "R2023b", "R2023a", "R2022b", "R2022a"]:
                common_paths.extend([
                    f"/usr/local/MATLAB/{version}/extern/engines/python",
                    f"/opt/MATLAB/{version}/extern/engines/python",
                    os.path.expanduser(f"~/MATLAB/{version}/extern/engines/python")
                ])

        # Check each common path
        for path in common_paths:
            if os.path.exists(os.path.join(path, "setup.py")):
                return path

        return None

    def run(self):
        """Install MATLAB Engine for Python."""
        logging.info("Starting MATLAB Engine for Python installation...")

        # Find the MATLAB Engine installation path
        engine_path = self.find_matlab_engine_path()

        if not engine_path:
            error_msg = (
                "Could not find MATLAB installation. Please ensure MATLAB is installed "
                "and try one of these manual installation methods:\n\n"
                "Method 1 - In MATLAB:\n"
                "  cd(fullfile(matlabroot,'extern','engines','python'))\n"
                "  system('python setup.py install')\n\n"
                "Method 2 - In Terminal/CMD:\n"
                "  cd <matlabroot>/extern/engines/python\n"
                "  python setup.py install"
            )
            logging.error(error_msg)
            self.finished.emit(False, error_msg)
            return

        logging.info(f"Found MATLAB Engine path: {engine_path}")

        # Extract MATLABROOT from engine path
        # engine_path is like: <MATLABROOT>/extern/engines/python
        matlabroot = os.path.dirname(os.path.dirname(os.path.dirname(engine_path)))
        logging.info(f"MATLABROOT: {matlabroot}")

        # Copy all source files to a temporary directory
        # This is necessary because MATLAB's setup.py tries to write to the source directory
        temp_dir = None
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix="matlab_engine_install_")
            logging.info(f"Created temporary directory: {temp_dir}")

            # Copy all files from MATLAB Engine directory to temp
            logging.info("Copying MATLAB Engine sources to temporary directory...")
            for item in os.listdir(engine_path):
                src = os.path.join(engine_path, item)
                dst = os.path.join(temp_dir, item)
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                except Exception as e:
                    logging.warning(f"Failed to copy {item}: {e}")

            logging.info("Successfully copied MATLAB Engine sources")

            # Set up environment with MATLABROOT pointing to the original installation
            # This allows setup.py to validate the MATLAB installation
            env = os.environ.copy()
            env["MATLABROOT"] = matlabroot

            # Install from temporary directory using pip
            logging.info(f"Installing MATLAB Engine from {temp_dir}")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-cache-dir", temp_dir],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode == 0:
                logging.info("Successfully installed MATLAB Engine for Python")
                self.finished.emit(True, "MATLAB Engine for Python installed successfully")
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logging.error(f"Failed to install MATLAB Engine: {error_msg}")

                # Provide helpful error message
                if "corrupted" in error_msg.lower() or "zugriff verweigert" in error_msg.lower():
                    error_msg = (
                        "Automatic installation failed. Please try manual installation:\n\n"
                        "In MATLAB:\n"
                        "  cd(fullfile(matlabroot,'extern','engines','python'))\n"
                        "  system('python setup.py install')\n\n"
                        "Or in Terminal/CMD:\n"
                        f"  cd \"{engine_path}\"\n"
                        "  python setup.py install"
                    )

                self.finished.emit(False, error_msg)

        except subprocess.TimeoutExpired:
            error_msg = "Installation timed out (>5 minutes)"
            logging.error(error_msg)
            self.finished.emit(False, error_msg)
        except Exception as e:
            error_msg = f"Installation error: {str(e)}"
            logging.error(error_msg)
            self.finished.emit(False, error_msg)
        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logging.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logging.warning(f"Failed to clean up temporary directory: {e}")
