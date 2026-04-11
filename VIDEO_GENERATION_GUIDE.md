# Video Generation Workflow Guide

## Overview

This guide explains how to resume video generation from where you left off, especially after switching from image-based generation to video-only generation.

## Current Status

- **Completed clips**: 1-32 (video clips)
- **Remaining clips**: 33-200 (need video prompts regenerated)
- **Issue**: Original prompts for scenes 33+ were designed for static images with Ken Burns zoom effect
- **Solution**: Regenerate video prompts for scenes 33-200, then resume generation

## Quick Start

### Option 1: Complete Workflow (Recommended)

Run the complete workflow script that handles everything:

```bash
./complete_video_workflow.sh
```

This will:
1. Show current progress
2. Ask if you want to regenerate prompts for remaining scenes
3. Ask if you want to start video generation
4. Track progress automatically

### Option 2: Manual Steps

#### Step 1: Regenerate Video Prompts

Regenerate prompts for scenes 33-200:

```bash
python3 regenerate_video_prompts.py \
    --prompts-file "outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml" \
    --script-file "outputs/Why it Sucks to Be an Egyptian Concubine/spanish_script.txt" \
    --start-scene 33
```

**What this does:**
- Loads existing prompts.yaml
- Creates a backup (prompts.yaml.backup)
- Generates new video prompts for scenes 33-200 using Gemini
- Updates prompts.yaml with proper video motion prompts
- Preserves existing prompts for scenes 1-32

#### Step 2: Resume Video Generation

Start generating videos from scene 33:

```bash
python3 utils/generate_videos.py \
    "outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml" \
    -o "outputs/Why it Sucks to Be an Egyptian Concubine/clips" \
    --resume \
    --grok-api-base "http://localhost:8001" \
    --retries 5
```

**What this does:**
- Reads the progress file to find where to resume
- Skips scenes 1-32 (already exist)
- Generates videos for scenes 33-200
- Saves progress after each scene
- Can be interrupted and resumed anytime

## Progress Tracking

Progress is automatically tracked in:
```
outputs/Why it Sucks to Be an Egyptian Concubine/video_generation_progress.json
```

This file contains:
- `completed_scenes`: List of successfully generated scenes
- `failed_scenes`: List of scenes that failed
- `next_scene_to_generate`: Where to resume from
- `total_scenes`: Total number of scenes (200)

## Key Changes Made

### 1. Video Generation Script (`utils/generate_videos.py`)

**Changed:**
- `VIDEO_CLIP_MINUTES = 999999` (was 3) - Now generates videos for ALL scenes
- Added `--resume` flag to resume from checkpoint
- Added `--start-from` flag to manually specify start scene
- Automatic progress tracking after each scene

**New features:**
- `load_progress()` - Loads checkpoint file
- `save_progress()` - Saves progress after each scene
- Skips existing clips automatically

### 2. Prompt Regeneration Script (`regenerate_video_prompts.py`)

**Purpose:**
- Regenerates video prompts for scenes that were originally designed for images
- Uses the same Gemini-based generation as the original pipeline
- Preserves existing prompts for completed scenes

**Features:**
- Batch processing (8 scenes at a time)
- Automatic backup of original prompts
- Character profile generation for consistency
- Proper video motion prompts (not static image prompts)

## Video vs Image Prompts

### Old Image Prompts (Scenes 33+)
- Designed for static images
- Ken Burns zoom effect applied via FFmpeg
- No motion description
- Character appearance fully described

### New Video Prompts (All Scenes)
- Designed for video generation
- Motion beats with timestamps (0-2s, 2-4s, 4-6s)
- Camera movements
- Character actions and environment animation
- Proper 6-second video clips

## Troubleshooting

### If generation fails:

1. **Check Grok2API server:**
   ```bash
   curl http://localhost:8001/health
   ```

2. **Check progress file:**
   ```bash
   cat "outputs/Why it Sucks to Be an Egyptian Concubine/video_generation_progress.json" | jq
   ```

3. **Resume from specific scene:**
   ```bash
   python3 utils/generate_videos.py \
       "outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml" \
       -o "outputs/Why it Sucks to Be an Egyptian Concubine/clips" \
       --start-from 50 \
       --grok-api-base "http://localhost:8001"
   ```

4. **Check failed scenes:**
   ```bash
   jq '.failed_scenes' "outputs/Why it Sucks to Be an Egyptian Concubine/video_generation_progress.json"
   ```

### If prompts look wrong:

1. **Restore from backup:**
   ```bash
   cp "outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml.backup" \
      "outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml"
   ```

2. **Regenerate specific range:**
   ```bash
   python3 regenerate_video_prompts.py --start-scene 100
   ```

## Rate Limiting

The script includes automatic delays:
- **60 seconds** between each scene generation
- **2 seconds** between prompt generation batches
- **Retry delays** increase with each attempt (15s, 30s, 45s...)

This prevents hitting API rate limits.

## Next Steps

After all videos are generated:

1. **Check completion:**
   ```bash
   ls -1 "outputs/Why it Sucks to Be an Egyptian Concubine/clips" | wc -l
   ```
   Should show 200 clips.

2. **Assemble final video:**
   ```bash
   python3 utils/combine_all.py \
       --clips-dir "outputs/Why it Sucks to Be an Egyptian Concubine/clips" \
       --prompts-file "outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml" \
       -o "outputs/Why it Sucks to Be an Egyptian Concubine/final_video.mp4"
   ```

## Files Reference

- `regenerate_video_prompts.py` - Regenerates video prompts for specific scenes
- `complete_video_workflow.sh` - Complete automated workflow
- `resume_video_generation.sh` - Quick resume script
- `utils/generate_videos.py` - Main video generation script (modified)
- `video_generation_progress.json` - Progress tracking file

## Support

If you encounter issues:
1. Check the progress file for failed scenes
2. Review the prompts.yaml to ensure video prompts look correct
3. Verify Grok2API server is running
4. Check available disk space for video files
