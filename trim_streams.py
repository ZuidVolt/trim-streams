# trim_streams.py
import argparse
import json
import logging
import subprocess
from enum import Enum
from pathlib import Path
from typing import TypedDict, Any
from pydantic import BaseModel, Field
from validate import validate_dependencies, validate_system_resources


class ProcessorError(Exception):
    """Base error for video processing"""


class FFProbeError(ProcessorError):
    """FFprobe specific errors"""


class FFMPEGError(ProcessorError):
    """FFmpeg specific errors"""


class ProcessingStatus(Enum):
    """Status of video processing"""

    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    PROCESSING = "processing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class StreamDict(TypedDict):
    """Stream information dictionary"""

    index: int
    codec_type: str
    codec_name: str | None
    tags: dict[str, str] | None
    language: str | None


class ProbeData(TypedDict):
    """FFprobe output data structure"""

    streams: list[StreamDict]
    format: dict[str, Any]


class ProcessingConfig(BaseModel):
    """Configuration model for video stream processing.

    Attributes:
        audio_langs (list[str]): List of audio language codes to keep (e.g., ['eng', 'kor', 'jpn'])
        subtitle_langs (list[str]): List of subtitle language codes to keep (e.g., ['eng'])
        copy_streams (bool): Whether to use stream copy mode (True) or re-encode (False)
        verify_output (bool): Whether to verify the output file after processing
    """

    audio_langs: list[str] = Field(default=["eng", "kor", "jpn"])
    subtitle_langs: list[str] = Field(default=["eng"])
    copy_streams: bool = Field(default=True)
    verify_output: bool = Field(default=True)

    class Config:
        arbitrary_types_allowed: bool = True


class VideoProcessor:
    """Handles video file processing to remove unwanted language tracks.

    This class manages the analysis and processing of video files, allowing selective
    retention of audio and subtitle tracks based on language preferences.

    Args:
        input_file (Path): Path to the input video file
        config (ProcessingConfig): Processing configuration settings

    Attributes:
        input_file (Path): Path to the input video file
        config (ProcessingConfig): Processing configuration settings
        status (ProcessingStatus): Current processing status
        probe_data (ProbeData | None): Cached FFprobe data
        logger (logging.Logger): Logger instance

    Raises:
        FFProbeError: When FFprobe analysis fails
        FFMPEGError: When FFmpeg processing fails
        ProcessorError: For general processing errors
    """

    def __init__(self, input_file: Path, config: ProcessingConfig) -> None:
        self.input_file: Path = input_file
        self.config: ProcessingConfig = config
        self.status: ProcessingStatus = ProcessingStatus.INITIALIZING
        self.probe_data: ProbeData | None = None
        self.logger: logging.Logger = logging.getLogger(__name__)

    def probe_file(self, file_path: Path | None = None) -> ProbeData:
        # Use cached probe_data if available and probing the input file
        if file_path is None and self.probe_data is not None:
            return self.probe_data

        target_path = file_path or self.input_file
        self.status = ProcessingStatus.ANALYZING
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(target_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe_data: ProbeData = json.loads(result.stdout)

            # Cache the result if it's for the input file
            if file_path is None:
                self.probe_data = probe_data

            return probe_data

        except subprocess.CalledProcessError as e:
            self.status = ProcessingStatus.FAILED
            raise FFProbeError(f"FFprobe failed with return code {e.returncode}: {e.stderr}") from e
        except json.JSONDecodeError as e:
            self.status = ProcessingStatus.FAILED
            raise FFProbeError(f"Failed to parse FFprobe output: {e!s}") from e

    def get_stream_mappings(self) -> list[str]:
        """Generate ffmpeg mapping arguments based on language preferences."""
        if self.probe_data is None:
            self.probe_data = self.probe_file()

        mappings: list[str] = []
        video_mapped: bool = False

        for stream in self.probe_data["streams"]:
            index: int = stream["index"]
            codec_type: str = stream["codec_type"]
            tags: Any = stream.get("tags", {})
            language: str = tags.get("language", "und")

            if codec_type == "video" and not video_mapped:
                mappings.extend(["-map", f"0:{index}"])
                video_mapped = True
                self.logger.debug(f"Mapped video stream: {index}")
            elif codec_type == "audio" and language in self.config.audio_langs:
                mappings.extend(["-map", f"0:{index}"])
                self.logger.debug(f"Mapped audio stream: {index} ({language})")
            elif codec_type == "subtitle" and language in self.config.subtitle_langs:
                mappings.extend(["-map", f"0:{index}"])
                self.logger.debug(f"Mapped subtitle stream: {index} ({language})")

        if not video_mapped:
            raise FFProbeError(f"No video stream in '{self.input_file.name}'")
        if not mappings:
            raise FFProbeError(f"No matching streams found in '{self.input_file.name}' for specified languages")

        return mappings

    def verify_output(self, output_file: Path) -> None:
        """Verify the output file was created successfully"""
        self.status = ProcessingStatus.VERIFYING

        if not output_file.exists():
            raise FFMPEGError(f"Failed to create: {output_file.name}")
        if output_file.stat().st_size == 0:
            raise FFMPEGError(f"Empty output file: {output_file.name}")

        try:
            self.probe_file()  # Verify the output file can be probed
        except FFProbeError as e:
            raise FFMPEGError(f"Output file verification failed: {e!s}") from e

    def process(self, output_file: Path) -> None:
        """Process the video file, keeping only specified language tracks."""
        self.status = ProcessingStatus.PROCESSING

        try:
            mappings = self.get_stream_mappings()
            cmd = ["ffmpeg", "-i", str(self.input_file), *mappings]

            if self.config.copy_streams:
                cmd.extend(["-c", "copy"])

            cmd.append(str(output_file))
            subprocess.run(cmd, check=True, capture_output=True)

            if self.config.verify_output:
                self.verify_output(output_file)

            self.status = ProcessingStatus.COMPLETED

        except subprocess.CalledProcessError as e:
            self.status = ProcessingStatus.FAILED
            error_output = e.stderr.decode("utf-8", errors="replace")
            raise FFMPEGError(f"FFMPEG failed with return code {e.returncode}: {error_output}") from e
        except Exception:
            self.status = ProcessingStatus.FAILED
            raise


def setup_logging() -> None:
    """Configure logging settings"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description="Remove unwanted language tracks from video files")
    parser.add_argument("input_path", type=str, help="Input video file or directory")
    parser.add_argument(
        "--audio-langs",
        nargs="+",
        type=str,
        default=["eng", "en", "kor", "jpn", "chi", "zho", "cmn"],
        help="List of audio language codes to keep (default: eng, kor, jpn, chi)",
    )
    parser.add_argument(
        "--subtitle-langs",
        nargs="+",
        type=str,
        default=["eng", "en"],
        help="List of subtitle language codes to keep (default: eng)",
    )
    parser.add_argument("--no-copy", action="store_true", help="Don't use stream copy mode (will re-encode streams)")
    parser.add_argument("--no-verify", action="store_true", help="Skip output file verification")

    args = parser.parse_args()
    input_path = Path(args.input_path).resolve()

    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        return

    if not validate_dependencies():
        logger.error("process stopped due to missing dependencies.")
        return

    validate_system_resources()

    # Create configuration
    config = ProcessingConfig(
        audio_langs=args.audio_langs,
        subtitle_langs=args.subtitle_langs,
        copy_streams=not args.no_copy,
        verify_output=not args.no_verify,
    )

    # Create output directory
    output_dir = input_path / "processed"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        logger.error(f"Permission denied: Unable to create output directory at {output_dir}")
        logger.exception("Failed to create output directory", exc_info=e)
        return

    if input_path.is_file():
        files_to_process = [input_path]
    else:
        files_to_process = [
            f
            for f in input_path.rglob("*")
            if f.is_file() and f.parent.name != "processed" and f.suffix.lower() in {".mkv", ".mp4", ".avi", ".mov"}
        ]

    # Process each file
    success_count = 0
    total_files = len(files_to_process)

    for video_file in files_to_process:
        try:
            logger.info(f"Processing [{success_count + 1}/{total_files}]: {video_file.name}")
            output_file = output_dir / video_file.name

            if output_file.exists():
                logger.warning(f"Output file already exists, skipping: {output_file}")
                continue

            processor = VideoProcessor(video_file, config)
            processor.process(output_file)
            success_count += 1
            logger.info(f"Successfully processed: {video_file.name}")

        except (FFProbeError, FFMPEGError) as e:
            logger.error(f"Failed to process {video_file.name}")
            logger.exception("Processing error", exc_info=e)
        except Exception as e:
            logger.error(f"Unexpected error processing {video_file.name}")
            logger.exception("Unexpected error", exc_info=e)

    logger.info(f"Processing complete! Successfully processed {success_count}/{total_files} files")


if __name__ == "__main__":
    main()
