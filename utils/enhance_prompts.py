#!/usr/bin/env python3
"""
Prompt Enhancement Module for Cinematic Story Flow.

Each AI video generation request is stateless — the model has no memory of
previous clips. Therefore every prompt must be fully self-contained with:
  - Complete visual style anchor
  - Full environment / location description
  - Complete character appearance for every character in the scene
  - Scene action and emotional tone
  - NO transitional language ("continuing from", "scene shifts to", etc.)

This module rewrites prompts so they stand alone as complete visual briefs.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from utils.story_context import track_story_context


# Tone → camera/lighting style mapping
TONE_VISUAL_STYLE: Dict[str, str] = {
    'tense':    'tight framing, dark shadows, low-key lighting',
    'dramatic': 'high contrast lighting, dynamic angle',
    'action':   'dynamic framing, sharp angles, motion blur lines',
    'calm':     'wide shot, warm soft lighting, balanced composition',
    'neutral':  'balanced framing, even lighting',
}


def read_prompts_yaml(prompts_path: str) -> Dict:
    try:
        path = Path(prompts_path)
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if data else {}
    except Exception as e:
        print(f"Warning: Failed to read prompts file: {e}")
        return {}


def write_prompts_yaml(prompts_path: str, data: Dict) -> bool:
    try:
        path = Path(prompts_path)
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True,
                      default_flow_style=False, width=10000)
        return True
    except Exception as e:
        print(f"Error: Failed to write prompts file: {e}")
        return False


def extract_character_anchors(prompts_data: Dict) -> Dict[str, str]:
    """Return {character_name: appearance_anchor} from character_profile."""
    anchors: Dict[str, str] = {}
    char_profile = prompts_data.get('character_profile', {})
    for char in char_profile.get('characters', []):
        name = char.get('name', '').strip()
        anchor = char.get('appearance_anchor', '').strip()
        if name and anchor:
            anchors[name] = anchor
    return anchors


def get_style_anchor(prompts_data: Dict) -> str:
    """Return the global style_anchor string from prompts.yaml."""
    return prompts_data.get('style_anchor', '').strip()


def ensure_character_anchors_in_prompt(
    prompt: str,
    characters_in_scene: List[str],
    character_anchors: Dict[str, str],
) -> str:
    """
    For every character in the scene, make sure their full appearance anchor
    appears in the prompt.  If the character name is already present, replace
    the bare name with "Name (anchor)".  If the name is absent, append a
    character description line at the end.
    """
    for name in characters_in_scene:
        anchor = character_anchors.get(name, '')
        if not anchor:
            continue

        full_desc = f"{name} ({anchor})"

        # Already has the anchor inline — skip
        if anchor in prompt:
            continue

        if name in prompt:
            # Replace first bare occurrence with full description
            prompt = prompt.replace(name, full_desc, 1)
        else:
            # Character not mentioned at all — append
            prompt = prompt.rstrip('. ') + f". {full_desc} is present in this scene."

    return prompt


def ensure_location_in_prompt(prompt: str, location: str) -> str:
    """
    Make sure the location is explicitly stated in the prompt.
    If it's already there (case-insensitive), do nothing.
    Otherwise prepend a short location clause.
    """
    if not location or location in ('unknown location', 'unknown', ''):
        return prompt

    if location.lower() in prompt.lower():
        return prompt

    # Map raw extracted location tokens to readable descriptions
    location_labels: Dict[str, str] = {
        'siria': 'ancient Syria',
        'syria': 'ancient Syria',
        'egipto': 'ancient Egypt',
        'egypt': 'ancient Egypt',
        'menfis': 'Memphis, Egypt',
        'memphis': 'Memphis, Egypt',
        'mediterráneo': 'the Mediterranean Sea',
        'mediterranean': 'the Mediterranean Sea',
        'barco': 'a wooden ship at sea',
        'ship': 'a wooden ship at sea',
        'boat': 'a wooden boat',
        'calle': 'a dusty street',
        'street': 'a dusty street',
        'harén': 'the royal harem',
        'harem': 'the royal harem',
        'palacio': 'the royal palace',
        'palace': 'the royal palace',
        'habitación': 'a palace chamber',
        'room': 'a palace chamber',
        'cuarto': 'a private room',
        'chamber': 'a stone chamber',
        'courtyard': 'a palace courtyard',
        'patio': 'an open courtyard',
        'ciudad': 'the city of Memphis',
        'city': 'the city',
        'desierto': 'the desert',
        'desert': 'the desert',
        'templo': 'an Egyptian temple',
        'temple': 'an Egyptian temple',
        'festival': 'the Opet Festival street',
        'casa': 'a mud-brick house',
        'house': 'a mud-brick house',
        'home': 'a simple home',
    }

    label = location_labels.get(location.lower(), location)
    return f"Setting: {label}. {prompt}"


def ensure_tone_style_in_prompt(prompt: str, tone: str) -> str:
    """
    Append a camera/lighting style note if the tone is non-neutral and
    the prompt doesn't already contain lighting/camera keywords.
    """
    if tone in ('neutral', ''):
        return prompt

    style = TONE_VISUAL_STYLE.get(tone, '')
    if not style:
        return prompt

    # Don't duplicate if already present
    if any(kw in prompt.lower() for kw in ['lighting', 'framing', 'camera', 'shadow']):
        return prompt

    return prompt.rstrip('. ') + f". Visual style: {style}."


def truncate_prompt(prompt: str, max_length: int = 950) -> str:
    """Truncate to max_length, cutting at a sentence boundary where possible."""
    if len(prompt) <= max_length:
        return prompt

    truncated = prompt[:max_length - 3]
    last_period = truncated.rfind('. ')
    last_comma = truncated.rfind(', ')

    if last_period > max_length * 0.7:
        truncated = truncated[:last_period + 1]
    elif last_comma > max_length * 0.8:
        truncated = truncated[:last_comma + 1]

    return truncated + '...' if len(truncated) < len(prompt) else truncated


def enhance_single_prompt(
    original_prompt: str,
    scene_context: Dict,
    character_anchors: Dict[str, str],
) -> str:
    """
    Make a single prompt fully self-contained.

    Strategy (each step is additive, never removes existing content):
    1. Ensure every character in the scene has their full appearance anchor
       stated explicitly in the prompt.
    2. Ensure the location is stated explicitly.
    3. Append a camera/lighting style note matching the scene's emotional tone.
    4. Truncate to 950 chars if needed.

    No "Continuing from", no "Scene shifts to" — the prompt must read as a
    complete, standalone visual brief.
    """
    prompt = original_prompt

    # 1. Character anchors
    characters_in_scene = scene_context.get('characters', [])
    if characters_in_scene and character_anchors:
        prompt = ensure_character_anchors_in_prompt(
            prompt, characters_in_scene, character_anchors
        )

    # 2. Location
    location = scene_context.get('location', '')
    prompt = ensure_location_in_prompt(prompt, location)

    # 3. Tone / visual style
    tone = scene_context.get('tone', 'neutral')
    prompt = ensure_tone_style_in_prompt(prompt, tone)

    # 4. Truncate
    prompt = truncate_prompt(prompt, max_length=950)

    return prompt


def enhance_prompts(
    prompts_path: str,
    script_path: str,
    output_path: Optional[str] = None,
) -> bool:
    """
    Main entry point.  Reads prompts.yaml + script, enriches every scene
    prompt to be fully self-contained, writes result back.

    Args:
        prompts_path: Path to prompts.yaml (source of truth)
        script_path:  Path to script file used to derive per-scene context
        output_path:  Optional separate output path (defaults to prompts_path)
    """
    # 1. Read prompts
    prompts_data = read_prompts_yaml(prompts_path)
    if not prompts_data:
        print("Error: Could not read prompts file")
        return False

    scenes = prompts_data.get('scenes', [])
    if not scenes:
        print("Warning: No scenes found in prompts file")
        return False

    num_scenes = len(scenes)
    print(f"\n📝 Enriching {num_scenes} scene prompts (self-contained mode)...")

    # 2. Character anchors
    character_anchors = extract_character_anchors(prompts_data)
    if character_anchors:
        print(f"  ✓ Characters: {list(character_anchors.keys())}")

    # 3. Per-scene story context (location, tone, characters present)
    character_names = list(character_anchors.keys())
    story_contexts = track_story_context(script_path, num_scenes, character_names)

    if not story_contexts:
        print("Warning: Could not extract story context — using empty contexts")
        story_contexts = [
            {
                'scene_number': i + 1,
                'location': 'unknown',
                'characters': character_names[:1],
                'action': 'scene continues',
                'tone': 'neutral',
            }
            for i in range(num_scenes)
        ]

    # 4. Enrich each scene
    for i, scene in enumerate(scenes):
        scene_context = story_contexts[i] if i < len(story_contexts) else {}

        for field in ('image_prompt', 'video_prompt'):
            raw = scene.get(field, '')
            if isinstance(raw, dict):
                raw = raw.get('prompt', '')
            if raw:
                scene[field] = enhance_single_prompt(raw, scene_context, character_anchors)

        if (i + 1) % 20 == 0:
            print(f"  ✓ {i + 1}/{num_scenes} scenes processed...")

    print(f"  ✓ All {num_scenes} scenes enriched")

    # 5. Write
    output_file = output_path or prompts_path
    success = write_prompts_yaml(output_file, prompts_data)
    if success:
        print(f"  ✓ Written to {output_file}")
    return success


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python enhance_prompts.py <prompts.yaml> <script.txt> [output.yaml]")
        sys.exit(1)

    success = enhance_prompts(sys.argv[1], sys.argv[2],
                              sys.argv[3] if len(sys.argv) > 3 else None)
    sys.exit(0 if success else 1)
