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

Uses Gemini WebUI (ADVANCED_PRO) in batches of 8.
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

# Add Gemini-API-New to path
sys.path.insert(0, str(Path(__file__).parent.parent / "Gemini-API-New" / "src"))

from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BATCH_SIZE = 8
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Art style — applied to image prompts only
# ---------------------------------------------------------------------------

# Base style rules to be adapted by the character profile
CHARACTER_BASE_STYLE = """\
BASE ART STYLE (mandatory):
- Characters have an OVERSIZED cartoon head (~40% of total figure height).
- Face is HIGHLY DETAILED and expressive: wrinkles, prominent nose, heavy eyelids, 
  realistic skin texture — drawn with thick black outlines.
- Body is a STICK FIGURE: thin black lines for arms, legs, and torso. No muscle, no bulk.
- Flat digital coloring. Hard black outlines on everything.
- Characters ADAPT appearance to the story's cultural context (clothing, skin tone, hair).
"""

IMAGE_NEGATIVE_PROMPT = (
    "photorealistic, 3D render, CGI, anime, chibi, full body proportions, "
    "realistic body, muscular, detailed hands, watermark, text, subtitle, "
    "blurry, low quality, multiple characters merged, collage, grid layout, "
    "tiled images, split screen, photo montage"
)

VIDEO_NEGATIVE_PROMPT = (
    "photorealistic, 3D render, CGI, watermark, text, subtitle, blurry, "
    "low quality, multiple panels, split screen, collage, static image"
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

CHARACTER_PROFILE_PROMPT = """\
You are a Character Designer. Based on the SCRIPT, define the visual profiles for the main characters.

{base_style}

IMPORTANT: Characters must be culturally authentic to the story's setting.
- A Viking character should have Norse features, fur clothing, braided hair.
- A Chinese character should have East Asian features, period-appropriate clothing.
- An Egyptian character should have Egyptian features, linen garments, kohl eyeliner.
- Adapt EVERYTHING (skin tone, hair, clothing, accessories) to the story's culture and era.
- Do NOT use generic Western defaults.

For each recurring character, define their specific features based on the script's culture/era.
Return ONLY a JSON object.

SCRIPT:
{script_text}

OUTPUT FORMAT:
{{
  "characters": [
    {{
      "name": "...",
      "role": "...",
      "cultural_context": "(e.g. Ancient Egyptian, Viking Age Norse, Han Dynasty Chinese)",
      "visual_attributes": {{
        "skin_tone": "...",
        "hair": "...",
        "eyes": "...",
        "clothing": "...",
        "accessories": "..."
      }},
      "micro_details": [
        "Stick-figure limbs drawn with thick black lines",
        "Oversized cartoon head (~40% of total figure height)",
        "Highly detailed face: [specific features for this character]",
        "Wearing: [specific culturally-accurate clothing]",
        "..."
      ]
    }}
  ]
}}
"""

IMAGE_BATCH_PROMPT = """\
You are an expert Prompt Engineer for AI IMAGE generation.
Generate a high-detail structured JSON image prompt for each script segment.
These prompts will be fed directly to an image generation model (like Imagen or DALL-E).

{base_style}

CHARACTER PROFILE (LOCK — use these exact visual details in every scene, adapt ONLY the emotion/pose):
{character_profiles}

NEGATIVE PROMPT (apply to every scene):
{negative_prompt}

CRITICAL RULES:
1. NEVER describe a character as "angry" or with a negative emotion unless the script explicitly calls for it.
2. Emotions MUST match the script moment — vary them naturally (curious, surprised, determined, sad, amused, etc.).
3. NEVER produce a collage, grid, split-screen, or multi-panel layout. ONE single illustration per scene.
4. Every character object MUST include all micro_details from the CHARACTER PROFILE.
5. Environment objects MUST use "Digital ink" / "Flat/Digital" textures — never photorealistic.
6. Include at least 3 environment/background objects with detailed micro_details.
7. The image_prompt MUST be a self-contained JSON — no references to "previous scenes".

OUTPUT FORMAT — produce a JSON object with a "scenes" array. Each scene:
{{
  "scene_number": N,
  "image_prompt": {{
    "meta": {{
      "image_quality": "High",
      "image_type": "Illustration/Animation Frame",
      "resolution_estimation": "1280x720"
    }},
    "global_context": {{
      "scene_description": "A high-detail 2D digital illustration depicting [specific action] in [specific environment], featuring [character name(s)] with oversized cartoon heads and stick-figure bodies, flat digital coloring, thick black outlines.",
      "time_of_day": "...",
      "weather_atmosphere": "...",
      "lighting": {{
        "source": "Artificial/Digital Flat Lighting",
        "direction": "...",
        "quality": "Hard",
        "color_temp": "..."
      }}
    }},
    "color_palette": {{
      "dominant_hex_estimates": ["#XXXXXX", "#XXXXXX", "#XXXXXX"],
      "accent_colors": ["...", "..."],
      "contrast_level": "High"
    }},
    "composition": {{
      "camera_angle": "...",
      "framing": "...",
      "depth_of_field": "Deep (everything in focus)",
      "focal_point": "..."
    }},
    "objects": [
      {{
        "id": "obj_001",
        "label": "[Character Name]",
        "category": "Person/Character",
        "location": "...",
        "prominence": "Foreground",
        "visual_attributes": {{
          "color": "[skin tone, hair color, clothing color from profile]",
          "texture": "Smooth/Digital",
          "material": "Digital ink/color",
          "state": "[emotion matching the script moment]",
          "dimensions_relative": "Large"
        }},
        "micro_details": [
          "Stick-figure limbs drawn with thick black lines, no muscle",
          "Oversized cartoon head (~40% of total figure height)",
          "Highly detailed face: [copy exact face details from character profile]",
          "Wearing: [copy exact clothing from character profile]",
          "[Emotion matching this specific script moment — e.g. 'wide curious eyes', 'slight smirk']",
          "[Pose detail — e.g. 'right stick-arm raised, pointing forward']"
        ],
        "pose_or_orientation": "...",
        "text_content": null
      }},
      {{
        "id": "obj_002",
        "label": "[Second character or major prop]",
        "category": "...",
        "location": "...",
        "prominence": "Midground",
        "visual_attributes": {{
          "color": "...",
          "texture": "Smooth/Digital",
          "material": "Digital ink/color",
          "state": "...",
          "dimensions_relative": "..."
        }},
        "micro_details": ["...", "..."],
        "pose_or_orientation": "...",
        "text_content": null
      }},
      {{
        "id": "obj_003",
        "label": "[Background environment element 1]",
        "category": "Environment/...",
        "location": "Background",
        "prominence": "Background",
        "visual_attributes": {{
          "color": "...",
          "texture": "Flat/Digital",
          "material": "Digital ink",
          "state": "Undamaged",
          "dimensions_relative": "Large"
        }},
        "micro_details": [
          "Thick black outlines defining the structure",
          "Flat digital coloring",
          "..."
        ],
        "pose_or_orientation": "Static",
        "text_content": null
      }},
      {{
        "id": "obj_004",
        "label": "[Background environment element 2 — ground/floor/terrain]",
        "category": "Environment/Terrain",
        "location": "Bottom",
        "prominence": "Background",
        "visual_attributes": {{
          "color": "...",
          "texture": "Flat/Digital",
          "material": "Digital ink",
          "state": "Undamaged",
          "dimensions_relative": "Large"
        }},
        "micro_details": ["...", "..."],
        "pose_or_orientation": "Horizontal",
        "text_content": null
      }}
    ],
    "text_ocr": {{ "present": false, "content": null }},
    "semantic_relationships": [
      "[Character] is [doing action] with/near [object/environment]",
      "..."
    ],
    "negative_prompt": "{negative_prompt}"
  }}
}}

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

OUTPUT: A single JSON object with a "scenes" array containing exactly {batch_size} scenes.
Return ONLY the JSON. No markdown, no explanation.
"""

VIDEO_BATCH_PROMPT = """\
You are an expert Prompt Engineer for AI VIDEO generation (image-to-video).
The video model receives a REFERENCE IMAGE that already shows the characters.
Your job is to describe MOTION ONLY — camera moves, environmental animation, and character actions.

CRITICAL RULES — READ CAREFULLY:
1. DO NOT describe character appearance, clothing, hair, or facial features. The reference image handles that.
2. DO NOT include a character_description field with physical details. It will override the reference image and cause distortion.
3. DO NOT repeat the character profile. The video model uses the image as the visual anchor.
4. ONLY describe: what moves, how it moves, camera motion, and environment animation.
5. Action beats MUST cover the full 6 seconds with 2-3 specific timed beats.
6. Keep character actions simple and physical: "raises arm", "turns head left", "walks forward", "sits down".
7. DO NOT describe emotions in the video prompt — emotions are locked in the reference image.
8. Environment motion is encouraged: wind, dust, fire flicker, water ripple, leaves falling, etc.

OUTPUT FORMAT — produce a JSON object with a "scenes" array. Each scene:
{{
  "scene_number": N,
  "video_prompt": {{
    "meta": {{
      "clip_duration": "6s",
      "style": "2D animation, flat illustration, stick-figure characters with oversized cartoon heads, digital ink"
    }},
    "global_context": {{
      "scene_description": "A 2D animation clip of [specific action] in [specific environment]. [Brief motion summary].",
      "environment_description": "[Describe the setting background: walls, ground, sky, props — all in flat digital ink style. No character appearance here.]"
    }},
    "camera_motion": {{
      "primary_move": "...",
      "secondary_move": null,
      "start_frame": "...",
      "end_frame": "..."
    }},
    "action_beats": [
      {{
        "time_range": "0.0s-2.0s",
        "action": "[Specific physical action — e.g. 'Character slowly raises right stick-arm upward']",
        "camera": "[Camera state — e.g. 'Static medium shot']"
      }},
      {{
        "time_range": "2.0s-4.0s",
        "action": "[Next beat — e.g. 'Character turns head to the left, dust particles drift across foreground']",
        "camera": "[Camera state]"
      }},
      {{
        "time_range": "4.0s-6.0s",
        "action": "[Final beat — e.g. 'Character lowers arm, background torch flickers']",
        "camera": "[Camera state]"
      }}
    ],
    "objects_in_motion": [
      {{
        "label": "[What is moving — character limb, prop, environment element]",
        "motion_description": "[How it moves — direction, speed, style]"
      }}
    ],
    "negative_prompt": "photorealistic, 3D render, CGI, watermark, text, subtitle, blurry, low quality, multiple panels, split screen, collage, static image"
  }}
}}

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

OUTPUT: A single JSON object with a "scenes" array containing exactly {batch_size} scenes.
Return ONLY the JSON. No markdown, no explanation.
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


async def _generate_character_profile(script_text: str) -> dict:
    """Define recurring characters based on the full script."""
    print(f"\n  👤 Generating character profile for consistency...")
    prompt = CHARACTER_PROFILE_PROMPT.format(
        base_style=CHARACTER_BASE_STYLE,
        script_text=script_text
    )
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chat = client.start_chat(model=Model.G_3_0_FLASH)
            resp = await chat.send_message(prompt)
            json_text = _parse_json_block(resp.text)
            return json.loads(json_text)
        except Exception as e:
            print(f"    ⚠ Character profile attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(5 * attempt)
    
    return {"characters": []}


async def _run_image_batch(scene_tasks: list, char_profile: dict, batch_idx: int, num_batches: int) -> list:
    """Generate structured JSON image prompts for a batch of scenes."""
    batch_size = len(scene_tasks)
    start_num = scene_tasks[0][0]
    end_num = scene_tasks[-1][0]

    segments_text = ""
    for sn, seg_text in scene_tasks:
        segments_text += f"\n--- SEGMENT {sn} ---\n{seg_text}\n"

    prompt = IMAGE_BATCH_PROMPT.format(
        base_style=CHARACTER_BASE_STYLE,
        character_profiles=json.dumps(char_profile, indent=2),
        negative_prompt=IMAGE_NEGATIVE_PROMPT,
        start_num=start_num,
        end_num=end_num,
        segments_text=segments_text,
        batch_size=batch_size,
    )

    print(f"\n  [Image] Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chat = client.start_chat(model=Model.G_3_0_FLASH)
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
            "segment_text": seg_text,
            "image_prompt": _make_placeholder_image_prompt(seg_text),
            "negative_prompt": IMAGE_NEGATIVE_PROMPT,
        }
        for sn, seg_text in scene_tasks
    ]


async def _run_video_batch(scene_tasks: list, char_profile: dict, batch_idx: int, num_batches: int) -> list:
    """Generate structured JSON video prompts for a batch of scenes.
    
    NOTE: Video prompts are motion-only. Character appearance is NOT included
    here — it is locked by the reference image passed to the video model.
    """
    batch_size = len(scene_tasks)
    start_num = scene_tasks[0][0]
    end_num = scene_tasks[-1][0]

    segments_text = ""
    for sn, seg_text in scene_tasks:
        segments_text += f"\n--- SEGMENT {sn} ---\n{seg_text}\n"

    prompt = VIDEO_BATCH_PROMPT.format(
        start_num=start_num,
        end_num=end_num,
        segments_text=segments_text,
        batch_size=batch_size,
    )

    print(f"\n  [Video] Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chat = client.start_chat(model=Model.G_3_0_FLASH)
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

        chat = client.start_chat(model=Model.G_3_0_FLASH)
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
                    # In the new structure, we update the whole image_prompt if needed
                    # but usually fixes are minor strings. This part might need adaptation
                    # depending on how detailed the 'fix' is.
                    print(f"    ⚠ Manual fix required for scene {sn} (structure change)")
        else:
            print(f"    ✅ All image prompts are consistent!")
    except Exception as e:
        print(f"    ⚠ Consistency review failed (non-critical): {e}")
    return all_scenes


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

async def generate_visual_prompts(script_text: str, clip_count: int) -> dict:
    """Generate image + video prompts for all clips (two separate passes)."""
    await client.init(timeout=300, watchdog_timeout=120)

    # 1. Generate Character Profile
    char_profile = await _generate_character_profile(script_text)

    segments = split_script_into_segments(script_text, clip_count)
    scene_tasks = [(i + 1, segments[i]) for i in range(clip_count)]
    num_batches = math.ceil(clip_count / BATCH_SIZE)

    print(f"\n{'='*60}")
    print(f"  🎨 Visual Prompt Generator — 2D Illustration Style")
    print(f"{'='*60}")
    print(f"  Clip count : {clip_count}")
    print(f"  Batches    : {num_batches} × {BATCH_SIZE}")
    print(f"  Art style  : Big cartoon heads + stick-figure bodies")
    print(f"  Pass 1     : Image prompts (Rich character description)")
    print(f"  Pass 2     : Video prompts (Motion ONLY)")

    # --- Pass 1: Image prompts ---
    image_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, clip_count)
        batch = scene_tasks[start_i:end_i]
        result = await _run_image_batch(batch, char_profile, batch_idx, num_batches)
        image_scenes_flat.extend(result)

    # --- Pass 2: Video prompts ---
    video_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, clip_count)
        batch = scene_tasks[start_i:end_i]
        result = await _run_video_batch(batch, char_profile, batch_idx, num_batches)
        video_scenes_flat.extend(result)

    # --- Merge ---
    all_scenes = _merge_image_and_video(image_scenes_flat, video_scenes_flat)

    final_data = {
        "art_style": "2D illustration — big cartoon heads, stick-figure bodies",
        "character_profile": char_profile,
        "scenes": all_scenes,
    }

    print(f"\n  ✅ Generated {len(all_scenes)} visual prompts total")
    return final_data


# ---------------------------------------------------------------------------
# Chunk-Aware Visual Prompt Generation
# ---------------------------------------------------------------------------

async def generate_visual_prompts_from_manifest(manifest: dict) -> dict:
    """Generate visual prompts driven by the audio chunks manifest."""
    await client.init(timeout=300, watchdog_timeout=120)

    chunks = manifest.get("chunks", [])
    full_script = " ".join([c["text"] for c in chunks])
    
    # 1. Generate Character Profile
    char_profile = await _generate_character_profile(full_script)

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
        result = await _run_image_batch(batch, char_profile, batch_idx, num_batches)
        image_scenes_flat.extend(result)

    # --- Pass 2: Video prompts ---
    video_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(scene_tasks))
        batch = scene_tasks[start_i:end_i]
        result = await _run_video_batch(batch, char_profile, batch_idx, num_batches)
        video_scenes_flat.extend(result)

    # --- Merge ---
    all_scenes = _merge_image_and_video(image_scenes_flat, video_scenes_flat)

    final_data = {
        "art_style": "2D illustration — big cartoon heads, stick-figure bodies",
        "character_profile": char_profile,
        "chunk_synced": True,
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
