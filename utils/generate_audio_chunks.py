#!/usr/bin/env python3
"""
Chunk-Aware Audio Generator.

Generates TTS audio for each text chunk individually and saves a manifest
file that maps each chunk to its:
  - text content
  - audio file path
  - measured duration in seconds

This manifest becomes the single source of truth for the rest of the
pipeline: visual prompt generation, video clip generation, and final
assembly all reference these chunks to maintain perfect audio-video sync.

Usage (standalone):
    python generate_audio_chunks.py script.txt -o outputs/audio_chunks/
    python generate_audio_chunks.py script.txt -o outputs/audio_chunks/ --language sw

Usage (from pipeline):
    from utils.generate_audio_chunks import generate_chunked_audio
    manifest = generate_chunked_audio(script_text, output_dir, ...)
"""

import argparse
import asyncio
import base64
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

import edge_tts

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:2048")
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = "es-ES-AlvaroNeural" # Changed from Charon
DEFAULT_MAX_CHUNK_CHARS = 1000
MAX_RETRIES = 3
CLIP_SECONDS = 6  # Grok text-to-video clip length

# Voice mapping for edge-tts
VOICE_MAPPING = {
    "Charon": "es-ES-AlvaroNeural",
    "es": "es-ES-AlvaroNeural",
    "sw": "sw-KE-RafikiNeural"
}

# ---------------------------------------------------------------------------
# Text chunking  (reused from generate_audio.py)
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?…])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _split_at_clauses(text: str, max_chars: int) -> list[str]:
    parts = re.split(r'(?<=[,;:])\s+', text)
    chunks, current = [], ""
    for part in parts:
        if current and len(current) + len(part) + 1 > max_chars:
            chunks.append(current.strip())
            current = part
        else:
            current = f"{current} {part}" if current else part
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _merge_units(units: list[str], max_chars: int) -> list[str]:
    chunks, current = [], ""
    for unit in units:
        if current and len(current) + len(unit) + 1 > max_chars:
            chunks.append(current.strip())
            current = unit
        else:
            current = f"{current} {unit}" if current else unit
    if current.strip():
        chunks.append(current.strip())
    return chunks


def split_text_into_chunks(text: str, max_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at natural breaking points."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.strip().split('\n') if p.strip()]

    all_units = []
    for para in paragraphs:
        if len(para) <= max_chars:
            all_units.append(para)
        else:
            sentences = _split_sentences(para)
            if len(sentences) <= 1:
                all_units.extend(_split_at_clauses(para, max_chars))
            else:
                all_units.extend(sentences)

    return _merge_units(all_units, max_chars)


# ---------------------------------------------------------------------------
# TTS call (single chunk)
# ---------------------------------------------------------------------------

async def _generate_speech_async(text, voice):
    """Generate speech for a text chunk using edge-tts."""
    # Map AIStudio voice name to edge-tts voice if necessary
    actual_voice = VOICE_MAPPING.get(voice, voice)
    
    start = time.time()
    try:
        communicate = edge_tts.Communicate(text, actual_voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        
        if not audio_bytes:
            return None

        # Convert MP3 (edge-tts default) to WAV using FFmpeg
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            process = subprocess.Popen(
                [ffmpeg, "-i", "pipe:0", "-f", "wav", "-ar", "24000", "-ac", "1", "pipe:1"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            wav_bytes, err = process.communicate(input=audio_bytes)
            if process.returncode == 0:
                audio_bytes = wav_bytes
            else:
                print(f"  ⚠ FFmpeg conversion failed: {err.decode()[:200]}")

        elapsed = time.time() - start
        print(f"    ✓ Generated {len(audio_bytes)/1024:.1f} KB in {elapsed:.1f}s (edge-tts: {actual_voice})")
        return audio_bytes
    except Exception as e:
        print(f"  ✗ edge-tts Failed: {e}")
        return None

def _generate_speech(text: str, api_base: str, model: str, voice: str,
                     timeout: int) -> bytes | None:
    """Synchronous wrapper for _generate_speech_async."""
    return asyncio.run(_generate_speech_async(text, voice))


# ---------------------------------------------------------------------------
# WAV duration measurement
# ---------------------------------------------------------------------------

def _wav_duration_ffprobe(wav_path: Path) -> float:
    """Get duration of a WAV file using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return _wav_duration_header(wav_path)
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path)],
            capture_output=True, text=True, timeout=30
        )
        return float(r.stdout.strip())
    except Exception:
        return _wav_duration_header(wav_path)


def _wav_duration_header(wav_path: Path) -> float:
    """Fallback: estimate duration from WAV header bytes."""
    try:
        data = wav_path.read_bytes()
        # Find fmt chunk for sample rate and byte rate
        pos = 12
        sample_rate = 24000
        byte_rate = 48000
        data_size = 0
        while pos < len(data) - 8:
            chunk_id = data[pos:pos+4]
            chunk_size = struct.unpack_from('<I', data, pos+4)[0]
            if chunk_id == b'fmt ' and chunk_size >= 16:
                sample_rate = struct.unpack_from('<I', data, pos+8+4)[0]
                byte_rate = struct.unpack_from('<I', data, pos+8+8)[0]
            elif chunk_id == b'data':
                data_size = chunk_size
                break
            pos += 8 + chunk_size
        if byte_rate > 0 and data_size > 0:
            return data_size / byte_rate
        return 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# WAV normalization
# ---------------------------------------------------------------------------

def _normalize_wav(wav_path: Path) -> bool:
    """Normalize WAV to 24000Hz mono 16-bit via FFmpeg (in-place)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    temp = wav_path.with_suffix(".norm.wav")
    cmd = [
        ffmpeg, "-y", "-i", str(wav_path),
        "-ar", "24000", "-ac", "1", "-acodec", "pcm_s16le",
        "-af", "aresample=resampler=soxr",
        str(temp)
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            temp.replace(wav_path)
            return True
        temp.unlink(missing_ok=True)
        return False
    except Exception:
        temp.unlink(missing_ok=True)
        return False


# ---------------------------------------------------------------------------
# Core: generate chunked audio + manifest
# ---------------------------------------------------------------------------

def generate_chunked_audio(
    script_text: str,
    output_dir: Path,
    api_base: str = DEFAULT_API_BASE,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
    timeout: int = 900,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    language: str = "sw",
    clip_seconds: int = CLIP_SECONDS,
) -> dict:
    """Generate audio for each text chunk individually.

    Returns a manifest dict like:
    {
        "language": "sw",
        "clip_seconds": 6,
        "total_duration": 180.5,
        "combined_audio": "narration.wav",
        "chunks": [
            {
                "chunk_index": 0,
                "text": "Hapo mwanzo kabisa...",
                "audio_file": "chunk_000.wav",
                "duration": 12.3,
                "clips_needed": 3,
                "scene_numbers": [1, 2, 3]
            },
            ...
        ]
    }
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pick voice based on language if still default
    if voice == DEFAULT_VOICE or voice == "Charon":
        if language == "sw":
            voice = "sw-KE-RafikiNeural"
        else:
            voice = "es-ES-AlvaroNeural"

    chunks = split_text_into_chunks(script_text, max_chars=max_chunk_chars)

    print(f"\n{'='*60}")
    print(f"  🎙️  Chunk-Aware Audio Generator")
    print(f"{'='*60}")
    print(f"  Script: {len(script_text)} chars → {len(chunks)} chunks")
    print(f"  Voice:  {voice} | Language: {language}")
    print(f"  Max chunk: {max_chunk_chars} chars")

    manifest_chunks = []
    all_wav_bytes = []
    total_duration = 0.0
    scene_counter = 1

    for i, chunk_text in enumerate(chunks):
        chunk_file = output_dir / f"chunk_{i:03d}.wav"
        print(f"\n  Chunk {i+1}/{len(chunks)} ({len(chunk_text)} chars)...")

        # Generate audio for this chunk (with retries)
        audio_bytes = None
        for attempt in range(1, MAX_RETRIES + 1):
            audio_bytes = _generate_speech(chunk_text, api_base, model, voice, timeout)
            if audio_bytes is not None:
                break
            wait = 10 * attempt
            print(f"    ⚠ Attempt {attempt}/{MAX_RETRIES} failed, retrying in {wait}s...")
            time.sleep(wait)

        if audio_bytes is None:
            print(f"  ❌ Chunk {i+1} failed after {MAX_RETRIES} attempts!")
            return {}

        # Save chunk WAV
        chunk_file.write_bytes(audio_bytes)
        _normalize_wav(chunk_file)
        all_wav_bytes.append(chunk_file.read_bytes())

        # Measure duration
        duration = _wav_duration_ffprobe(chunk_file)
        if duration <= 0:
            print(f"    ⚠ Could not measure duration for chunk {i+1}")
            duration = 6.0  # fallback

        # Calculate how many 6s clips this chunk needs
        clips_needed = max(1, math.ceil(duration / clip_seconds))
        scene_numbers = list(range(scene_counter, scene_counter + clips_needed))
        scene_counter += clips_needed

        manifest_chunks.append({
            "chunk_index": i,
            "text": chunk_text,
            "audio_file": chunk_file.name,
            "duration": round(duration, 2),
            "clips_needed": clips_needed,
            "scene_numbers": scene_numbers,
        })

        total_duration += duration
        print(f"    Duration: {duration:.2f}s → {clips_needed} clip(s) (scenes {scene_numbers[0]}-{scene_numbers[-1]})")

        # Rate-limit delay
        if i < len(chunks) - 1:
            time.sleep(3)

    # Concatenate all chunks into one narration.wav (for final assembly)
    combined_path = output_dir / "narration.wav"
    _concatenate_wavs_ffmpeg(
        [output_dir / c["audio_file"] for c in manifest_chunks],
        combined_path
    )

    total_clips = sum(c["clips_needed"] for c in manifest_chunks)

    manifest = {
        "language": language,
        "clip_seconds": clip_seconds,
        "total_duration": round(total_duration, 2),
        "total_clips": total_clips,
        "combined_audio": "narration.wav",
        "chunks": manifest_chunks,
    }

    # Save manifest
    manifest_path = output_dir / "chunks_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  ✅ Audio Generation Complete")
    print(f"     Chunks:  {len(manifest_chunks)}")
    print(f"     Clips:   {total_clips}")
    print(f"     Total:   {total_duration:.1f}s ({total_duration/60:.1f} min)")
    print(f"     Audio:   {combined_path}")
    print(f"     Manifest:{manifest_path}")
    print(f"{'='*60}")

    return manifest


def _concatenate_wavs_ffmpeg(wav_files: list[Path], output: Path):
    """Concatenate multiple WAV files using FFmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or len(wav_files) == 0:
        return

    if len(wav_files) == 1:
        shutil.copy2(wav_files[0], output)
        return

    # Write concat list
    list_file = output.with_suffix(".concat.txt")
    list_file.write_text(
        "\n".join(f"file '{f.resolve()}'" for f in wav_files if f.exists())
    )

    cmd = [
        ffmpeg, "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-ar", "24000", "-ac", "1", "-acodec", "pcm_s16le",
        str(output)
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  ✓ Combined audio: {output.name}")
        else:
            print(f"  ⚠ FFmpeg concat failed: {r.stderr[:200]}")
    except Exception as e:
        print(f"  ⚠ Concat error: {e}")
    finally:
        list_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Chunk-Aware TTS Audio")
    parser.add_argument("script_file", help="Path to script file")
    parser.add_argument("-o", "--output-dir", default="outputs/audio_chunks/")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-chunk-chars", type=int, default=DEFAULT_MAX_CHUNK_CHARS)
    parser.add_argument("--language", default="sw", choices=["es", "sw"])

    args = parser.parse_args()
    script_path = Path(args.script_file)

    if not script_path.exists():
        print(f"Error: {script_path} not found")
        sys.exit(1)

    script_text = script_path.read_text(encoding="utf-8").strip()
    manifest = generate_chunked_audio(
        script_text,
        output_dir=Path(args.output_dir),
        api_base=args.api_base,
        voice=args.voice,
        timeout=args.timeout,
        max_chunk_chars=args.max_chunk_chars,
        language=args.language,
    )

    if not manifest:
        print("❌ Audio generation failed")
        sys.exit(1)

    print(f"\n✅ Done. Manifest: {Path(args.output_dir) / 'chunks_manifest.json'}")
