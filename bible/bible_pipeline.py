#!/usr/bin/env python3
"""
Bible Pipeline — Main Orchestrator.

Autonomous pipeline that generates Swahili Bible narration videos
for Tanzanian audience. No input video needed — creates everything
from scratch.

Pipeline per video:
  1. Pick topic (from curated list, skip used)
  2. Generate YouTube title
  3. Generate Bible story script (Gem-based style guide)
  4. Generate audio narration (TTS)
  5. Generate visual prompts (photorealistic biblical era)
  6. Generate images (AIStudio2API Nano Banana / Gemini 2.5 Flash)
  7. Generate video clips (Meta AI API — image-to-video with cookie rotation)
  8. Assemble final video
  9. Track topic + copy to final_bibles/
"""

import argparse
import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

# Ensure project root is on sys.path so `bible.*` and `utils.*` imports work
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
PYTHON = sys.executable

STATUS_FILE = PROJECT_DIR / "bible_status.json"
FINAL_DIR = PROJECT_DIR / "final_bibles"
OUTPUT_BASE = PROJECT_DIR / "outputs"

DEFAULT_AISTUDIO_PORT = 2048
DEFAULT_META_PORT = 8000

# ---------------------------------------------------------------------------
# Status Tracking
# ---------------------------------------------------------------------------

def load_status() -> dict:
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    return {}

def save_status(status: dict):
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

def update_video_status(topic: str, step: str, state: str = "completed",
                        assets: dict = None, metadata: dict = None):
    status = load_status()
    if topic not in status:
        status[topic] = {"steps": {}, "assets": {}, "metadata": {}}
    status[topic]["steps"][step] = state
    if assets:
        status[topic]["assets"].update(assets)
    if metadata:
        status[topic]["metadata"].update(metadata)
    save_status(status)


# ---------------------------------------------------------------------------
# Pipeline Step Runner
# ---------------------------------------------------------------------------

def run_step(topic: str, step_name: str, cmd: list[str],
             assets: dict = None, metadata: dict = None) -> bool:
    """Run a pipeline step as subprocess. Returns True on success."""
    print(f"\n{'='*60}")
    print(f"  [{step_name}] {topic}")
    print(f"{'='*60}")
    print(f"  Command: {' '.join(cmd[:5])}...")

    update_video_status(topic, step_name, "running")
    start = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            capture_output=False,  # Show output live
            text=True,
            timeout=7200,  # 2 hour timeout per step
        )
        elapsed = time.time() - start

        if result.returncode == 0:
            print(f"\n  ✅ {step_name} completed in {elapsed:.0f}s")
            update_video_status(topic, step_name, "completed", assets, metadata)
            return True
        else:
            print(f"\n  ❌ {step_name} failed (exit code {result.returncode}) after {elapsed:.0f}s")
            update_video_status(topic, step_name, "failed")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n  ❌ {step_name} timed out after 2 hours")
        update_video_status(topic, step_name, "timeout")
        return False
    except Exception as e:
        print(f"\n  ❌ {step_name} error: {e}")
        update_video_status(topic, step_name, "error")
        return False


# ---------------------------------------------------------------------------
# Sanitize filename
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name[:200] if name else "untitled"


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

async def process_one_video(topic: str, output_dir: Path,
                            aistudio_port: int, meta_port: int) -> bool:
    """Run the full pipeline for one Bible story video."""
    print(f"\n{'#'*60}")
    print(f"  📖 BIBLE VIDEO: {topic}")
    print(f"  📂 Output: {output_dir}")
    print(f"{'#'*60}")

    output_dir.mkdir(parents=True, exist_ok=True)

    api_base = f"http://localhost:{aistudio_port}"
    meta_base = f"http://localhost:{meta_port}"

    # File paths
    title_file = output_dir / "title.txt"
    script_file = output_dir / "swahili_script.txt"
    audio_file = output_dir / "narration.wav"
    prompts_file = output_dir / "prompts.yaml"
    clips_dir = output_dir / "clips"
    images_dir = output_dir / "images"
    final_video = output_dir / f"{sanitize_filename(topic)}_bible.mp4"

    # -----------------------------------------------------------------------
    # Step 1: Generate Title
    # -----------------------------------------------------------------------
    if not title_file.exists():
        # Import and run async title generation
        from bible.generate_title import generate_title
        try:
            title = await generate_title(topic)
            title_file.write_text(title, encoding="utf-8")
            update_video_status(topic, "title", "completed",
                                assets={"title": str(title_file)},
                                metadata={"youtube_title": title})
            print(f"  🏷️  Title: {title}")
        except Exception as e:
            print(f"  ❌ Title generation failed: {e}")
            title = f"Hadithi ya Biblia: {topic} 📖"
            title_file.write_text(title, encoding="utf-8")
            update_video_status(topic, "title", "completed",
                                metadata={"youtube_title": title})
    else:
        title = title_file.read_text(encoding="utf-8").strip()
        print(f"  🏷️  Title (cached): {title}")

    # -----------------------------------------------------------------------
    # Step 2: Generate Script
    # -----------------------------------------------------------------------
    if not script_file.exists():
        from bible.generate_script import generate_bible_script
        try:
            script = await generate_bible_script(topic)
            script_file.write_text(script, encoding="utf-8")
            word_count = len(script.split())
            update_video_status(topic, "script", "completed",
                                assets={"script": str(script_file)},
                                metadata={"word_count": word_count})
            print(f"  📝 Script: {word_count} words")
        except Exception as e:
            print(f"  ❌ Script generation failed: {e}")
            return False
    else:
        script = script_file.read_text(encoding="utf-8").strip()
        print(f"  📝 Script (cached): {len(script.split())} words")

    # -----------------------------------------------------------------------
    # Step 3: Generate Chunked Audio (per-chunk WAVs + manifest)
    # -----------------------------------------------------------------------
    audio_chunks_dir = output_dir / "audio_chunks"
    manifest_file = audio_chunks_dir / "chunks_manifest.json"

    if not manifest_file.exists():
        from utils.generate_audio_chunks import generate_chunked_audio
        try:
            script_text = script_file.read_text(encoding="utf-8").strip()
            manifest = generate_chunked_audio(
                script_text,
                output_dir=audio_chunks_dir,
                api_base=api_base,
                voice="Charon",
                timeout=1800,
                max_chunk_chars=1000,
                language="sw",
            )
            if not manifest or not manifest.get("chunks"):
                print("  ❌ Chunked audio generation failed")
                return False

            update_video_status(topic, "audio", "completed",
                                assets={"audio_chunks_dir": str(audio_chunks_dir),
                                        "manifest": str(manifest_file)},
                                metadata={"total_duration": manifest.get("total_duration", 0),
                                          "total_clips": manifest.get("total_clips", 0),
                                          "num_chunks": len(manifest["chunks"])})
            print(f"  🔊 Audio: {manifest['total_duration']:.1f}s in {len(manifest['chunks'])} chunks → {manifest['total_clips']} clips")
        except Exception as e:
            print(f"  ❌ Chunked audio generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        print(f"  🔊 Audio (cached): {manifest['total_duration']:.1f}s, {len(manifest['chunks'])} chunks, {manifest['total_clips']} clips")

    # Set audio_file to the combined narration for assembly
    audio_file = audio_chunks_dir / manifest.get("combined_audio", "narration.wav")
    if not audio_file.exists():
        # Fallback: check the old location
        old_audio = output_dir / "narration.wav"
        if old_audio.exists():
            audio_file = old_audio
        else:
            print(f"  ❌ Combined audio not found at {audio_file}")
            return False

    # -----------------------------------------------------------------------
    # Step 4: Generate Visual Prompts (chunk-aware)
    # -----------------------------------------------------------------------
    if not prompts_file.exists():
        from bible.generate_visuals import generate_visual_prompts_from_manifest
        import yaml
        try:
            prompts_data = await generate_visual_prompts_from_manifest(manifest)
            with open(prompts_file, "w", encoding="utf-8") as f:
                yaml.dump(prompts_data, f, sort_keys=False, allow_unicode=True)
            scene_count = len(prompts_data.get("scenes", []))
            update_video_status(topic, "visual_prompts", "completed",
                                assets={"prompts": str(prompts_file)},
                                metadata={"clip_count": scene_count,
                                          "chunk_synced": True})
            print(f"  🎨 Visual prompts: {scene_count} chunk-synced scenes")
        except Exception as e:
            print(f"  ❌ Visual prompt generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print(f"  🎨 Visual prompts (cached): {prompts_file}")

    # -----------------------------------------------------------------------
    # Step 5: Generate Images (AIStudio2API Nano Banana / Gemini 2.5 Flash)
    # -----------------------------------------------------------------------
    images_dir.mkdir(parents=True, exist_ok=True)
    existing_images = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg"))
    total_scenes = len(manifest.get("chunks", []))

    if len(existing_images) < max(3, total_scenes // 2):
        ok = run_step(topic, "images", [
            PYTHON, str(PROJECT_DIR / "utils" / "generate_images.py"),
            str(prompts_file),
            "-o", str(images_dir),
            "--api-base", api_base,
            "--model", "gemini-2.5-flash-image",
            "--aspect-ratio", "16:9",
        ], assets={"images_dir": str(images_dir)})
        if not ok:
            print("  ⚠ Image generation had issues — continuing with available images")
    else:
        print(f"  🖼️  Images (cached): {len(existing_images)} images")

    # -----------------------------------------------------------------------
    # Step 6: Generate Video Clips (Meta AI — image-to-video with cookie rotation)
    # -----------------------------------------------------------------------
    clips_dir.mkdir(parents=True, exist_ok=True)
    existing_clips = list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.webm"))
    total_clips_needed = manifest.get("total_clips", 0)
    if len(existing_clips) < max(5, total_clips_needed // 2):
        gen_videos_cmd = [
            PYTHON, str(PROJECT_DIR / "utils" / "generate_videos.py"),
            str(prompts_file),
            "--output-dir", str(clips_dir),
            "--meta-api-base", meta_base,
            "--aspect-ratio", "16:9",
            "--retries", "5",
        ]
        # Pass images directory for image-to-video
        if images_dir.exists() and any(images_dir.iterdir()):
            gen_videos_cmd.extend(["--images-dir", str(images_dir)])
        ok = run_step(topic, "videos", gen_videos_cmd,
                      assets={"clips_dir": str(clips_dir)})
        if not ok:
            print("  ⚠ Video generation had issues — continuing with available clips")
    else:
        print(f"  🎬 Clips (cached): {len(existing_clips)} clips")

    # -----------------------------------------------------------------------
    # Step 7: Assemble Final Video (chunk-aware sync)
    # -----------------------------------------------------------------------
    if not final_video.exists():
        assembly_args = [
            PYTHON, str(PROJECT_DIR / "utils" / "combine_all.py"),
            "--clips-dir", str(clips_dir),
            "--music", str(audio_file),
            "--prompts-file", str(prompts_file),
            "-o", str(final_video),
        ]
        # Pass chunk manifest for precise sync
        if manifest_file.exists():
            assembly_args.extend(["--chunk-manifest", str(manifest_file)])

        ok = run_step(topic, "assembly", assembly_args,
                      assets={"final_video": str(final_video)})
        if not ok:
            print("  ❌ Assembly failed")
            return False
    else:
        print(f"  🎬 Final video (cached): {final_video}")


    # -----------------------------------------------------------------------
    # Step 8: Copy to final_bibles/
    # -----------------------------------------------------------------------
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = sanitize_filename(title)
    final_dest = FINAL_DIR / f"{safe_title}.mp4"

    if final_video.exists() and not final_dest.exists():
        shutil.copy2(final_video, final_dest)
        print(f"  📦 Final copy: {final_dest.name}")
        update_video_status(topic, "final_copy", "completed",
                            assets={"final_bible": str(final_dest)})

    # -----------------------------------------------------------------------
    # Step 9: Save topic as used
    # -----------------------------------------------------------------------
    from bible.topic_tracker import save_topic
    save_topic(topic, title)
    update_video_status(topic, "bible_process", "completed")

    print(f"\n  🎉 DONE: {topic}")
    print(f"  📺 Final: {final_dest}")
    return True


# ---------------------------------------------------------------------------
# Main — Process N Videos
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Bible Narration Pipeline — Generate Swahili Bible Videos"
    )
    parser.add_argument("--count", type=int, default=1,
                        help="Number of videos to generate (default: 1)")
    parser.add_argument("--topic", type=str, default=None,
                        help="Specific topic (overrides auto-selection)")
    parser.add_argument("--aistudio-port", type=int, default=DEFAULT_AISTUDIO_PORT)
    parser.add_argument("--meta-port", type=int, default=DEFAULT_META_PORT)
    # BWC
    parser.add_argument("--grok-port", type=int, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    print(f"\n{'#'*60}")
    print(f"  📖 Bible Narration Pipeline")
    print(f"  Videos to generate: {args.count}")
    print(f"{'#'*60}")

    # Determine topics
    if args.topic:
        topics = [args.topic] * args.count
    else:
        from bible.topic_tracker import get_suggested_topics
        topics = get_suggested_topics(args.count)
        if len(topics) < args.count:
            print(f"  ⚠ Only {len(topics)} unused topics available (requested {args.count})")
            if not topics:
                print("  ❌ No more unused topics! All stories have been generated.")
                sys.exit(0)

    print(f"  Topics selected:")
    for i, t in enumerate(topics, 1):
        print(f"    {i}. {t}")

    # Process each video
    success_count = 0
    for i, topic in enumerate(topics, 1):
        print(f"\n{'='*60}")
        print(f"  VIDEO {i}/{len(topics)}")
        print(f"{'='*60}")

        output_dir = OUTPUT_BASE / sanitize_filename(topic)

        try:
            meta_port = args.meta_port if args.meta_port else (args.grok_port or DEFAULT_META_PORT)
            result = asyncio.run(
                process_one_video(topic, output_dir, args.aistudio_port, meta_port)
            )
            if result:
                success_count += 1
        except KeyboardInterrupt:
            print("\n\n  ⛔ Interrupted by user")
            break
        except Exception as e:
            print(f"\n  ❌ Pipeline error for {topic}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"  📊 Results: {success_count}/{len(topics)} videos completed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
