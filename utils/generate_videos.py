#!/usr/bin/env python3
"""
Video Generator — Text-to-Video via Grok2API.

Strategy:
  - First 3 minutes of narration -> full AI-generated video clips (Grok Aurora)
  - Remaining narration -> static images (Grok Imagine) with Ken Burns zoom effect

After the main pass, any still-missing clips are retried up to RETRY_ROUNDS times
with progressively simplified prompts. The script only exits when every scene either
has a valid clip on disk or has genuinely exhausted all attempts.

Exit codes:
  0 -- all clips generated
  1 -- some clips failed but enough exist for assembly (>= MIN_CLIP_FRACTION)
  2 -- too many clips missing, assembly should not proceed
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import requests
    import yaml
except ImportError:
    print("Error: 'requests' and 'pyyaml' required. Install: pip install requests pyyaml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

DEFAULT_OUTPUT_DIR = "outputs/clips"
DEFAULT_GROK_API_BASE = os.environ.get("GROK_API_BASE", "http://localhost:8000")
DEFAULT_API_KEY = os.environ.get("GROK_API_KEY", "grok2api")

VIDEO_CLIP_MINUTES = 3      # first N minutes of narration get real video clips
MAX_RETRIES = 5             # per-scene attempts in the main pass
RETRY_ROUNDS = 3            # extra rounds after main pass for still-missing scenes
MIN_CLIP_FRACTION = 0.6     # minimum coverage required before assembly is allowed

VIDEO_TIMEOUT = 300
IMAGE_TIMEOUT = 120
ZOOM_FPS = 30


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def load_prompts_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) if path.suffix in (".yaml", ".yml") else json.loads(raw)
    if not isinstance(data, dict) or "scenes" not in data:
        print("Error: Prompts file must contain a 'scenes' list.")
        sys.exit(1)
    return data


def extract_character_context(prompts_data: dict) -> str:
    chars = prompts_data.get("recurring_characters", [])
    if not chars:
        scenes = prompts_data.get("scenes", [])
        if scenes:
            first = scenes[0]
            vp = first.get("video_prompt", {})
            subject = (first.get("subject", "")
                       or (vp.get("prompt", "") if isinstance(vp, dict) else "")[:80])
            if subject:
                return (f"CONSISTENT CHARACTER: {subject}. "
                        "Maintain EXACT same appearance in every scene.")
        return ""
    lines = []
    for c in chars[:3]:
        desc = c.get("visual_description", "") or c.get("canonical_description", "")
        if desc:
            lines.append(f"{c.get('name', 'character')}: {desc}")
    return ("CONSISTENT CHARACTERS — maintain EXACT same appearance in every scene: "
            + "; ".join(lines)) if lines else ""


def _simplify_prompt(raw: str) -> str:
    """Strip timestamped beats and trim length for retry attempts."""
    p = re.sub(r'\[\d+\.\d+s-\d+\.\d+s\][^\[]*', '', raw).strip()
    p = re.sub(r'\s+', ' ', p)
    return p[:397] + "..." if len(p) > 400 else p


def build_video_prompt(scene: dict, style_prefix: str, char_context: str,
                       simplified: bool = False) -> str:
    vp = scene.get("video_prompt", {})
    raw = vp.get("prompt", "") if isinstance(vp, dict) else str(vp)
    ip = scene.get("image_prompt", {})
    prompt = raw or (ip.get("prompt", "") if isinstance(ip, dict) else str(ip))
    if not prompt:
        return ""
    if simplified:
        prompt = _simplify_prompt(prompt)
    if style_prefix and not prompt.lower().startswith(style_prefix.lower()[:20]):
        prompt = f"{style_prefix}. {prompt}"
    if char_context:
        prompt = f"{char_context}. {prompt}"
    if "cinematic" not in prompt.lower():
        prompt += " Cinematic quality, smooth natural motion."
    return prompt[:947] + "..." if len(prompt) > 950 else prompt


def build_image_prompt(scene: dict, style_prefix: str, char_context: str,
                       simplified: bool = False) -> str:
    ip = scene.get("image_prompt", {})
    raw = ip.get("prompt", "") if isinstance(ip, dict) else str(ip)
    vp = scene.get("video_prompt", {})
    prompt = raw or (vp.get("prompt", "") if isinstance(vp, dict) else str(vp))
    if not prompt:
        return ""
    if simplified:
        prompt = _simplify_prompt(prompt)
    if style_prefix and not prompt.lower().startswith(style_prefix.lower()[:20]):
        prompt = f"{style_prefix}. {prompt}"
    if char_context:
        prompt = f"{char_context}. {prompt}"
    return prompt[:947] + "..." if len(prompt) > 950 else prompt


# ---------------------------------------------------------------------------
# Grok2API calls
# ---------------------------------------------------------------------------

def grok_generate_video(prompt: str, api_base: str, api_key: str,
                        aspect_ratio: str = "16:9", video_length: int = 6,
                        timeout: int = VIDEO_TIMEOUT) -> Optional[str]:
    """Call Grok Aurora for video generation. Returns a download URL or None."""
    url = f"{api_base.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": "grok-imagine-1.0-video",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "video_config": {
            "aspect_ratio": aspect_ratio,
            "video_length": video_length,
            "resolution_name": "720p",
            "preset": "normal",
        },
    }
    try:
        resp = requests.post(url, json=payload,
                             headers={"Authorization": f"Bearer {api_key}"},
                             timeout=timeout)
        resp.raise_for_status()
        content = (resp.json()
                   .get("choices", [{}])[0]
                   .get("message", {})
                   .get("content", ""))
        for pattern in [
            r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*',
            r'https?://assets\.grok\.com/[^\s"\'<>]+',
            r'src=["\']([^"\']+)["\']',
        ]:
            m = re.search(pattern, content)
            if m:
                return m.group(1) if m.lastindex else m.group(0)
        print(f"    ⚠ No video URL in response: {content[:200]}")
        return None
    except Exception as e:
        print(f"    ✗ Video API error: {e}")
        return None


def grok_generate_image(prompt: str, api_base: str, api_key: str,
                        size: str = "1280x720",
                        timeout: int = IMAGE_TIMEOUT) -> Optional[bytes]:
    """Call Grok Imagine for image generation. Returns raw image bytes or None."""
    url = f"{api_base.rstrip('/')}/v1/images/generations"
    payload = {
        "model": "grok-imagine-1.0",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "response_format": "url",
    }
    try:
        resp = requests.post(url, json=payload,
                             headers={"Authorization": f"Bearer {api_key}"},
                             timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        img_url = data.get("data", [{}])[0].get("url", "")
        if img_url:
            r = requests.get(img_url, timeout=60)
            r.raise_for_status()
            return r.content
        b64 = data.get("data", [{}])[0].get("b64_json", "")
        if b64:
            import base64
            return base64.b64decode(b64)
        print(f"    ⚠ No image data in response: {str(data)[:200]}")
        return None
    except Exception as e:
        print(f"    ✗ Image API error: {e}")
        return None


def download_video(url: str, out_path: Path, timeout: int = 120) -> bool:
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
# Ken Burns zoom effect
# ---------------------------------------------------------------------------

def apply_ken_burns(image_path: Path, out_path: Path, duration: float = 6.0,
                    fps: int = ZOOM_FPS, zoom_in: bool = True,
                    target_w: int = 1280, target_h: int = 720) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("    ✗ FFmpeg not found")
        return False
    n_frames = int(duration * fps)
    if zoom_in:
        zoom_expr = "zoom='min(zoom+0.0025,1.15)'"
    else:
        zoom_expr = "zoom='if(eq(on,1),1.15,max(1.0,zoom-0.0025))'"
    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"
    vf = (f"scale={target_w*2}:{target_h*2},"
          f"zoompan={zoom_expr}:x='{x_expr}':y='{y_expr}':"
          f"d={n_frames}:s={target_w}x{target_h}:fps={fps},"
          f"scale={target_w}:{target_h}")
    cmd = [ffmpeg, "-y", "-loop", "1", "-i", str(image_path),
           "-vf", vf, "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-t", str(duration), "-an", str(out_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1024:
            return True
        print(f"    ✗ FFmpeg zoom failed: {r.stderr[:200]}")
        return False
    except Exception as e:
        print(f"    ✗ FFmpeg zoom error: {e}")
        return False


# ---------------------------------------------------------------------------
# Narration timing helpers
# ---------------------------------------------------------------------------

def load_chunk_manifest(output_dir: Path) -> Optional[dict]:
    candidates = [
        output_dir.parent / "audio_chunks" / "chunks_manifest.json",
        output_dir.parent.parent / "audio_chunks" / "chunks_manifest.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                return json.loads(c.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def compute_scene_cumulative_times(manifest: Optional[dict], total_scenes: int) -> list:
    if not manifest:
        return [i * 6.0 for i in range(total_scenes)]
    clip_seconds = manifest.get("clip_seconds", 6)
    scene_start = {}
    cumulative = 0.0
    for chunk in manifest.get("chunks", []):
        dur = chunk.get("duration", clip_seconds)
        scene_nums = chunk.get("scene_numbers", [])
        per_scene = dur / max(len(scene_nums), 1)
        for sn in scene_nums:
            scene_start[sn] = cumulative
            cumulative += per_scene
    return [scene_start.get(i + 1, i * float(clip_seconds)) for i in range(total_scenes)]


# ---------------------------------------------------------------------------
# Core: generate one scene (video or zoom-image)
# ---------------------------------------------------------------------------

def generate_scene(scene: dict, out_path: Path, use_video: bool,
                   style_prefix: str, char_context: str,
                   api_base: str, api_key: str, aspect_ratio: str,
                   retries: int, zoom_in: bool,
                   simplified: bool = False) -> bool:
    """Attempt to generate a single scene clip. Returns True on success."""

    if use_video:
        prompt = build_video_prompt(scene, style_prefix, char_context, simplified)
        if not prompt or len(prompt.strip()) < 10:
            print(f"    ⚠ Empty video prompt")
            return False
        print(f"    Prompt: {prompt[:140]}{'...' if len(prompt) > 140 else ''}")

        for attempt in range(1, retries + 1):
            if attempt > 1:
                wait = min(attempt * 15, 90)
                print(f"    [Retry {attempt}/{retries}] waiting {wait}s...")
                time.sleep(wait)
            t0 = time.time()
            video_url = grok_generate_video(prompt, api_base, api_key,
                                            aspect_ratio=aspect_ratio, video_length=6)
            elapsed = time.time() - t0
            if video_url and download_video(video_url, out_path):
                size_mb = out_path.stat().st_size / 1_048_576
                print(f"    ✓ Video saved: {out_path.name} ({size_mb:.1f} MB, {elapsed:.1f}s)")
                return True
            print(f"    ✗ Attempt {attempt} failed ({elapsed:.1f}s)")

    else:
        prompt = build_image_prompt(scene, style_prefix, char_context, simplified)
        if not prompt or len(prompt.strip()) < 10:
            print(f"    ⚠ Empty image prompt")
            return False
        print(f"    Prompt: {prompt[:140]}{'...' if len(prompt) > 140 else ''}")

        tmp_img = out_path.with_suffix(".tmp.png")
        for attempt in range(1, retries + 1):
            if attempt > 1:
                wait = min(attempt * 10, 60)
                print(f"    [Retry {attempt}/{retries}] waiting {wait}s...")
                time.sleep(wait)
            img_bytes = grok_generate_image(prompt, api_base, api_key, size="1280x720")
            if img_bytes and len(img_bytes) > 1024:
                tmp_img.write_bytes(img_bytes)
                effect = "zoom-in" if zoom_in else "zoom-out"
                print(f"    ✓ Image generated ({len(img_bytes)//1024} KB) — applying {effect}...")
                if apply_ken_burns(tmp_img, out_path, zoom_in=zoom_in):
                    tmp_img.unlink(missing_ok=True)
                    size_mb = out_path.stat().st_size / 1_048_576
                    print(f"    ✓ Zoom clip saved: {out_path.name} ({size_mb:.1f} MB)")
                    return True
                tmp_img.unlink(missing_ok=True)
                print(f"    ✗ Zoom effect failed")
                return False  # FFmpeg failure — no point retrying same image
            print(f"    ✗ Image attempt {attempt} failed")

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate video clips via Grok2API.")
    parser.add_argument("prompts_file")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--grok-api-base", default=DEFAULT_GROK_API_BASE)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--retries", type=int, default=MAX_RETRIES)
    parser.add_argument("--video-minutes", type=float, default=VIDEO_CLIP_MINUTES)
    parser.add_argument("--aspect-ratio", default="16:9")
    # BWC args silently ignored
    for bwc in ["--images-dir", "--meta-api-base", "--cookies-file",
                "--timeout", "--video-length", "--model", "--resolution", "--analysis-file"]:
        parser.add_argument(bwc, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    prompts_path = Path(args.prompts_file).resolve()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not prompts_path.exists():
        print(f"Error: Prompts file not found: {prompts_path}")
        sys.exit(1)

    api_base = args.grok_api_base
    api_key = args.api_key
    video_cutoff = args.video_minutes * 60

    print("=" * 60)
    print("  Video Generator — Grok2API")
    print("=" * 60)
    print(f"  API      : {api_base}")
    print(f"  Output   : {output_dir}")
    print(f"  Video    : first {args.video_minutes:.1f} min of narration")
    print(f"  Zoom     : remaining narration (Ken Burns)")

    prompts_data = load_prompts_file(prompts_path)
    scenes = prompts_data.get("scenes", [])
    total = len(scenes)
    visual_style = prompts_data.get("visual_style", "")
    style_sub = prompts_data.get("style_subcategory", "")
    style_prefix = f"{visual_style}, {style_sub}" if visual_style and style_sub else visual_style
    char_context = extract_character_context(prompts_data)

    if char_context:
        print(f"  Chars    : {char_context[:80]}...")
    print(f"  Scenes   : {total}")
    print("-" * 60)

    manifest = load_chunk_manifest(output_dir)
    scene_starts = compute_scene_cumulative_times(manifest, total)

    # Build a scene lookup by scene_number for retry rounds
    scene_by_num = {s.get("scene_number", i + 1): s for i, s in enumerate(scenes)}

    zoom_toggle = True

    # -----------------------------------------------------------------------
    # Main pass — iterate every scene
    # -----------------------------------------------------------------------
    print("\n  [PASS 1] Main generation pass...")
    for i, scene in enumerate(scenes, 1):
        scene_num = scene.get("scene_number", i)
        out_path = output_dir / f"clip_{scene_num:02d}.mp4"

        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"\n  [{i}/{total}] Scene {scene_num}: ✓ Already exists")
            zoom_toggle = not zoom_toggle  # keep toggle in sync
            continue

        use_video = scene_starts[i - 1] < video_cutoff
        mode = "VIDEO" if use_video else "ZOOM "
        print(f"\n  [{i}/{total}] Scene {scene_num} [{mode}] (t={scene_starts[i-1]:.0f}s)...")

        ok = generate_scene(
            scene=scene,
            out_path=out_path,
            use_video=use_video,
            style_prefix=style_prefix,
            char_context=char_context,
            api_base=api_base,
            api_key=api_key,
            aspect_ratio=args.aspect_ratio,
            retries=args.retries,
            zoom_in=zoom_toggle,
            simplified=False,
        )
        if not ok:
            print(f"    ✗ Scene {scene_num} failed main pass.")
        if not use_video:
            zoom_toggle = not zoom_toggle

    # -----------------------------------------------------------------------
    # Retry rounds — only for scenes still missing after the main pass
    # -----------------------------------------------------------------------
    for round_num in range(1, RETRY_ROUNDS + 1):
        missing = [
            scene_num for scene_num in sorted(scene_by_num)
            if not (output_dir / f"clip_{scene_num:02d}.mp4").exists()
            or (output_dir / f"clip_{scene_num:02d}.mp4").stat().st_size < 1024
        ]
        if not missing:
            break

        present = total - len(missing)
        print(f"\n  [RETRY ROUND {round_num}/{RETRY_ROUNDS}] "
              f"{len(missing)} scenes still missing: {missing}")
        print(f"  Coverage so far: {present}/{total} ({present/total:.0%})")

        # On round 2+ use simplified prompts — shorter = less likely to be rejected
        simplified = round_num >= 2

        for scene_num in missing:
            scene = scene_by_num.get(scene_num)
            if not scene:
                continue
            out_path = output_dir / f"clip_{scene_num:02d}.mp4"
            # Find original scene index to get its start time
            idx = next((i for i, s in enumerate(scenes)
                        if s.get("scene_number", i + 1) == scene_num), 0)
            use_video = scene_starts[idx] < video_cutoff
            mode = "VIDEO" if use_video else "ZOOM "
            print(f"\n    Scene {scene_num} [{mode}] retry (simplified={simplified})...")

            ok = generate_scene(
                scene=scene,
                out_path=out_path,
                use_video=use_video,
                style_prefix=style_prefix,
                char_context=char_context,
                api_base=api_base,
                api_key=api_key,
                aspect_ratio=args.aspect_ratio,
                retries=3,
                zoom_in=(scene_num % 2 == 0),  # deterministic zoom direction on retry
                simplified=simplified,
            )
            if not ok:
                print(f"    ✗ Scene {scene_num} still failed (round {round_num}).")

        # Short pause between rounds to let rate limits recover
        if round_num < RETRY_ROUNDS:
            time.sleep(10)

    # -----------------------------------------------------------------------
    # Final tally and exit code
    # -----------------------------------------------------------------------
    for tmp in output_dir.glob("*.tmp.png"):
        tmp.unlink(missing_ok=True)

    final_missing = [
        sn for sn in sorted(scene_by_num)
        if not (output_dir / f"clip_{sn:02d}.mp4").exists()
        or (output_dir / f"clip_{sn:02d}.mp4").stat().st_size < 1024
    ]
    success = total - len(final_missing)
    coverage = success / total if total > 0 else 1.0

    print("\n" + "=" * 60)
    print(f"  Generated : {success}/{total} clips ({coverage:.0%})")
    if final_missing:
        print(f"  Failed    : {len(final_missing)} scenes — {final_missing}")
    print(f"  Output    : {output_dir}")
    print("=" * 60)

    if coverage >= 1.0:
        sys.exit(0)
    elif coverage >= MIN_CLIP_FRACTION:
        # Enough to assemble — caller decides whether to proceed
        sys.exit(1)
    else:
        # Too many missing — block assembly
        print(f"\n  ❌ Only {coverage:.0%} coverage after all retries. "
              f"Assembly blocked (minimum {MIN_CLIP_FRACTION:.0%}).")
        sys.exit(2)


if __name__ == "__main__":
    main()
