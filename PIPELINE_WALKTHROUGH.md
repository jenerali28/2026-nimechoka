# Video Clone Pipeline Walkthrough

This document outlines the architecture and workflow of the **Video Clone Pipeline**, which takes English input videos and automatically recreates them as Spanish-narrated videos with AI-generated visuals.

## 🚀 Pipeline Overview

The pipeline is launched via `bash init_and_run.sh`, which:
1. Kills stale services and clears ports
2. Starts **AIStudio2API** (multi-worker mode on port 2048)
3. Starts **grok2api** (port 8000)
4. Runs `bulk_processor.py` to process all videos in `input_videos/`

Each video goes through **7 sequential steps**:

1.  **Audio Extraction & Transcription** (FFmpeg + Whisper)
2.  **Gemini Multimodal Flow** (Analysis + Style-Matched Prompt Engineering)
3.  **Script Rewriting to Spanish** (DeepSeek V3.1 via NVIDIA NIM)
4.  **Spanish Audio Generation** (Gemini TTS via AIStudio2API)
5.  **Image Generation** (Imagen 4 via imageFX-api)
6.  **Video Generation** (Grok via grok2api)
7.  **Final Assembly** (FFmpeg + Whisper Alignment)

---

## 🛠️ Components & Architecture

### 1. **Entry Point (`init_and_run.sh`)**
   - Starts all services and launches the bulk processor.
   - **Usage**:
     ```bash
     bash init_and_run.sh
     ```

### 2. **Bulk Orchestrator (`bulk_processor.py`)**
   - Discovers all videos in `input_videos/`, processes each through the full pipeline.
   - Tracks progress via `status.json` (resume-safe: skips completed steps).

### 3. **Services (auto-started by init_and_run.sh)**
   - **AIStudio2API** (Port `2048`): Proxies requests to Google AI Studio.
     - Used for: Multimodal Analysis, Script Rewriting, TTS.
   - **grok2api** (Port `8000`): Proxies requests to xAI Grok.
     - Used for: Video Animation (Image-to-Video).
   - **imageFX-api** (CLI): Node.js tool for Imagen generation.
     - Used for: Generating high-quality landscape images.

---

## 📝 Step-by-Step Workflow

### Step 1: Extract & Transcribe
- **Script**: `utils/extract_script.py`
- **Action**: Extracts audio from the input video and uses local **Whisper** model to transcribe it to English text.
- **Output**: `outputs/<video>/english_script.txt`

### Step 2: Gemini Multimodal Flow (Analysis + Prompt Engineering)
- **Script**: `utils/multimodal_orchestrator.py`
- **Model**: **Gemini 3.0 Flash Thinking** (via gemini_webapi)
- **Action**: Two-turn conversation with Gemini:
   - **Turn 1**: Analyzes the video visually scene-by-scene, detecting the visual style (3D animation, 2D, stick figure, motion graphics, photorealistic, etc.), color palette, rendering aesthetic, style subcategory, and animation complexity.
  - **Turn 2**: Generates style-matched image & video prompts + Spanish script segments, enforcing visual consistency.
- **Output**: `outputs/<video>/analysis.yaml`, `outputs/<video>/prompts.yaml`

### Step 3: Rewrite Script to Spanish
- **Script**: `utils/rewrite_script.py`
- **Model**: **DeepSeek V3.1** (via NVIDIA NIM)
- **Action**: Translates and adapts the English script into a Spanish narration script suitable for the video's tone.
- **Output**: `outputs/<video>/spanish_script.txt`

### Step 4: Generate Audio (TTS)
- **Script**: `utils/generate_audio.py`
- **Model**: **Gemini 2.5 Flash TTS** (Voice: `Charon`)
- **Action**: Generates a deep, cinematic Spanish voiceover from the rewritten script.
- **Output**: `outputs/<video>/narration.wav`

### Step 5: Generate Images
- **Script**: `utils/generate_images.py`
- **Tool**: **imageFX-api** (CLI)
- **Model**: **Imagen 4**
- **Action**: Generates a landscape (16:9) image for each scene defined in the prompts.
- **Output**: `outputs/<video>/images/scene_01.png`, etc.

### Step 6: Generate Videos
- **Script**: `utils/generate_videos.py`
- **Model**: **Grok** (grok-imagine-1.0-video via grok2api)
- **Action**: Animates each generated image using the corresponding motion prompt.
- **Output**: `outputs/<video>/clips/clip_01.mp4`, etc.

### Step 7: Final Assembly
- **Script**: `utils/combine_all.py`
- **Tool**: **FFmpeg + Whisper**
- **Action**: Aligns clips to narration timestamps using Whisper, speed-adjusts each clip, then concatenates and overlays the Spanish audio.
- **Output**: `outputs/<video>/<video>_cloned.mp4`

---

## ⚙️ Configuration

### Authentication
- **imageFX Auth**: Stored in `imageFX-api/.auth` (token rotation supported).
- **AIStudio Auth**: Worker profiles in `AIStudio2API/data/workers.json` (auto-configured by `init_and_run.sh`).
- **Grok Auth**: Managed via `grok2api` cookies.

### Resume Support
- Progress is tracked in `status.json`.
- Re-running the pipeline resumes from the last failed step per video.
- Assets are verified on disk before skipping (not just status flags).

---

## 🐛 Troubleshooting

- **502/503 Errors (AIStudio)**: The browser session may be stale. Restart via `init_and_run.sh` which kills and re-initializes everything.
- **Image Generation Failures**: Ensure `imageFX-api` is built (`npm run build`) and the `.auth` token is fresh.
- **Style Mismatch in Output**: The `multimodal_orchestrator.py` enforces style detection. If output images look realistic when source is 3D, check that `analysis.yaml` has `visual_style: "3D animation"`.
- **Unrealistic Video Motions**: Video prompts are constrained to simple camera movements + subtle animations. Complex actions should be avoided.
