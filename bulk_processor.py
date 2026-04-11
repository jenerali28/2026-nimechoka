#!/usr/bin/env python3
import json
import math
import os
import re
import sys
import time
import yaml
import shutil
import subprocess
from pathlib import Path

# Local utility
from utils.trim_preview import get_video_duration, trim_preview

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
UTILS_DIR = SCRIPT_DIR / "utils"
INPUT_DIR = SCRIPT_DIR / "input_videos"
OUTPUT_BASE = SCRIPT_DIR / "outputs"
FINAL_DIR = SCRIPT_DIR / "final_clones"
STATUS_FILE = SCRIPT_DIR / "status.json"

# NVIDIA NIM (DeepSeek V3.1) for title translation
NVIDIA_API_KEY = "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"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "deepseek-ai/deepseek-v3.1"

PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Asset Tracking & Persistence
# ---------------------------------------------------------------------------

def load_status():
    if not STATUS_FILE.exists():
        return {}
    try:
        with open(STATUS_FILE, "r") as f:
            content = f.read().strip()
            if not content: return {}
            return json.loads(content)
    except json.JSONDecodeError:
        return {}

def save_status(status):
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)

def update_video_status(video_name, step, state="completed", assets=None, metadata=None):
    status = load_status()
    if video_name not in status:
        status[video_name] = {"steps": {}, "assets": {}, "metadata": {}}
    
    status[video_name]["steps"][step] = state
    if assets:
        status[video_name]["assets"].update(assets)
    if metadata:
        status[video_name]["metadata"].update(metadata)
    
    save_status(status)

# ---------------------------------------------------------------------------
# Pipeline Wrapper
# ---------------------------------------------------------------------------

def run_step(video_name, step_name, cmd, assets=None, metadata=None):
    status = load_status()
    video_status = status.get(video_name, {})
    
    # Check if marked as completed
    if video_status.get("steps", {}).get(step_name) == "completed":
        # Extra safety: Check if all expected assets for this step actually exist on disk
        if assets:
            all_exist = True
            for key, path_str in assets.items():
                if not Path(path_str).exists():
                    print(f"  [RESUMING] {step_name} (missing asset: {key})")
                    all_exist = False
                    break
            if all_exist:
                print(f"  [SKIPPING] {step_name} (already completed)")
                return True
        else:
            print(f"  [SKIPPING] {step_name} (already completed)")
            return True

    print(f"\n  [RUNNING] {step_name}...")
    print(f"  Command: {' '.join(cmd)}")
    
    # Always ensure output directory for assets exists
    if assets:
        for path_str in assets.values():
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode == 0:
        update_video_status(video_name, step_name, "completed", assets, metadata)
        return True
    else:
        # Don't overwrite if it was already completed but we decided to run it (shouldn't happen with logic above)
        update_video_status(video_name, step_name, "failed")
        print(f"  ✗ {step_name} failed for {video_name}")
        return False
# Bulk Processing Logic
# ---------------------------------------------------------------------------

def process_video(video_path):
    video_name = video_path.name
    video_stem = video_path.stem
    output_dir = OUTPUT_BASE / video_stem
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*80)
    print(f" Processing: {video_name}")
    print("="*80)

    # --- Step 1: Transcription ---
    eng_script = output_dir / "english_script.txt"
    orig_audio = output_dir / "original_audio.wav"
    if not run_step(video_name, "transcription", [
        PYTHON, str(UTILS_DIR / "extract_script.py"),
        str(video_path), "-o", str(eng_script), "--audio-output", str(orig_audio)
    ], assets={"english_script": str(eng_script), "original_audio": str(orig_audio)}):
        return False

    # --- Step 1.5: Video Duration & Preview Trimming ---
    video_duration = get_video_duration(str(video_path))
    preview_path, _, was_trimmed = trim_preview(
        str(video_path),
        output_path=str(output_dir / f"{video_stem}_preview.mp4"),
    )
    if was_trimmed:
        print(f"  📐 Long video detected ({video_duration:.0f}s) — using preview clip for analysis")
    else:
        print(f"  📐 Short video ({video_duration:.0f}s) — analyzing in full")

    # --- Step 2: Rewrite Script (DeepSeek-R1) ---
    spa_script = output_dir / "spanish_script.txt"
    if not run_step(video_name, "rewrite", [
        PYTHON, str(UTILS_DIR / "rewrite_script_gemini.py"),
        str(eng_script), "-o", str(spa_script)
    ], assets={"spanish_script": str(spa_script)}):
        return False

    # --- Step 3: TTS (Chunked Narration) — BEFORE prompt generation ---
    audio_chunks_dir = output_dir / "audio_chunks"
    manifest_file = audio_chunks_dir / "chunks_manifest.json"
    
    if not run_step(video_name, "tts", [
        PYTHON, str(UTILS_DIR / "generate_audio_chunks.py"),
        str(spa_script), "-o", str(audio_chunks_dir), 
        "--language", "es"
    ], assets={"audio_chunks_dir": str(audio_chunks_dir), "manifest": str(manifest_file)}):
        return False

    # --- Step 3.5: Calculate clip count from narration duration ---
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        clip_count = manifest.get("total_clips", 0)
        narration_duration = manifest.get("total_duration", 0)
        narration_wav = audio_chunks_dir / manifest.get("combined_audio", "narration.wav")
    else:
        print("  ❌ Chunked audio generation manifest missing")
        return False
        
    CLIP_LENGTH = 6  # seconds per video clip
    coverage = clip_count * CLIP_LENGTH
    print(f"  🎬 Narration: {narration_duration:.1f}s → {clip_count} clips × {CLIP_LENGTH}s = {coverage}s")

    # --- Step 4: Gemini Multimodal (Analysis + Batched Prompts) ---
    analysis_file = output_dir / "analysis.yaml"
    prompts_file = output_dir / "prompts.yaml"
    multimodal_cmd = [
        PYTHON, str(UTILS_DIR / "multimodal_orchestrator.py"),
        str(preview_path), str(analysis_file), str(prompts_file),
        "--clip-count", str(clip_count),
        "--script", str(spa_script),  # enables batched prompt generation
    ]
    # For long videos, pass transcript and duration for scene reconstruction
    if was_trimmed:
        multimodal_cmd.extend([
            "--transcript", str(eng_script),
            "--duration", str(video_duration),
        ])
    if not run_step(video_name, "multimodal_flow", multimodal_cmd,
                    assets={"analysis": str(analysis_file), "prompts": str(prompts_file)}):
        return False

    # --- Step 4.5: Extract Keyframes from Original Video (SKIPPED in text-to-video mode) ---
    # keyframes_dir = output_dir / "keyframes"
    # if not run_step(video_name, "keyframes", [ ...

    # --- Step 4.7: Generate Style & Character Bibles (SKIPPED in text-to-video mode) ---
    # style_bible_file = output_dir / "style_bible.yaml"
    # char_bible_file = output_dir / "character_bible.yaml"

    # --- Step 5: Images (SKIPPED in text-to-video mode) ---
    # images_dir = output_dir / "images"
    # ...

    # --- Step 6: Videos (Grok2API — Text-to-Video + Zoom for remainder) ---
    # generate_videos.py owns all retry logic internally.
    # Exit code 0 = all clips present, 1 = partial but enough, 2 = too many missing.
    clips_dir = output_dir / "clips"
    gen_videos_cmd = [
        PYTHON, str(UTILS_DIR / "generate_videos.py"),
        str(prompts_file), "-o", str(clips_dir),
        "--grok-api-base", os.environ.get("GROK_API_BASE", "http://localhost:8000"),
        "--api-key", os.environ.get("GROK_API_KEY", "grok2api"),
        "--aspect-ratio", "16:9", "--retries", "5",
    ]

    print(f"\n  [RUNNING] videos...")
    print(f"  Command: {' '.join(gen_videos_cmd)}")
    video_result = subprocess.run(gen_videos_cmd, capture_output=False)

    if video_result.returncode == 2:
        # Too many clips missing even after internal retries — do not assemble
        update_video_status(video_name, "videos", "failed")
        print(f"  ❌ Video generation: too many clips missing — aborting.")
        return False
    elif video_result.returncode == 0:
        update_video_status(video_name, "videos", "completed",
                            assets={"clips_dir": str(clips_dir)})
    else:
        # exit 1 = partial success — enough clips to assemble, mark completed
        update_video_status(video_name, "videos", "completed",
                            assets={"clips_dir": str(clips_dir)})

    # --- Step 7: Final Assembly (Native Speed — no stretching) ---
    final_video = output_dir / f"{video_stem}_cloned.mp4"
    assembly_cmd = [
        PYTHON, str(UTILS_DIR / "combine_all.py"),
        "--clips-dir", str(clips_dir),
        "--music", str(narration_wav),
        "--prompts-file", str(prompts_file),
        "-o", str(final_video)
    ]
    if manifest_file.exists():
        assembly_cmd.extend(["--chunk-manifest", str(manifest_file)])

    # Assembly exit code 2 means clips are still missing — mark videos step as
    # failed so the next run re-enters the retry loop instead of skipping it.
    result = subprocess.run(assembly_cmd, capture_output=False)
    if result.returncode == 2:
        print(f"  ❌ Assembly aborted due to missing clips — resetting video step for retry.")
        update_video_status(video_name, "videos", "failed")
        update_video_status(video_name, "assembly", "failed")
        return False
    elif result.returncode != 0:
        update_video_status(video_name, "assembly", "failed")
        print(f"  ✗ assembly failed for {video_name}")
        return False

    update_video_status(video_name, "assembly", "completed",
                        assets={"final_video": str(final_video)})

    # --- Step 8: Spanish Captions ---
    captioned_video = output_dir / f"{video_stem}_captioned.mp4"
    if not run_step(video_name, "captions", [
        PYTHON, str(UTILS_DIR / "caption_video.py"),
        str(final_video), "-o", str(captioned_video),
        "--language", "es", "--model", "base"
    ], assets={"captioned_video": str(captioned_video)}):
        return False

    # --- Phase 3: Metadata Consolidation ---
    print(f"\n  [CONSOLIDATING] Metadata for {video_name}...")
    status = load_status()
    video_status = status.get(video_name, {})
    
    metadata = {
        "video_name": video_name,
        "english_script": eng_script.read_text() if eng_script.exists() else "",
        "spanish_script": spa_script.read_text() if spa_script.exists() else "",
        "analysis": yaml.safe_load(analysis_file.read_text()) if analysis_file.exists() else {},
        "prompts": yaml.safe_load(prompts_file.read_text()) if prompts_file.exists() else {},
        "assets": video_status.get("assets", {})
    }
    meta_json = output_dir / "full_metadata.json"
    with open(meta_json, "w") as f:
        json.dump(metadata, f, indent=2)

    # --- Step 9: Spanish Rename + Copy to final_clones/ ---
    # Export the captioned version (or fall back to uncaptioned)
    export_video = captioned_video if captioned_video.exists() else final_video
    spanish_title = translate_single_title(video_stem)
    safe_name = sanitize_filename(spanish_title)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = FINAL_DIR / f"{safe_name}.mp4"
    
    if export_video.exists():
        shutil.copy2(str(export_video), str(dest_path))
        print(f"  ✅ Exported: {safe_name}.mp4")
        update_video_status(video_name, "bulk_process", "completed", 
                           assets={"metadata_json": str(meta_json), "final_spanish": str(dest_path)},
                           metadata={"spanish_title": spanish_title})

        # --- Step 10: Cleanup intermediate files (DISABLED for testing) ---
        # if dest_path.exists():
        #     try:
        #         shutil.rmtree(str(output_dir))
        #         print(f"  🧹 Cleaned up intermediate files: {output_dir.name}/")
        #     except Exception as e:
        #         print(f"  ⚠ Cleanup failed (non-fatal): {e}")
        print(f"  📁 Intermediate files kept in: {output_dir.name}/")
    else:
        update_video_status(video_name, "bulk_process", "completed", assets={"metadata_json": str(meta_json)})
    
    return True

# ---------------------------------------------------------------------------
# Title Translation (NVIDIA NIM)
# ---------------------------------------------------------------------------

def translate_single_title(english_title: str) -> str:
    """Translate a single English video title to catchy Spanish using NVIDIA NIM."""
    from openai import OpenAI
    
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    
    prompt = f"""\
Translate this English video title to a catchy, viral Spanish title.
Keep emojis. Keep the dramatic/curiosity tone. Do NOT translate literally — adapt for a Spanish-speaking audience.
Return ONLY the translated title, nothing else. No quotes, no explanation.

English title: {english_title}"""

    try:
        print(f"  [NAMING] Translating title to Spanish...")
        completion = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": "You are a bilingual title translator for viral Spanish YouTube content. Return ONLY the translated title."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=256,
            stream=False,
        )
        
        result = completion.choices[0].message.content.strip().strip('"').strip("'")
        print(f"    {english_title}  →  {result}")
        return result
        
    except Exception as e:
        print(f"  ⚠ Title translation failed: {e}. Using English name.")
        return english_title


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    name = name.replace("/", "-").replace("\\", "-").replace(":", "-")
    name = name.replace("?", "").replace("*", "").replace('"', "").replace("<", "").replace(">", "").replace("|", "")
    return name.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not INPUT_DIR.exists():
        print(f"Error: Input directory {INPUT_DIR} not found.")
        sys.exit(1)

    videos = [f for f in INPUT_DIR.iterdir() if f.is_file() and f.suffix.lower() in [".mp4", ".mov", ".mkv"]]
    
    if not videos:
        print(f"No videos found in {INPUT_DIR}")
        return

    print(f"Found {len(videos)} videos to process.")
    
    for v in sorted(videos):
        try:
            process_video(v)
        except Exception as e:
            print(f"Unexpected error processing {v.name}: {e}")
            import traceback
            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()
