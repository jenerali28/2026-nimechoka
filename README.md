# 🤖 YT Video Cloner with Grok API

Automated pipeline to clone English YouTube videos into high-quality Spanish versions with AI-generated visuals. Supports horizontal (landscape) format with automatic visual style detection (2D animation, 3D render, stick figures, photorealistic, etc.).

## 🚀 Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize Services**:
   This single command kills stale processes, starts all required API workers (AIStudio & Grok), and begins processing.
   ```bash
   bash init_and_run.sh
   ```

3. **Add Videos**:
   Drop your `.mp4` files into the `input_videos/` folder.
   
4. **Download Videos**:
   ```bash
   python utils/download_shorts.py [YOUTUBE_URL] --limit 5
   ```

## 📂 Project Structure

- `main.py`: The central orchestrator.
- `bulk_processor.py`: Handles batch processing of multiple videos.
- `utils/`: Core logic for transcription, translation, image/video generation, and assembly.
- `outputs/`: Where all intermediate assets (scripts, images, clips) are stored.
- `final_clones/`: Where the finished Spanish videos are saved.

## 📄 Documentation

For detailed information, please refer to:
- [**Usage Guide**](USAGE_GUIDE.md): Advanced features, bulk downloading, and worker setup.
- [**Pipeline Walkthrough**](PIPELINE_WALKTHROUGH.md): Step-by-step breakdown of how the AI processes your videos.

## 🛠️ Features

- **Multimodal Analysis**: Uses Gemini to detect visual styles (3D, 2D, stick figures, photorealistic, etc.) and generate exact prompts.
- **Auto Style Detection**: Automatically classifies video style, complexity, and rendering approach to adapt prompts.
- **Imagen 4 Integration**: High-quality 16:9 landscape image generation via `imageFX-api`.
- **Grok Video Animation**: Smooth image-to-video animation for every scene.
- **Whisper Alignment**: Perfect audio-visual sync using subtitle-level timestamping.
- **Resumable**: Tracks progress in `status.json` so you never lose work.
# 2026-nimechoka
