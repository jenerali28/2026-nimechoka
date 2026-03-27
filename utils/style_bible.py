#!/usr/bin/env python3
"""
Style & Character Bible Generator.

Extracts visual style and recurring character information from analysis.yaml
and generates persistent "bibles" that ensure visual consistency across
all generated images and video clips.

Usage:
    python style_bible.py analysis.yaml -o outputs/
    python style_bible.py analysis.yaml -o outputs/ --api-base http://localhost:2048
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: 'pyyaml' required. Install with: pip install pyyaml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NVIDIA_API_KEY = "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"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "deepseek-ai/deepseek-v3.1"


# ---------------------------------------------------------------------------
# Style Bible
# ---------------------------------------------------------------------------

def generate_style_bible(analysis_data: dict) -> dict:
    """Extract and structure style information from analysis data.

    Creates a comprehensive style bible that can be prepended to all
    image and video prompts for visual consistency.
    """
    style_bible = {
        "visual_style": analysis_data.get("visual_style", "unknown"),
        "style_subcategory": analysis_data.get("style_subcategory", "unknown"),
        "animation_complexity": analysis_data.get("animation_complexity", "moderate"),
        "color_palette": analysis_data.get("color_palette", "vibrant colors"),
        "rendering_style": analysis_data.get("rendering_style", "smooth surfaces, soft shadows"),
        "audio_mood": analysis_data.get("audio", ""),
    }

    # Extract key colors from scenes if available
    scenes = analysis_data.get("scenes", [])
    all_key_colors = []
    all_lighting = set()
    all_environments = set()

    for scene in scenes:
        # Collect key colors
        key_colors = scene.get("key_colors", [])
        if isinstance(key_colors, list):
            all_key_colors.extend(key_colors)

        # Collect lighting styles
        lighting = scene.get("lighting", "")
        if lighting:
            all_lighting.add(lighting)

        # Collect environment types
        env = scene.get("environment", "")
        if env:
            all_environments.add(env)

    # Deduplicate colors while preserving order
    seen_colors = set()
    unique_colors = []
    for c in all_key_colors:
        if c not in seen_colors:
            seen_colors.add(c)
            unique_colors.append(c)

    style_bible["key_colors"] = unique_colors[:10]  # top 10 colors
    style_bible["lighting_styles"] = sorted(all_lighting)[:5]
    style_bible["common_environments"] = sorted(all_environments)[:5]

    # Build the prompt prefix for image generation
    style_prefix = (
        f"{style_bible['visual_style']}, {style_bible['style_subcategory']}. "
        f"Color palette: {style_bible['color_palette']}. "
        f"Rendering: {style_bible['rendering_style']}."
    )
    style_bible["prompt_prefix"] = style_prefix

    # Build negative prompt based on style
    style_lower = style_bible["visual_style"].lower()
    if any(kw in style_lower for kw in ["3d", "cgi", "animation", "animated", "cartoon"]):
        style_bible["negative_prompt"] = (
            "photorealistic, live-action, photograph, DSLR, real skin texture, "
            "watermark, text, subtitle, blurry, low quality, text overlay"
        )
    elif any(kw in style_lower for kw in ["realistic", "live-action", "photo"]):
        style_bible["negative_prompt"] = (
            "3D render, cartoon, anime, CGI, plastic texture, "
            "watermark, text, subtitle, blurry, low quality, text overlay"
        )
    else:
        style_bible["negative_prompt"] = (
            "watermark, text, subtitle, blurry, low quality, text overlay, "
            "inconsistent style, mixed media"
        )

    return style_bible


# ---------------------------------------------------------------------------
# Character Bible
# ---------------------------------------------------------------------------

def extract_characters_from_analysis(analysis_data: dict) -> list[dict]:
    """Identify recurring characters/subjects from scene descriptions.

    Scans all scene descriptions for recurring subjects and builds
    a character bible entry for each.
    """
    scenes = analysis_data.get("scenes", [])
    if not scenes:
        return []

    # Collect all subjects
    subject_mentions = {}
    for scene in scenes:
        subject = scene.get("subject", "")
        if not subject:
            continue

        # Normalize subject name (lowercase, strip articles)
        key = _normalize_subject(subject)
        if key not in subject_mentions:
            subject_mentions[key] = {
                "raw_descriptions": [],
                "scene_numbers": [],
                "count": 0,
            }
        subject_mentions[key]["raw_descriptions"].append(subject)
        subject_mentions[key]["scene_numbers"].append(scene.get("scene_number", 0))
        subject_mentions[key]["count"] += 1

    # Only keep subjects that appear in 2+ scenes (recurring)
    recurring = {k: v for k, v in subject_mentions.items() if v["count"] >= 2}

    if not recurring:
        # If nothing recurring, at least capture the most common subject
        if subject_mentions:
            top = max(subject_mentions.items(), key=lambda x: x[1]["count"])
            recurring = {top[0]: top[1]}
        else:
            return []

    # Build character entries
    characters = []
    for name, data in recurring.items():
        # Use the longest description as the canonical one
        best_desc = max(data["raw_descriptions"], key=len)

        characters.append({
            "name": name,
            "canonical_description": best_desc,
            "appearances": data["scene_numbers"],
            "frequency": data["count"],
            "consistency_note": (
                f"This character/subject appears in {data['count']} scenes. "
                f"Maintain consistent visual appearance across all scenes."
            ),
        })

    # Sort by frequency (most common first)
    characters.sort(key=lambda x: x["frequency"], reverse=True)

    return characters


def _normalize_subject(subject: str) -> str:
    """Normalize a subject name for matching."""
    s = subject.lower().strip()
    # Remove common articles
    for article in ["a ", "an ", "the ", "un ", "una ", "el ", "la ", "los ", "las "]:
        if s.startswith(article):
            s = s[len(article):]
    # Take first 50 chars and strip trailing whitespace
    return s[:50].strip()


def generate_character_bible(analysis_data: dict) -> dict:
    """Generate a character bible from analysis data.

    Returns a dict with character entries and consistency instructions.
    """
    characters = extract_characters_from_analysis(analysis_data)

    bible = {
        "characters": characters,
        "total_characters": len(characters),
        "consistency_rules": [
            "Every character must maintain the EXACT same visual appearance across all scenes.",
            "Character proportions, colors, and distinctive features must remain constant.",
            "Clothing and accessories should stay the same unless the scene explicitly changes them.",
            "Facial features, body type, and skin tone must be identical in every frame.",
        ],
    }

    # Build a prompt suffix for character consistency
    if characters:
        char_notes = []
        for c in characters[:3]:  # Top 3 characters
            char_notes.append(f"- {c['name']}: {c['canonical_description']}")
        bible["prompt_suffix"] = (
            "CHARACTER CONSISTENCY: " + "; ".join(
                f"{c['name']} must look exactly as: {c['canonical_description']}"
                for c in characters[:3]
            )
        )
    else:
        bible["prompt_suffix"] = ""

    return bible


# ---------------------------------------------------------------------------
# AI-Enhanced Character Extraction (Optional)
# ---------------------------------------------------------------------------

def enhance_character_bible_with_ai(analysis_data: dict, characters: list[dict]) -> list[dict]:
    """Use AI to generate richer character descriptions from analysis context.

    This is optional and requires the NVIDIA NIM API. Falls back gracefully.
    """
    if not characters:
        return characters

    try:
        from openai import OpenAI
        client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    except ImportError:
        print("  ⚠ openai package not available, skipping AI character enhancement")
        return characters

    scenes = analysis_data.get("scenes", [])
    scene_text = "\n".join(
        f"Scene {s.get('scene_number', '?')}: "
        f"Subject: {s.get('subject', 'N/A')} | "
        f"Description: {s.get('description', 'N/A')}"
        for s in scenes[:20]  # limit to first 20 scenes
    )

    char_names = [c["name"] for c in characters]

    prompt = f"""\
Analyze these scene descriptions and create detailed visual character profiles.

SCENE DATA:
{scene_text}

CHARACTERS TO DESCRIBE: {', '.join(char_names)}

For each character, provide a detailed, consistent visual description including:
- Physical appearance (body type, proportions, distinctive features)
- Color scheme (exact colors of skin, hair, clothing, accessories)
- Art style characteristics (how they fit the visual style)

Output as JSON:
{{
  "characters": [
    {{
      "name": "...",
      "visual_profile": "Complete visual description for image generation prompts"
    }}
  ]
}}
Return ONLY the JSON, no other text."""

    try:
        print("  ✨ Enhancing character bible with AI...")
        completion = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": "You are a visual character design expert. Provide precise, prompt-ready character descriptions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        result = completion.choices[0].message.content.strip()

        # Parse JSON
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        data = json.loads(result)
        ai_chars = data.get("characters", [])

        # Merge AI descriptions back into character entries
        ai_lookup = {c["name"].lower(): c for c in ai_chars}
        for char in characters:
            ai_match = ai_lookup.get(char["name"].lower(), {})
            if "visual_profile" in ai_match:
                char["visual_profile"] = ai_match["visual_profile"]
                print(f"    ✓ Enhanced: {char['name']}")

        return characters

    except Exception as e:
        print(f"  ⚠ AI enhancement failed (non-fatal): {e}")
        return characters


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Style & Character Bibles from analysis.")
    parser.add_argument("analysis_file", help="Path to analysis.yaml")
    parser.add_argument("-o", "--output-dir", default="outputs", help="Output directory")
    parser.add_argument("--enhance", action="store_true", help="Use AI to enhance character descriptions")

    args = parser.parse_args()

    analysis_path = Path(args.analysis_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not analysis_path.exists():
        print(f"Error: Analysis file not found: {analysis_path}")
        sys.exit(1)

    print("=" * 60)
    print("  Style & Character Bible Generator")
    print("=" * 60)

    # Load analysis
    analysis_data = yaml.safe_load(analysis_path.read_text(encoding="utf-8"))
    if not analysis_data:
        print("Error: Could not parse analysis file.")
        sys.exit(1)

    # Generate Style Bible
    print("\n[1/2] Generating Style Bible...")
    style_bible = generate_style_bible(analysis_data)
    style_path = output_dir / "style_bible.yaml"
    with open(style_path, "w", encoding="utf-8") as f:
        yaml.dump(style_bible, f, sort_keys=False, allow_unicode=True)
    print(f"  ✓ Style Bible saved: {style_path}")
    print(f"    Visual style:  {style_bible['visual_style']}")
    print(f"    Subcategory:   {style_bible['style_subcategory']}")
    print(f"    Prompt prefix: {style_bible['prompt_prefix'][:80]}...")

    # Generate Character Bible
    print("\n[2/2] Generating Character Bible...")
    char_bible = generate_character_bible(analysis_data)

    if args.enhance and char_bible["characters"]:
        char_bible["characters"] = enhance_character_bible_with_ai(
            analysis_data, char_bible["characters"]
        )

    char_path = output_dir / "character_bible.yaml"
    with open(char_path, "w", encoding="utf-8") as f:
        yaml.dump(char_bible, f, sort_keys=False, allow_unicode=True)
    print(f"  ✓ Character Bible saved: {char_path}")
    print(f"    Characters found: {char_bible['total_characters']}")
    for c in char_bible["characters"][:5]:
        print(f"      - {c['name']} ({c['frequency']} appearances)")

    print(f"\n✅ Bibles generated in: {output_dir}")


if __name__ == "__main__":
    main()
