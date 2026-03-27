#!/usr/bin/env python3
"""
Standalone Video Analysis Tool using the SEALCaM Framework.

This is a standalone version of the analysis tool (separate from the pipeline's
utils/analyze_video.py) that can be run independently to analyze any video.

Uses the Gemini API to analyze a video file, uploading it to Gemini,
waiting for processing, then performing a detailed SEALCaM breakdown.

Extracts for each scene:
  - Scene description
  - Subject (main focus)
  - Environment/setting
  - Action (what motion occurs)
  - Lighting style
  - Camera angle/movement
  - Approximate duration
  - Key colors (hex codes)

Also captures music/sound descriptions.
Output: YAML format for easy parsing.

Usage:
    python tools/analyze_video.py input_videos/video.mp4
    python tools/analyze_video.py input_videos/video.mp4 -o analysis.yaml
"""

import argparse
import asyncio
import os
import re
import sys
import json
from pathlib import Path

# Attempt to import gemini_webapi for direct Gemini access
try:
    from gemini_webapi import GeminiClient
    from gemini_webapi.constants import Model
    HAS_GEMINI_WEBAPI = True
except ImportError:
    HAS_GEMINI_WEBAPI = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ---------------------------------------------------------------------------
# SEALCaM Analysis Prompt (Clone-Quality Precision)
# ---------------------------------------------------------------------------

SEALCAM_PROMPT = """\
You are an expert video analyst. Your task is to describe EXACTLY what is visible in this video 
with enough precision that someone could PERFECTLY RECREATE each frame without seeing the original.

Analyze the video content scene-by-scene from the VERY FIRST FRAME to the VERY LAST FRAME.

CRITICAL RULES:
1. Break the video into distinct chronological scenes (e.g., Initial State -> Action -> Result).
   Do NOT summarize the entire video into one scene. Capture EVERY key visual step.
2. Describe ONLY the visual action and environment. Do NOT mention text overlays, subtitles, 
   labels, or UI elements. Pretend they are not there.
3. Your descriptions must be EXACT enough to clone the video. Describe:
   - EXACT colors (not "blue" but "bright cerulean blue" or "deep navy #001f3f")
   - EXACT positions and compositions (left/right/center, foreground/background)
   - EXACT shapes, sizes, and proportions of all objects
   - EXACT textures and materials (smooth, rough, glossy, matte, translucent)
   - EXACT visual perspective and framing

VISUAL MEDIUM DETECTION:
First, determine the overall visual medium/style. Options:
- "3D animation" (CGI, Blender/C4D style, stylized characters, smooth surfaces)
- "2D animation" (flat, cartoon, motion graphics, hand-drawn)
- "realistic" (live-action footage, real photography, documentary)
- "mixed media" (combination of styles)
State this ONCE as the top-level `visual_style` field.

For EACH scene, provide:
- scene_number: Sequential integer (1, 2, 3...)
- timestamp: "MM:SS - MM:SS" range
- duration: Duration (e.g. "3s")
- description: HIGHLY detailed, objective description of what is happening
- subject: The main element or character in focus (describe exact appearance)
- environment: Background/setting with exact colors and details
- action: Specific movement or activity (describe simply and literally)
- lighting: Lighting conditions ONLY (e.g., "bright studio lighting", "warm golden hour")
- camera: Camera perspective and movement
- key_colors: List of 3-5 dominant hex color codes visible in this scene

Global context:
- visual_style: The detected visual medium
- color_palette: Dominant colors and mood description
- rendering_style: Specific rendering details
- audio: Brief audio mood/content description

Return the result as **valid YAML**. Do not output markdown code blocks.
Use this format:

visual_style: "..."
color_palette: "..."
rendering_style: "..."
audio: "..."
scenes:
  - scene_number: 1
    timestamp: "00:00 - 00:04"
    duration: "4s"
    description: "..."
    subject: "..."
    environment: "..."
    action: "..."
    lighting: "..."
    camera: "..."
    key_colors: ["#RRGGBB", "#RRGGBB", "#RRGGBB"]
"""


def extract_yaml_block(text: str) -> str:
    """Extract YAML content from the response, stripping markdown fences if present."""
    fenced = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def format_yaml_output(raw_yaml: str) -> str:
    """Optionally re-format YAML through PyYAML for consistency."""
    if not HAS_YAML:
        return raw_yaml
    try:
        parsed = yaml.safe_load(raw_yaml)
        if parsed is None:
            return raw_yaml
        return yaml.dump(parsed, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception:
        return raw_yaml


async def analyze_with_gemini_webapi(video_path: str) -> str:
    """Analyze video using gemini-webapi (direct Gemini access)."""
    print("  Using gemini-webapi for direct Gemini access...")
    client = GeminiClient()
    await client.init()
    
    chat = client.start_chat(model=Model.G_3_0_FLASH_THINKING)
    
    print("  Uploading video and analyzing (this may take a while)...")
    resp = await chat.send_message(SEALCAM_PROMPT, files=[video_path])
    return resp.text


async def analyze_with_api_proxy(video_path: str, api_base: str, model: str, timeout: int) -> str:
    """Analyze video using AIStudio2API proxy (OpenAI-compatible endpoint)."""
    import base64
    import requests
    
    # Read and encode video
    video_file = Path(video_path)
    mime_types = {
        ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
        ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
    }
    mime = mime_types.get(video_file.suffix.lower(), "video/mp4")
    
    print(f"  Reading video file ({video_file.stat().st_size / 1_048_576:.1f} MB)...")
    with open(video_file, "rb") as f:
        raw = f.read()
    
    encoded = base64.b64encode(raw).decode("ascii")
    data_uri = f"data:{mime};base64,{encoded}"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SEALCAM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": "Analyze this video using the SEALCaM framework. Return valid YAML."},
                ],
            },
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
    }
    
    url = f"{api_base.rstrip('/')}/v1/chat/completions"
    print(f"  Sending request to {url}...")
    
    resp = requests.post(url, json=payload, timeout=timeout, headers={"Content-Type": "application/json"})
    
    if resp.status_code != 200:
        raise Exception(f"API returned status {resp.status_code}: {resp.text[:500]}")
    
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a video file using the SEALCaM framework.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video_path", type=str, help="Path to the video file to analyze")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Path to save YAML output (default: print to stdout)")
    parser.add_argument("--api-base", type=str, 
                        default=os.environ.get("API_BASE_URL", "http://localhost:2048"),
                        help="AIStudio2API base URL (default: http://localhost:2048)")
    parser.add_argument("--model", type=str, default="gemini-3-flash-preview",
                        help="Model for analysis (default: gemini-3-flash-preview)")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Request timeout in seconds (default: 600)")
    parser.add_argument("--use-proxy", action="store_true",
                        help="Force using AIStudio2API proxy instead of gemini-webapi")

    args = parser.parse_args()

    video_path = Path(args.video_path).resolve()
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)

    print("=" * 60)
    print("  Video Analysis Tool — SEALCaM Framework")
    print("=" * 60)
    print(f"  Video   : {video_path.name}")
    print(f"  Size    : {video_path.stat().st_size / 1_048_576:.1f} MB")
    if args.output:
        print(f"  Output  : {args.output}")
    print("-" * 60)

    # Choose analysis method
    if HAS_GEMINI_WEBAPI and not args.use_proxy:
        print("\n[1/2] Analyzing video via gemini-webapi...")
        raw_response = asyncio.run(analyze_with_gemini_webapi(str(video_path)))
    else:
        print("\n[1/2] Analyzing video via API proxy...")
        raw_response = asyncio.run(
            analyze_with_api_proxy(str(video_path), args.api_base, args.model, args.timeout)
        )

    print("\n[2/2] Processing results...")
    yaml_content = extract_yaml_block(raw_response)
    formatted = format_yaml_output(yaml_content)

    print("\n" + "=" * 60)
    print("  ANALYSIS RESULT")
    print("=" * 60 + "\n")
    print(formatted)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(formatted, encoding="utf-8")
        print(f"\n✅ Analysis saved to: {output_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
