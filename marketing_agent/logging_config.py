"""
Logging Configuration for Marketing Agent Email Tracking
Creates log file for tracking email opens and clicks
"""
import logging
import os
from pathlib import Path

# Create logs directory if it doesn't exist
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Marketing Agent log file
MARKETING_TRACKING_LOG_FILE = LOGS_DIR / 'marketing_tracking.log'


def setup_marketing_tracking_logging():
    """
    Setup logging configuration for Marketing Agent Email Tracking.
    Creates file handler and console handler with appropriate formatting.
    """
    # Get or create logger
    logger = logging.getLogger('marketing_agent.views_email_tracking')
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
    file_handler = logging.FileHandler(MARKETING_TRACKING_LOG_FILE)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Console handler - simple logs (for terminal)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Show all tracking info in console
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # Also configure email service logger
    email_service_logger = logging.getLogger('marketing_agent.services.email_service')
    email_service_logger.setLevel(logging.INFO)
    if not email_service_logger.handlers:
        email_service_logger.addHandler(file_handler)
        email_service_logger.addHandler(console_handler)
    
    return logger


# Initialize logging on module import
setup_marketing_tracking_logging()

