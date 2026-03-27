#!/usr/bin/env python3
"""
End-to-End Pipeline Test — Smoke Test.

Tests every step of the pipeline from audio generation to final video,
using a minimal subset to verify each component works.

Architecture:
  - Audio:  AIStudio2API TTS (port 2048)
  - Images: Whisk API CLI (Imagen 3.5, no server needed)
  - Video:  MetaAI SDK direct (no server needed)
  - Assembly: FFmpeg combine_all.py

Usage:
    python3 test_pipeline.py
    python3 test_pipeline.py --skip-audio
    python3 test_pipeline.py --step images
"""

import argparse
import json
import os
import subprocess
import sys
import time
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable
UTILS_DIR = SCRIPT_DIR / "utils"

AISTUDIO_BASE = os.environ.get("AISTUDIO_API_BASE", "http://localhost:2048")

TEST_DIR = SCRIPT_DIR / "outputs" / "pipeline_test"

# Short test script — 3 scenes only (David & Goliath excerpt)
TEST_SCRIPT = textwrap.dedent("""\
    The Israelites and the Philistines were enemies. The Philistine army \
gathered together to fight against the Israelites. A huge champion named \
Goliath came out of the Philistine camp. He was almost ten feet tall and \
wore heavy bronze armor.

    Young David was a shepherd boy who took care of his father's sheep. \
He was brave and trusted God completely. When he heard Goliath's challenge, \
he volunteered to fight the giant.

    David chose five smooth stones from a stream. He put one stone in his \
sling and threw it at Goliath. The stone hit the giant on his forehead and \
he fell face down. David won because he trusted God.
""")

# Minimal prompts YAML for 3 scenes
TEST_PROMPTS_YAML = textwrap.dedent("""\
    visual_style: "Photorealistic, biblical era, 35mm film, cinematic"
    style_subcategory: "Ancient Middle East, warm golden lighting"
    scenes:
      - scene_number: 1
        image_prompt:
          prompt: >
            Wide establishing shot of two ancient armies facing each other
            across a rocky desert valley. Thousands of soldiers in bronze
            armor and leather shields. Dramatic golden hour lighting.
            35mm film, natural lighting, historically accurate.
          negative_prompt: "cartoon, anime, modern objects"
        video_prompt:
          prompt: >
            Camera slowly pans across a vast desert valley with two ancient
            armies on opposite hillsides. Dust rises in the golden sunlight.
            Soldiers shift nervously. Cinematic, smooth motion.
      - scene_number: 2
        image_prompt:
          prompt: >
            Close-up portrait of a young shepherd boy, around 15 years old,
            standing in green pastures with sheep behind him. He has
            determined brown eyes and holds a wooden staff. Warm afternoon
            sunlight. 35mm film, natural skin tones.
          negative_prompt: "cartoon, anime, modern clothing"
        video_prompt:
          prompt: >
            A young shepherd boy looks up with determination, sunlight on
            his face. He grips his wooden staff tightly. Behind him, sheep
            graze peacefully. The wind moves his simple tunic. Smooth motion.
      - scene_number: 3
        image_prompt:
          prompt: >
            Dynamic action shot of a smooth stone flying through the air
            toward a towering armored giant. Desert valley background.
            Motion blur on the stone. Dramatic low-angle perspective.
            35mm film, cinematic composition.
          negative_prompt: "cartoon, anime, blood, gore"
        video_prompt:
          prompt: >
            A young boy swings a leather sling and releases a stone. The
            stone flies through the air toward a massive armored warrior.
            The giant falls forward face-down with a crash. Dramatic
            cinematic moment. Smooth slow-motion.
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def run(cmd, label, timeout=600):
    """Run a command, print output, return success."""
    print(f"  $ {' '.join(str(c) for c in cmd)}\n")
    start = time.time()
    result = subprocess.run(cmd, timeout=timeout)
    elapsed = time.time() - start
    ok = result.returncode == 0
    status = "PASS" if ok else "FAIL"
    print(f"\n  {status} — {label} ({elapsed:.1f}s)\n")
    return ok


def check_service(url, name):
    """Quick health check for a service."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read().decode()
            if "ok" in data.lower() or resp.status == 200:
                print(f"  ✓ {name} is running")
                return True
    except Exception as e:
        print(f"  ✗ {name} not reachable at {url} ({e})")
    return False


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_setup():
    """Create test directory and write test files."""
    banner("Step 0: Setup")

    TEST_DIR.mkdir(parents=True, exist_ok=True)
    (TEST_DIR / "audio_chunks").mkdir(exist_ok=True)
    (TEST_DIR / "images").mkdir(exist_ok=True)
    (TEST_DIR / "clips").mkdir(exist_ok=True)

    script_file = TEST_DIR / "script.txt"
    script_file.write_text(TEST_SCRIPT.strip(), encoding="utf-8")
    print(f"  ✓ Test script: {script_file} ({len(TEST_SCRIPT)} chars)")

    prompts_file = TEST_DIR / "prompts.yaml"
    prompts_file.write_text(TEST_PROMPTS_YAML.strip(), encoding="utf-8")
    print(f"  ✓ Test prompts: {prompts_file}")

    return True


def step_health_check():
    """Check services and cookies."""
    banner("Step 0.5: Health Check")

    # AIStudio2API only needed for audio (TTS)
    check_service(f"{AISTUDIO_BASE}/health", "AIStudio2API (TTS)")

    # Check whisk cookie
    cookie_file = SCRIPT_DIR / "whisk_cookie.txt"
    if cookie_file.exists() and cookie_file.stat().st_size > 50:
        print(f"  ✓ Whisk cookie file exists ({cookie_file.stat().st_size} bytes)")
    elif os.environ.get("WHISK_COOKIE"):
        print(f"  ✓ WHISK_COOKIE env var set")
    else:
        print(f"  ✗ No Whisk cookie found (images will fail)")

    # Check meta cookies
    meta_cookies = SCRIPT_DIR / "meta_cookies.json"
    if meta_cookies.exists():
        print(f"  ✓ Meta AI cookies file exists")
    else:
        print(f"  ✗ No meta_cookies.json found (videos will fail)")

    return True


def step_audio():
    """Generate audio narration using TTS."""
    banner("Step 1: Audio Generation (TTS)")

    script_file = TEST_DIR / "script.txt"
    audio_dir = TEST_DIR / "audio_chunks"

    ok = run([
        PYTHON, str(UTILS_DIR / "generate_audio_chunks.py"),
        str(script_file),
        "-o", str(audio_dir),
        "--api-base", AISTUDIO_BASE,
        "--voice", "Charon",
        "--language", "sw",
        "--clip-seconds", "6",
    ], "Audio Generation", timeout=300)

    manifest = audio_dir / "chunks_manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        dur = data.get('total_duration', 0)
        print(f"  Manifest: {data.get('total_clips', '?')} clips, {dur:.1f}s total")
    else:
        print(f"  ✗ Manifest not found")

    return ok


def step_visuals():
    """Visual prompts — using static test prompts."""
    banner("Step 2: Visual Prompts (static)")
    print(f"  ✓ Using pre-built test prompts (skipping AI generation)")
    return True


def step_images():
    """Generate images using Whisk API (Imagen 3.5)."""
    banner("Step 3: Image Generation (Whisk API / Imagen 3.5)")

    prompts_file = TEST_DIR / "prompts.yaml"
    images_dir = TEST_DIR / "images"

    ok = run([
        PYTHON, str(UTILS_DIR / "generate_images.py"),
        str(prompts_file),
        "-o", str(images_dir),
        "--aspect-ratio", "LANDSCAPE",
        "--retries", "2",
    ], "Image Generation", timeout=600)

    images = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg"))
    print(f"  Generated {len(images)} images")
    for img in images:
        print(f"     {img.name} ({img.stat().st_size / 1024:.0f} KB)")

    return ok or len(images) > 0


def step_videos():
    """Generate videos using Meta AI SDK (direct)."""
    banner("Step 4: Video Generation (Meta AI SDK)")

    prompts_file = TEST_DIR / "prompts.yaml"
    clips_dir = TEST_DIR / "clips"

    ok = run([
        PYTHON, str(UTILS_DIR / "generate_videos.py"),
        str(prompts_file),
        "-o", str(clips_dir),
        "--retries", "3",
    ], "Video Generation", timeout=900)

    clips = list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.webm"))
    print(f"  Generated {len(clips)} video clips")
    for clip in clips:
        print(f"     {clip.name} ({clip.stat().st_size / 1_048_576:.1f} MB)")

    return ok or len(clips) > 0


def step_assembly():
    """Combine clips + audio into final video."""
    banner("Step 5: Final Assembly")

    clips_dir = TEST_DIR / "clips"
    audio_dir = TEST_DIR / "audio_chunks"
    final_video = TEST_DIR / "final_test_video.mp4"
    prompts_file = TEST_DIR / "prompts.yaml"
    manifest_file = audio_dir / "chunks_manifest.json"

    clips = list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.webm"))
    if not clips:
        print("  No video clips available — skipping assembly")
        return False

    cmd = [
        PYTHON, str(UTILS_DIR / "combine_all.py"),
        "--clips-dir", str(clips_dir),
        "--prompts-file", str(prompts_file),
        "-o", str(final_video),
    ]

    if manifest_file.exists():
        data = json.loads(manifest_file.read_text())
        narration_name = data.get("combined_audio", "narration.wav")
        narration = audio_dir / narration_name
        if narration.exists():
            cmd.extend(["--music", str(narration)])
            print(f"  Using narration: {narration.name}")
        cmd.extend(["--chunk-manifest", str(manifest_file)])

    ok = run(cmd, "Final Assembly", timeout=300)

    if final_video.exists():
        size_mb = final_video.stat().st_size / 1_048_576
        print(f"  ✓ Final video: {final_video} ({size_mb:.1f} MB)")
    else:
        print(f"  ✗ Final video not created")

    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="End-to-end pipeline smoke test.")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--skip-videos", action="store_true")
    parser.add_argument("--skip-assembly", action="store_true")
    parser.add_argument("--step", type=str, default=None,
                        choices=["audio", "visuals", "images", "videos", "assembly"])
    parser.add_argument("--aistudio-base", type=str, default=AISTUDIO_BASE)

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  PIPELINE END-TO-END TEST")
    print("=" * 60)
    print(f"  AIStudio (TTS) : {args.aistudio_base}")
    print(f"  Images         : Whisk API (Imagen 3.5)")
    print(f"  Videos         : Meta AI SDK (direct)")
    print(f"  Test Dir       : {TEST_DIR}")
    print()

    results = {}
    start = time.time()

    step_setup()
    step_health_check()

    # Determine steps
    if args.step:
        steps_to_run = {args.step}
    else:
        steps_to_run = {"audio", "visuals", "images", "videos", "assembly"}
        if args.skip_audio: steps_to_run.discard("audio")
        if args.skip_images: steps_to_run.discard("images")
        if args.skip_videos: steps_to_run.discard("videos")
        if args.skip_assembly: steps_to_run.discard("assembly")

    step_fns = {
        "audio": step_audio,
        "visuals": step_visuals,
        "images": step_images,
        "videos": step_videos,
        "assembly": step_assembly,
    }

    for step_name in ["audio", "visuals", "images", "videos", "assembly"]:
        if step_name not in steps_to_run:
            results[step_name] = "SKIPPED"
            continue
        try:
            ok = step_fns[step_name]()
            results[step_name] = "PASS" if ok else "FAIL"
        except Exception as e:
            print(f"  Exception in {step_name}: {e}")
            results[step_name] = "ERROR"

    # Summary
    elapsed = time.time() - start
    banner("RESULTS")
    for name in ["audio", "visuals", "images", "videos", "assembly"]:
        s = results.get(name, "N/A")
        icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥", "SKIPPED": "⏭"}.get(s, "❓")
        print(f"  {icon}  {name.upper():12s}  {s}")

    m, s = divmod(int(elapsed), 60)
    print(f"\n  Total: {m}m {s}s")

    p = sum(1 for v in results.values() if v == "PASS")
    f = sum(1 for v in results.values() if v in ("FAIL", "ERROR"))
    print(f"  Passed: {p}  Failed: {f}")

    sys.exit(1 if f > 0 else 0)


if __name__ == "__main__":
    main()
