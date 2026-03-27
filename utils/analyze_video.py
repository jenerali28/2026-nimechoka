#!/usr/bin/env python3
"""
Video Analysis Tool using the SEALCaM Framework.

Analyzes a video file scene-by-scene via the AIStudio2API proxy,
extracting structured information about Subject, Environment, Action,
Lighting, and Camera for each scene. Outputs YAML.

Usage:
    python analyze_video.py video.mp4
    python analyze_video.py video.mp4 -o analysis.yaml
    python analyze_video.py video.mp4 --model gemini-2.5-pro
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required. Install with: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIME_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".m4v": "video/x-m4v",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
}

SEALCAM_PROMPT = """\
You are an expert video analyst. Your task is to describe EXACTLY what is visible in the video.

Analyze the video content scene-by-scene. Do not hallucinate details that are not present.

CRITICAL: You MUST break the video down into distinct chronological scenes (e.g., Initial State -> Action/Intervention -> Result). Do NOT summarize the entire video into one scene. Capture every key step of the process shown.
CRITICAL: Describe ONLY the visual action and environment. Do NOT mention text overlays, subtitles, labels, or UI elements. Pretend they are not there.

CRITICAL — VISUAL MEDIUM DETECTION:
First, determine the overall visual medium/style of this video. Be as specific as possible. Options:
- "3D animation" (CGI, Blender/C4D style, stylized characters, smooth surfaces)
- "2D animation" (flat, cartoon, motion graphics, hand-drawn)
- "stick figure animation" (simple line-drawn characters, minimal detail, whiteboard style)
- "motion graphics" (geometric shapes, kinetic typography, infographic-style)
- "screen recording" (software UI, desktop capture, tutorial recording)
- "realistic" (live-action footage, real photography, documentary)
- "photorealistic CGI" (CGI that closely mimics real photography)
- "stop motion" (claymation, paper cutout, physical object animation)
- "mixed media" (combination of styles)
State this ONCE as the top-level `visual_style` field.

Also determine:
- `style_subcategory`: A more specific label (e.g. "cel-shaded anime", "Pixar-style CGI", "whiteboard animation", "gopro footage", "drone aerial", "2D explainer", "stick figure explainer")
- `animation_complexity`: One of "simple" (stick figures, basic shapes, flat colors), "moderate" (stylized 3D, clean 2D with shading), or "complex" (photorealistic, high-detail textures, realistic lighting)

Also describe the `color_palette` and `rendering_style`.

For EACH scene, provide the following structured analysis:

- **scene_number**: Sequential integer (1, 2, 3...)
- **timestamp**: Start time (MM:SS)
- **duration**: Duration (e.g. "3s")
- **description**: A detailed, objective description of what is happening.
- **subject**: The main element or character in focus.
- **environment**: The background, setting, or visual context (e.g., "white background", "human skin", "microscopic view").
- **action**: The specific movement or activity occurring. Describe simply and literally.
- **lighting**: Lighting conditions ONLY (e.g., "bright studio lighting", "warm golden hour", "soft diffused light"). Do NOT put the visual medium here.
- **camera**: camera perspective (e.g., "close-up", "cross-section", "macro").

Global context:
- **visual_style**: The detected visual medium (e.g. "3D animation", "stick figure animation", "realistic")
- **style_subcategory**: More specific style label
- **animation_complexity**: "simple", "moderate", or "complex"
- **color_palette**: Dominant colors and mood (e.g. "vibrant blues, clean whites, bright saturated")
- **rendering_style**: Specific rendering details (e.g. "smooth plastic-like surfaces, soft shadows, stylized proportions")
- **audio**: Briefly describe the audio mood/content.

Return the result as **valid YAML**. Do not output markdown code blocks.
Use this format:

visual_style: "..."
style_subcategory: "..."
animation_complexity: "..."
color_palette: "..."
rendering_style: "..."
audio: "..."
scenes:
  - scene_number: 1
    timestamp: "00:00"
    duration: "..."
    description: "..."
    subject: "..."
    environment: "..."
    action: "..."
    lighting: "..."
    camera: "..."
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_mime_type(path: Path) -> str:
    """Determine MIME type from file extension."""
    ext = path.suffix.lower()
    mime = MIME_TYPES.get(ext)
    if not mime:
        supported = ", ".join(MIME_TYPES.keys())
        print(f"Error: Unsupported video format '{ext}'. Supported: {supported}")
        sys.exit(1)
    return mime


def read_and_encode_video(path: Path) -> tuple:
    """Read a video file and return (base64_string, mime_type, file_size_bytes)."""
    mime = get_mime_type(path)
    size = path.stat().st_size
    print(f"  Reading video file ({size / 1_048_576:.1f} MB)...")

    with open(path, "rb") as f:
        raw = f.read()

    print("  Encoding video to base64...")
    encoded = base64.b64encode(raw).decode("ascii")
    return encoded, mime, size


def build_request_payload(
    encoded_video: str,
    mime_type: str,
    model: str,
) -> dict:
    """Build the OpenAI-compatible chat completion request payload."""
    data_uri = f"data:{mime_type};base64,{encoded_video}"

    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": SEALCAM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Analyze this video using the SEALCaM framework as instructed. "
                            "Return the full analysis as valid YAML."
                        ),
                    },
                ],
            },
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
    }


def extract_yaml_block(text: str) -> str:
    """Extract YAML content from the response, stripping markdown fences if present."""
    # Strip ```yaml ... ``` fences
    fenced = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def send_analysis_request(
    payload: dict,
    api_base: str,
    timeout: int,
) -> str:
    """Send the analysis request to the API and return the response text."""
    url = f"{api_base.rstrip('/')}/v1/chat/completions"
    print(f"  Sending request to {url}...")
    print(f"  Model: {payload['model']}")
    print("  Waiting for analysis (this may take a while for long videos)...")

    start = time.time()

    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
    except requests.exceptions.ConnectionError:
        print(
            f"\nError: Could not connect to API at {api_base}."
            "\nMake sure AIStudio2API is running (python -m src.app_launcher)."
        )
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(
            f"\nError: Request timed out after {timeout}s."
            "\nTry increasing --timeout for longer videos."
        )
        sys.exit(1)

    elapsed = time.time() - start
    print(f"  Response received in {elapsed:.1f}s")

    if resp.status_code != 200:
        print(f"\nError: API returned status {resp.status_code}")
        try:
            detail = resp.json().get("detail", resp.text[:500])
        except Exception:
            detail = resp.text[:500]
        print(f"  Detail: {detail}")
        sys.exit(1)

    data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        print("\nError: Unexpected response structure from API.")
        print(f"  Response: {json.dumps(data, indent=2)[:1000]}")
        sys.exit(1)

    return content


def format_yaml_output(raw_yaml: str) -> str:
    """Optionally re-format YAML through PyYAML for consistency."""
    try:
        import yaml

        parsed = yaml.safe_load(raw_yaml)
        if parsed is None:
            return raw_yaml
        return yaml.dump(parsed, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except ImportError:
        # PyYAML not installed — return raw model output
        return raw_yaml
    except Exception:
        # YAML parsing failed — return raw model output
        return raw_yaml


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a video file using the SEALCaM framework via AIStudio2API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python analyze_video.py clip.mp4\n"
            "  python analyze_video.py clip.mp4 -o analysis.yaml\n"
            "  python analyze_video.py clip.mp4 --model gemini-2.5-pro --api-base http://localhost:2048\n"
        ),
    )
    parser.add_argument(
        "video_path",
        type=str,
        help="Path to the video file to analyze",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Path to save the YAML analysis output (default: print to stdout)",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default=os.environ.get("API_BASE_URL", "http://localhost:2048"),
        help="AIStudio2API base URL (default: $API_BASE_URL or http://localhost:2048)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-3-flash-preview",
        help="Model to use for analysis (default: gemini-3-flash-preview)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Request timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Only analyze the first 60s of long videos (>90s). Short videos are unaffected.",
    )

    args = parser.parse_args()

    # -- Validate input --
    video_path = Path(args.video_path).resolve()
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    if not video_path.is_file():
        print(f"Error: Not a file: {video_path}")
        sys.exit(1)

    # -- Banner --
    print("=" * 60)
    print("  Video Analysis Tool — SEALCaM Framework")
    print("=" * 60)
    print(f"  Video   : {video_path.name}")
    print(f"  Model   : {args.model}")
    print(f"  API     : {args.api_base}")
    if args.output:
        print(f"  Output  : {args.output}")
    print("-" * 60)

    # -- Step 0.5: Optional preview trim --
    actual_video_path = video_path
    if args.preview:
        try:
            from utils.trim_preview import trim_preview
            preview_path, total_dur, was_trimmed = trim_preview(str(video_path))
            if was_trimmed:
                actual_video_path = Path(preview_path)
                print(f"  🎬 Using preview clip (first 60s of {total_dur:.0f}s video)")
        except ImportError:
            print("  ⚠ trim_preview not available, analyzing full video")

    # -- Step 1: Read & encode --
    print("\n[1/4] Preparing video...")
    encoded, mime, size = read_and_encode_video(actual_video_path)
    print(f"  Video format: {mime}")
    print(f"  Encoded payload size: {len(encoded) / 1_048_576:.1f} MB")

    # -- Step 2: Build request --
    print("\n[2/4] Building analysis request...")
    payload = build_request_payload(encoded, mime, args.model)
    print("  SEALCaM prompt attached")
    print(f"  Temperature: {payload['temperature']}")

    # -- Step 3: Send & receive --
    print("\n[3/4] Analyzing video...")
    raw_response = send_analysis_request(payload, args.api_base, args.timeout)

    # -- Step 4: Process output --
    print("\n[4/4] Processing results...")
    yaml_content = extract_yaml_block(raw_response)
    formatted = format_yaml_output(yaml_content)

    # Print result
    print("\n" + "=" * 60)
    print("  ANALYSIS RESULT")
    print("=" * 60 + "\n")
    print(formatted)

    # Optionally save
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(formatted, encoding="utf-8")
        print(f"\n✅ Analysis saved to: {output_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
