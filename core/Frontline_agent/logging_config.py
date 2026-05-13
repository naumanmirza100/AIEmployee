"""
Logging Configuration for Frontline Agent
Enterprise-level logging setup
"""
import logging
import os
from pathlib import Path
from django.conf import settings

# Create logs directory if it doesn't exist
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Frontline Agent log file
FRONTLINE_LOG_FILE = LOGS_DIR / 'frontline_agent.log'


def setup_frontline_logging():
    """
    Setup logging configuration for Frontline Agent.
    Creates file handler and console handler with appropriate formatting.
    """
    # Get or create logger
    logger = logging.getLogger('frontline_agent')
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler - detailed logs
    file_handler = logging.FileHandler(FRONTLINE_LOG_FILE)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Console handler - simple logs
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # Only warnings and errors to console
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # Also configure sub-loggers
    for sub_logger_name in ['frontline_agent.database_service', 
                           'frontline_agent.services',
                           'frontline_agent.rules',
                           'frontline_agent.views']:
        sub_logger = logging.getLogger(sub_logger_name)
        sub_logger.setLevel(logging.INFO)
        if not sub_logger.handlers:
            sub_logger.addHandler(file_handler)
            sub_logger.addHandler(console_handler)
    
    return logger


# Initialize logging on module import
setup_frontline_logging()

