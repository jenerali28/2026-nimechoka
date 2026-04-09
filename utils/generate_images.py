#!/usr/bin/env python3
"""
Image Generator — Batch Image Generation via ImageFX API (Imagen 4).

Takes a prompts file (YAML) and generates one image per scene using
Google's ImageFX through the imageFX-api CLI.

Usage:
    python generate_images.py prompts.yaml -o outputs/images/
    python generate_images.py prompts.yaml -o outputs/images/ --aspect-ratio LANDSCAPE
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
IMAGEFX_CLI = PROJECT_ROOT / "imageFX-api" / "dist" / "cli.js"

DEFAULT_OUTPUT_DIR = Path("outputs/images")
DEFAULT_ASPECT_RATIO = "LANDSCAPE"  # SQUARE, PORTRAIT, LANDSCAPE
MAX_RETRIES = 3

# Map common aspect ratios to imageFX format
ASPECT_MAP = {
    "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "1:1": "IMAGE_ASPECT_RATIO_SQUARE",
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "square": "IMAGE_ASPECT_RATIO_SQUARE",
    "LANDSCAPE": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "PORTRAIT": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "SQUARE": "IMAGE_ASPECT_RATIO_SQUARE",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_prompts(path: Path) -> dict:
    """Load prompts from YAML/JSON."""
    import yaml
    if not path.exists():
        print(f"Error: Prompts file not found: {path}")
        sys.exit(1)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_aspect(aspect_str: str) -> str:
    """Convert aspect ratio string to imageFX format."""
    return ASPECT_MAP.get(aspect_str, "IMAGE_ASPECT_RATIO_LANDSCAPE")


def generate_image_fx(
    prompt: str,
    cookie: str,
    output_dir: Path,
    aspect: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
    model: str = "IMAGEN_4",
    timeout: int = 120,
) -> tuple:
    """Generate image using imageFX-api CLI.

    Returns (success: bool, output_path: Path | None, error: str | None).
    """
    if not IMAGEFX_CLI.exists():
        return False, None, f"imageFX-api CLI not found at {IMAGEFX_CLI}"

    cmd = [
        "node", str(IMAGEFX_CLI),
        "--prompt", prompt,
        "--ratio", aspect,
        "--dir", str(output_dir),
        "--cookie", cookie,
        "--model", model,
        "--count", "1"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT / "imageFX-api"),
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            error_msg = stderr or stdout or "Unknown error"
            if "cookie" in error_msg.lower() or "token" in error_msg.lower():
                return False, None, f"auth_error: {error_msg[:200]}"
            return False, None, error_msg[:300]

        # ImageFX CLI saves images with random names like image_1740512345678.png
        # We look for the most recently created image in the output_dir
        images = sorted(output_dir.glob("image_*.png"), key=lambda p: p.stat().st_mtime)
        if images:
            return True, images[-1], None
        
        return False, None, f"No image file found. stdout: {stdout[:200]}"

    except subprocess.TimeoutExpired:
        return False, None, f"Timeout after {timeout}s"
    except Exception as e:
        return False, None, str(e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate images via ImageFX API (Imagen 4)."
    )
    parser.add_argument("prompts_file", help="Path to prompts.yaml")
    parser.add_argument("-o", "--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Output directory")
    parser.add_argument("--cookie", type=str,
                        default=os.environ.get("IMAGEFX_COOKIE", ""),
                        help="Google account cookie for ImageFX (or set IMAGEFX_COOKIE env)")
    parser.add_argument("--aspect-ratio", default=DEFAULT_ASPECT_RATIO,
                        help=f"Aspect ratio: LANDSCAPE, PORTRAIT, SQUARE, 16:9, etc. (default: {DEFAULT_ASPECT_RATIO})")
    parser.add_argument("--retries", type=int, default=MAX_RETRIES,
                        help=f"Max retries per scene (default: {MAX_RETRIES})")
    parser.add_argument("--model", type=str, default="IMAGEN_4", 
                        help="Model to use (default: IMAGEN_4)")
    # BWC args (ignored silently)
    parser.add_argument("--api-base", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--keyframes-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--style-bible", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--character-bible", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Cookie is required
    cookie = args.cookie
    if not cookie:
        # Try loading from imagefx_cookie.txt or whisk_cookie.txt
        for cf in ["imagefx_cookie.txt", "whisk_cookie.txt"]:
            cookie_file = PROJECT_ROOT / cf
            if cookie_file.exists():
                cookie = cookie_file.read_text().strip()
                break
        
        if not cookie:
            print("Error: Cookie is required. Pass --cookie or set IMAGEFX_COOKIE env var.")
            print("  Or create imagefx_cookie.txt in the project root.")
            sys.exit(1)

    prompts_path = Path(args.prompts_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    aspect = resolve_aspect(args.aspect_ratio)

    data = load_prompts(prompts_path)
    scenes = data.get("scenes", [])

    # --- Banner ---
    print("=" * 60)
    print("  Image Generator — ImageFX API (Imagen 4)")
    print("=" * 60)
    print(f"  CLI      : {IMAGEFX_CLI}")
    print(f"  Output   : {output_dir}")
    print(f"  Aspect   : {aspect}")
    print(f"  Model    : {args.model}")
    print(f"  Scenes   : {len(scenes)}")
    print("-" * 60)

    success_count = 0
    # Temp dir for imageFX output
    fx_tmp = output_dir / "_imagefx_tmp"
    fx_tmp.mkdir(exist_ok=True)

    for i, scene in enumerate(scenes, 1):
        scene_num = scene.get("scene_number", i)
        img_prompt_data = scene.get("image_prompt", {})

        # Handle structured JSON format (new format) or legacy flat string
        if isinstance(img_prompt_data, dict) and "global_context" in img_prompt_data:
            # Flatten structured prompt to string
            gc = img_prompt_data.get("global_context", {})
            scene_desc = gc.get("scene_description", "")
            time_of_day = gc.get("time_of_day", "")
            weather = gc.get("weather_atmosphere", "")
            lighting = img_prompt_data.get("global_context", {}).get("lighting", {})
            light_desc = f"{lighting.get('quality','')} {lighting.get('source','')} lighting"
            comp = img_prompt_data.get("composition", {})
            camera = comp.get("camera_angle", "")
            framing = comp.get("framing", "")
            focal = comp.get("focal_point", "")
            objects = img_prompt_data.get("objects", [])
            obj_descs = []
            for obj in objects:
                label = obj.get("label", "")
                loc = obj.get("location", "")
                attrs = obj.get("visual_attributes", {})
                color = attrs.get("color", "")
                micro = obj.get("micro_details", [])
                pose = obj.get("pose_or_orientation", "")
                micro_str = ", ".join(micro[:3]) if micro else ""
                obj_descs.append(f"{label} ({loc}): {color}. {micro_str}. {pose}".strip(". "))
            rels = img_prompt_data.get("semantic_relationships", [])
            parts = [
                "2D digital illustration, animation frame.",
                scene_desc,
                f"{time_of_day}, {weather}." if time_of_day else "",
                light_desc + ".",
                f"{camera}, {framing}. Focal point: {focal}." if camera else "",
            ] + obj_descs + rels + [
                "Oversized cartoon heads, stick-figure bodies, thick black outlines, flat digital coloring."
            ]
            prompt_text = " ".join(p for p in parts if p.strip())
        else:
            prompt_text = img_prompt_data.get("prompt", "") if isinstance(img_prompt_data, dict) else str(img_prompt_data)

        if not prompt_text:
            print(f"[{i}/{len(scenes)}] Scene {scene_num}: ⚠ No prompt found.")
            continue

        out_path = output_dir / f"scene_{scene_num:02d}.png"
        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"[{i}/{len(scenes)}] Scene {scene_num}: ✓ Already exists.")
            success_count += 1
            continue

        # Clean prompt
        clean_prompt = prompt_text.strip()
        if len(clean_prompt) > 1000:
            clean_prompt = clean_prompt[:997] + "..."

        print(f"[{i}/{len(scenes)}] Scene {scene_num}...")
        print(f"  Prompt: {clean_prompt[:120]}{'...' if len(clean_prompt) > 120 else ''}")

        scene_success = False
        for attempt in range(1, args.retries + 1):
            if attempt > 1:
                wait = min(attempt * 5, 30)
                print(f"  [Retry {attempt}/{args.retries}] waiting {wait}s...")
                time.sleep(wait)

            ok, img_path, error = generate_image_fx(
                prompt=clean_prompt,
                cookie=cookie,
                output_dir=fx_tmp,
                aspect=aspect,
                model=args.model,
            )

            if ok and img_path:
                # Move to final location with proper name
                shutil.move(str(img_path), str(out_path))
                size_kb = out_path.stat().st_size / 1024
                print(f"  ✓ Saved: {out_path} ({size_kb:.0f} KB)")
                scene_success = True
                success_count += 1
                break
            else:
                print(f"  ✗ Attempt {attempt} failed: {error}")
                if error and "auth_error" in error:
                    print("  ⚠ Authentication error — cookie may be expired.")
                    break  # Don't retry auth errors

        if not scene_success:
            print(f"  ✗ Failed to generate image for Scene {scene_num}.")

    # Cleanup temp dir
    try:
        shutil.rmtree(fx_tmp, ignore_errors=True)
    except Exception:
        pass

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  Summary: {success_count}/{len(scenes)} images generated.")
    print(f"  Output:  {output_dir}")
    print(f"{'=' * 60}")

    failed_count = len(scenes) - success_count
    if failed_count > 0:
        fail_ratio = failed_count / max(len(scenes), 1)
        if fail_ratio > 0.5:
            print(f"Error: Too many failures ({failed_count}/{len(scenes)} = {fail_ratio:.0%}). Aborting.")
            sys.exit(1)
        else:
            print(f"Warning: {failed_count} scene(s) failed, but {success_count}/{len(scenes)} succeeded. Continuing.")


if __name__ == "__main__":
    main()
