import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from podqueue.config import settings

def setup_logging():
    # Root logger
    root_logger = logging.getLogger()
    # Clear existing handlers
    root_logger.handlers = []
    
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(log_level)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # App file handler (1 MB, 3 backups)
    app_log_file = settings.LOGS_DIR / "podqueue.log"
    app_file_handler = RotatingFileHandler(
        app_log_file,
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=3,
        encoding='utf-8'
    )
    app_file_handler.setFormatter(formatter)
    root_logger.addHandler(app_file_handler)
    
    # Setup job logger
    job_logger = logging.getLogger("podqueue_job")
    job_logger.handlers = []
    job_logger.setLevel(logging.INFO)
    job_logger.propagate = False
    
    job_log_file = settings.LOGS_DIR / "last_job.log"
    job_file_handler = RotatingFileHandler(
        job_log_file,
        maxBytes=500 * 1024,  # 500 KB
        backupCount=2,
        encoding='utf-8'
    )
    job_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    job_file_handler.setFormatter(job_formatter)
    job_logger.addHandler(job_file_handler)
    
    # Also log job outputs to console for visibility
    job_console_handler = logging.StreamHandler()
    job_console_handler.setFormatter(job_formatter)
    job_logger.addHandler(job_console_handler)

# Initialize logging on import
setup_logging()
