#!/usr/bin/env python3
"""
Whisper Segment Aligner — Match audio segments to exact transcript text.

Uses faster-whisper to detect word-level timestamps in each audio chunk,
then splits each chunk into 6-second segments aligned to word boundaries.
Each segment gets the exact text being spoken during those seconds.

This is the bridge between audio generation and video prompt generation:
the prompt engineer knows EXACTLY what is being said during each 6s clip.

Usage (standalone):
    python whisper_segment_aligner.py outputs/audio_chunks/

Usage (from pipeline):
    from utils.whisper_segment_aligner import align_chunks_to_segments
    segments = align_chunks_to_segments(manifest, audio_dir)
"""

import json
import math
import sys
from pathlib import Path

WHISPER_MODEL = "base"
CLIP_SECONDS = 6  # target duration per segment


# ---------------------------------------------------------------------------
# Whisper Word-Level Alignment
# ---------------------------------------------------------------------------

def get_word_timestamps(audio_path: str, language: str = None) -> list[dict]:
    """Run faster-whisper for word-level timestamps on a single audio file."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  ⚠ faster-whisper not installed (pip install faster-whisper)")
        return []

    try:
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segs, info = model.transcribe(
            audio_path, word_timestamps=True, language=language
        )
        words = []
        for seg in segs:
            for w in (seg.words or []):
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                })
        return words
    except Exception as e:
        print(f"  ⚠ Whisper error on {audio_path}: {e}")
        return []


# ---------------------------------------------------------------------------
# Split words into 6-second segments
# ---------------------------------------------------------------------------

def split_words_into_segments(
    words: list[dict],
    total_duration: float,
    clip_seconds: int = CLIP_SECONDS,
) -> list[dict]:
    """Split a list of timestamped words into fixed-duration segments.

    Each segment covers roughly `clip_seconds` of audio, snapping to word
    boundaries so no word is split mid-utterance.

    Returns list of:
        {
            "segment_index": 0,
            "start_time": 0.0,
            "end_time": 6.0,
            "text": "the exact words spoken in this window",
            "word_count": 12,
        }
    """
    if not words:
        # Fallback: no whisper data, create uniform segments
        n_segs = max(1, math.ceil(total_duration / clip_seconds))
        return [
            {
                "segment_index": i,
                "start_time": round(i * clip_seconds, 3),
                "end_time": round(min((i + 1) * clip_seconds, total_duration), 3),
                "text": "",
                "word_count": 0,
            }
            for i in range(n_segs)
        ]

    n_segs = max(1, math.ceil(total_duration / clip_seconds))
    segments = []

    word_idx = 0
    for seg_i in range(n_segs):
        seg_start = seg_i * clip_seconds
        seg_end = min((seg_i + 1) * clip_seconds, total_duration)

        # Collect all words whose midpoint falls within this segment
        seg_words = []
        while word_idx < len(words):
            w = words[word_idx]
            w_mid = (w["start"] + w["end"]) / 2.0
            if w_mid < seg_end:
                seg_words.append(w)
                word_idx += 1
            else:
                break

        # If this is the last segment, collect remaining words
        if seg_i == n_segs - 1:
            while word_idx < len(words):
                seg_words.append(words[word_idx])
                word_idx += 1

        text = " ".join(w["word"] for w in seg_words).strip()

        # Refine boundaries to actual word boundaries
        actual_start = seg_words[0]["start"] if seg_words else seg_start
        actual_end = seg_words[-1]["end"] if seg_words else seg_end

        segments.append({
            "segment_index": seg_i,
            "start_time": round(actual_start if seg_i == 0 else seg_start, 3),
            "end_time": round(actual_end if seg_i == n_segs - 1 else seg_end, 3),
            "text": text,
            "word_count": len(seg_words),
        })

    return segments


# ---------------------------------------------------------------------------
# Main: align all chunks from manifest → per-clip segments
# ---------------------------------------------------------------------------

def align_chunks_to_segments(
    manifest: dict,
    audio_dir: Path,
    language: str = None,
) -> list[dict]:
    """Process all chunks from a manifest & return per-clip segment data.

    Returns a flat list of segments, each containing:
        {
            "scene_number": N,       # global scene number (1-indexed)
            "chunk_index": M,        # which audio chunk it belongs to
            "text": "exact text",    # what is being spoken
            "start_time": 0.0,       # time within chunk
            "end_time": 6.0,
        }
    """
    chunks = manifest.get("chunks", [])
    clip_seconds = manifest.get("clip_seconds", CLIP_SECONDS)
    lang = language or (manifest.get("language") if manifest.get("language") != "sw" else None)

    # If language is Spanish, hint whisper
    if manifest.get("language") == "es":
        lang = "es"

    all_segments = []

    print(f"\n{'='*60}")
    print(f"  🎙️  Whisper Segment Aligner")
    print(f"{'='*60}")
    print(f"  Audio chunks: {len(chunks)}")
    print(f"  Clip length:  {clip_seconds}s")

    for chunk in chunks:
        chunk_idx = chunk["chunk_index"]
        chunk_duration = chunk["duration"]
        scene_numbers = chunk["scene_numbers"]
        audio_file = audio_dir / chunk["audio_file"]

        if not audio_file.exists():
            print(f"  ⚠ Missing audio: {audio_file}")
            # Create empty segments
            for i, sn in enumerate(scene_numbers):
                all_segments.append({
                    "scene_number": sn,
                    "chunk_index": chunk_idx,
                    "text": "",
                    "start_time": i * clip_seconds,
                    "end_time": (i + 1) * clip_seconds,
                })
            continue

        print(f"\n  Chunk {chunk_idx}: {chunk_duration:.1f}s → {len(scene_numbers)} clips")
        print(f"    Audio: {audio_file.name}")

        # Run Whisper on this chunk
        words = get_word_timestamps(str(audio_file), language=lang)
        if words:
            print(f"    ✅ {len(words)} words detected")
        else:
            print(f"    ⚠ No words detected, using chunk text split")

        # Split into segments
        segments = split_words_into_segments(words, chunk_duration, clip_seconds)

        # If Whisper couldn't detect words, fall back to text-based split
        if not words and chunk.get("text"):
            chunk_text = chunk["text"]
            # Split text proportionally across segments
            words_list = chunk_text.split()
            per_seg = max(1, len(words_list) // len(segments))
            for i, seg in enumerate(segments):
                start_w = i * per_seg
                end_w = (i + 1) * per_seg if i < len(segments) - 1 else len(words_list)
                seg["text"] = " ".join(words_list[start_w:end_w])
                seg["word_count"] = end_w - start_w

        # Map segments to scene numbers
        for i, seg in enumerate(segments):
            if i < len(scene_numbers):
                sn = scene_numbers[i]
            else:
                sn = scene_numbers[-1]  # overflow → last scene

            all_segments.append({
                "scene_number": sn,
                "chunk_index": chunk_idx,
                "text": seg["text"],
                "start_time": seg["start_time"],
                "end_time": seg["end_time"],
            })

            # Print alignment info
            text_preview = seg["text"][:60] + "..." if len(seg["text"]) > 60 else seg["text"]
            print(f"    Scene {sn:3d}: [{seg['start_time']:.1f}s-{seg['end_time']:.1f}s] \"{text_preview}\"")

    print(f"\n  ✅ Total segments: {len(all_segments)}")
    print(f"{'='*60}")

    return all_segments


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Whisper Segment Aligner")
    parser.add_argument("audio_dir", help="Path to audio_chunks directory")
    parser.add_argument("-o", "--output", default=None,
                        help="Output JSON path (default: audio_dir/aligned_segments.json)")
    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    manifest_path = audio_dir / "chunks_manifest.json"

    if not manifest_path.exists():
        print(f"Error: {manifest_path} not found")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    segments = align_chunks_to_segments(manifest, audio_dir)

    out_path = Path(args.output) if args.output else audio_dir / "aligned_segments.json"
    out_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Saved: {out_path}")
