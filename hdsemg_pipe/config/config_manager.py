import json
import shutil
import enum
from pathlib import Path
from threading import Lock
from hdsemg_pipe._log.log_config import logger, APP_DIR
from hdsemg_pipe.config.config_enums import Settings

CONFIG_FILE = APP_DIR / "config.json"
_LEGACY_CONFIG_FILE = Path(__file__).parent / "config.json"


class ConfigManager:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Ensure a single instance (Singleton Pattern)."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ConfigManager, cls).__new__(cls)
                cls._instance.settings = {}
                cls._instance.load_config()
        return cls._instance

    def _migrate_legacy_config(self):
        """Copy config from old package location to user dir on first run."""
        if not CONFIG_FILE.exists() and _LEGACY_CONFIG_FILE.exists():
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_LEGACY_CONFIG_FILE, CONFIG_FILE)
            logger.info(f"Migrated config to {CONFIG_FILE}")

    def load_config(self):
        """Load configuration from JSON file."""
        self._migrate_legacy_config()
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                try:
                    self.settings = json.load(f)
                    self.check_installations()
                except json.JSONDecodeError:
                    self.settings = {}
                    logger.error("Failed to open config file.")
                    self.check_installations()
        else:
            logger.info("Config file not found, creating new one...")
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.touch()
            self.settings = {}
            self.check_installations()

    def save_config(self):
        """Save configuration to JSON file."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(CONFIG_FILE, "w") as f:
            json.dump(self.settings, f, indent=4)

    def set(self, key, value):
        """Set a configuration value and save it."""
        if isinstance(key, enum.Enum):
            key = key.name  # Store enum as a string
        self.settings[key] = value
        self.save_config()

    def get(self, key, default=None):
        """Get a configuration value."""
        key = key.name
        return self.settings.get(key, default)

    def is_package_installed(self, package_name):
        """Check if a specific package is installed."""
        try:
            import importlib
            importlib.import_module(package_name)
            return True
        except ImportError:
            return False


    def is_matlab_available(self):
        """Check if MATLAB Engine for Python is available."""
        try:
            import matlab.engine
            # Try to check if MATLAB is actually accessible
            engines = matlab.engine.find_matlab()
            return True
        except (ImportError, Exception):
            return False

    def is_octave_available(self):
        """Check if Octave and oct2py are available."""
        try:
            import oct2py
            # Try to initialize octave to verify it works
            oc = oct2py.Oct2Py()
            oc.exit()
            return True
        except (ImportError, Exception):
            return False

    def check_installations(self):
        """Check if the configuration still exists."""
        self.set(Settings.HDSEMG_SELECT_INSTALLED, self.is_package_installed("hdsemg_select"))
        self.set(Settings.OPENHDEMG_INSTALLED, self.is_package_installed("openhdemg"))
        self.set(Settings.MATLAB_INSTALLED, self.is_matlab_available())
        self.set(Settings.OCTAVE_INSTALLED, self.is_octave_available())

# Singleton instance
config = ConfigManager()
