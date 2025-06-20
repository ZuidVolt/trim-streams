"""Module for validating dependencies and system resources."""

# validate.py
import logging
import subprocess

import pkg_resources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Constants
MIN_REQUIRED_MEMORY = 4 * 1024 * 1024 * 1024  # 4 GB


def log_warning(message: str) -> None:
    """Log a warning message."""
    logger.warning(message)


def log_error(message: str) -> None:
    """Log an error message."""
    logger.error(message)


def log_error_and_return_false(message: str) -> bool:
    """Log an error message and return False."""
    logger.error(message)
    return False


def validate_dependencies(silent: bool = False) -> bool:  # noqa: FBT001, FBT002
    """Checks if the dependencies are installed correctly."""
    required_dependencies = {
        "pydantic",
        "pydantic-core",
    }

    # Check Python dependencies
    for dependency in required_dependencies:
        try:
            pkg_resources.get_distribution(dependency)
        except pkg_resources.DistributionNotFound:
            log_error_and_return_false(
                (
                    f"Missing required Python dependency: {dependency}. "
                    f"Please install it using pip: pip install {dependency}"
                ),
            )

    # Check if ffmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not silent:
            logger.info("FFmpeg is available in the system's PATH.")
    except FileNotFoundError:
        log_error_and_return_false(
            "Missing dependency: ffmpeg. Please install ffmpeg and make sure it's available in the system's PATH.",
        )
    except Exception as e:  # noqa: BLE001
        log_error_and_return_false(f"An unexpected error occurred while checking ffmpeg availability: {e}.")
    if not silent:
        logger.info("All dependencies are installed and available.")
    return True
