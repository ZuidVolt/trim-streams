# Trim Streams 🎬

A powerful Python utility for managing and removing Unwanted video language tracks, allowing precise control over audio and subtitle streams in your media files.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

## 🚀 Features

- 🎯 **Selective Track Retention**: Keep only the audio and subtitle tracks you want
- 📁 **Batch Processing**: Handle single files or entire directories
- ⚡ **Stream Copy**: Preserve quality with no re-encoding
- ✅ **Verification**: Automatic output validation
- 🎥 **Wide Format Support**: Works with MKV, MP4, AVI, and MOV

## 📋 Prerequisites

- Python 3.11 or higher
- FFmpeg in system PATH
- Required Python packages:

  ```toml
  psutil==6.1.1
  pydantic==2.10.4
  setuptools==75.6
  ```

## 🔧 Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/zuidvolt/trim-streams.git
   cd trim-streams
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## 📖 Usage Guide

### Basic Command Structure

```bash
python trim_streams.py [options] input_path
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `input_path` | Video file or directory to process | Required |
| `--audio-langs` | Audio language codes to retain | eng,en,kor,jpn,chi,zho,cmn |
| `--subtitle-langs` | Subtitle language codes to keep | eng,en |
| `--no-copy` | Disable stream copy mode | False |
| `--no-verify` | Skip output verification | False |

### Common Use Cases

1. **Keep specific languages:**

   ```bash
   python trim_streams.py video.mkv --audio-langs eng jpn --subtitle-langs eng
   ```

2. **Process entire directory:**

   ```bash
   python trim_streams.py /path/to/videos
   ```

3. **Re-encode streams:**

   ```bash
   python trim_streams.py video.mkv --no-copy
   ```

### Output Structure

- Processed files are saved in a `processed` subdirectory
- Original directory structure is preserved
- Output maintains original filename

## 🛠️ Development

### Tools & Quality Checks

| Tool | Purpose | Command |
|------|---------|---------|
| ruff | Linting & Formatting | `make ruff-check` |
| mypy | Static Type Checking | `make mypy-strict` |
| coverage | Test Coverage | `make coverage` |
| radon | Code Complexity | `make radon/ make radon-mi` |
| vulture | Dead Code Detection | `make vulture` |

### Run All Checks

```bash
make check
```

### Development Setup

1. Create virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Unix
   # or
   .venv\Scripts\activate  # Windows
   ```

2. Install dev dependencies:

```bash
pip install -e ".[dev]"
```

   or if you using the uv packages manager

```bash
uv pip install -r pyproject.toml --all-extras
```

## 📊 API Reference

### VideoProcessor Class

```python
processor = VideoProcessor(input_file: Path, config: ProcessingConfig)
```

#### Methods

| Method | Description |
|--------|-------------|
| `probe_file()` | Analyze video file metadata |
| `process(output_file: Path)` | Process video with current settings |
| `verify_output(output_file: Path)` | Validate processed file |

#### ProcessingConfig Options

```python
config = ProcessingConfig(
    audio_langs=["eng", "jpn"],
    subtitle_langs=["eng"],
    copy_streams=True,
    verify_output=True
)
```

## License

This project is licensed under the Apache License, Version 2.0 with important additional terms, including specific commercial use conditions. Users are strongly advised to read the full [LICENSE](LICENSE) file carefully before using, modifying, or distributing this work. The additional terms contain crucial information about liability, data collection, indemnification, and commercial usage requirements that may significantly affect your rights and obligations.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch

   ```bash
   git checkout -b feature/amazing-feature
   ```

3. Commit changes

   ```bash
   git commit -m 'Add: amazing feature'
   ```

4. Push to branch

   ```bash
   git push origin feature/amazing-feature
   ```

5. Open Pull Request

### Contribution Guidelines

- Follow PEP 8 style guide
- Add tests for new features
- Update documentation
- Maintain type hints
- Run quality checks before submitting

## 🐛 Bug Reports

Report issues via GitHub Issues, including:

- Python version
- Operating system
- Minimal reproducible example
- Error messages
- Expected vs actual behavior
