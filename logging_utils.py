import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """
    Set up logging to output to standard output with standard log levels.
    
    Args:
        level: The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Convert string level to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ],
        force=True  # Force reconfiguration if already configured
    )
    
    # Get the root logger
    logger = logging.getLogger()
    logger.info(f"Logging configured with level: {logging.getLevelName(log_level)}")
