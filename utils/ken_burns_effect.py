#!/usr/bin/env python3
"""
Image-to-Video Ken Burns Effect — Create animated clips from still images.

Takes a directory of images and creates video clips with smooth zoom/pan
effects (Ken Burns) that match target durations for audio sync.

Used for the "images" portion of the hybrid video+image pipeline:
- First 3 minutes: Grok video API (real video clips)
- After 3 minutes: Grok image API + Ken Burns effect (this module)

Usage:
    python ken_burns_effect.py --images-dir outputs/images/ --output-dir outputs/clips/ --durations 6,6,6
"""

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_FPS = 30
DEFAULT_RESOLUTION = (1280, 720)


# ---------------------------------------------------------------------------
# Ken Burns Effects
# ---------------------------------------------------------------------------

def _get_zoom_filter(
    effect: str,
    duration: float,
    width: int = 1280,
    height: int = 720,
    fps: int = DEFAULT_FPS,
) -> str:
    """Build ffmpeg zoompan filter for a Ken Burns effect.

    Effects:
      - zoom_in:       slow zoom into center
      - zoom_out:      start zoomed in, slowly zoom out
      - zoom_in_left:  zoom in toward left side
      - zoom_in_right: zoom in toward right side
      - pan_left:      slow pan from right to left
      - pan_right:     slow pan from left to right
    """
    total_frames = int(duration * fps)
    # zoompan requires d (duration per frame, we set to 1) and total frames via s
    # z = zoom level, x/y = position

    if effect == "zoom_in":
        # Zoom from 1.0x to 1.3x, centered
        return (
            f"zoompan=z='min(zoom+0.001,1.3)':d=1:s={width}x{height}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={fps}"
        )
    elif effect == "zoom_out":
        # Zoom from 1.3x to 1.0x, centered
        return (
            f"zoompan=z='if(eq(on,1),1.3,max(zoom-0.001,1.0))':d=1:s={width}x{height}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={fps}"
        )
    elif effect == "zoom_in_left":
        # Zoom into the left third
        return (
            f"zoompan=z='min(zoom+0.001,1.3)':d=1:s={width}x{height}"
            f":x='iw/6-(iw/zoom/6)':y='ih/2-(ih/zoom/2)':fps={fps}"
        )
    elif effect == "zoom_in_right":
        # Zoom into the right third
        return (
            f"zoompan=z='min(zoom+0.001,1.3)':d=1:s={width}x{height}"
            f":x='5*iw/6-(5*iw/zoom/6)':y='ih/2-(ih/zoom/2)':fps={fps}"
        )
    elif effect == "pan_left":
        # Pan from right to left
        max_pan = int(width * 0.15)
        return (
            f"zoompan=z='1.15':d=1:s={width}x{height}"
            f":x='max(0,{max_pan}-on*{max_pan}/{total_frames})'"
            f":y='ih/2-(ih/zoom/2)':fps={fps}"
        )
    elif effect == "pan_right":
        # Pan from left to right
        max_pan = int(width * 0.15)
        return (
            f"zoompan=z='1.15':d=1:s={width}x{height}"
            f":x='min(iw-iw/zoom, on*{max_pan}/{total_frames})'"
            f":y='ih/2-(ih/zoom/2)':fps={fps}"
        )
    else:
        # Default: gentle zoom in
        return (
            f"zoompan=z='min(zoom+0.0008,1.2)':d=1:s={width}x{height}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={fps}"
        )


# Cycle through effects for visual variety
EFFECT_CYCLE = [
    "zoom_in", "zoom_out", "pan_right", "zoom_in_left",
    "zoom_out", "zoom_in_right", "pan_left", "zoom_in",
]


def apply_ken_burns(
    image_path: Path,
    output_path: Path,
    duration: float = 6.0,
    effect: str | None = None,
    effect_index: int = 0,
    width: int = 1280,
    height: int = 720,
    fps: int = DEFAULT_FPS,
) -> bool:
    """Apply Ken Burns effect to an image, producing a video clip.

    Args:
        image_path: Path to the source image
        output_path: Path for the output .mp4
        duration: Target duration in seconds
        effect: Specific effect name, or None for auto-cycle
        effect_index: Used for cycling effects when effect=None
        width, height: Output resolution
        fps: Frames per second

    Returns:
        True on success
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  ✗ FFmpeg not found")
        return False

    if not image_path.exists():
        print(f"  ✗ Image not found: {image_path}")
        return False

    # Pick effect from cycle
    if effect is None:
        effect = EFFECT_CYCLE[effect_index % len(EFFECT_CYCLE)]

    total_frames = int(duration * fps)

    # Build zoompan filter
    zoom_filter = _get_zoom_filter(effect, duration, width, height, fps)

    # Ensure we have enough frames, and apply scaling
    cmd = [
        ffmpeg, "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", (
            f"scale={width*2}:{height*2}:force_original_aspect_ratio=decrease,"
            f"pad={width*2}:{height*2}:(ow-iw)/2:(oh-ih)/2,"
            f"{zoom_filter},"
            f"scale={width}:{height}"
        ),
        "-t", str(duration),
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-an",
        str(output_path),
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024:
            return True
        else:
            # Fallback: simpler approach without complex zoompan
            simple_cmd = [
                ffmpeg, "-y",
                "-loop", "1",
                "-i", str(image_path),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-t", str(duration),
                "-c:v", "libx264",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                "-an",
                str(output_path),
            ]
            r2 = subprocess.run(simple_cmd, capture_output=True, text=True, timeout=120)
            if r2.returncode == 0:
                print(f"    ⚠ Used simple static fallback for {image_path.name}")
                return True
            print(f"    ✗ FFmpeg failed: {r.stderr[:200]}")
            return False
    except Exception as e:
        print(f"    ✗ Ken Burns error: {e}")
        return False


# ---------------------------------------------------------------------------
# Batch Processing
# ---------------------------------------------------------------------------

def batch_ken_burns(
    images: list[tuple[int, Path]],  # (scene_number, image_path)
    output_dir: Path,
    durations: dict[int, float] | None = None,
    default_duration: float = 6.0,
    width: int = 1280,
    height: int = 720,
) -> dict[int, Path]:
    """Apply Ken Burns to a batch of images.

    Args:
        images: List of (scene_number, image_path) tuples
        output_dir: Directory for output clips
        durations: Optional dict of scene_number → duration
        default_duration: Default clip duration
        width, height: Output resolution

    Returns:
        Dict of scene_number → output clip path
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    print(f"\n{'='*60}")
    print(f"  🎬 Ken Burns Image Animator")
    print(f"{'='*60}")
    print(f"  Images:     {len(images)}")
    print(f"  Output:     {output_dir}")
    print(f"  Resolution: {width}×{height}")

    for idx, (scene_num, img_path) in enumerate(images):
        dur = durations.get(scene_num, default_duration) if durations else default_duration
        out_path = output_dir / f"clip_{scene_num:02d}.mp4"

        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"  [{idx+1}/{len(images)}] Scene {scene_num}: ✓ Already exists")
            results[scene_num] = out_path
            continue

        effect = EFFECT_CYCLE[idx % len(EFFECT_CYCLE)]
        print(f"  [{idx+1}/{len(images)}] Scene {scene_num}: {effect} ({dur:.1f}s)...")

        ok = apply_ken_burns(
            img_path, out_path,
            duration=dur,
            effect=effect,
            effect_index=idx,
            width=width,
            height=height,
        )

        if ok:
            size_kb = out_path.stat().st_size / 1024
            print(f"    ✓ Saved: {out_path.name} ({size_kb:.0f} KB)")
            results[scene_num] = out_path
        else:
            print(f"    ✗ Failed: scene {scene_num}")

    print(f"\n  ✅ Animated: {len(results)}/{len(images)} images")
    print(f"{'='*60}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apply Ken Burns zoom/pan effects to images → video clips"
    )
    parser.add_argument("--images-dir", required=True, help="Directory with scene images")
    parser.add_argument("--output-dir", default="outputs/clips/", help="Output clips directory")
    parser.add_argument("--duration", type=float, default=6.0, help="Clip duration (seconds)")
    parser.add_argument("--width", type=int, default=1280, help="Output width")
    parser.add_argument("--height", type=int, default=720, help="Output height")

    args = parser.parse_args()

    images_dir = Path(args.images_dir)
    if not images_dir.exists():
        print(f"Error: {images_dir} not found")
        sys.exit(1)

    # Collect images
    import re
    images = []
    for f in sorted(images_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            m = re.search(r'(\d+)', f.name)
            scene_num = int(m.group(1)) if m else len(images) + 1
            images.append((scene_num, f))

    if not images:
        print("No images found")
        sys.exit(1)

    batch_ken_burns(
        images,
        Path(args.output_dir),
        default_duration=args.duration,
        width=args.width,
        height=args.height,
    )
