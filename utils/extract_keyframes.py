#!/usr/bin/env python3
"""
Keyframe Extractor — Extracts representative frames from a video based on scene timestamps.

Given a video file and an analysis.yaml (with scene timestamps), this tool extracts
the most representative frame from each scene. These frames are used as REFERENCE
images for the image generation step, anchoring the output to the original video's
visual composition.

Usage:
    python extract_keyframes.py video.mp4 analysis.yaml -o outputs/keyframes/
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: 'pyyaml' package is required. Install with: pip install pyyaml")
    sys.exit(1)


def check_ffmpeg() -> str:
    """Find ffmpeg binary."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Error: FFmpeg not found. Please install FFmpeg.")
        sys.exit(1)
    return ffmpeg


def parse_timestamp(ts: str) -> float:
    """Parse a timestamp string like '00:04', '00:04 - 00:08', '0:30', etc. into seconds.
    
    If a range is given (e.g., '00:04 - 00:08'), returns the midpoint.
    """
    # Handle range format: "00:04 - 00:08"
    if " - " in ts:
        parts = ts.split(" - ")
        start = _ts_to_seconds(parts[0].strip())
        end = _ts_to_seconds(parts[1].strip())
        # Extract frame at ~30% into the scene (biased toward start for better visual clarity)
        return start + (end - start) * 0.3
    return _ts_to_seconds(ts.strip())


def _ts_to_seconds(ts: str) -> float:
    """Convert MM:SS or HH:MM:SS to seconds."""
    parts = ts.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        try:
            return float(ts)
        except ValueError:
            return 0.0


def get_video_duration(ffmpeg_path: str, video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def extract_frame(ffmpeg_path: str, video_path: str, timestamp_sec: float,
                  output_path: str, quality: int = 2) -> bool:
    """Extract a single frame from the video at the given timestamp.
    
    Args:
        ffmpeg_path: Path to ffmpeg binary
        video_path: Path to input video
        timestamp_sec: Time in seconds to extract
        output_path: Path to save the PNG frame
        quality: JPEG quality (1=best, 31=worst), only applies to jpg
    """
    cmd = [
        ffmpeg_path, "-y",
        "-ss", f"{timestamp_sec:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", str(quality),
        str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0 and Path(output_path).exists()
    except Exception as e:
        print(f"  ✗ Frame extraction error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Extract keyframes from a video based on scene analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python extract_keyframes.py video.mp4 analysis.yaml\n"
            "  python extract_keyframes.py video.mp4 analysis.yaml -o outputs/keyframes/\n"
        ),
    )
    parser.add_argument("video_path", type=str, help="Path to the input video file")
    parser.add_argument("analysis_file", type=str, help="Path to the scene analysis YAML")
    parser.add_argument("-o", "--output-dir", type=str, default="outputs/keyframes",
                        help="Directory to save extracted keyframes (default: outputs/keyframes)")

    args = parser.parse_args()

    video_path = Path(args.video_path).resolve()
    analysis_path = Path(args.analysis_file).resolve()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    if not analysis_path.exists():
        print(f"Error: Analysis file not found: {analysis_path}")
        sys.exit(1)

    ffmpeg = check_ffmpeg()

    # Load analysis
    analysis = yaml.safe_load(analysis_path.read_text(encoding="utf-8"))
    scenes = analysis.get("scenes", [])

    if not scenes:
        print("Error: No scenes found in analysis file.")
        sys.exit(1)

    video_duration = get_video_duration(ffmpeg, str(video_path))

    print("=" * 60)
    print("  Keyframe Extractor")
    print("=" * 60)
    print(f"  Video    : {video_path.name}")
    print(f"  Duration : {video_duration:.1f}s")
    print(f"  Scenes   : {len(scenes)}")
    print(f"  Output   : {output_dir}")
    print("-" * 60)

    success_count = 0
    for scene in scenes:
        scene_num = scene.get("scene_number", 0)
        timestamp = scene.get("timestamp", "00:00")
        
        extract_time = parse_timestamp(timestamp)
        
        # Clamp to valid range
        if extract_time >= video_duration and video_duration > 0:
            extract_time = video_duration - 0.5
        if extract_time < 0:
            extract_time = 0

        out_path = output_dir / f"keyframe_{scene_num:02d}.png"

        print(f"\n  Scene {scene_num}: extracting at {extract_time:.2f}s (from '{timestamp}')...")
        
        if extract_frame(ffmpeg, str(video_path), extract_time, str(out_path)):
            size_kb = out_path.stat().st_size / 1024
            print(f"  ✓ Saved: {out_path.name} ({size_kb:.0f} KB)")
            success_count += 1
        else:
            print(f"  ✗ Failed to extract frame for scene {scene_num}")

    print(f"\n{'=' * 60}")
    print(f"  ✅ Extracted {success_count}/{len(scenes)} keyframes")
    print(f"  📁 Output: {output_dir}")
    print("=" * 60)

    if success_count < len(scenes):
        print("\nWarning: Some frames could not be extracted.")
        sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
