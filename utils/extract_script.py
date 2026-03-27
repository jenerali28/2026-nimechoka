#!/usr/bin/env python3
"""
Script Extractor — Extract audio from video and transcribe with OpenAI Whisper.

Extracts the audio track from an input video using FFmpeg, then transcribes
the audio to English text using OpenAI's Whisper model (runs locally).

Usage:
    python extract_script.py input_videos/video.mp4
    python extract_script.py input_videos/video.mp4 -o outputs/script/english_script.txt
    python extract_script.py input_videos/video.mp4 --whisper-model medium
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = "outputs/script/english_script.txt"
DEFAULT_WHISPER_MODEL = "base"
SUPPORTED_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".flv"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def check_ffmpeg() -> str:
    """Check that FFmpeg is available and return its path."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Error: FFmpeg is not installed or not on PATH.")
        print("  Install with: sudo apt install ffmpeg  (Linux)")
        print("                brew install ffmpeg       (macOS)")
        sys.exit(1)
    return ffmpeg


def extract_audio(ffmpeg_path: str, video_path: Path, audio_output: Path) -> bool:
    """Extract audio track from a video file using FFmpeg.

    Outputs a 16kHz mono WAV file (optimal for Whisper).
    """
    audio_output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_path,
        "-y",                   # overwrite output
        "-i", str(video_path),
        "-vn",                  # no video
        "-acodec", "pcm_s16le", # 16-bit PCM
        "-ar", "16000",         # 16kHz sample rate (Whisper optimal)
        "-ac", "1",             # mono
        str(audio_output),
    ]

    print(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  ✗ FFmpeg audio extraction failed (exit code {result.returncode})")
        if result.stderr:
            stderr_lines = result.stderr.strip().splitlines()
            for line in stderr_lines[-10:]:
                print(f"    {line}")
        return False

    return True


def transcribe_audio(audio_path: Path, model_name: str) -> str:
    """Transcribe audio using OpenAI Whisper (local model).

    Returns the transcribed text.
    """
    try:
        import whisper
    except ImportError:
        print("Error: 'openai-whisper' package is required.")
        print("  Install with: pip install openai-whisper")
        sys.exit(1)

    print(f"  Loading Whisper model '{model_name}'...")
    model = whisper.load_model(model_name)

    print(f"  Transcribing audio ({audio_path.name})...")
    result = model.transcribe(
        str(audio_path),
        language="en",
        verbose=False,
    )

    return result


def format_transcript(result: dict) -> str:
    """Format the Whisper result into a readable transcript.

    Returns the full text and a timestamped version.
    """
    lines = []

    # Full text at the top
    full_text = result.get("text", "").strip()
    lines.append("# English Transcript")
    lines.append("")
    lines.append(full_text)
    lines.append("")

    # Timestamped segments
    segments = result.get("segments", [])
    if segments:
        lines.append("# Timestamped Segments")
        lines.append("")
        for seg in segments:
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "").strip()

            # Format as MM:SS
            start_m, start_s = divmod(int(start), 60)
            end_m, end_s = divmod(int(end), 60)

            lines.append(f"[{start_m:02d}:{start_s:02d} - {end_m:02d}:{end_s:02d}] {text}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Extract audio from a video and transcribe it using OpenAI Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python extract_script.py input_videos/video.mp4\n"
            "  python extract_script.py input_videos/video.mp4 -o outputs/script/english.txt\n"
            "  python extract_script.py input_videos/video.mp4 --whisper-model medium\n"
        ),
    )
    parser.add_argument(
        "video_path",
        type=str,
        help="Path to the input video file",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"Path to save the transcript (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--audio-output",
        type=str,
        default=None,
        help="Path to save the extracted audio WAV file (default: temp file, deleted after)",
    )
    parser.add_argument(
        "--whisper-model",
        type=str,
        default=DEFAULT_WHISPER_MODEL,
        choices=["tiny", "base", "small", "medium", "large"],
        help=f"Whisper model size (default: {DEFAULT_WHISPER_MODEL})",
    )

    args = parser.parse_args()

    # -- Validate input --
    video_path = Path(args.video_path).resolve()
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    if not video_path.is_file():
        print(f"Error: Not a file: {video_path}")
        sys.exit(1)
    if video_path.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
        print(f"Warning: Unexpected video format '{video_path.suffix}'. Proceeding anyway...")

    output_path = Path(args.output).resolve()

    # -- Banner --
    print("=" * 60)
    print("  Script Extractor — FFmpeg + OpenAI Whisper")
    print("=" * 60)
    print(f"  Video    : {video_path.name}")
    print(f"  Model    : {args.whisper_model}")
    print(f"  Output   : {output_path}")
    print("-" * 60)

    # -- Step 1: Check FFmpeg --
    ffmpeg = check_ffmpeg()

    # -- Step 2: Extract audio --
    print("\n[1/3] Extracting audio from video...")

    keep_audio = args.audio_output is not None
    if keep_audio:
        audio_path = Path(args.audio_output).resolve()
    else:
        # Use temp file that we'll clean up
        temp_dir = tempfile.mkdtemp(prefix="extract_script_")
        audio_path = Path(temp_dir) / "extracted_audio.wav"

    if not extract_audio(ffmpeg, video_path, audio_path):
        print("\n  ✗ Audio extraction failed. Aborting.")
        sys.exit(1)

    size_mb = audio_path.stat().st_size / 1_048_576
    print(f"  ✓ Audio extracted: {audio_path.name} ({size_mb:.1f} MB)")

    # -- Step 3: Transcribe --
    print("\n[2/3] Transcribing audio with Whisper...")
    result = transcribe_audio(audio_path, args.whisper_model)

    full_text = result.get("text", "").strip()
    segments = result.get("segments", [])
    print(f"  ✓ Transcription complete: {len(full_text)} characters, {len(segments)} segments")

    # -- Step 4: Save output --
    print("\n[3/3] Saving transcript...")
    formatted = format_transcript(result)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(formatted, encoding="utf-8")
    print(f"  ✓ Transcript saved to: {output_path}")

    # -- Cleanup temp audio if needed --
    if not keep_audio:
        import shutil as _shutil
        _shutil.rmtree(temp_dir, ignore_errors=True)
        print("  ✓ Temp audio file cleaned up")
    else:
        print(f"  ✓ Audio file kept at: {audio_path}")

    # -- Summary --
    print("\n" + "=" * 60)
    print("  ✅ Script extraction complete!")
    print(f"     Transcript : {output_path}")
    print(f"     Characters : {len(full_text)}")
    print(f"     Segments   : {len(segments)}")
    print("=" * 60)

    # Print first 200 chars as preview
    print(f"\n  Preview: {full_text[:200]}{'...' if len(full_text) > 200 else ''}")
    print("\nDone.")


if __name__ == "__main__":
    main()
