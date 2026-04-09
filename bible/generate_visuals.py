#!/usr/bin/env python3
"""
Visual Prompt Generator — 2D Illustration Animation Frame Prompts.

Splits a narration script into segments and generates separate
image prompts and video prompts for each scene.

IMAGE PROMPTS: Rich 2D illustration style — big expressive cartoon heads,
stick-figure bodies, flat digital ink art. Characters adapt to the story
context (cultural appearance, clothing) but always share the same art style.

VIDEO PROMPTS: Motion-only. No character description. Pure camera movement
and environmental action beats. Character appearance is locked by the image,
not re-described in the video prompt.

Uses Gemini WebUI (G_3_0_PRO) in batches of 8.
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

# ---------------------------------------------------------------------------
# Art style — applied to both image and video prompts
# ---------------------------------------------------------------------------

# Character design rules injected into every prompt
CHARACTER_RULES = """\
CHARACTER DESIGN (mandatory for every scene):
- Every character has an OVERSIZED cartoon head (~40% of total figure height) with a
  highly-detailed realistic face: expressive eyes, prominent nose, heavy eyelids,
  visible teeth when mouth is open, wrinkles/skin texture — drawn with thick black outlines.
- Body is a STICK FIGURE: thin black lines for arms, legs, and torso. No muscle, no bulk.
- Flat digital coloring. Hard black outlines on everything.
- Characters ADAPT appearance to the story's cultural context:
    Biblical/Middle Eastern → robes, head coverings, sandals, olive/brown skin
    Chinese → hanfu robes, black hair, East Asian features
    Viking → furs, horned helmet, blonde/red hair, pale skin
    African → colorful kente/dashiki, dark skin, natural hair
    Modern → contemporary clothing
- Match the character's facial expression to the EMOTION in the script moment.
  Do NOT default to angry/intense — use calm, curious, sad, joyful, fearful as appropriate.
- Maximum 2 characters per scene. Position them clearly: left foreground, right background, etc.\
"""

IMAGE_NEGATIVE_PROMPT = (
    "photorealistic, 3D render, CGI, anime, chibi, full body proportions, "
    "realistic body, muscular, detailed hands, watermark, text, subtitle, "
    "blurry, low quality, multiple characters merged, collage, grid layout, "
    "tiled images, split screen, photo montage"
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

IMAGE_BATCH_PROMPT = """\
You are an expert Prompt Engineer for AI IMAGE generation (still frames).
I'll give you SCRIPT SEGMENTS. For each, produce a structured JSON image prompt
describing the scene as a 2D digital illustration still frame.

{character_rules}

OUTPUT FORMAT — for each scene produce a JSON object matching this exact structure:
{{
  "meta": {{
    "image_quality": "High",
    "image_type": "Illustration/Animation Frame",
    "resolution_estimation": "1280x720"
  }},
  "global_context": {{
    "scene_description": "(one sentence: who is doing what, where, in the art style)",
    "time_of_day": "(Daytime / Night / Dusk / Dawn)",
    "weather_atmosphere": "(Clear / Stormy / Snowy / Dusty / etc.)",
    "lighting": {{
      "source": "(Natural sunlight / Torchlight / Moonlight / etc.)",
      "direction": "(Top-down / Side / Front / etc.)",
      "quality": "(Soft / Hard / Dramatic)",
      "color_temp": "(Warm / Cool / Neutral)"
    }}
  }},
  "color_palette": {{
    "dominant_hex_estimates": ["#XXXXXX", "#XXXXXX", "#XXXXXX"],
    "accent_colors": ["color1", "color2"],
    "contrast_level": "(High / Medium / Low)"
  }},
  "composition": {{
    "camera_angle": "(Eye-level / Low angle / High angle / Over-shoulder)",
    "framing": "(Wide shot / Medium shot / Close-up / Medium-close)",
    "depth_of_field": "(Deep — everything in focus / Shallow — background blurred)",
    "focal_point": "(what the eye is drawn to)"
  }},
  "objects": [
    {{
      "id": "obj_001",
      "label": "(descriptive label)",
      "category": "(Person/Character | Animal | Object/Prop | Environment/Flora | Environment/Terrain | Environment/Sky)",
      "location": "(Top-Left | Top-Center | Top-Right | Center-Left | Center | Center-Right | Bottom-Left | Bottom-Center | Bottom-Right | Background | Foreground | Midground)",
      "prominence": "(Foreground | Midground | Background)",
      "visual_attributes": {{
        "color": "(description)",
        "texture": "(Smooth/Digital | Wood | Fabric | Stone | etc.)",
        "material": "(Digital ink | Wood | Cloth | etc.)",
        "state": "(Undamaged | Damaged | In motion | etc.)",
        "dimensions_relative": "(Very Small | Small | Medium | Large | Very Large)"
      }},
      "micro_details": ["detail 1", "detail 2"],
      "pose_or_orientation": "(description of pose, direction facing, or spatial orientation)",
      "text_content": null
    }}
  ],
  "text_ocr": {{
    "present": false,
    "content": null
  }},
  "semantic_relationships": [
    "(subject) is (doing/holding/near) (object)",
    "(character) is positioned (relative to) (other character/object)"
  ]
}}

RULES:
- The first object in the array MUST be the main character (if present).
- Characters must always be described with: oversized cartoon head, stick-figure body,
  thick black outlines, flat digital coloring.
- Include at least one environment object (background, ground, sky).
- semantic_relationships must list every meaningful spatial or action connection.
- Do NOT produce a collage or multi-panel layout — one unified scene only.

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

OUTPUT: A single valid JSON object:
{{
  "scenes": [
    {{
      "scene_number": {start_num},
      "swahili_script": "(the script segment text)",
      "image_prompt": {{ ...the structured prompt object above... }},
      "negative_prompt": "{negative_prompt}"
    }}
  ]
}}

Generate EXACTLY {batch_size} scenes. Return ONLY the JSON, no other text.
"""

VIDEO_BATCH_PROMPT = """\
You are an expert Prompt Engineer for AI VIDEO generation (6-second animated clips).
I'll give you SCRIPT SEGMENTS. For each, produce a structured JSON video prompt
describing the scene as a 2D animated clip — including what the characters are DOING
and how the camera moves.

{character_rules}

VIDEO PROMPT RULES:
- Describe BOTH the scene action (what characters are doing) AND camera movement.
- Use video-generation language: "the figure slowly raises its arm", "camera pans left",
  "wind ripples through the trees", "character kneels down", "slow zoom toward face".
- Refer to characters by role/position only: "the figure on the left", "the seated character",
  "the standing figure" — do NOT re-describe hair color, clothing details, or face features
  (those are locked by the image prompt).
- Break 6 seconds into timed action beats covering the FULL duration.
- Keep all movements SLOW and DELIBERATE. Avoid fast cuts, running, fighting close-ups.

OUTPUT FORMAT — for each scene produce a JSON object matching this exact structure:
{{
  "meta": {{
    "clip_duration": "6s",
    "style": "2D animation, flat illustration, stick-figure characters with oversized cartoon heads"
  }},
  "global_context": {{
    "scene_description": "(one sentence: what is happening in this clip)",
    "time_of_day": "(Daytime / Night / Dusk / Dawn)",
    "weather_atmosphere": "(Clear / Stormy / Snowy / etc.)",
    "lighting": {{
      "source": "(Natural sunlight / Torchlight / Moonlight / etc.)",
      "direction": "(Top-down / Side / Front)",
      "quality": "(Soft / Hard / Dramatic)",
      "color_temp": "(Warm / Cool / Neutral)"
    }}
  }},
  "camera_motion": {{
    "primary_move": "(slow pan left | slow pan right | gentle zoom in | gentle zoom out | static | slow tilt up | slow tilt down)",
    "secondary_move": "(optional secondary move or null)",
    "start_frame": "(describe what the camera sees at 0.0s)",
    "end_frame": "(describe what the camera sees at 6.0s)"
  }},
  "action_beats": [
    {{
      "time_range": "0.0s-2.0s",
      "action": "(what is happening — character action + any environmental motion)",
      "camera": "(camera state during this beat)"
    }},
    {{
      "time_range": "2.0s-4.5s",
      "action": "(next action beat)",
      "camera": "(camera state)"
    }},
    {{
      "time_range": "4.5s-6.0s",
      "action": "(final beat — can be a hold, a reaction, or a transition gesture)",
      "camera": "(camera state)"
    }}
  ],
  "objects_in_motion": [
    {{
      "label": "(what is moving)",
      "motion_description": "(how it moves)"
    }}
  ],
  "semantic_relationships": [
    "(subject) is (doing/moving toward/reacting to) (object/other character)"
  ]
}}

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

OUTPUT: A single valid JSON object:
{{
  "scenes": [
    {{
      "scene_number": {start_num},
      "swahili_script": "(the script segment text)",
      "video_prompt": {{ ...the structured prompt object above... }}
    }}
  ]
}}

Generate EXACTLY {batch_size} scenes. Return ONLY the JSON, no other text.
"""

REVIEW_PROMPT = """\
Review these scene prompts for a 2D animated story video.
Check that every scene uses the correct art style and that character emotions
vary naturally across scenes (not the same expression everywhere).

SCENES:
{scenes_yaml}

Check:
1. Does every image_prompt describe characters with oversized cartoon heads + stick-figure bodies?
2. Do character expressions match the script moment (not always angry/intense)?
3. Is the cultural appearance consistent with the story setting across all scenes?
4. Does any image_prompt risk producing a collage or multi-panel layout?
5. Do video_prompt action_beats cover the full 6 seconds?

Output fixes as JSON:
{{
  "fixes": [
    {{
      "scene_number": N,
      "field": "image_prompt" or "video_prompt",
      "issue": "description",
      "fix": "(describe what to change — do not rewrite the full prompt)"
    }}
  ]
}}

If everything is fine: {{"fixes": []}}
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
    sentences = re.split(r'(?<=[.!?…])\s+', script_text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) == 0:
        return [script_text] * num_segments

    if len(sentences) <= num_segments:
        segments = sentences[:]
        while len(segments) < num_segments:
            segments.append(segments[-1])
        return segments

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


def _make_placeholder_image_prompt(seg_text: str) -> dict:
    return {
        "meta": {"image_quality": "Medium", "image_type": "Illustration/Animation Frame", "resolution_estimation": "1280x720"},
        "global_context": {
            "scene_description": f"2D illustration scene: {seg_text[:100]}",
            "time_of_day": "Daytime", "weather_atmosphere": "Clear",
            "lighting": {"source": "Natural sunlight", "direction": "Top-down", "quality": "Soft", "color_temp": "Warm"}
        },
        "color_palette": {"dominant_hex_estimates": ["#87CEEB", "#8B6914", "#228B22"], "accent_colors": ["Brown", "Green"], "contrast_level": "High"},
        "composition": {"camera_angle": "Eye-level", "framing": "Medium shot", "depth_of_field": "Deep", "focal_point": "Main character"},
        "objects": [{"id": "obj_001", "label": "Main Character", "category": "Person/Character", "location": "Center", "prominence": "Foreground",
                     "visual_attributes": {"color": "Varied", "texture": "Smooth/Digital", "material": "Digital ink", "state": "Undamaged", "dimensions_relative": "Large"},
                     "micro_details": ["Oversized cartoon head", "Stick-figure body", "Thick black outlines"], "pose_or_orientation": "Standing, facing forward", "text_content": None}],
        "text_ocr": {"present": False, "content": None},
        "semantic_relationships": ["Main character is standing in the scene"],
    }


def _make_placeholder_video_prompt(scene_num: int) -> dict:
    return {
        "meta": {"clip_duration": "6s", "style": "2D animation, flat illustration, stick-figure characters with oversized cartoon heads"},
        "global_context": {
            "scene_description": f"Scene {scene_num}: character stands in environment",
            "time_of_day": "Daytime", "weather_atmosphere": "Clear",
            "lighting": {"source": "Natural sunlight", "direction": "Top-down", "quality": "Soft", "color_temp": "Warm"}
        },
        "camera_motion": {"primary_move": "gentle zoom in", "secondary_move": None,
                          "start_frame": "Wide shot of scene", "end_frame": "Slightly closer on character"},
        "action_beats": [
            {"time_range": "0.0s-2.0s", "action": "Scene opens, character stands still, ambient wind moves background elements", "camera": "Static wide shot"},
            {"time_range": "2.0s-4.5s", "action": "Character slowly turns head, looks around", "camera": "Gentle zoom in begins"},
            {"time_range": "4.5s-6.0s", "action": "Character holds position, scene settles", "camera": "Camera holds on character"},
        ],
        "objects_in_motion": [{"label": "Background foliage", "motion_description": "Gentle sway from wind"}],
        "semantic_relationships": ["Character is standing in the environment"],
    }


async def _run_image_batch(scene_tasks: list, batch_idx: int, num_batches: int) -> list:
    """Generate structured JSON image prompts for a batch of scenes."""
    batch_size = len(scene_tasks)
    start_num = scene_tasks[0][0]
    end_num = scene_tasks[-1][0]

    segments_text = ""
    for sn, seg_text in scene_tasks:
        segments_text += f"\n--- SEGMENT {sn} ---\n{seg_text}\n"

    prompt = IMAGE_BATCH_PROMPT.format(
        character_rules=CHARACTER_RULES,
        negative_prompt=IMAGE_NEGATIVE_PROMPT,
        start_num=start_num,
        end_num=end_num,
        segments_text=segments_text,
        batch_size=batch_size,
    )

    print(f"\n  [Image] Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chat = client.start_chat(model=Model.G_3_0_PRO)
            resp = await chat.send_message(prompt)
            json_text = _parse_json_block(resp.text)
            batch_data = json.loads(json_text)
            batch_scenes = batch_data.get("scenes", [])
            if batch_scenes:
                for k, scene in enumerate(batch_scenes):
                    if k < len(scene_tasks):
                        scene["scene_number"] = scene_tasks[k][0]
                print(f"    ✅ Got {len(batch_scenes)} image prompts")
                return batch_scenes
            print(f"    ⚠ No scenes in response, retrying...")
        except Exception as e:
            print(f"    ⚠ Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(5 * attempt)

    print(f"    ❌ Image batch {batch_idx + 1} failed — using placeholders")
    return [
        {
            "scene_number": sn,
            "swahili_script": seg_text,
            "image_prompt": _make_placeholder_image_prompt(seg_text),
            "negative_prompt": IMAGE_NEGATIVE_PROMPT,
        }
        for sn, seg_text in scene_tasks
    ]


async def _run_video_batch(scene_tasks: list, image_scenes: dict,
                           batch_idx: int, num_batches: int) -> list:
    """Generate structured JSON video prompts for a batch of scenes."""
    batch_size = len(scene_tasks)
    start_num = scene_tasks[0][0]
    end_num = scene_tasks[-1][0]

    # Include the scene_description from the image prompt as context
    segments_text = ""
    for sn, seg_text in scene_tasks:
        img_scene = image_scenes.get(sn, {})
        img_prompt = img_scene.get("image_prompt", {})
        scene_desc = ""
        if isinstance(img_prompt, dict):
            scene_desc = img_prompt.get("global_context", {}).get("scene_description", "")
        segments_text += f"\n--- SEGMENT {sn} ---\nScript: {seg_text}\nScene context: {scene_desc}\n"

    prompt = VIDEO_BATCH_PROMPT.format(
        character_rules=CHARACTER_RULES,
        start_num=start_num,
        end_num=end_num,
        segments_text=segments_text,
        batch_size=batch_size,
    )

    print(f"\n  [Video] Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chat = client.start_chat(model=Model.G_3_0_PRO)
            resp = await chat.send_message(prompt)
            json_text = _parse_json_block(resp.text)
            batch_data = json.loads(json_text)
            batch_scenes = batch_data.get("scenes", [])
            if batch_scenes:
                for k, scene in enumerate(batch_scenes):
                    if k < len(scene_tasks):
                        scene["scene_number"] = scene_tasks[k][0]
                print(f"    ✅ Got {len(batch_scenes)} video prompts")
                return batch_scenes
            print(f"    ⚠ No scenes in response, retrying...")
        except Exception as e:
            print(f"    ⚠ Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(5 * attempt)

    print(f"    ❌ Video batch {batch_idx + 1} failed — using placeholders")
    return [
        {"scene_number": sn, "video_prompt": _make_placeholder_video_prompt(sn)}
        for sn, _ in scene_tasks
    ]


def _merge_image_and_video(image_scenes: list, video_scenes: list) -> list:
    """Merge image and video prompt results into unified scene dicts."""
    video_map = {s["scene_number"]: s.get("video_prompt") for s in video_scenes}
    merged = []
    for scene in image_scenes:
        sn = scene["scene_number"]
        scene["video_prompt"] = video_map.get(sn, _make_placeholder_video_prompt(sn))
        merged.append(scene)
    return merged


async def _run_consistency_review(all_scenes: list) -> list:
    """Review image prompts for art style consistency. Returns updated scenes list."""
    print(f"\n  🔍 Running image consistency review...")
    try:
        # Only review image_prompt fields
        review_input = [
            {"scene_number": s["scene_number"],
             "image_prompt": s.get("image_prompt", {})}
            for s in all_scenes[:24]
        ]
        scenes_yaml = yaml.dump(review_input, default_flow_style=False, allow_unicode=True)
        review_prompt = REVIEW_PROMPT.format(scenes_yaml=scenes_yaml)

        chat = client.start_chat(model=Model.G_3_0_PRO)
        resp = await chat.send_message(review_prompt)
        review_json = _parse_json_block(resp.text)
        review_data = json.loads(review_json)
        fixes = review_data.get("fixes", [])

        if fixes:
            print(f"    Found {len(fixes)} consistency issues, applying fixes...")
            scene_map = {s["scene_number"]: s for s in all_scenes}
            for fix in fixes:
                sn = fix.get("scene_number")
                fixed_prompt = fix.get("fixed_prompt", "")
                if sn and fixed_prompt and sn in scene_map:
                    ip = scene_map[sn].get("image_prompt", {})
                    if isinstance(ip, dict):
                        ip["prompt"] = fixed_prompt
                        print(f"    ✓ Fixed scene {sn} image_prompt")
        else:
            print(f"    ✅ All image prompts are consistent!")
    except Exception as e:
        print(f"    ⚠ Consistency review failed (non-critical): {e}")
    return all_scenes


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

async def generate_visual_prompts(script_text: str, clip_count: int) -> dict:
    """Generate image + video prompts for all clips (two separate passes).

    Returns a dict with 'scenes' list ready for YAML output.
    """
    await client.init(timeout=300, watchdog_timeout=120)

    segments = split_script_into_segments(script_text, clip_count)
    scene_tasks = [(i + 1, segments[i]) for i in range(clip_count)]
    num_batches = math.ceil(clip_count / BATCH_SIZE)

    print(f"\n{'='*60}")
    print(f"  🎨 Visual Prompt Generator — 2D Illustration Style")
    print(f"{'='*60}")
    print(f"  Clip count : {clip_count}")
    print(f"  Batches    : {num_batches} × {BATCH_SIZE}")
    print(f"  Art style  : Big cartoon heads + stick-figure bodies")
    print(f"  Pass 1     : Image prompts (scene composition + characters)")
    print(f"  Pass 2     : Video prompts (motion only, no character description)")

    # --- Pass 1: Image prompts ---
    image_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, clip_count)
        batch = scene_tasks[start_i:end_i]
        result = await _run_image_batch(batch, batch_idx, num_batches)
        image_scenes_flat.extend(result)

    image_scenes_map = {s["scene_number"]: s for s in image_scenes_flat}

    # --- Pass 2: Video prompts (informed by image context) ---
    video_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, clip_count)
        batch = scene_tasks[start_i:end_i]
        result = await _run_video_batch(batch, image_scenes_map, batch_idx, num_batches)
        video_scenes_flat.extend(result)

    # --- Merge ---
    all_scenes = _merge_image_and_video(image_scenes_flat, video_scenes_flat)

    # --- Consistency review (image prompts only) ---
    if len(all_scenes) > 3:
        all_scenes = await _run_consistency_review(all_scenes)

    final_data = {
        "art_style": "2D illustration — big cartoon heads, stick-figure bodies",
        "animation_complexity": "moderate",
        "scenes": all_scenes,
    }

    print(f"\n  ✅ Generated {len(all_scenes)} visual prompts total")
    return final_data


# ---------------------------------------------------------------------------
# Chunk-Aware Visual Prompt Generation
# ---------------------------------------------------------------------------

async def generate_visual_prompts_from_manifest(manifest: dict) -> dict:
    """Generate visual prompts driven by the audio chunks manifest.

    Two-pass approach:
      Pass 1 — Image prompts (scene composition, characters, environment)
      Pass 2 — Video prompts (motion only, informed by image context)

    Each chunk specifies: text, clips_needed, scene_numbers.
    """
    await client.init(timeout=300, watchdog_timeout=120)

    chunks = manifest.get("chunks", [])
    total_clips = manifest.get("total_clips", sum(c["clips_needed"] for c in chunks))

    print(f"\n{'='*60}")
    print(f"  🎨 Chunk-Aware Visual Prompt Generator — 2D Illustration")
    print(f"{'='*60}")
    print(f"  Audio chunks : {len(chunks)}")
    print(f"  Total clips  : {total_clips}")
    print(f"  Art style    : Big cartoon heads + stick-figure bodies")
    print(f"  Pass 1       : Image prompts")
    print(f"  Pass 2       : Video prompts (motion only)")

    # Build flat list of (scene_number, segment_text)
    scene_tasks = []
    for chunk in chunks:
        chunk_text = chunk["text"]
        clips_needed = chunk["clips_needed"]
        scene_nums = chunk["scene_numbers"]

        if clips_needed == 1:
            scene_tasks.append((scene_nums[0], chunk_text))
        else:
            sub_segments = split_script_into_segments(chunk_text, clips_needed)
            for j, sn in enumerate(scene_nums):
                seg_text = sub_segments[j] if j < len(sub_segments) else sub_segments[-1]
                scene_tasks.append((sn, seg_text))

    num_batches = math.ceil(len(scene_tasks) / BATCH_SIZE)

    # --- Pass 1: Image prompts ---
    image_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(scene_tasks))
        batch = scene_tasks[start_i:end_i]
        result = await _run_image_batch(batch, batch_idx, num_batches)
        image_scenes_flat.extend(result)

    image_scenes_map = {s["scene_number"]: s for s in image_scenes_flat}

    # --- Pass 2: Video prompts ---
    video_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(scene_tasks))
        batch = scene_tasks[start_i:end_i]
        result = await _run_video_batch(batch, image_scenes_map, batch_idx, num_batches)
        video_scenes_flat.extend(result)

    # --- Merge ---
    all_scenes = _merge_image_and_video(image_scenes_flat, video_scenes_flat)

    # --- Consistency review ---
    if len(all_scenes) > 3:
        all_scenes = await _run_consistency_review(all_scenes)

    final_data = {
        "art_style": "2D illustration — big cartoon heads, stick-figure bodies",
        "animation_complexity": "moderate",
        "chunk_synced": True,
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
