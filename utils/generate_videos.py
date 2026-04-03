#!/usr/bin/env python3
"""
Video Generator — Text-to-Video via Meta AI SDK.

Uses the MetaAI SDK directly (as in metaai-api/test_meta_video.py).
Cookies are loaded from metaai-api/.env automatically by the SDK.

Usage:
    python generate_videos.py prompts.yaml -o outputs/clips/
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' required. Install: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

DEFAULT_OUTPUT_DIR = "outputs/clips"
MAX_RETRIES = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_prompts_file(path: Path) -> dict:
    """Load a prompts YAML or JSON file."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            print("Error: 'pyyaml' required. Install: pip install pyyaml")
            sys.exit(1)
        data = yaml.safe_load(raw)
    elif path.suffix == ".json":
        data = json.loads(raw)
    else:
        try:
            import yaml
            data = yaml.safe_load(raw)
        except Exception:
            data = json.loads(raw)

    if not isinstance(data, dict) or "scenes" not in data:
        print("Error: Prompts file must contain a 'scenes' list.")
        sys.exit(1)
    return data


def build_video_prompt(scene: dict, visual_style: str = "") -> str:
    """Build a text prompt for video generation from scene data."""
    vp = scene.get("video_prompt", {})
    raw = vp.get("prompt", "") if isinstance(vp, dict) else str(vp)

    ip = scene.get("image_prompt", {})
    img = ip.get("prompt", "") if isinstance(ip, dict) else str(ip)

    prompt = raw or img
    if not prompt:
        return ""

    if visual_style and not prompt.lower().startswith(visual_style.lower()[:20]):
        prompt = f"{visual_style}. {prompt}"

    if "cinematic" not in prompt.lower():
        prompt += " Cinematic quality, smooth natural motion."

    if len(prompt) > 950:
        prompt = prompt[:947] + "..."
    return prompt


def find_scene_image(images_dir: Path, scene_num: int) -> Optional[Path]:
    """Find an image file for a specific scene number."""
    if not images_dir or not images_dir.exists():
        return None
    
    # Try common naming patterns
    patterns = [
        f"scene_{scene_num:02d}.png",
        f"scene_{scene_num:02d}.jpg",
        f"clip_{scene_num:02d}.png",
        f"clip_{scene_num:02d}.jpg",
        f"{scene_num:02d}.png",
        f"{scene_num:02d}.jpg",
    ]
    
    for pattern in patterns:
        img_path = images_dir / pattern
        if img_path.exists():
            return img_path
            
    # Try searching for any file containing the number
    for f in images_dir.iterdir():
        if f.is_file() and f.suffix.lower() in ('.png', '.jpg', '.jpeg'):
            if f"_{scene_num:02d}" in f.name or f" {scene_num}" in f.name:
                return f
                
    return None


def get_metaai_instance():
    """Create MetaAI instance with cookies from .env file or meta_cookies.json.

    The SDK loads from metaai-api/.env automatically via dotenv.
    We also support passing cookies from meta_cookies.json.
    """
    # Add metaai-api/src to path
    metaai_src = str(PROJECT_ROOT / "metaai-api" / "src")
    if metaai_src not in sys.path:
        sys.path.insert(0, metaai_src)

    from metaai_api import MetaAI

    # Try loading cookies from meta_cookies.json first
    cookies = None
    cookies_file = PROJECT_ROOT / "meta_cookies.json"
    if cookies_file.exists():
        try:
            data = json.loads(cookies_file.read_text())
            # Handle both list of dicts (for rotation) and single dict
            c = data[0] if isinstance(data, list) and data else data
            
            if isinstance(c, dict):
                # Required core cookies for MetaAI (Restricted to requested ones)
                cookies = {
                    "datr": c.get("datr", ""),
                    "abra_sess": c.get("abra_sess", ""),
                    "ecto_1_sess": c.get("ecto_1_sess", ""),
                }
                # Other cookies (wd, dpr, ps_l, ps_n, rd_challenge) are ignored to stick to 'required only'
                print(f"  Loaded required cookies from {cookies_file.name}")
        except Exception as e:
            print(f"  ⚠ Failed to load {cookies_file}: {e}")

    if cookies:
        ai = MetaAI(cookies=cookies)
    else:
        # SDK will load from .env automatically
        ai = MetaAI()

    return ai


def download_video(url: str, out_path: Path, timeout: int = 120) -> bool:
    """Download video from URL to file."""
    if not url:
        return False
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        if resp.status_code == 200:
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            if out_path.stat().st_size > 1024:
                return True
            out_path.unlink(missing_ok=True)
    except Exception as e:
        print(f"      ⚠ Download error: {e}")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Generate video clips using Meta AI SDK (as in test_meta_video.py).",
    )
    parser.add_argument("prompts_file", type=str, help="Path to prompts YAML/JSON")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--retries", type=int, default=MAX_RETRIES)
    # BWC args (kept silently)
    parser.add_argument("--images-dir", type=str, default=None, help="Optional directory containing images to animate (scene_XX.png)")
    parser.add_argument("--meta-api-base", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--cookies-file", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--aspect-ratio", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--video-length", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--grok-api-base", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--api-key", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--model", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--resolution", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--analysis-file", type=str, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    prompts_path = Path(args.prompts_file).resolve()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not prompts_path.exists():
        print(f"Error: Prompts file not found: {prompts_path}")
        sys.exit(1)

    # -- Initialize MetaAI SDK --
    print("=" * 60)
    print("  Video Generator — Meta AI SDK")
    print("=" * 60)
    print("  Initializing MetaAI...")

    try:
        ai = get_metaai_instance()
        print("  ✓ MetaAI initialized")
    except Exception as e:
        print(f"  ✗ Failed to initialize MetaAI: {e}")
        sys.exit(1)

    # -- Load prompts --
    prompts_data = load_prompts_file(prompts_path)
    scenes = prompts_data.get("scenes", [])
    total = len(scenes)
    visual_style = prompts_data.get("visual_style", "")
    style_sub = prompts_data.get("style_subcategory", "")
    style_prefix = f"{visual_style}, {style_sub}" if visual_style and style_sub else visual_style

    print(f"  Output   : {output_dir}")
    print(f"  Scenes   : {total}")
    print(f"  Retries  : {args.retries}")
    if style_prefix:
        print(f"  Style    : {style_prefix[:80]}")
    print("-" * 60)

    # -- Video generation loop --
    success_count = 0
    fail_count = 0
    images_dir = Path(args.images_dir) if args.images_dir else None

    for i, scene in enumerate(scenes, 1):
        scene_num = scene.get("scene_number", i)
        video_prompt = build_video_prompt(scene, style_prefix)

        if not video_prompt or len(video_prompt.strip()) < 10:
            print(f"\n  [{i}/{total}] Scene {scene_num}: ⚠ Empty prompt, skipping.")
            fail_count += 1
            continue

        out_path = output_dir / f"clip_{scene_num:02d}.mp4"

        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"\n  [{i}/{total}] Scene {scene_num}: ✓ Already exists ({out_path.stat().st_size / 1_048_576:.1f} MB)")
            success_count += 1
            continue

        print(f"\n  [{i}/{total}] Scene {scene_num}...")
        print(f"    Prompt: {video_prompt[:150]}{'...' if len(video_prompt) > 150 else ''}")

        # Try to find reference image for animation
        media_ids = None
        attachment_metadata = None
        if images_dir:
            img_path = find_scene_image(images_dir, scene_num)
            if img_path:
                print(f"    🖼 Found reference image: {img_path.name}")
                print(f"    ⬆ Uploading image to Meta AI...")
                upload_res = ai.upload_image(str(img_path))
                if upload_res.get("success") and upload_res.get("media_id"):
                    media_ids = [upload_res["media_id"]]
                    attachment_metadata = {
                        "file_size": upload_res.get("file_size"),
                        "mime_type": upload_res.get("mime_type")
                    }
                    print(f"    ✓ Image uploaded (ID: {media_ids[0]})")
                else:
                    print(f"    ⚠ Image upload failed: {upload_res.get('error')}")

        scene_done = False
        for attempt in range(1, args.retries + 1):
            if attempt > 1:
                wait = min(attempt * 10, 60)
                print(f"    [Retry {attempt}/{args.retries}] waiting {wait}s...")
                time.sleep(wait)

            start = time.time()
            try:
                # Use generate_video() — has built-in polling, returns actual URLs
                result = ai.generate_video(
                    prompt=video_prompt,
                    media_ids=media_ids,
                    attachment_metadata=attachment_metadata,
                    wait_before_poll=15,
                    max_attempts=40,
                    wait_seconds=5,
                    verbose=True,
                )
                elapsed = time.time() - start

                if result.get("success") and result.get("video_urls"):
                    video_urls = result["video_urls"]
                    print(f"    ✓ Generated {len(video_urls)} video(s) ({elapsed:.1f}s)")

                    downloaded = False
                    for vurl in video_urls:
                        if download_video(vurl, out_path):
                            size_mb = out_path.stat().st_size / 1_048_576
                            print(f"    ✓ Saved: {out_path} ({size_mb:.1f} MB)")
                            downloaded = True
                            break
                        else:
                            print(f"    ⚠ Download failed: {vurl[:80]}...")

                    if downloaded:
                        success_count += 1
                        scene_done = True
                        break
                    else:
                        # Save URLs for manual retrieval
                        urls_file = output_dir / f"clip_{scene_num:02d}_urls.txt"
                        urls_file.write_text("\n".join(video_urls), encoding="utf-8")
                        print(f"    ⚠ URLs saved to {urls_file}")
                else:
                    error = result.get("error", "No video URLs returned")
                    print(f"    ✗ Failed ({elapsed:.1f}s): {error}")

            except Exception as e:
                elapsed = time.time() - start
                print(f"    ✗ Exception ({elapsed:.1f}s): {e}")

        if not scene_done:
            print(f"    ✗ FAILED: Scene {scene_num} after {args.retries} attempts.")
            fail_count += 1

    # -- Summary --
    print("\n" + "=" * 60)
    print(f"  ✅ Generated: {success_count}/{total} video clips")
    if fail_count:
        print(f"  ⚠  Failed:    {fail_count}/{total}")
    print(f"  📁 Output:    {output_dir}")
    print("=" * 60)

    if fail_count == total and total > 0:
        sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
