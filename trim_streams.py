"""Remove unwanted language tracks from video files using async processing."""

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


# ===== SECTION: Type Definitions and Data Structures =====
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
    language: str = Field(alias="tags.language", default="und")
    codec_name: str | None = None


class ProbeData(BaseModel):
    """Structured FFprobe output."""

    streams: list[StreamInfo] = Field(default_factory=list)


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

    @field_validator("audio_langs", "subtitle_langs")
    @classmethod
    def convert_to_tuple(cls, v: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        """Convert list to tuple if needed."""
        return tuple(v) if isinstance(v, list) else v


# ===== SECTION: Pure Functions =====
def create_output_path(input_path: Path) -> Path:
    """Generate output path preserving directory structure."""
    output_dir = input_path.parent / "processed"
    return output_dir / input_path.name


def is_video_file(path: Path) -> bool:
    """Check if file has video extension."""
    return path.suffix.lower() in {".mkv", ".mp4", ".avi", ".mov"}


def setup_logging() -> None:
    """Initialize structured logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.captureWarnings(capture=True)


# ===== SECTION: Stateful Functions / Classes =====
class AsyncVideoProcessor:
    """Async processor for video stream manipulation."""

    def __init__(self, config: ProcessingConfig) -> None:
        self.config = config
        self.logger = logging.getLogger("AsyncVideoProcessor")

    async def probe_file(self, file_path: Path) -> ProbeData:
        """Async video file analysis using FFprobe."""
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(file_path)]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                msg = f"FFprobe error: {stderr.decode().strip()}"
                raise FFProbeError(msg)

            return ProbeData(**json.loads(stdout))

        except (json.JSONDecodeError, TypeError) as e:
            msg = f"Probe data parsing failed: {e}"
            raise FFProbeError(msg) from e

    async def run_ffmpeg(self, cmd: list[str], file_name: str) -> None:
        """Execute FFmpeg command with progress logging."""
        self.logger.debug(f"Executing: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        while True:
            if process.stderr is None:
                continue

            line = await process.stderr.readline()
            if not line:
                break

            self.logger.debug(f"FFmpeg: {line.decode().strip()}")

        if await process.wait() != 0:
            msg = f"FFmpeg failed for {file_name} (code {process.returncode})"
            raise FFMPEGError(msg)

    async def generate_mapping(self, probe_data: ProbeData, file_name: str) -> list[str]:
        """Build stream map based on language preferences."""
        video_mapped = False
        mappings: list[str] = []

        for stream in probe_data.streams:
            idx = stream.index

            if stream.codec_type == "video" and not video_mapped:
                mappings.extend(["-map", f"0:{idx}"])
                video_mapped = True
                self.logger.debug(f"Mapped video stream {idx}")

            elif stream.codec_type == "audio" and stream.language in self.config.audio_langs:
                mappings.extend(["-map", f"0:{idx}"])
                self.logger.debug(f"Mapped audio stream {idx} ({stream.language})")

            elif stream.codec_type == "subtitle" and stream.language in self.config.subtitle_langs:
                mappings.extend(["-map", f"0:{idx}"])
                self.logger.debug(f"Mapped subtitle stream {idx} ({stream.language})")

        if not video_mapped:
            msg = f"No video stream found in {file_name}"
            raise FFProbeError(msg)
        if not mappings:
            msg = f"No streams matched languages in {file_name}"
            raise FFProbeError(msg)

        return mappings

    async def verify_output(self, output_file: Path) -> None:
        """Validate processing output existence and content."""
        if not output_file.exists():
            msg = f"Output not created: {output_file.name}"
            raise FFMPEGError(msg)
        if output_file.stat().st_size == 0:
            msg = f"Empty output file: {output_file.name}"
            raise FFMPEGError(msg)

    async def process_file(self, input_file: Path, output_file: Path) -> ProcessingResult:
        """Full async processing pipeline for a video file."""
        try:
            # Create parent directory if required
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Stream analysis
            probe_data = await self.probe_file(input_file)
            mappings = await self.generate_mapping(probe_data, input_file.name)

            # Build processing command
            cmd = [
                "ffmpeg",
                "-v",
                "warning",
                "-stats",
                "-i",
                str(input_file),
                *mappings,
                "-c",
                "copy" if self.config.copy_streams else "auto",
                "-y",
                str(output_file),
            ]

            # Execute processing
            await self.run_ffmpeg(cmd, input_file.name)

            # Optional verification
            if self.config.verify_output:
                await self.verify_output(output_file)

            return ProcessingResult(input_file=input_file, success=True, message=f"Processed: {input_file.name}")

        except (FFProbeError, FFMPEGError) as e:
            return ProcessingResult(
                input_file=input_file, success=False, message=f"Processing failed: {type(e).__name__} - {e}"
            )


async def async_main() -> None:
    """Async entry point for video processing."""
    logger = logging.getLogger("async_main")

    parser = argparse.ArgumentParser(
        description=("Language-focused video stream processor | Removes unwanted audio/subtitle tracks")
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
    args = parser.parse_args()

    # Validate input path
    input_path = Path(args.input_path).resolve()
    if not input_path.exists():
        logger.error(f"Invalid path: {input_path}")
        return

    # Configure processing
    config = ProcessingConfig(
        audio_langs=args.audio_langs,
        subtitle_langs=args.subtitle_langs,
        copy_streams=not args.no_copy,
        verify_output=not args.no_verify,
    )

    # Collect target files
    if input_path.is_file():
        files = [input_path]
    else:
        files = [p for p in input_path.rglob("*") if p.is_file() and p.parent.name != "processed" and is_video_file(p)]

    # Process all videos
    processor = AsyncVideoProcessor(config)
    tasks = [processor.process_file(input_file=file, output_file=create_output_path(file)) for file in files]

    # Execute with progress tracking
    results = await asyncio.gather(*tasks)

    # Summarize results
    success_count = sum(1 for r in results if r.success)
    for result in results:
        if result.success:
            logger.info(result.message)
        else:
            logger.error(result.message)

    logger.info(f"Processed {success_count}/{len(files)} files successfully")


def main() -> None:
    logger = logging.getLogger("main")
    setup_logging()
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.warning("\nProcessing interrupted by user")


if __name__ == "__main__":
    main()
