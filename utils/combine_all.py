#!/usr/bin/env python3
"""
Video Assembler — Per-Scene Synchronized Assembly.

Uses Whisper to detect word-level timestamps in the narration audio,
then stretches/compresses each video clip to match its corresponding
narration segment precisely.

When clips are missing, their audio time is distributed to neighboring
clips, with a slowdown cap to prevent frozen-looking video.

Modes:
  1. Synced  (--prompts-file): per-scene sync via Whisper
  2. Legacy  (no --prompts-file): uniform stretch across all clips
"""

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = "outputs/final_video.mp4"
DEFAULT_CLIPS_DIR = "outputs/clips"
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}

# 2.0x = 50% speed.  Beyond this clips look frozen.
MAX_SLOWDOWN_FACTOR = 2.0
WHISPER_MODEL = "base"

# Minimum fraction of clips that must be present to proceed with assembly.
# If fewer than this fraction exist, assembly is aborted to prevent a broken video.
MIN_CLIP_FRACTION = 0.6

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Error: FFmpeg not found.")
        sys.exit(1)
    return ffmpeg


def get_duration(ffmpeg_path, media_path):
    ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe")
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def get_resolution(ffmpeg_path, path):
    ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe")
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", str(path)],
            capture_output=True, text=True, timeout=30)
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 0, 0


def collect_clips(clips_dir):
    if not clips_dir or not clips_dir.exists():
        return []
    clips = [f for f in clips_dir.iterdir()
             if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
    clips.sort(key=lambda x: (
        int(re.search(r'(\d+)', x.name).group(1))
        if re.search(r'(\d+)', x.name) else 0))
    return clips


def clip_scene_number(p: Path) -> int:
    m = re.search(r'(\d+)', p.name)
    return int(m.group(1)) if m else 0


def build_clip_map(clips):
    return {clip_scene_number(c): c for c in clips}


def target_resolution(ffmpeg_path, clips):
    from collections import Counter
    res = [get_resolution(ffmpeg_path, c) for c in clips]
    valid = [(w, h) for w, h in res if w > 0 and h > 0]
    if valid:
        return Counter(valid).most_common(1)[0][0]
    return 1280, 720


def normalize_audio(ffmpeg_path, audio_path, temp_dir):
    norm = temp_dir / "narration_norm.wav"
    r = subprocess.run(
        [ffmpeg_path, "-y", "-i", str(audio_path),
         "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le", str(norm)],
        capture_output=True, text=True)
    if r.returncode == 0:
        print("  ✓ Audio resampled to 44100Hz stereo")
        return norm
    print(f"  ⚠ Resample failed, using original")
    return audio_path


def load_scene_scripts(prompts_path):
    """Load prompts YAML → ordered list of script texts per scene."""
    try:
        import yaml
    except ImportError:
        print("  ⚠ PyYAML required. pip install pyyaml")
        return []
    try:
        data = yaml.safe_load(prompts_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠ Failed to load prompts: {e}")
        return []
    if not isinstance(data, dict) or "scenes" not in data:
        return []
    scenes = sorted(data["scenes"], key=lambda s: s.get("scene_number", 0))
    return [s.get("swahili_script", "") or s.get("script", "") or "" for s in scenes]


# ---------------------------------------------------------------------------
# Whisper Alignment
# ---------------------------------------------------------------------------

def get_word_timestamps(audio_path):
    """Run faster-whisper for word-level timestamps."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  ⚠ faster-whisper not installed (pip install faster-whisper)")
        print("    → Falling back to proportional timing.")
        return []
    print(f"  🎙️  Running Whisper alignment (model={WHISPER_MODEL})...")
    try:
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segs, info = model.transcribe(audio_path, word_timestamps=True, language=None)
        words = []
        for seg in segs:
            for w in (seg.words or []):
                words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
        if words:
            print(f"    ✅ {len(words)} words detected (lang={info.language})")
        else:
            print("    ⚠ No words detected")
        return words
    except Exception as e:
        print(f"  ⚠ Whisper error: {e}")
        return []


def scene_timings_from_whisper(words, scripts, total_dur):
    """Proportionally assign Whisper words to scenes → time ranges."""
    n = len(scripts)
    tw = len(words)
    counts = [max(1, len(s.split())) for s in scripts]
    total_w = sum(counts)

    raw = []
    idx = 0
    for wc in counts:
        n_assign = max(1, round(wc / total_w * tw))
        n_assign = min(n_assign, tw - idx)
        if n_assign <= 0 or idx >= tw:
            t = words[-1]["end"] if words else total_dur
            raw.append((t, t))
        else:
            raw.append((words[idx]["start"], words[idx + n_assign - 1]["end"]))
            idx += n_assign

    # Make contiguous
    adj = []
    for i in range(n):
        s = 0.0 if i == 0 else adj[i - 1][1]
        e = total_dur if i == n - 1 else max(raw[i][1], s + 0.1)
        adj.append((s, e))
    return adj


def scene_timings_proportional(scripts, total_dur):
    """Fallback: proportional by character count."""
    n = len(scripts)
    if n == 0:
        return []
    chars = [max(1, len(s)) for s in scripts]
    total = sum(chars)
    t = []
    cur = 0.0
    for c in chars:
        d = (c / total) * total_dur
        t.append((cur, cur + d))
        cur += d
    if t:
        t[-1] = (t[-1][0], total_dur)
    return t


# ---------------------------------------------------------------------------
# Synced Assembly
# ---------------------------------------------------------------------------

def assemble_synced(ffmpeg_path, clips, audio_path, output_path, scene_timings, n_scenes):
    temp_dir = Path(tempfile.mkdtemp(prefix="assemble_synced_"))
    try:
        _do_synced(ffmpeg_path, clips, audio_path, output_path, scene_timings, n_scenes, temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _do_synced(ffmpeg_path, clips, audio_path, output_path, scene_timings, n_scenes, temp_dir):
    norm_audio = normalize_audio(ffmpeg_path, audio_path, temp_dir)
    narr_dur = get_duration(ffmpeg_path, norm_audio)
    clip_map = build_clip_map(clips)
    tw, th = target_resolution(ffmpeg_path, clips)
    print(f"  Resolution: {tw}×{th}")

    # Build segments
    segs = []
    for i in range(n_scenes):
        sn = i + 1
        s, e = scene_timings[i]
        segs.append({"sn": sn, "clip": clip_map.get(sn), "dur": e - s})

    avail = sum(1 for s in segs if s["clip"])
    miss = n_scenes - avail
    print(f"  Clips: {avail}/{n_scenes} present, {miss} missing")

    # Guard: abort if too many clips are missing to prevent a broken video.
    # bulk_processor.retry_missing_clips() should have filled gaps before we get here.
    if n_scenes > 0 and avail / n_scenes < MIN_CLIP_FRACTION:
        print(f"\n  ❌ ASSEMBLY ABORTED: only {avail}/{n_scenes} clips present "
              f"({avail/n_scenes:.0%} < {MIN_CLIP_FRACTION:.0%} minimum).")
        print(f"     Missing scenes: {[s['sn'] for s in segs if s['clip'] is None]}")
        sys.exit(2)

    # Redistribute missing clip time to neighbors — the missing scene's audio
    # duration is absorbed by the nearest present clip so the audio stays intact.
    changed = True
    while changed:
        changed = False
        for i in range(len(segs)):
            if segs[i]["clip"] is not None:
                continue
            dur = segs[i]["dur"]
            # prefer previous neighbor, then next
            if i > 0 and segs[i - 1]["clip"] is not None:
                segs[i - 1]["dur"] += dur
                segs.pop(i); changed = True; break
            elif i < len(segs) - 1 and segs[i + 1]["clip"] is not None:
                segs[i + 1]["dur"] += dur
                segs.pop(i); changed = True; break

    segs = [s for s in segs if s["clip"] is not None]
    if not segs:
        print("  ❌ No clips available"); sys.exit(1)

    # Encode each clip with its stretch factor
    print(f"\n  📐 Per-scene timing:")
    vf_base = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2"
    norm_clips = []

    for seg in segs:
        cd = get_duration(ffmpeg_path, seg["clip"])
        if cd <= 0:
            continue
        stretch = seg["dur"] / cd
        capped = min(stretch, MAX_SLOWDOWN_FACTOR)
        actual = cd * capped
        pct = (1.0 / capped) * 100

        if capped < stretch:
            icon, note = "⚠", f"capped {MAX_SLOWDOWN_FACTOR}x, {seg['dur']-actual:.1f}s gap"
        elif capped > 1.2:
            icon, note = "🐢", f"{pct:.0f}% speed"
        elif capped < 0.8:
            icon, note = "⚡", f"{pct:.0f}% speed"
        else:
            icon, note = "✓", f"{pct:.0f}% speed"
        print(f"    Scene {seg['sn']:2d}: {cd:.1f}s → {actual:.1f}s  {icon} {note}")

        vf = vf_base if abs(capped - 1.0) < 0.03 else f"setpts={capped}*PTS,{vf_base}"
        out = temp_dir / f"n_{seg['sn']:03d}.mp4"
        cmd = [ffmpeg_path, "-y", "-i", str(seg["clip"]),
               "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
               "-an", "-pix_fmt", "yuv420p", "-r", "30",
               "-vf", vf, "-t", str(actual), str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            norm_clips.append(out)
        else:
            print(f"    ⚠ Encode failed scene {seg['sn']}")

    if not norm_clips:
        print("  ❌ No clips encoded"); sys.exit(1)

    # Concatenate
    cat = temp_dir / "list.txt"
    cat.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips))
    vis = temp_dir / "visuals.mp4"
    subprocess.run([ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
                    "-i", str(cat), "-c", "copy", str(vis)],
                   check=True, capture_output=True)

    # Merge with audio
    vd = get_duration(ffmpeg_path, vis)
    print(f"\n  [Final] Video: {vd:.1f}s | Narration: {narr_dur:.1f}s")
    subprocess.run([ffmpeg_path, "-y",
                    "-i", str(vis), "-i", str(norm_audio),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v", "-map", "1:a",
                    "-t", str(narr_dur), str(output_path)],
                   check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Legacy Assembly (uniform stretch — no prompts file)
# ---------------------------------------------------------------------------

def assemble_legacy(ffmpeg_path, clips, audio_path, output_path):
    temp_dir = Path(tempfile.mkdtemp(prefix="assemble_legacy_"))
    try:
        _do_legacy(ffmpeg_path, clips, audio_path, output_path, temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _do_legacy(ffmpeg_path, clips, audio_path, output_path, temp_dir):
    norm_audio = normalize_audio(ffmpeg_path, audio_path, temp_dir)
    narr_dur = get_duration(ffmpeg_path, norm_audio)
    total_cd = sum(get_duration(ffmpeg_path, c) for c in clips)
    tw, th = target_resolution(ffmpeg_path, clips)

    print(f"  Clips: {total_cd:.1f}s | Narration: {narr_dur:.1f}s")
    if total_cd <= 0:
        print("Error: no valid clips"); sys.exit(1)

    if total_cd >= narr_dur:
        factor = 1.0
        print(f"  ✓ Native speed, trimming to {narr_dur:.1f}s")
    else:
        factor = narr_dur / total_cd
        print(f"  🐢 Uniform stretch: {(1/factor)*100:.0f}% speed (×{factor:.2f})")

    vf_base = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2"
    vf = vf_base if factor == 1.0 else f"setpts={factor}*PTS,{vf_base}"

    norm_clips = []
    for i, clip in enumerate(clips):
        out = temp_dir / f"norm_{i:02d}.mp4"
        subprocess.run([ffmpeg_path, "-y", "-i", str(clip),
                        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                        "-an", "-pix_fmt", "yuv420p", "-r", "30",
                        "-vf", vf, str(out)],
                       capture_output=True, check=True)
        norm_clips.append(out)

    cat = temp_dir / "list.txt"
    cat.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips))
    vis = temp_dir / "visuals.mp4"
    subprocess.run([ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
                    "-i", str(cat), "-c", "copy", str(vis)],
                   check=True, capture_output=True)

    subprocess.run([ffmpeg_path, "-y",
                    "-i", str(vis), "-i", str(norm_audio),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v", "-map", "1:a",
                    "-t", str(narr_dur), "-shortest", str(output_path)],
                   check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Chunk-Manifest Assembly (deterministic — no Whisper)
# ---------------------------------------------------------------------------

def load_chunk_manifest(manifest_path):
    """Load chunks_manifest.json → list of chunk dicts."""
    try:
        import json
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        print(f"  ⚠ Failed to load chunk manifest: {e}")
        return None


def assemble_chunk_synced(ffmpeg_path, clips, audio_path, output_path, manifest):
    """Assemble using chunk manifest for deterministic sync.

    Each chunk in the manifest specifies:
      - duration: exact audio duration for this chunk
      - scene_numbers: which clip(s) cover this chunk's audio

    For each chunk, we stretch/compress the assigned clip(s) to exactly
    fill that chunk's audio duration. No Whisper, no guessing.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="assemble_chunk_"))
    try:
        _do_chunk_synced(ffmpeg_path, clips, audio_path, output_path, manifest, temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _do_chunk_synced(ffmpeg_path, clips, audio_path, output_path, manifest, temp_dir):
    norm_audio = normalize_audio(ffmpeg_path, audio_path, temp_dir)
    narr_dur = get_duration(ffmpeg_path, norm_audio)
    clip_map = build_clip_map(clips)
    tw, th = target_resolution(ffmpeg_path, clips)
    print(f"  Resolution: {tw}×{th}")

    chunks = manifest.get("chunks", [])
    clip_seconds = manifest.get("clip_seconds", 6)

    print(f"\n  📐 Chunk-Synced Assembly:")
    print(f"     Audio chunks: {len(chunks)}")
    print(f"     Narration:    {narr_dur:.1f}s")
    print(f"     Clip length:  {clip_seconds}s each")

    # Guard: count how many scene numbers from the manifest actually have clips
    all_scene_nums = set()
    for chunk in chunks:
        all_scene_nums.update(chunk.get("scene_numbers", []))
    present = sum(1 for sn in all_scene_nums if sn in clip_map)
    total_expected = len(all_scene_nums)
    if total_expected > 0 and present / total_expected < MIN_CLIP_FRACTION:
        missing_sns = sorted(sn for sn in all_scene_nums if sn not in clip_map)
        print(f"\n  ❌ ASSEMBLY ABORTED: only {present}/{total_expected} clips present "
              f"({present/total_expected:.0%} < {MIN_CLIP_FRACTION:.0%} minimum).")
        print(f"     Missing scenes: {missing_sns}")
        sys.exit(2)
    print(f"     Clips present: {present}/{total_expected}")

    # Build a flat ordered list of (scene_number, target_duration, clip_path|None)
    # one entry per scene number across all chunks.
    flat = []
    for chunk in chunks:
        chunk_dur = chunk["duration"]
        scene_nums = chunk["scene_numbers"]
        n = len(scene_nums)
        per_scene = chunk_dur / max(n, 1)
        for sn in scene_nums:
            flat.append({
                "sn": sn,
                "dur": per_scene,
                "clip": clip_map.get(sn),
                "chunk_idx": chunk["chunk_index"],
            })

    # Redistribute duration from missing scenes to their nearest present neighbor.
    # This keeps the total video duration equal to narr_dur so audio never drifts.
    changed = True
    while changed:
        changed = False
        for i, entry in enumerate(flat):
            if entry["clip"] is not None:
                continue
            dur = entry["dur"]
            # Prefer previous neighbor, then next
            if i > 0 and flat[i - 1]["clip"] is not None:
                flat[i - 1]["dur"] += dur
                flat.pop(i)
                changed = True
                break
            elif i < len(flat) - 1 and flat[i + 1]["clip"] is not None:
                flat[i + 1]["dur"] += dur
                flat.pop(i)
                changed = True
                break

    flat = [e for e in flat if e["clip"] is not None]
    if not flat:
        print("  ❌ No clips available after redistribution")
        sys.exit(1)

    vf_base = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2"
    norm_clips = []

    print(f"\n  📐 Per-scene timing:")
    for entry in flat:
        sn = entry["sn"]
        clip_path = entry["clip"]
        target_dur = entry["dur"]

        cd = get_duration(ffmpeg_path, clip_path)
        if cd <= 0:
            print(f"    Scene {sn:2d}: ⚠ Could not read duration, skipping")
            continue

        stretch = target_dur / cd
        capped = min(stretch, MAX_SLOWDOWN_FACTOR)
        actual = cd * capped
        pct = (1.0 / capped) * 100

        if capped < stretch:
            icon, note = "⚠", f"capped {MAX_SLOWDOWN_FACTOR}x, gap {target_dur - actual:.1f}s"
        elif capped > 1.2:
            icon, note = "🐢", f"{pct:.0f}% speed"
        elif capped < 0.8:
            icon, note = "⚡", f"{pct:.0f}% speed"
        else:
            icon, note = "✓", f"{pct:.0f}% speed"

        print(f"    Scene {sn:2d}: {cd:.1f}s → {actual:.1f}s  {icon} {note}")

        vf = vf_base if abs(capped - 1.0) < 0.03 else f"setpts={capped}*PTS,{vf_base}"
        out = temp_dir / f"n_{sn:05d}.mp4"
        cmd = [ffmpeg_path, "-y", "-i", str(clip_path),
               "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
               "-an", "-pix_fmt", "yuv420p", "-r", "30",
               "-vf", vf, "-t", str(actual), str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            norm_clips.append(out)
        else:
            print(f"    ⚠ Encode failed scene {sn}: {r.stderr[:120]}")

    if not norm_clips:
        print("  ❌ No clips encoded")
        sys.exit(1)

    # Concatenate all normalized clips in scene order
    cat = temp_dir / "list.txt"
    cat.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips), encoding="utf-8")
    vis = temp_dir / "visuals.mp4"
    subprocess.run([ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
                    "-i", str(cat), "-c", "copy", str(vis)],
                   check=True, capture_output=True)

    # Merge with audio — audio is the master clock.
    # If video is shorter than audio it means clips are still missing despite retries.
    # Abort hard so the pipeline knows to retry rather than produce a broken video.
    vd = get_duration(ffmpeg_path, vis)
    print(f"\n  [Final] Video: {vd:.1f}s | Narration: {narr_dur:.1f}s")

    if vd < narr_dur * 0.95:
        gap = narr_dur - vd
        print(f"\n  ❌ ASSEMBLY ABORTED: assembled video ({vd:.1f}s) is {gap:.1f}s shorter than "
              f"narration ({narr_dur:.1f}s).")
        print(f"     This means clips are still missing. Re-run to regenerate them.")
        sys.exit(2)

    subprocess.run([ffmpeg_path, "-y",
                    "-i", str(vis), "-i", str(norm_audio),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v", "-map", "1:a",
                    "-t", str(narr_dur), str(output_path)],
                   check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Assemble video clips synced to narration audio.")
    parser.add_argument("--clips-dir", type=str, default=DEFAULT_CLIPS_DIR)
    parser.add_argument("-o", "--output", type=str, default=DEFAULT_OUTPUT)
    parser.add_argument("--music", type=str, required=True,
                        help="Path to narration WAV")
    parser.add_argument("--prompts-file", type=str, default=None,
                        help="Path to prompts.yaml for per-scene sync")
    parser.add_argument("--chunk-manifest", type=str, default=None,
                        help="Path to chunks_manifest.json for deterministic chunk sync")

    args = parser.parse_args()
    ffmpeg = check_ffmpeg()
    output_path = Path(args.output).resolve()
    audio_path = Path(args.music).resolve()
    clips_dir = Path(args.clips_dir).resolve()

    print("=" * 60)
    print("  Video Assembler — Per-Scene Synchronized")
    print("=" * 60)

    clips = collect_clips(clips_dir)
    if not clips:
        print("Error: No clips found."); sys.exit(1)
    print(f"  Found {len(clips)} clips\n")

    # Mode 1: Chunk-manifest (deterministic — preferred)
    if args.chunk_manifest:
        mp = Path(args.chunk_manifest).resolve()
        if mp.exists():
            manifest = load_chunk_manifest(mp)
            if manifest and manifest.get("chunks"):
                print(f"  🔗 Using chunk manifest ({len(manifest['chunks'])} chunks)")
                assemble_chunk_synced(ffmpeg, clips, audio_path, output_path, manifest)
                print(f"\n✅ Video saved to: {output_path}")
                return
        print(f"  ⚠ Chunk manifest unavailable → trying prompts-file mode")

    # Mode 2: Prompts-file + Whisper (fallback)
    if args.prompts_file:
        pp = Path(args.prompts_file).resolve()
        if pp.exists():
            scripts = load_scene_scripts(pp)
            if scripts:
                n_scenes = len(scripts)
                narr_dur = get_duration(ffmpeg, audio_path)
                words = get_word_timestamps(str(audio_path))
                if words:
                    timings = scene_timings_from_whisper(words, scripts, narr_dur)
                    print(f"  ✅ Whisper-based scene timings ({n_scenes} scenes)")
                else:
                    timings = scene_timings_proportional(scripts, narr_dur)
                    print(f"  📊 Proportional scene timings ({n_scenes} scenes)")
                assemble_synced(ffmpeg, clips, audio_path, output_path, timings, n_scenes)
                print(f"\n✅ Video saved to: {output_path}")
                return

        print(f"  ⚠ Prompts unavailable → falling back to legacy mode")

    # Mode 3: Legacy (uniform stretch)
    assemble_legacy(ffmpeg, clips, audio_path, output_path)
    print(f"\n✅ Video saved to: {output_path}")


if __name__ == "__main__":
    main()

