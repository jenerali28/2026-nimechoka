#!/usr/bin/env python3
"""
Visual Prompt Generator — Photorealistic Biblical-Era Scene Prompts.

Splits a Swahili narration script into segments and generates
image + video prompts for each, targeting realistic biblical-era visuals.

Uses Gemini WebUI (G_3_0_PRO) in batches of 8.
Includes a self-review pass for visual consistency.
"""

import asyncio
import argparse
import json
import math
import re
import sys
import time
import yaml
from pathlib import Path

from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BATCH_SIZE = 8
MAX_RETRIES = 3

# Fixed visual style — no source video to analyze
VISUAL_STYLE = "Photorealistic, cinematic biblical-era scene"
STYLE_SUB = "Epic historical drama cinematography, Middle Eastern ancient setting"
COLOR_PALETTE = "Warm earthy tones, golden sunlight, deep desert ochres, dusty sandstone, olive greens, deep blue sky"
RENDERING = "Natural film grain, dramatic chiaroscuro lighting, 35mm cinematic lens, shallow depth of field"

NEGATIVE_PROMPT = (
    "cartoon, anime, CGI, 3D render, plastic texture, "
    "modern clothing, contemporary objects, digital art, illustration, "
    "watermark, text, subtitle, blurry, low quality, oversaturated, "
    "fantasy lighting, neon colors, UI elements"
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

BATCH_PROMPT = """\
You are an expert Prompt Engineer for AI image and video generation.
I'll give you a set of SCRIPT SEGMENTS from a Swahili Bible narration.
For each segment, generate prompts for PHOTOREALISTIC BIBLICAL-ERA visuals.

VISUAL STYLE CONTEXT:
- Style: {visual_style}
- Sub-style: {style_sub}
- Color palette: {color_palette}
- Rendering: {rendering}
- Setting: Ancient Middle East / biblical era (roughly 2000 BC - 30 AD depending on story)
- People: Middle Eastern / North-East African appearance, period-accurate clothing
  (robes, tunics, sandals, head coverings, leather belts)
- Environments: Desert landscapes, stone buildings, olive groves, dusty roads,
  ancient cities, temples, rivers, mountains, caves

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

For EACH segment, generate:

**Image Prompt** (MUST be in English):
- Start with: "Photorealistic cinematic biblical-era scene."
- Describe the exact moment from the narration
- Include: specific character appearances (age, expression, clothing, posture)
- Include: environment (architecture, landscape, weather, time of day)
- Include: lighting (golden hour, harsh midday, torchlight, moonlight)
- Include: camera angle (wide establishing shot, close-up, over-shoulder, low angle)
- End with: "35mm film, natural lighting, historically accurate, cinematic composition."

**Video Prompt** (MUST include timestamped choreography, in English):
Break 6 seconds into timed action beats:
  "[0.0s-2.5s] Description of what happens..."
  "[2.5s-4.5s] Description of next action..."
  "[4.5s-6.0s] Description of final moment..."

Rules for action beats:
- COVER THE FULL 6 SECONDS
- Keep movements SLOW and DELIBERATE
- One specific action per beat
- Include camera movement in at least one beat
- Prefer: gazing, walking slowly, turning head, gesturing, kneeling, rising
- AVOID: fast action, fighting close-ups, running (these create artifacts)

OUTPUT: A single valid JSON object:
{{
  "scenes": [
    {{
      "scene_number": {start_num},
      "swahili_script": "(the script segment text)",
      "image_prompt": {{
         "prompt": "(full image prompt in English)",
         "negative_prompt": "{negative_prompt}",
         "aspect_ratio": "16:9"
      }},
      "video_prompt": {{
         "prompt": "(scene setup + timestamped beats + quality tag)",
         "duration": "6s",
         "camera_motion": "(primary camera movement)"
      }}
    }}
  ]
}}

Generate EXACTLY {batch_size} scenes. Return ONLY the JSON, no other text.
"""

REVIEW_PROMPT = """\
Review these visual prompts for a Bible story video.
Check for VISUAL CONSISTENCY — characters should be described the same way
throughout, settings should be geographically consistent, lighting should be
coherent within the same time of day.

SCENES:
{scenes_yaml}

Check:
1. Are characters described consistently? (same age, clothing, features across scenes)
2. Is the setting consistent where it should be?
3. Do lighting/time-of-day references make sense chronologically?
4. Are any prompts too vague or too modern-looking?

If you find inconsistencies, output a JSON object with the fixes:
{{
  "fixes": [
    {{
      "scene_number": N,
      "field": "image_prompt" or "video_prompt",
      "issue": "description of the problem",
      "fixed_prompt": "the corrected prompt text"
    }}
  ]
}}

If everything is consistent, output: {{"fixes": []}}
Return ONLY the JSON.
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

client = GeminiClient()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_block(text: str) -> str:
    """Extract JSON from markdown fences if present."""
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def split_script_into_segments(script_text: str, num_segments: int) -> list[str]:
    """Split script into N roughly equal segments by sentence boundaries."""
    # Split into sentences
    sentences = re.split(r'(?<=[.!?…])\s+', script_text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) == 0:
        return [script_text] * num_segments

    if len(sentences) <= num_segments:
        # Fewer sentences than segments — pad
        segments = sentences[:]
        while len(segments) < num_segments:
            segments.append(segments[-1])
        return segments

    # Distribute sentences across segments
    segments = []
    per_segment = len(sentences) / num_segments
    for i in range(num_segments):
        start = int(i * per_segment)
        end = int((i + 1) * per_segment)
        if i == num_segments - 1:
            end = len(sentences)
        chunk = " ".join(sentences[start:end])
        segments.append(chunk)

    return segments


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

async def generate_visual_prompts(script_text: str, clip_count: int) -> dict:
    """Generate image + video prompts for all clips.

    Returns a dict with 'scenes' list ready for YAML output.
    """
    await client.init(timeout=300, watchdog_timeout=120)

    segments = split_script_into_segments(script_text, clip_count)
    num_batches = math.ceil(clip_count / BATCH_SIZE)

    print(f"\n{'='*60}")
    print(f"  🎨 Visual Prompt Generator — Biblical Era")
    print(f"{'='*60}")
    print(f"  Clip count: {clip_count}")
    print(f"  Batches: {num_batches} × {BATCH_SIZE}")
    print(f"  Style: {VISUAL_STYLE}")

    all_scenes = []

    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, clip_count)
        batch_segments = segments[start_i:end_i]
        batch_size = len(batch_segments)
        start_num = start_i + 1
        end_num = end_i

        # Format segments
        segments_text = ""
        for j, seg in enumerate(batch_segments):
            scene_num = start_i + j + 1
            segments_text += f"\n--- SEGMENT {scene_num} ---\n{seg}\n"

        prompt = BATCH_PROMPT.format(
            visual_style=VISUAL_STYLE,
            style_sub=STYLE_SUB,
            color_palette=COLOR_PALETTE,
            rendering=RENDERING,
            negative_prompt=NEGATIVE_PROMPT,
            start_num=start_num,
            end_num=end_num,
            segments_text=segments_text,
            batch_size=batch_size,
        )

        print(f"\n  Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

        batch_done = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                chat = client.start_chat(model=Model.G_3_0_PRO)
                resp = await chat.send_message(prompt)
                json_text = _parse_json_block(resp.text)
                batch_data = json.loads(json_text)
                batch_scenes = batch_data.get("scenes", [])

                if batch_scenes:
                    all_scenes.extend(batch_scenes)
                    print(f"    ✅ Got {len(batch_scenes)} scenes")
                    batch_done = True
                    break
                else:
                    print(f"    ⚠ No scenes in response, retrying...")
            except Exception as e:
                print(f"    ⚠ Attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(5 * attempt)

        if not batch_done:
            print(f"    ❌ Batch {batch_idx + 1} failed — generating placeholder prompts")
            for j in range(batch_size):
                scene_num = start_i + j + 1
                all_scenes.append({
                    "scene_number": scene_num,
                    "swahili_script": batch_segments[j],
                    "image_prompt": {
                        "prompt": f"Photorealistic cinematic biblical-era scene. {VISUAL_STYLE}. Ancient Middle Eastern setting. 35mm film.",
                        "negative_prompt": NEGATIVE_PROMPT,
                        "aspect_ratio": "16:9",
                    },
                    "video_prompt": {
                        "prompt": f"Photorealistic biblical scene. [0.0s-3.0s] Wide establishing shot of ancient landscape. [3.0s-6.0s] Slow camera push-in.",
                        "duration": "6s",
                        "camera_motion": "slow push-in",
                    },
                })

    # --- Self-review for consistency ---
    if len(all_scenes) > 3:
        print(f"\n  🔍 Running visual consistency review...")
        try:
            scenes_yaml = yaml.dump(all_scenes[:24], default_flow_style=False,
                                     allow_unicode=True)  # Review first 24 scenes
            review_prompt = REVIEW_PROMPT.format(scenes_yaml=scenes_yaml)

            chat = client.start_chat(model=Model.G_3_0_PRO)
            resp = await chat.send_message(review_prompt)
            review_json = _parse_json_block(resp.text)
            review_data = json.loads(review_json)
            fixes = review_data.get("fixes", [])

            if fixes:
                print(f"    Found {len(fixes)} consistency issues, applying fixes...")
                for fix in fixes:
                    scene_num = fix.get("scene_number")
                    field = fix.get("field", "image_prompt")
                    fixed_prompt = fix.get("fixed_prompt", "")
                    if scene_num and fixed_prompt:
                        for scene in all_scenes:
                            if scene.get("scene_number") == scene_num:
                                if field in scene and isinstance(scene[field], dict):
                                    scene[field]["prompt"] = fixed_prompt
                                    print(f"    ✓ Fixed scene {scene_num} {field}")
                                break
            else:
                print(f"    ✅ All prompts are visually consistent!")

        except Exception as e:
            print(f"    ⚠ Consistency review failed (non-critical): {e}")

    # Assemble final data
    final_data = {
        "visual_style": VISUAL_STYLE,
        "style_subcategory": STYLE_SUB,
        "animation_complexity": "complex",
        "scenes": all_scenes,
    }

    print(f"\n  ✅ Generated {len(all_scenes)} visual prompts total")
    return final_data


# ---------------------------------------------------------------------------
# Chunk-Aware Visual Prompt Generation
# ---------------------------------------------------------------------------

async def generate_visual_prompts_from_manifest(manifest: dict) -> dict:
    """Generate visual prompts driven by the audio chunks manifest.

    Each chunk in the manifest specifies:
      - text: the narration text for that chunk
      - clips_needed: how many 6s video clips are needed for that chunk
      - scene_numbers: the scene numbers assigned to those clips

    This ensures perfect 1:1 mapping between audio segments and visuals.
    """
    await client.init(timeout=300, watchdog_timeout=120)

    chunks = manifest.get("chunks", [])
    total_clips = manifest.get("total_clips", sum(c["clips_needed"] for c in chunks))

    print(f"\n{'='*60}")
    print(f"  🎨 Chunk-Aware Visual Prompt Generator — Biblical Era")
    print(f"{'='*60}")
    print(f"  Audio chunks: {len(chunks)}")
    print(f"  Total clips:  {total_clips}")
    print(f"  Style: {VISUAL_STYLE}")

    all_scenes = []

    # Process chunks in batches (group multiple chunks per Gemini call)
    # Build a flat list of (scene_number, chunk_text, clips_in_chunk) for batching
    scene_tasks = []
    for chunk in chunks:
        chunk_text = chunk["text"]
        clips_needed = chunk["clips_needed"]
        scene_nums = chunk["scene_numbers"]

        if clips_needed == 1:
            # One clip for this chunk — use the full text as the segment
            scene_tasks.append((scene_nums[0], chunk_text))
        else:
            # Multiple clips for this chunk — split text into sub-segments
            sub_segments = split_script_into_segments(chunk_text, clips_needed)
            for j, sn in enumerate(scene_nums):
                seg_text = sub_segments[j] if j < len(sub_segments) else sub_segments[-1]
                scene_tasks.append((sn, seg_text))

    # Process in batches of BATCH_SIZE
    num_batches = math.ceil(len(scene_tasks) / BATCH_SIZE)

    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(scene_tasks))
        batch_tasks = scene_tasks[start_i:end_i]
        batch_size = len(batch_tasks)
        start_num = batch_tasks[0][0]
        end_num = batch_tasks[-1][0]

        # Format segments
        segments_text = ""
        for sn, seg_text in batch_tasks:
            segments_text += f"\n--- SEGMENT {sn} ---\n{seg_text}\n"

        prompt = BATCH_PROMPT.format(
            visual_style=VISUAL_STYLE,
            style_sub=STYLE_SUB,
            color_palette=COLOR_PALETTE,
            rendering=RENDERING,
            negative_prompt=NEGATIVE_PROMPT,
            start_num=start_num,
            end_num=end_num,
            segments_text=segments_text,
            batch_size=batch_size,
        )

        print(f"\n  Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

        batch_done = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                chat = client.start_chat(model=Model.G_3_0_PRO)
                resp = await chat.send_message(prompt)
                json_text = _parse_json_block(resp.text)
                batch_data = json.loads(json_text)
                batch_scenes = batch_data.get("scenes", [])

                if batch_scenes:
                    # Ensure scene numbers match what we expect
                    for k, scene in enumerate(batch_scenes):
                        expected_sn = batch_tasks[k][0] if k < len(batch_tasks) else None
                        if expected_sn and scene.get("scene_number") != expected_sn:
                            scene["scene_number"] = expected_sn

                    all_scenes.extend(batch_scenes)
                    print(f"    ✅ Got {len(batch_scenes)} scenes")
                    batch_done = True
                    break
                else:
                    print(f"    ⚠ No scenes in response, retrying...")
            except Exception as e:
                print(f"    ⚠ Attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(5 * attempt)

        if not batch_done:
            print(f"    ❌ Batch {batch_idx + 1} failed — generating placeholder prompts")
            for sn, seg_text in batch_tasks:
                all_scenes.append({
                    "scene_number": sn,
                    "swahili_script": seg_text,
                    "image_prompt": {
                        "prompt": f"Photorealistic cinematic biblical-era scene. {VISUAL_STYLE}. Ancient Middle Eastern setting. 35mm film.",
                        "negative_prompt": NEGATIVE_PROMPT,
                        "aspect_ratio": "16:9",
                    },
                    "video_prompt": {
                        "prompt": f"Photorealistic biblical scene. [0.0s-3.0s] Wide establishing shot of ancient landscape. [3.0s-6.0s] Slow camera push-in.",
                        "duration": "6s",
                        "camera_motion": "slow push-in",
                    },
                })

    # --- Self-review for consistency (reuse existing logic) ---
    if len(all_scenes) > 3:
        print(f"\n  🔍 Running visual consistency review...")
        try:
            scenes_yaml = yaml.dump(all_scenes[:24], default_flow_style=False,
                                     allow_unicode=True)
            review_prompt = REVIEW_PROMPT.format(scenes_yaml=scenes_yaml)

            chat = client.start_chat(model=Model.G_3_0_PRO)
            resp = await chat.send_message(review_prompt)
            review_json = _parse_json_block(resp.text)
            review_data = json.loads(review_json)
            fixes = review_data.get("fixes", [])

            if fixes:
                print(f"    Found {len(fixes)} consistency issues, applying fixes...")
                for fix in fixes:
                    scene_num = fix.get("scene_number")
                    field = fix.get("field", "image_prompt")
                    fixed_prompt = fix.get("fixed_prompt", "")
                    if scene_num and fixed_prompt:
                        for scene in all_scenes:
                            if scene.get("scene_number") == scene_num:
                                if field in scene and isinstance(scene[field], dict):
                                    scene[field]["prompt"] = fixed_prompt
                                    print(f"    ✓ Fixed scene {scene_num} {field}")
                                break
            else:
                print(f"    ✅ All prompts are visually consistent!")

        except Exception as e:
            print(f"    ⚠ Consistency review failed (non-critical): {e}")

    # Assemble final data — include chunk mapping for assembly
    final_data = {
        "visual_style": VISUAL_STYLE,
        "style_subcategory": STYLE_SUB,
        "animation_complexity": "complex",
        "chunk_synced": True,  # Flag: this was generated from audio chunks
        "chunk_mapping": [
            {
                "chunk_index": c["chunk_index"],
                "audio_file": c["audio_file"],
                "duration": c["duration"],
                "scene_numbers": c["scene_numbers"],
            }
            for c in chunks
        ],
        "scenes": all_scenes,
    }

    print(f"\n  ✅ Generated {len(all_scenes)} chunk-synced visual prompts")
    return final_data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Biblical Visual Prompts")
    parser.add_argument("script_file", help="Path to Swahili script file")
    parser.add_argument("-o", "--output", default="outputs/prompts.yaml")
    parser.add_argument("--clip-count", type=int, default=0,
                        help="Number of clips (0 = auto from script length)")

    args = parser.parse_args()
    script_path = Path(args.script_file)
    output_path = Path(args.output)

    if not script_path.exists():
        print(f"Error: {script_path} not found")
        sys.exit(1)

    script_text = script_path.read_text(encoding="utf-8").strip()

    # Auto-calculate clip count if not specified
    clip_count = args.clip_count
    if clip_count <= 0:
        # Estimate: ~150 words/min narration speed, 6 seconds per clip
        word_count = len(script_text.split())
        est_duration_sec = (word_count / 150) * 60
        clip_count = max(10, int(est_duration_sec / 6))
        print(f"  Auto clip count: {clip_count} ({word_count} words, ~{est_duration_sec/60:.1f} min)")

    final_data = asyncio.run(generate_visual_prompts(script_text, clip_count))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(final_data, f, sort_keys=False, allow_unicode=True)

    print(f"  Saved to: {output_path}")
