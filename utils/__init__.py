# Video Clone Pipeline — Utility Scripts
#
# Pipeline modules (called by bulk_processor.py):
#   extract_script.py          — FFmpeg audio extraction + Whisper transcription
#   multimodal_orchestrator.py — Gemini multimodal analysis + style-matched prompt engineering
#   extract_keyframes.py       — Extract reference keyframes from original video
#   rewrite_script.py          — English → Spanish script rewriting
#   generate_audio.py          — Spanish TTS narration (AIStudio2API)
#   generate_images.py         — Scene image generation (Imagen 4)
#   generate_videos.py         — Video clip generation (grok2api)
#   combine_all.py             — FFmpeg concat + audio overlay
#   caption_video.py           — Whisper-based word-by-word captions
