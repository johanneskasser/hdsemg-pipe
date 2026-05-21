import logging
import logging.config
from pathlib import Path

APP_DIR = Path.home() / ".hdsemg-pipe"
LOG_DIR = APP_DIR / "logs"


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = str(LOG_DIR / "hdsemg-pipe.log")

    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            },
            'detailed': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
                'level': 'DEBUG',
                'stream': 'ext://sys.stdout',
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'standard',
                'level': 'DEBUG',
                'filename': log_file,
                'mode': 'a',
                'maxBytes': 1_000_000,  # 1 MB
                'backupCount': 3,  # Keep 3 backup files
                'encoding': 'utf-8'
            }
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['console', 'file'],
                'level': 'DEBUG',
                'propagate': True
            },
            'hdsemg-pipe': {
                'handlers': ['console', 'file'],
                'level': 'DEBUG',
                'propagate': False
            },
            'matplotlib.font_manager': {  # Exclude matplotlib.font_manager logs
                'handlers': ['console', 'file'],
                'level': 'WARNING',
                'propagate': False
            }
        }
    }

    logging.config.dictConfig(logging_config)

# Create a global logger instance for the application.
logger = logging.getLogger("hdsemg-pipe")