"""Remove unwanted language tracks from video files using async processing."""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import BaseModel, Field, field_validator

from validate import validate_dependencies

# ===== SECTION: Constants =====
PROCESSED_DIR: Final[str] = "processed"
VIDEO_EXTENSIONS: Final[frozenset[str]] = frozenset({".mkv", ".mp4", ".avi", ".mov"})
STREAM_TYPES: Final[dict[str, str]] = {"VIDEO": "video", "AUDIO": "audio", "SUBTITLE": "subtitle"}


# ===== SECTION: Type Definitions and Data Strfuctures =====
class ProcessorError(Exception):
    """Base error for video processing."""


class FFProbeError(ProcessorError):
    """FFprobe specific errors."""


class FFMPEGError(ProcessorError):
    """FFmpeg specific errors."""


class StreamInfo(BaseModel):
    """Individual stream metadata from FFprobe."""

    index: int
    codec_type: str
    tags: dict[str, str] | None = None
    codec_name: str | None = None

    @property
    def language(self) -> str:
        """Extract language from tags, lowercased and stripped, defaulting to 'und' if not present."""
        if self.tags and "language" in self.tags:
            return self.tags.get("language", "und").strip().lower()
        return "und"


class ProbeData(BaseModel):
    """Structured FFprobe output."""

    streams: list[StreamInfo] = Field(default_factory=list)


class FilteredStreams(NamedTuple):
    """Filtered streams organized by type."""

    video: list[StreamInfo]
    audio: list[StreamInfo]
    subtitle: list[StreamInfo]


@dataclass(frozen=True)
class ProcessingResult:
    """Immutable result container for processing operations."""

    input_file: Path
    success: bool
    message: str = ""


class ProcessingConfig(BaseModel):
    """Configuration for video processing operations."""

    audio_langs: tuple[str, ...] = ("eng", "kor", "jpn")
    subtitle_langs: tuple[str, ...] = ("eng",)
    copy_streams: bool = True
    verify_output: bool = True
    concurrency: int = 4

    @field_validator("audio_langs", "subtitle_langs")
    @classmethod
    def convert_to_tuple(cls, v: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        """Convert list to tuple if needed."""
        langs = tuple(v) if isinstance(v, list) else v
        return tuple(lang.lower() for lang in langs)


# ===== SECTION: Pure Functions =====
def create_output_path(input_path: Path) -> Path:
    """Generate output path preserving directory structure."""
    output_dir = input_path.parent / PROCESSED_DIR
    return output_dir / input_path.name


def is_video_file(path: Path) -> bool:
    """Check if file has video extension."""
    return path.suffix.lower() in VIDEO_EXTENSIONS


def setup_logging() -> None:
    """Initialize structured logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.captureWarnings(capture=True)


def select_primary_video_stream(video_streams: list[StreamInfo]) -> StreamInfo:
    """Select primary video stream - error if multiple streams found."""
    if not video_streams:
        msg = "No video streams available for selection"
        raise FFProbeError(msg)

    if len(video_streams) == 1:
        return video_streams[0]

    # Error on multiple video streams - let user handle this case
    msg = f"Multiple video streams found ({len(video_streams)}). Please specify which stream to use."
    raise FFProbeError(msg)


def filter_streams_by_type_and_language(streams: list[StreamInfo], config: ProcessingConfig) -> FilteredStreams:
    """Pure function to filter streams by type and language preferences."""
    video_streams: list[StreamInfo] = []
    audio_streams: list[StreamInfo] = []
    subtitle_streams: list[StreamInfo] = []

    logger = logging.getLogger("filter_streams_by_type_and_language")

    for stream in streams:
        if stream.codec_type == STREAM_TYPES["VIDEO"]:
            video_streams.append(stream)
        elif stream.codec_type == STREAM_TYPES["AUDIO"] and stream.language in config.audio_langs:
            audio_streams.append(stream)
        elif stream.codec_type == STREAM_TYPES["SUBTITLE"] and stream.language in config.subtitle_langs:
            subtitle_streams.append(stream)
        elif stream.codec_type not in {STREAM_TYPES["VIDEO"], STREAM_TYPES["AUDIO"], STREAM_TYPES["SUBTITLE"]}:
            logger.warning(f"Encountered unexpected codec_type '{stream.codec_type}' (index {stream.index})")

    return FilteredStreams(video=video_streams, audio=audio_streams, subtitle=subtitle_streams)


def validate_filtered_streams(filtered: FilteredStreams, file_name: str) -> None:
    """Validate that we have the minimum required streams."""
    if not filtered.video:
        msg = f"No video stream found in {file_name}"
        raise FFProbeError(msg)

    # We need at least one stream to be mapped beyond video
    total_streams = len(filtered.audio) + len(filtered.subtitle)
    if total_streams == 0:
        msg = f"No audio or subtitle streams matched desired languages in {file_name}"
        raise FFProbeError(msg)


def build_ffmpeg_stream_mappings(filtered: FilteredStreams) -> list[str]:
    """Build FFmpeg stream mapping arguments using type-qualified selectors."""
    mappings: list[str] = []

    # Map primary video stream
    if filtered.video:
        # Use the position in the filtered list as the stream number for type-qualified mapping
        primary_video = select_primary_video_stream(filtered.video)
        video_idx = filtered.video.index(primary_video)
        mappings.extend(["-map", f"0:v:{video_idx}"])

    # Map all filtered audio streams
    for i in range(len(filtered.audio)):
        mappings.extend(["-map", f"0:a:{i}"])

    # Map all filtered subtitle streams
    for i in range(len(filtered.subtitle)):
        mappings.extend(["-map", f"0:s:{i}"])

    # Validate we have at least one stream mapped
    return mappings


def build_ffmpeg_command(
    input_file: Path,
    output_file: Path,
    stream_mappings: list[str],
    copy_streams: bool = True,  # noqa: FBT001, FBT002
) -> list[str]:
    """Build complete FFmpeg command."""
    cmd = [
        "ffmpeg",
        "-v",
        "warning",
        "-stats",
        "-i",
        str(input_file),
        *stream_mappings,
    ]

    if copy_streams:
        cmd.extend(["-c", "copy"])

    cmd.extend(["-y", str(output_file)])
    return cmd


async def _run_subprocess_with_timeout(cmd: list[str], timeout: float) -> tuple[bytes, bytes, int]:  # noqa: ASYNC109
    """Helper function to run subprocess with timeout and basic error handling."""
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return stdout, stderr, process.returncode or 0
    except TimeoutError:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=300.0)
        except TimeoutError:
            process.kill()
            await process.wait()
        raise
    except asyncio.CancelledError:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=300.0)
        except TimeoutError:
            process.kill()
            await process.wait()
        raise


# ===== SECTION: I/O Operations =====
class StreamProber:
    """Handles FFprobe operations."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("StreamProber")

    async def probe_file(self, file_path: Path, *, timeout: float = 30.0) -> ProbeData:  # noqa: ASYNC109
        """Async video file analysis using FFprobe."""
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(file_path)]

        try:
            stdout, stderr, returncode = await _run_subprocess_with_timeout(cmd, timeout)

            if returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                msg = f"FFprobe failed for {file_path.name}: {error_msg}"
                raise FFProbeError(msg)

            if not stdout:
                msg = f"FFprobe returned empty output for {file_path.name}"
                raise FFProbeError(msg)

            return ProbeData(**json.loads(stdout))

        except TimeoutError as e:
            msg = f"FFprobe timeout ({timeout}s) for {file_path.name}"
            raise FFProbeError(msg) from e
        except (json.JSONDecodeError, TypeError) as e:
            msg = f"Failed to parse probe data for {file_path.name}: {e}"
            raise FFProbeError(msg) from e


class CommandExecutor:
    """Handles FFmpeg command execution."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("CommandExecutor")

    async def execute_ffmpeg(self, cmd: list[str], file_name: str, *, timeout: float = 300.0) -> None:  # noqa: ASYNC109
        """Execute FFmpeg command."""
        self.logger.debug(f"Executing: {' '.join(cmd)}")

        try:
            _, stderr, returncode = await _run_subprocess_with_timeout(cmd, timeout)

            if returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                msg = f"FFmpeg failed for {file_name}: {error_msg}"
                raise FFMPEGError(msg)

        except TimeoutError as e:
            msg = f"FFmpeg timeout ({timeout}s) for {file_name}"
            raise FFMPEGError(msg) from e


def verify_output_file(output_file: Path) -> None:
    """Validate processing output existence and content."""
    if not output_file.exists():
        msg = f"Output file was not created: {output_file.name}"
        raise FFMPEGError(msg)

    if output_file.stat().st_size == 0:
        msg = f"Output file is empty: {output_file.name}"
        raise FFMPEGError(msg)


# ===== SECTION: Main Processing Logic =====
class VideoProcessor:
    """Coordinates video processing operations."""

    def __init__(self, config: ProcessingConfig) -> None:
        self.config = config
        self.prober = StreamProber()
        self.executor = CommandExecutor()
        self.logger = logging.getLogger("VideoProcessor")

    async def process_file(self, input_file: Path, output_file: Path) -> ProcessingResult:
        """Process a single video file through the complete pipeline."""
        try:
            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Step 1: Probe file for stream information
            probe_data = await self.prober.probe_file(input_file)

            # Step 2: Filter streams based on configuration
            filtered = filter_streams_by_type_and_language(probe_data.streams, self.config)

            # Step 3: Validate we have required streams
            validate_filtered_streams(filtered, input_file.name)

            # Step 4: Build FFmpeg command
            stream_mappings = build_ffmpeg_stream_mappings(filtered)
            cmd = build_ffmpeg_command(input_file, output_file, stream_mappings, self.config.copy_streams)

            # Step 5: Execute FFmpeg
            await self.executor.execute_ffmpeg(cmd, input_file.name)

            # Step 6: Verify output if requested
            if self.config.verify_output:
                verify_output_file(output_file)

            return ProcessingResult(input_file=input_file, success=True)

        except (FFProbeError, FFMPEGError, PermissionError) as e:
            error_msg = f"{type(e).__name__}: {e}"
            return ProcessingResult(input_file=input_file, success=False, message=error_msg)


async def async_main() -> None:
    """Async entry point for video processing."""
    logger = logging.getLogger("async_main")

    parser = argparse.ArgumentParser(
        description="Language-focused video stream processor | Removes unwanted audio/subtitle tracks"
    )
    parser.add_argument("input_path", type=str, help="Input file/directory")
    parser.add_argument(
        "--audio-langs", nargs="+", default=["eng", "kor", "jpn"], help="Audio languages to retain (space separated)"
    )
    parser.add_argument(
        "--subtitle-langs", nargs="+", default=["eng"], help="Subtitle languages to retain (space separated)"
    )
    parser.add_argument("--no-copy", action="store_true", help="Re-encode streams instead of copying")
    parser.add_argument("--no-verify", action="store_true", help="Skip output verification")
    parser.add_argument("--concurrency", type=int, default=4, help="Number of files to process at once (default: 4)")

    parser.parse_known_args()
    silent_dependencies_validation = "--help" in sys.argv or "-h" in sys.argv
    result = validate_dependencies(silent=silent_dependencies_validation)
    if not result:
        logger.warning("WARNING: dependency validation failed - you may experience issues")

    args = parser.parse_args()

    input_path = Path(args.input_path).resolve()
    if not input_path.exists():
        logger.error(f"Invalid path: {input_path}")
        return

    config = ProcessingConfig(
        audio_langs=args.audio_langs,
        subtitle_langs=args.subtitle_langs,
        copy_streams=not args.no_copy,
        verify_output=not args.no_verify,
        concurrency=args.concurrency,
    )

    if input_path.is_file():
        all_files = [input_path]
    else:
        all_files = [
            p for p in input_path.rglob("*") if p.is_file() and p.parent.name != PROCESSED_DIR and is_video_file(p)
        ]

    files_to_process = [f for f in all_files if not create_output_path(f).exists()]
    skipped_count = len(all_files) - len(files_to_process)

    if skipped_count > 0:
        logger.info(f"Skipping {skipped_count} file(s) that already exist in output directory")

    if not files_to_process:
        logger.info("No new video files to process")
        return

    processor = VideoProcessor(config)
    semaphore = asyncio.Semaphore(config.concurrency)

    async def process_with_semaphore(file: Path) -> ProcessingResult:
        """Process file with concurrency control."""
        async with semaphore:
            return await processor.process_file(file, create_output_path(file))

    tasks = [process_with_semaphore(file) for file in files_to_process]
    success_count = 0
    total_files = len(files_to_process)

    logger.info(f"Processing {total_files} file(s) with concurrency level {config.concurrency}")

    for i, future in enumerate(asyncio.as_completed(tasks), 1):
        result = await future
        if result.success:
            success_count += 1
            logger.info(f"[{i}/{total_files}] SUCCESS: {result.input_file.name}")
        else:
            logger.error(f"[{i}/{total_files}] FAILED: {result.input_file.name} | {result.message}")

    logger.info(f"Processing complete! {success_count}/{total_files} files successful")


def main() -> None:
    logger = logging.getLogger("main")
    setup_logging()

    exit_code = 0
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.warning("Processing interrupted by user")
        exit_code = 130  # Standard SIGINT exit code
    except (RuntimeError, OSError):
        logger.exception("Runtime error")
        exit_code = 1
    except Exception:
        logger.exception("Unexpected error")
        exit_code = 2
    finally:
        # Cleanup any remaining resources
        logger.debug("Shutting down gracefully")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
