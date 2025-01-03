# validate.py
import psutil
import pkg_resources
import subprocess
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Constants
MIN_REQUIRED_MEMORY = 4 * 1024 * 1024 * 1024  # 4 GB


def log_warning(message: str) -> None:
    logger.warning(message)


def log_error(message: str) -> None:
    logger.error(message)


def log_error_and_return_false(message: str) -> bool:
    logger.error(message)
    return False


def validate_dependencies() -> bool:
    """
    Checks if the dependencies are installed correctly.
    """
    required_dependencies = {
        "annotated-types",
        "psutil",
        "pydantic",
        "pydantic-core",
        "types-psutil",
        "typing-extensions",
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
        logger.info("FFmpeg is available in the system's PATH.")
    except FileNotFoundError:
        log_error_and_return_false(
            "Missing dependency: ffmpeg. Please install ffmpeg and make sure it's available in the system's PATH.",
        )
    except Exception as e:
        log_error_and_return_false(f"An unexpected error occurred while checking ffmpeg availability: {e}.")

    logger.info("All dependencies are installed and available.")
    return True


def validate_system_resources() -> None:
    """Validate system resources before encoding."""
    try:
        available_memory = psutil.virtual_memory().available
        min_required_memory_gb = MIN_REQUIRED_MEMORY / (1024**3)
        if available_memory <= MIN_REQUIRED_MEMORY:
            log_warning(
                f"Low memory available. Recommended: {min_required_memory_gb:.2f} GB or more. Processing may be slow.",
            )
    except (FileNotFoundError, PermissionError) as e:
        log_error(f"Directory error: {e}")
    except Exception as e:
        log_error(f"Unexpected error during resource validation: {e}")
