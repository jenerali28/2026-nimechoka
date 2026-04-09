---
description: Debug and fix audio-visual sync in the video clone pipeline
---

# Audio-Visual Sync Fix Workflow

## Problem
Video clips don't match what's being said in the audio narration (e.g. audio says 
"a metal bar pierced his skull" but video shows something unrelated).

## Root Cause
The script was being split into N equal-length segments by character count, ignoring 
the actual timing of audio. Each video clip got a text segment that didn't correspond 
to what was being spoken during those 6 seconds.

## What We Changed

### New Files Created
1. **`utils/whisper_segment_aligner.py`** — Runs Whisper on each audio chunk to get 
   word-level timestamps, then splits into 6-second segments with exact text alignment.
2. **`utils/ken_burns_effect.py`** — Applies zoom/pan (Ken Burns) effects to still 
   images, producing animated video clips for the image-based portion.

### Files Modified
3. **`utils/multimodal_orchestrator.py`** — Updated to:
   - Accept `--aligned-segments` parameter for Whisper-aligned text
   - Accept `--video-cutoff` for hybrid video/image mode
   - Stronger prompt instructions to match narration content exactly
   - Tags scenes with `generation_mode: video|image`
4. **`utils/generate_videos.py`** — Updated for hybrid mode:
   - Video clips for scenes tagged `generation_mode: video`
   - Grok images + Ken Burns animation for `generation_mode: image`
5. **`bulk_processor.py`** — Added step 3.7 (Whisper alignment) before prompt generation
6. **`main.py`** — Same integration as bulk_processor

## Pipeline Flow (Updated)

```
1. Transcribe → english_script.txt
2. Rewrite → spanish_script.txt
3. TTS → audio_chunks/ + chunks_manifest.json
   3.7. Whisper Align → aligned_segments.json (NEW)
4. Gemini Prompts → prompts.yaml (now uses aligned text + hybrid mode)
5. Generate Videos/Images → clips/ (hybrid: video for first 3 min, images + Ken Burns for rest)
6. Assembly → final video (chunk-synced with manifest)
```

## How to Run

### Full Pipeline
```bash
// turbo
bash init_and_run.sh
```

### Test Whisper Aligner Only
```bash
python utils/whisper_segment_aligner.py outputs/<video>/audio_chunks/
```

### Test Ken Burns Only
```bash
python utils/ken_burns_effect.py --images-dir outputs/<video>/images/ --output-dir /tmp/kb_test/
```

## Verification

After running, check that the `aligned_segments.json` in `audio_chunks/` has text 
entries that match the narration. Each entry should have a `scene_number`, `text`, 
`start_time`, and `end_time`.

In `prompts.yaml`, each scene's `spanish_script` should now contain the exact text 
being spoken during that clip's 6-second window.
