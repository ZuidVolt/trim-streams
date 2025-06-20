"""Module for validating dependencies and system resources."""

import logging
import subprocess
from importlib.metadata import PackageNotFoundError, version


class DependencyValidationError(Exception):
    pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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


def check_package_installed(package_name: str) -> bool:
    try:
        version(package_name)
        return True
    except PackageNotFoundError:
        return False


def validate_dependencies(silent: bool = False) -> bool:  # noqa: FBT001, FBT002
    """Check if the dependencies are installed correctly.

    Args:
        silent: If True, suppress informational log messages

    Returns:
        True if all dependencies are available, False otherwise
    """
    required_dependencies: set[str] = {
        "pydantic",
        "pydantic-core",
    }

    # Check Python dependencies using importlib.metadata
    for dependency in required_dependencies:
        if not check_package_installed(dependency):
            return log_error_and_return_false(
                f"Missing required Python dependency: {dependency}. "
                f"Please install it using pip: pip install {dependency}"
            )

    # Check if ffmpeg is available
    try:
        subprocess.run(
            ["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
        )
        if not silent:
            logger.info("FFmpeg is available in the system's PATH.")
    except FileNotFoundError:
        return log_error_and_return_false(
            "Missing dependency: ffmpeg. Please install ffmpeg and make sure it's available in the system's PATH."
        )
    except subprocess.TimeoutExpired:
        return log_error_and_return_false("FFmpeg check timed out. Please verify ffmpeg installation.")
    except subprocess.CalledProcessError as e:
        return log_error_and_return_false(
            f"FFmpeg returned non-zero exit code: {e.returncode}. Please verify ffmpeg installation."
        )
    except DependencyValidationError as e:
        return log_error_and_return_false(f"An unexpected error occurred while checking ffmpeg availability: {e}.")

    if not silent:
        logger.info("All dependencies are installed and available.")
    return True


def get_package_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def list_dependency_versions(dependencies: set[str]) -> dict[str, str | None]:
    return {dep: get_package_version(dep) for dep in dependencies}


if __name__ == "__main__":
    # Test the validation
    print("Testing dependency validation...")
    is_valid = validate_dependencies(silent=False)
    print(f"Validation result: {'✓ PASS' if is_valid else '✗ FAIL'}")

    # Show versions of detected dependencies
    deps = {"pydantic", "pydantic-core"}
    versions = list_dependency_versions(deps)
    print("\nDetected package versions:")
    for pkg, ver in versions.items():
        status = f"v{ver}" if ver else "NOT FOUND"
        print(f"  {pkg}: {status}")
