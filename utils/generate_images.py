#!/usr/bin/env python3
"""
Image Generator — Batch Image Generation via Whisk API (Imagen 3.5).

Takes a prompts file (YAML) and generates one image per scene using
Google's Imagen 3.5 through the whisk-api CLI.

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
WHISK_CLI = PROJECT_ROOT / "whisk-api" / "dist" / "Cli.js"

DEFAULT_OUTPUT_DIR = Path("outputs/images")
DEFAULT_ASPECT_RATIO = "LANDSCAPE"  # SQUARE, PORTRAIT, LANDSCAPE
MAX_RETRIES = 3

# Map common aspect ratios to whisk format
ASPECT_MAP = {
    "16:9": "LANDSCAPE",
    "9:16": "PORTRAIT",
    "1:1": "SQUARE",
    "landscape": "LANDSCAPE",
    "portrait": "PORTRAIT",
    "square": "SQUARE",
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
    """Convert aspect ratio string to whisk format."""
    return ASPECT_MAP.get(aspect_str.lower(), aspect_str.upper())


def generate_image_whisk(
    prompt: str,
    cookie: str,
    output_dir: Path,
    aspect: str = "LANDSCAPE",
    timeout: int = 120,
) -> tuple:
    """Generate image using whisk-api CLI.

    Returns (success: bool, output_path: Path | None, error: str | None).
    """
    if not WHISK_CLI.exists():
        return False, None, f"whisk-api CLI not found at {WHISK_CLI}"

    cmd = [
        "node", str(WHISK_CLI),
        "generate",
        "--prompt", prompt,
        "--aspect", aspect,
        "--dir", str(output_dir),
        "--cookie", cookie,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT / "whisk-api"),
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            error_msg = stderr or stdout or "Unknown error"
            if "cookie" in error_msg.lower() or "token" in error_msg.lower():
                return False, None, f"auth_error: {error_msg[:200]}"
            return False, None, error_msg[:300]

        # Parse output to find saved file path
        # Expected: "[+] Saved to: /path/to/img_xxxxx.png"
        saved_path = None
        for line in stdout.splitlines():
            if "Saved to:" in line:
                saved_path = line.split("Saved to:")[-1].strip()
                break

        if saved_path and Path(saved_path).exists():
            return True, Path(saved_path), None
        else:
            # Check if any new image appeared in output_dir
            images = sorted(output_dir.glob("img_*.*"), key=lambda p: p.stat().st_mtime)
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
        description="Generate images via Whisk API (Imagen 3.5)."
    )
    parser.add_argument("prompts_file", help="Path to prompts.yaml")
    parser.add_argument("-o", "--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Output directory")
    parser.add_argument("--cookie", type=str,
                        default=os.environ.get("WHISK_COOKIE", ""),
                        help="Google account cookie for Whisk (or set WHISK_COOKIE env)")
    parser.add_argument("--aspect-ratio", default=DEFAULT_ASPECT_RATIO,
                        help=f"Aspect ratio: LANDSCAPE, PORTRAIT, SQUARE, 16:9, etc. (default: {DEFAULT_ASPECT_RATIO})")
    parser.add_argument("--retries", type=int, default=MAX_RETRIES,
                        help=f"Max retries per scene (default: {MAX_RETRIES})")
    # BWC args (ignored silently)
    parser.add_argument("--api-base", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--model", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--keyframes-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--style-bible", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--character-bible", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Cookie is required
    cookie = args.cookie
    if not cookie:
        # Try loading from a file
        cookie_file = PROJECT_ROOT / "whisk_cookie.txt"
        if cookie_file.exists():
            cookie = cookie_file.read_text().strip()
        else:
            print("Error: Cookie is required. Pass --cookie or set WHISK_COOKIE env var.")
            print("  Or create whisk_cookie.txt in the project root.")
            sys.exit(1)

    prompts_path = Path(args.prompts_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    aspect = resolve_aspect(args.aspect_ratio)

    data = load_prompts(prompts_path)
    scenes = data.get("scenes", [])

    # --- Banner ---
    print("=" * 60)
    print("  Image Generator — Whisk API (Imagen 3.5)")
    print("=" * 60)
    print(f"  CLI      : {WHISK_CLI}")
    print(f"  Output   : {output_dir}")
    print(f"  Aspect   : {aspect}")
    print(f"  Scenes   : {len(scenes)}")
    print("-" * 60)

    success_count = 0
    # Temp dir for whisk output (it names files randomly)
    whisk_tmp = output_dir / "_whisk_tmp"
    whisk_tmp.mkdir(exist_ok=True)

    for i, scene in enumerate(scenes, 1):
        scene_num = scene.get("scene_number", i)
        img_prompt_data = scene.get("image_prompt", {})
        prompt_text = img_prompt_data.get("prompt", "") if isinstance(img_prompt_data, dict) else str(img_prompt_data)

        if not prompt_text:
            print(f"[{i}/{len(scenes)}] Scene {scene_num}: ⚠ No prompt found.")
            continue

        out_path = output_dir / f"scene_{scene_num:02d}.png"
        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"[{i}/{len(scenes)}] Scene {scene_num}: ✓ Already exists.")
            success_count += 1
            continue

        # Clean prompt (whisk has a char limit)
        clean_prompt = prompt_text.strip()
        if len(clean_prompt) > 900:
            clean_prompt = clean_prompt[:897] + "..."

        print(f"[{i}/{len(scenes)}] Scene {scene_num}...")
        print(f"  Prompt: {clean_prompt[:120]}{'...' if len(clean_prompt) > 120 else ''}")

        scene_success = False
        for attempt in range(1, args.retries + 1):
            if attempt > 1:
                wait = min(attempt * 5, 30)
                print(f"  [Retry {attempt}/{args.retries}] waiting {wait}s...")
                time.sleep(wait)

            ok, img_path, error = generate_image_whisk(
                prompt=clean_prompt,
                cookie=cookie,
                output_dir=whisk_tmp,
                aspect=aspect,
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
        shutil.rmtree(whisk_tmp, ignore_errors=True)
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
