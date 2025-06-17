# hdsemg_pipe/version.py
import subprocess
from hdsemg_pipe._log.log_config import logger

try:
    tag = subprocess.check_output(
        ["git", "describe", "--tags", "--abbrev=0"],
        stderr=subprocess.DEVNULL,
    ).decode().strip()
    __version__ = tag[1:] if tag.startswith("v") else tag
except Exception:
    __version__ = "0.0.0"

logger.info("hdsemg-select version: %s", __version__)

