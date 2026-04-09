#!/usr/bin/env python3
"""
Audio Generator — Clean TTS Narration.

Generates a single high-quality narration WAV for the entire script.
Uses large chunks to maintain natural conversational flow.
Sends raw text to TTS with no extra prompting for natural default pacing.
"""

import argparse
import asyncio
import base64
import json
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
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:2048")
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = "es-ES-AlvaroNeural" # Changed from Charon
DEFAULT_OUTPUT = "outputs/audio/narration.wav"
DEFAULT_MAX_CHUNK_CHARS = 1000  # Small enough to avoid TTS timeout (default for Spanish)
MAX_RETRIES = 3                 # Retry failed chunks

# Voice mapping for edge-tts
VOICE_MAPPING = {
    "Charon": "es-ES-AlvaroNeural",
    "es": "es-ES-AlvaroNeural",
    "sw": "sw-KE-RafikiNeural"
}

# No prompt prefix — let TTS use its default natural pacing.
# Previous pacing instructions were causing the narration to sound slowed down.
PACE_PREFIX_ES = ""
PACE_PREFIX_SW = ""

# No style instructions — the official TTS API only uses voiceName.
STYLE_INSTRUCTIONS_ES = ""
STYLE_INSTRUCTIONS_SW = ""

# Language-specific config (kept for CLI compatibility, but values are empty)
LANG_CONFIG = {
    "es": {"pace_prefix": PACE_PREFIX_ES, "style": STYLE_INSTRUCTIONS_ES, "voice": "es-ES-AlvaroNeural"},
    "sw": {"pace_prefix": PACE_PREFIX_SW, "style": STYLE_INSTRUCTIONS_SW, "voice": "sw-KE-RafikiNeural"},
}

# Runtime state — set from CLI args
_active_pace_prefix = PACE_PREFIX_ES
_active_style = STYLE_INSTRUCTIONS_ES


def _split_sentences(text: str) -> list[str]:
    """Split text into individual sentences at .!?… boundaries."""
    sentences = re.split(r'(?<=[.!?…])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _split_at_clauses(text: str, max_chars: int) -> list[str]:
    """Last-resort split for very long sentences — break at commas/semicolons."""
    parts = re.split(r'(?<=[,;:])\s+', text)
    chunks = []
    current = ""
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
    """Merge a list of text units into chunks up to max_chars."""
    chunks = []
    current = ""
    for unit in units:
        # If adding this unit would exceed the limit, flush current chunk
        if current and len(current) + len(unit) + 1 > max_chars:
            chunks.append(current.strip())
            current = unit
        else:
            current = f"{current} {unit}" if current else unit
    if current.strip():
        chunks.append(current.strip())
    return chunks


def split_text_into_chunks(text: str, max_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at the most natural breaking points.

    Hierarchy (most natural → least natural):
      1. Paragraph breaks (double newline)
      2. Single newline breaks
      3. Sentence boundaries (.!?…)
      4. Clause boundaries (,;:) — only for very long sentences

    NEVER splits mid-word. Merges small units together up to max_chars.
    """
    if len(text) <= max_chars:
        return [text]

    # --- Level 1: Split on paragraph breaks (double newline) ---
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]

    # If no paragraph breaks, try single newlines
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.strip().split('\n') if p.strip()]

    # --- Level 2: Break paragraphs into sentences, then merge up to max_chars ---
    all_units = []
    for para in paragraphs:
        if len(para) <= max_chars:
            all_units.append(para)
        else:
            # Paragraph too long — split into sentences
            sentences = _split_sentences(para)
            if len(sentences) <= 1:
                # Single enormous sentence — split at clause boundaries
                all_units.extend(_split_at_clauses(para, max_chars))
            else:
                all_units.extend(sentences)

    # --- Level 3: Merge small units back together up to max_chars ---
    return _merge_units(all_units, max_chars)


async def generate_speech_async(text, voice):
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


def generate_speech(text, api_base, model, voice, timeout):
    """Synchronous wrapper for generate_speech_async."""
    return asyncio.run(generate_speech_async(text, voice))


def _parse_fmt_sample_rate(wav_bytes: bytes) -> int | None:
    """Extract the sample rate from a WAV fmt chunk."""
    pos = 12  # Skip RIFF header
    while pos < len(wav_bytes) - 8:
        chunk_id = wav_bytes[pos:pos+4]
        chunk_size = struct.unpack_from('<I', wav_bytes, pos+4)[0]
        if chunk_id == b'fmt ' and chunk_size >= 8:
            # Sample rate is at offset 4 within the fmt data
            sample_rate = struct.unpack_from('<I', wav_bytes, pos + 8 + 4)[0]
            return sample_rate
        pos += 8 + chunk_size
    return None


def concatenate_wav_bytes(wav_list: list[bytes]) -> bytes:
    """Concatenate multiple WAV byte arrays into a single WAV file.

    Validates that all WAVs share the same sample rate. Warns on mismatch.
    """
    if len(wav_list) == 1:
        return wav_list[0]

    # Validate sample rates across all chunks
    sample_rates = []
    for i, wav_bytes in enumerate(wav_list):
        sr = _parse_fmt_sample_rate(wav_bytes)
        sample_rates.append(sr)
        if sr and i > 0 and sr != sample_rates[0]:
            print(f"  ⚠ SAMPLE RATE MISMATCH: chunk {i+1} is {sr}Hz vs chunk 1 at {sample_rates[0]}Hz")
            print(f"    → Audio may play at wrong speed! Post-normalization will fix this.")

    if sample_rates and sample_rates[0]:
        print(f"  Audio sample rate: {sample_rates[0]}Hz")

    # Parse header from the first WAV to get format info
    first = wav_list[0]
    all_pcm = []
    fmt_chunk = None

    for wav_bytes in wav_list:
        pos = 12  # Skip RIFF header
        data_found = False
        while pos < len(wav_bytes) - 8:
            chunk_id = wav_bytes[pos:pos+4]
            chunk_size = struct.unpack_from('<I', wav_bytes, pos+4)[0]
            if chunk_id == b'fmt ':
                if fmt_chunk is None:
                    fmt_chunk = wav_bytes[pos:pos+8+chunk_size]
            elif chunk_id == b'data':
                all_pcm.append(wav_bytes[pos+8:pos+8+chunk_size])
                data_found = True
                break
            pos += 8 + chunk_size
        if not data_found:
            # Fallback: assume header is 44 bytes
            all_pcm.append(wav_bytes[44:])

    # Build new WAV
    combined_pcm = b''.join(all_pcm)
    data_size = len(combined_pcm)

    if fmt_chunk is None:
        # Fallback: extract fmt from first wav
        fmt_chunk = first[12:36]

    # RIFF header (12) + fmt chunk + data header (8) + data
    riff_size = 4 + len(fmt_chunk) + 8 + data_size
    output = bytearray()
    output.extend(b'RIFF')
    output.extend(struct.pack('<I', riff_size))
    output.extend(b'WAVE')
    output.extend(fmt_chunk)
    output.extend(b'data')
    output.extend(struct.pack('<I', data_size))
    output.extend(combined_pcm)

    return bytes(output)


def normalize_wav_with_ffmpeg(wav_path: Path) -> bool:
    """Normalize a WAV file to 24000Hz mono 16-bit using FFmpeg.

    This ensures consistent playback regardless of what the TTS API returned.
    Overwrites the file in place.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  ⚠ FFmpeg not found, skipping audio normalization")
        return False

    temp_path = wav_path.with_suffix(".norm.wav")
    cmd = [
        ffmpeg, "-y", "-i", str(wav_path),
        "-ar", "24000",      # 24kHz (TTS native rate)
        "-ac", "1",           # mono
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-af", "aresample=resampler=soxr",  # high-quality resampling
        str(temp_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # Replace original with normalized version
            temp_path.replace(wav_path)
            print("  ✓ Audio normalized (24kHz/mono/16-bit)")
            return True
        else:
            print(f"  ⚠ FFmpeg normalization failed: {result.stderr[:200]}")
            temp_path.unlink(missing_ok=True)
            return False
    except Exception as e:
        print(f"  ⚠ Audio normalization error: {e}")
        temp_path.unlink(missing_ok=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate Engaging Narration")
    parser.add_argument("script_file", help="Path to script file")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="Output WAV path")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-chunk-chars", type=int, default=DEFAULT_MAX_CHUNK_CHARS,
                        help="Max characters per TTS chunk (default: 1000, use 3000 for longer narrations)")
    parser.add_argument("--language", default="es", choices=["es", "sw"],
                        help="Language for pacing style (es=Spanish, sw=Swahili, default: es)")

    args = parser.parse_args()
    script_path = Path(args.script_file)
    output_path = Path(args.output)

    # Set language-specific config
    global _active_pace_prefix, _active_style
    lang_cfg = LANG_CONFIG.get(args.language, LANG_CONFIG["es"])
    _active_pace_prefix = lang_cfg["pace_prefix"]
    _active_style = lang_cfg["style"]
    
    # If voice is default, use language-specific voice
    if args.voice == DEFAULT_VOICE or args.voice == "Charon":
        args.voice = lang_cfg.get("voice", args.voice)

    max_chunk = args.max_chunk_chars

    if not script_path.exists():
        print(f"Error: {script_path} not found.")
        sys.exit(1)

    lang_label = "Swahili Bible" if args.language == "sw" else "Spanish Documentary"
    print(f"--- Generating {lang_label} Narration for: {script_path.name} ---")
    script_text = script_path.read_text(encoding="utf-8").strip()

    # Split into chunks for natural pacing
    chunks = split_text_into_chunks(script_text, max_chars=max_chunk)

    if len(chunks) == 1:
        print(f"  Sending request to {args.api_base.rstrip('/')}/generate-speech...")
        print(f"  Voice: {args.voice} | Length: {len(script_text)} chars")
        print(f"  Style: {lang_label} narration (natural pace)")
        audio_bytes = generate_speech(script_text, args.api_base, DEFAULT_MODEL, args.voice, args.timeout)
        if audio_bytes is None:
            print("❌ TTS generation failed.")
            sys.exit(1)
    else:
        print(f"  Script is {len(script_text)} chars — splitting into {len(chunks)} chunks (max {max_chunk} chars each)")
        print(f"  Voice: {args.voice} | Language: {args.language}")
        print(f"  Style: {lang_label} narration (natural pace)")
        wav_parts = []
        for i, chunk in enumerate(chunks, 1):
            print(f"\n  Chunk {i}/{len(chunks)} ({len(chunk)} chars)...")
            audio = None
            for retry in range(1, MAX_RETRIES + 1):
                audio = generate_speech(chunk, args.api_base, DEFAULT_MODEL, args.voice, args.timeout)
                if audio is not None:
                    break
                wait = 10 * retry
                print(f"  ⚠ Chunk {i} failed (attempt {retry}/{MAX_RETRIES}), retrying in {wait}s...")
                time.sleep(wait)
            if audio is None:
                print(f"❌ TTS generation failed on chunk {i} after {MAX_RETRIES} attempts.")
                sys.exit(1)
            wav_parts.append(audio)
            # Delay between chunks to avoid rate limiting
            if i < len(chunks):
                time.sleep(3)

        print(f"\n  Concatenating {len(wav_parts)} audio segments...")
        audio_bytes = concatenate_wav_bytes(wav_parts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio_bytes)

    # Normalize audio to consistent sample rate via FFmpeg
    print("  Normalizing audio...")
    normalize_wav_with_ffmpeg(output_path)

    final_size = output_path.stat().st_size
    print(f"✅ Narration saved: {output_path} ({final_size/1024:.1f} KB)")

if __name__ == "__main__":
    main()
