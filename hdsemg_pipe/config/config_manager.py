import json
import os
import enum
from threading import Lock
from hdsemg_pipe._log.log_config import logger
from hdsemg_pipe.config.config_enums import Settings

CONFIG_FILE = "config/config.json"

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

    def load_config(self):
        """Load configuration from JSON file."""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                try:
                    self.settings = json.load(f)
                    self.check_installations()
                except json.JSONDecodeError:
                    self.settings = {}
                    logger.error("Failed to open config file.")
                    self.check_installations()
        else:
            logger.error("Config file does not exist yet. Creating...")
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            open(CONFIG_FILE, "a").close()
            self.settings = {}
            self.check_installations()

    def save_config(self):
        """Save configuration to JSON file."""
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

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


    def check_installations(self):
        """Check if the configuration still exists."""
        self.set(Settings.HDSEMG_SELECT_INSTALLED, self.is_package_installed("hdsemg_select"))
        self.set(Settings.OPENHDEMG_INSTALLED, self.is_package_installed("openhdemg"))

# Singleton instance
config = ConfigManager()
