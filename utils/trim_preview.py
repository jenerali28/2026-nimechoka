#!/usr/bin/env python3
"""
Video Preview Trimmer — Extract first N seconds of a video for partial analysis.

For long videos, the pipeline only needs to visually analyze the first segment.
This utility extracts that preview clip using FFmpeg.

Usage:
    python trim_preview.py input.mp4 -o preview.mp4
    python trim_preview.py input.mp4 --duration 60 --threshold 90
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_PREVIEW_DURATION = 60   # seconds to extract
DEFAULT_THRESHOLD = 90          # only trim if video is longer than this


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        ffprobe = shutil.which("ffmpeg")
        if ffprobe:
            ffprobe = ffprobe.replace("ffmpeg", "ffprobe")
        else:
            print("Error: ffprobe/ffmpeg not found on PATH.")
            sys.exit(1)

    try:
        result = subprocess.run(
            [ffprobe, "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Warning: Could not determine video duration: {e}")
        return 0.0


def trim_preview(
    video_path: str,
    output_path: str | None = None,
    duration: int = DEFAULT_PREVIEW_DURATION,
    threshold: int = DEFAULT_THRESHOLD,
) -> tuple[str, float, bool]:
    """Extract the first `duration` seconds of a video if it exceeds `threshold`.

    Returns:
        (path_to_use, total_duration, was_trimmed)
        - path_to_use: the preview clip path if trimmed, or the original path
        - total_duration: the full video's duration in seconds
        - was_trimmed: True if a preview clip was created
    """
    total_duration = get_video_duration(video_path)

    if total_duration <= threshold:
        return video_path, total_duration, False

    # Default output: sibling file with _preview suffix
    if output_path is None:
        p = Path(video_path)
        output_path = str(p.parent / f"{p.stem}_preview{p.suffix}")

    # Already exists? Re-use it.
    if Path(output_path).exists():
        print(f"  ✓ Preview clip already exists: {output_path}")
        return output_path, total_duration, True

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Error: ffmpeg not found on PATH.")
        sys.exit(1)

    print(f"  🎬 Trimming first {duration}s of {total_duration:.0f}s video...")
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-t", str(duration),
        "-c", "copy",          # fast copy, no re-encode
        "-avoid_negative_ts", "make_zero",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  ✗ FFmpeg trim failed: {result.stderr[-300:]}")
        # Fallback: use original
        return video_path, total_duration, False

    print(f"  ✓ Preview clip created: {output_path}")
    return output_path, total_duration, True


def main():
    parser = argparse.ArgumentParser(
        description="Extract a preview clip from a long video.",
    )
    parser.add_argument("video_path", help="Path to the input video")
    parser.add_argument("-o", "--output", default=None, help="Output path for preview clip")
    parser.add_argument("--duration", type=int, default=DEFAULT_PREVIEW_DURATION,
                        help=f"Preview duration in seconds (default: {DEFAULT_PREVIEW_DURATION})")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Only trim videos longer than this (default: {DEFAULT_THRESHOLD}s)")

    args = parser.parse_args()

    path_used, total_dur, trimmed = trim_preview(
        args.video_path, args.output, args.duration, args.threshold
    )

    print(f"\n  Total duration : {total_dur:.1f}s")
    print(f"  Trimmed        : {'Yes' if trimmed else 'No (video is short enough)'}")
    print(f"  Path to use    : {path_used}")


if __name__ == "__main__":
    main()
