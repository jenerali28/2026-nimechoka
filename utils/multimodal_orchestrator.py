#!/usr/bin/env python3
"""
Gemini Multimodal Orchestrator — Natural Language Prompt Generation.

Generates plain natural-language prompts (not JSON schemas) for both
image and video generation, matching the style of hand-crafted prompts
like early 2000s webcomic / MS Paint aesthetic descriptions.

Flow:
  1. Extract character profiles from script (culturally authentic, style-locked)
  2. Build a style anchor string from the character profiles
  3. Generate image prompts: style anchor + scene description + characters + environment
  4. Generate video prompts: same as image + motion beats appended
"""

import asyncio
import math
import os
import re
import sys
import json
import yaml
from pathlib import Path

# Add project root to path so `utils.*` imports work regardless of cwd
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add Gemini-API-New to path
sys.path.insert(0, str(Path(__file__).parent.parent / "Gemini-API-New" / "src"))

from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model
from dotenv import load_dotenv

# Import story context enhancement
from utils.enhance_prompts import enhance_prompts

# Load environment variables
load_dotenv()

# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

# Initialize with cookies from environment variables if available
secure_1psid = os.getenv("SECURE_1PSID")
secure_1psidts = os.getenv("SECURE_1PSIDTS")

PLACEHOLDERS = ["YOUR_SECURE_1PSID_VALUE_HERE", "YOUR_SECURE_1PSIDTS_VALUE_HERE"]

if secure_1psid and secure_1psidts and secure_1psid not in PLACEHOLDERS and secure_1psidts not in PLACEHOLDERS:
    client = GeminiClient(secure_1psid, secure_1psidts)
    print("  🔐 Using Gemini cookies from environment variables")
else:
    client = GeminiClient()
    print("  🔐 Using Gemini cookies from browser (browser-cookie3)")

# ---------------------------------------------------------------------------
# Style context saved to analysis.yaml for downstream compatibility
# ---------------------------------------------------------------------------

STYLE_CONTEXT = {
    "visual_style": "2D Illustration",
    "style_subcategory": "Big cartoon heads, stick-figure bodies",
    "animation_complexity": "moderate",
    "color_palette": "vibrant digital colors",
    "rendering_style": "flat digital ink, thick black outlines",
}

# ---------------------------------------------------------------------------
# The style anchor injected into every prompt — matches the working example
# ---------------------------------------------------------------------------

STYLE_ANCHOR = (
    "crude minimalist cartoon in the style of early 2000s internet webcomics and MS Paint drawings, "
    "stick-figure bodies with detached oversized cartoon faces, highly detailed expressive faces with "
    "wrinkles and heavy eyelids on simple stick bodies, flat colors, simple black outlines, "
    "lazy and unrefined drawing style, low detail backgrounds, meme-like aesthetic, "
    "slightly off proportions, humorous vibe, cartoonish and amateurish look like old Newgrounds "
    "or Something Awful comics"
)

IMAGE_NEGATIVE = (
    "photorealistic, 3D render, CGI, anime, chibi, realistic body proportions, muscular, "
    "detailed hands, watermark, text overlay, subtitle, blurry, low quality, "
    "multiple panels, collage, grid layout, split screen, photo montage"
)

VIDEO_NEGATIVE = (
    "photorealistic, 3D render, CGI, watermark, text, subtitle, blurry, low quality, "
    "multiple panels, split screen, collage, static image, same expression every scene"
)

# ---------------------------------------------------------------------------
# Character profile prompt
# ---------------------------------------------------------------------------

CHARACTER_PROFILE_PROMPT = """\
You are a Character Designer for a crude minimalist cartoon series.

ART STYLE (mandatory for all characters):
- Body: thin black stick figure — lines only, no muscle, no bulk
- Head: OVERSIZED detached cartoon face (~40% of total figure height)
- Face: highly detailed and expressive — wrinkles, prominent nose, heavy eyelids
- Rendering: flat colors, thick black outlines, MS Paint / early 2000s webcomic aesthetic
- Characters MUST be culturally authentic to the story's setting

CULTURAL AUTHENTICITY RULES:
- Ancient Egyptian: dark olive/brown skin, kohl-lined eyes, white linen shendyt or dress, gold jewelry, sandals
- Viking Norse: pale skin, braided blonde/red hair, fur-trimmed tunic, horned or iron helmet, boots
- Han Dynasty Chinese: light skin, black topknot hair, silk hanfu robes, jade accessories
- Medieval European: pale skin, rough wool tunic, leather belt, simple boots
- Adapt EVERYTHING to the story's culture and time period

SCRIPT:
{script_text}

OUTPUT FORMAT — return ONLY this JSON:
{{
  "characters": [
    {{
      "name": "...",
      "role": "...",
      "cultural_context": "...",
      "appearance_anchor": "thin black stick figure, [hair], detached [skin color] face, [1-2 key facial features], [clothing in 3-4 words]",
      "visual_attributes": {{
        "skin_tone": "...",
        "hair": "...",
        "eyes": "...",
        "clothing": "...",
        "accessories": "..."
      }}
    }}
  ]
}}

CRITICAL: The "appearance_anchor" field MUST be SHORT — maximum 20 words.
Focus on the 3-4 most distinctive visual traits only.

GOOD EXAMPLES (use this brevity):
- "thin black stick figure, long wavy brown hair, detached white face with bored half-closed eyes, simple black tunic"
- "thin black stick figure, shaved head, detached dark brown face with bulging eyes, dazzling gold tunic"
- "small thin black stick figure, side-lock hair, detached light brown face with piercing eyes, white kilt and striped headdress"

BAD EXAMPLE (too long, too detailed):
- "a thin black stick figure with long wavy dark hair and a detached oversized olive-skinned face with heavy kohl-lined eyelids, visible teeth in a tense grimace, and a prominent nose, wearing an elegant sheer white linen kalasiris and a heavy gold usekh collar"

Keep it punchy. The model will infer the rest from the style anchor.
"""

# ---------------------------------------------------------------------------
# Image batch prompt
# ---------------------------------------------------------------------------

IMAGE_BATCH_PROMPT = """\
You are a prompt writer for an AI image generator.
Write one natural-language image prompt per script segment.

STYLE (include this in every prompt — do not change it):
{style_anchor}

CHARACTER APPEARANCES (use these exact descriptions every time a character appears):
{character_anchors}

RULES:
1. Each prompt is a single paragraph of natural language — NOT a JSON object, NOT bullet points.
2. Start every prompt with the style anchor words, then describe the scene.
3. Include the character's full appearance anchor phrase every time they appear.
4. Describe the environment in detail: setting, time of day, weather, colors, background elements.
5. Describe what the character is doing and their expression — match the script moment.
6. Vary expressions scene to scene — do NOT default to angry/intense unless the script calls for it.
7. End every prompt with the negative list: "negative: {negative}"
8. ONE single scene per prompt — no collage, no split screen, no multiple panels.

EXAMPLE of a good prompt (use this quality and style):
"A crude minimalist cartoon in the style of early 2000s internet webcomics and MS Paint drawings, snowy forest scene, tall brown tree trunks with green foliage in the background, light blue snow on the ground. In the foreground: a tall thin black stick figure with long wavy brown hair and a detached white face with a bored half-closed eyes expression, standing and holding a curved brown branch. To the right, a small stick figure with messy brown hair and a wide grin is sitting in the snow holding a leash attached to a solid black goat with horns. Green bushes poking through the snow. Simple black outlines, flat colors, lazy unrefined drawing style, meme-like aesthetic, slightly off proportions, humorous dark humor vibe. negative: photorealistic, 3D render, CGI, anime, realistic body, watermark, text, blurry, collage, split screen"

OUTPUT FORMAT — a JSON object with a "scenes" array:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "image_prompt": "full natural language prompt as a single string"
    }}
  ]
}}

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

Generate EXACTLY {batch_size} scenes. Return ONLY the JSON.
"""

# ---------------------------------------------------------------------------
# Video batch prompt
# ---------------------------------------------------------------------------

VIDEO_BATCH_PROMPT = """\
You are a prompt writer for an AI video generator (text-to-video, 6-second clips).
Write one natural-language video prompt per script segment.

STYLE (include this in every prompt):
{style_anchor}

CHARACTER APPEARANCES (use these exact descriptions — appearance is LOCKED across all clips):
{character_anchors}

RULES:
1. Each prompt is a single paragraph of natural language — NOT JSON, NOT bullet points.
2. Start with the style anchor, then describe the scene and characters (using their appearance anchors).
3. Character appearance must be NEUTRAL — describe what they look like, not their emotional state.
   WRONG: "the terrified protagonist with wide fearful eyes"
   RIGHT: "the protagonist — tall thin black stick figure with dark messy hair and a detached tan face"
4. After describing the scene, add motion: what physically moves during the 6 seconds.
   Use this format: "[0s-2s] action. [2s-4s] action. [4s-6s] action."
5. Include camera motion: static, slow push-in, pan left/right, slight zoom.
6. Include environment motion: dust drifting, torch flickering, leaves falling, water rippling.
7. End with: "negative: {negative}"
8. ONE continuous clip — no collage, no split screen.

EXAMPLE of a good video prompt:
"A crude minimalist cartoon in the style of early 2000s internet webcomics, dusty ancient Egyptian courtyard, sandy brown floor with flat coloring, mud-brick walls in the background with simple rectangular brick pattern. The protagonist — a tall thin black stick figure with dark messy hair and a detached tan face — stands in the center holding a broom. [0s-2s] Protagonist sweeps broom left to right, small dust clouds puff up from the floor. [2s-4s] Protagonist slows down, stick shoulders slump slightly, dust drifts upward. [4s-6s] Protagonist stops sweeping and leans on the broom handle, dust settles. Camera static medium shot throughout. Simple black outlines, flat colors, MS Paint aesthetic. negative: photorealistic, 3D render, CGI, watermark, text, blurry, collage, split screen, same expression every scene"

OUTPUT FORMAT — a JSON object with a "scenes" array:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "video_prompt": "full natural language prompt as a single string"
    }}
  ]
}}

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

Generate EXACTLY {batch_size} scenes. Return ONLY the JSON.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_block(text: str) -> str:
    """Extract JSON content, stripping markdown fences if present."""
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def _split_script_into_segments(script_text: str, num_segments: int) -> list[str]:
    """Split a script into N roughly equal segments."""
    paragraphs = re.split(r'\n\s*\n', script_text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if len(paragraphs) == 0:
        return [script_text] * num_segments
    if len(paragraphs) < num_segments:
        all_sentences = []
        for para in paragraphs:
            sents = re.split(r'(?<=[.!?…])\s+', para)
            all_sentences.extend([s.strip() for s in sents if s.strip()])
        units = all_sentences if len(all_sentences) >= num_segments else paragraphs
    else:
        units = paragraphs
    segments = []
    per_segment = len(units) / num_segments
    for i in range(num_segments):
        start = int(i * per_segment)
        end = int((i + 1) * per_segment)
        if i == num_segments - 1:
            end = len(units)
        chunk = " ".join(units[start:end])
        segments.append(chunk)
    return segments


def _build_character_anchors(char_profile: dict) -> str:
    """Build a character anchor string from the profile.

    Each character gets one line: their name and their appearance_anchor phrase.
    This is injected into every image and video batch prompt so the model
    uses the exact same description every scene.
    """
    characters = char_profile.get("characters", [])
    if not characters:
        return (
            "Main character: a tall thin black stick figure with an oversized detached cartoon face, "
            "flat colors, thick black outlines"
        )
    lines = []
    for c in characters:
        name = c.get("name", "Character")
        anchor = c.get("appearance_anchor", "")
        if not anchor:
            # Build from visual_attributes if appearance_anchor missing
            attrs = c.get("visual_attributes", {})
            skin = attrs.get("skin_tone", "white")
            hair = attrs.get("hair", "dark hair")
            clothing = attrs.get("clothing", "simple clothing")
            anchor = (
                f"a tall thin black stick figure with {hair} and a detached {skin} face "
                f"with expressive eyes, wearing {clothing}"
            )
        lines.append(f"{name}: {anchor}")
    return "\n".join(lines)


async def _get_character_profile(script_text: str) -> dict:
    """Extract character profiles from the script."""
    print("\n  👤 Defining characters for consistency...")
    prompt = CHARACTER_PROFILE_PROMPT.format(script_text=script_text)
    
    # Try different models in order of preference
    models_to_try = [Model.UNSPECIFIED, Model.G_3_0_FLASH, Model.G_3_0_PRO]
    
    for model in models_to_try:
        try:
            resp = await client.generate_content(prompt, model=model)
            json_text = _parse_json_block(resp.text)
            profile = json.loads(json_text)
            chars = profile.get("characters", [])
            print(f"  ✅ Defined {len(chars)} character(s): {[c.get('name') for c in chars]} (model: {model.model_name})")
            return profile
        except Exception as e:
            error_msg = str(e)
            if "405" in error_msg or "Method Not Allowed" in error_msg:
                print(f"  ⚠ Model {model.model_name} not available, trying next...")
                continue
            print(f"  ⚠ Failed with model {model.model_name}: {e}")
            continue
    
    print(f"  ⚠ All models failed for character profile generation")
    return {"characters": []}


# ---------------------------------------------------------------------------
# Main Flow
# ---------------------------------------------------------------------------

async def run_multimodal_flow(
    video_path: str,
    analysis_out: str,
    prompts_out: str,
    transcript_path: str | None = None,
    video_duration: float = 0.0,
    preview_duration: int = 60,
    clip_count: int = 0,
    script_path: str | None = None,
    enable_story_flow: bool = True,
):
    """Generate natural-language image and video prompts from a script."""
    print(f"🚀 Prompt Generation Mode — Style: Crude Cartoon / MS Paint Webcomic")

    await client.init(timeout=600, watchdog_timeout=300)

    if not script_path or not Path(script_path).exists():
        print("❌ Script path missing. Cannot generate prompts without script.")
        return

    script_text = Path(script_path).read_text(encoding="utf-8").strip()

    # 1. Define characters
    char_profile = await _get_character_profile(script_text)
    character_anchors = _build_character_anchors(char_profile)

    print(f"\n  Character anchors:\n{character_anchors}\n")

    # 2. Split script into segments
    segments = _split_script_into_segments(script_text, clip_count)

    print(f"\n[Batched Prompts] Generating {clip_count} scene prompts in batches of 8...")
    print(f"  Pass 1: Image prompts (natural language, style anchor + scene + characters)")
    print(f"  Pass 2: Video prompts (same + motion beats)")

    BATCH_SIZE = 8
    num_batches = math.ceil(clip_count / BATCH_SIZE)
    scene_tasks = [(i + 1, segments[i]) for i in range(clip_count)]

    # --- Pass 1: Image prompts ---
    image_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, clip_count)
        batch = scene_tasks[start_i:end_i]
        batch_size = len(batch)
        start_num = batch[0][0]
        end_num = batch[-1][0]

        segments_text = ""
        for sn, seg in batch:
            segments_text += f"\n--- SEGMENT {sn} ---\n{seg}\n"

        prompt = IMAGE_BATCH_PROMPT.format(
            style_anchor=STYLE_ANCHOR,
            character_anchors=character_anchors,
            negative=IMAGE_NEGATIVE,
            start_num=start_num,
            end_num=end_num,
            segments_text=segments_text,
            batch_size=batch_size,
        )

        print(f"\n  [Image] Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

        for attempt in range(1, 4):
            try:
                # Try different models in order of preference
                models_to_try = [Model.UNSPECIFIED, Model.G_3_0_FLASH, Model.G_3_0_PRO]
                
                for model in models_to_try:
                    try:
                        resp = await client.generate_content(prompt, model=model)
                        json_text = _parse_json_block(resp.text)
                        batch_data = json.loads(json_text)
                        batch_scenes = batch_data.get("scenes", [])
                        if batch_scenes:
                            for k, scene in enumerate(batch_scenes):
                                if k < len(batch):
                                    scene["scene_number"] = batch[k][0]
                            image_scenes_flat.extend(batch_scenes)
                            print(f"    ✅ Got {len(batch_scenes)} image prompts (model: {model.model_name})")
                            break
                    except Exception as model_error:
                        if "405" in str(model_error) or "Method Not Allowed" in str(model_error):
                            print(f"    ⚠ Model {model.model_name} not available, trying next...")
                            continue
                        raise model_error
                else:
                    raise Exception("All models failed")
                break
            except Exception as e:
                print(f"    ⚠ Attempt {attempt} failed: {e}")
                if attempt < 3:
                    wait_time = 10 * attempt
                    print(f"    Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)

    # --- Pass 2: Video prompts ---
    video_scenes_flat = []
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, clip_count)
        batch = scene_tasks[start_i:end_i]
        batch_size = len(batch)
        start_num = batch[0][0]
        end_num = batch[-1][0]

        segments_text = ""
        for sn, seg in batch:
            segments_text += f"\n--- SEGMENT {sn} ---\n{seg}\n"

        prompt = VIDEO_BATCH_PROMPT.format(
            style_anchor=STYLE_ANCHOR,
            character_anchors=character_anchors,
            negative=VIDEO_NEGATIVE,
            start_num=start_num,
            end_num=end_num,
            segments_text=segments_text,
            batch_size=batch_size,
        )

        print(f"\n  [Video] Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num}...")

        for attempt in range(1, 4):
            try:
                # Try different models in order of preference
                models_to_try = [Model.UNSPECIFIED, Model.G_3_0_FLASH, Model.G_3_0_PRO]
                
                for model in models_to_try:
                    try:
                        resp = await client.generate_content(prompt, model=model)
                        json_text = _parse_json_block(resp.text)
                        batch_data = json.loads(json_text)
                        batch_scenes = batch_data.get("scenes", [])
                        if batch_scenes:
                            for k, scene in enumerate(batch_scenes):
                                if k < len(batch):
                                    scene["scene_number"] = batch[k][0]
                            video_scenes_flat.extend(batch_scenes)
                            print(f"    ✅ Got {len(batch_scenes)} video prompts (model: {model.model_name})")
                            break
                    except Exception as model_error:
                        if "405" in str(model_error) or "Method Not Allowed" in str(model_error):
                            print(f"    ⚠ Model {model.model_name} not available, trying next...")
                            continue
                        raise model_error
                else:
                    raise Exception("All models failed")
                break
            except Exception as e:
                print(f"    ⚠ Attempt {attempt} failed: {e}")
                if attempt < 3:
                    wait_time = 10 * attempt
                    print(f"    Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)

    # --- Merge image + video ---
    video_map = {s["scene_number"]: s.get("video_prompt") for s in video_scenes_flat}
    all_scenes = []
    for scene in image_scenes_flat:
        sn = scene["scene_number"]
        scene["video_prompt"] = video_map.get(sn, (
            f"{STYLE_ANCHOR}. Scene {sn}. Character stands in environment. "
            "[0s-2s] Character stands still, ambient environment motion. "
            "[2s-4s] Slow camera push-in. [4s-6s] Scene holds. Camera static. "
            f"negative: {VIDEO_NEGATIVE}"
        ))
        all_scenes.append(scene)

    # Save prompts
    final_data = {
        "visual_style": STYLE_CONTEXT["visual_style"],
        "style_subcategory": STYLE_CONTEXT["style_subcategory"],
        "style_anchor": STYLE_ANCHOR,
        "character_profile": char_profile,
        "character_anchors": character_anchors,
        "scenes": all_scenes,
    }

    with open(prompts_out, "w", encoding="utf-8") as f:
        yaml.dump(final_data, f, sort_keys=False, allow_unicode=True)

    with open(analysis_out, "w", encoding="utf-8") as f:
        yaml.dump(STYLE_CONTEXT, f)

    print(f"\n✅ Prompt generation complete: {len(all_scenes)} scenes total.")
    if all_scenes:
        sample = all_scenes[0]
        print(f"\n  Sample image prompt (scene 1):\n  {str(sample.get('image_prompt',''))[:300]}...")
        print(f"\n  Sample video prompt (scene 1):\n  {str(sample.get('video_prompt',''))[:300]}...")
    
    # --- Story Context Enhancement ---
    if enable_story_flow and script_path and Path(script_path).exists():
        print(f"\n🎬 Enhancing prompts with story context...")
        try:
            success = enhance_prompts(
                prompts_path=prompts_out,
                script_path=script_path,
                output_path=prompts_out
            )
            if success:
                print(f"  ✅ Story context enhancement complete!")
            else:
                print(f"  ⚠ Story context enhancement failed, using base prompts")
        except Exception as e:
            print(f"  ⚠ Story context enhancement error: {e}")
            print(f"  Continuing with base prompts...")
    elif enable_story_flow:
        print(f"\n  ℹ Story flow enhancement skipped (no script file available)")
    else:
        print(f"\n  ℹ Story flow enhancement disabled")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Gemini Multimodal Orchestrator — Natural Language Prompt Generation."
    )
    parser.add_argument("video_path", help="Path to the video (or preview clip)")
    parser.add_argument("analysis_out", nargs="?", default="outputs/analysis.yaml")
    parser.add_argument("prompts_out", nargs="?", default="outputs/prompts.yaml")
    parser.add_argument("--transcript", default=None)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--preview-duration", type=int, default=60)
    parser.add_argument("--clip-count", type=int, default=0)
    parser.add_argument("--script", default=None)
    parser.add_argument("--enable-story-flow", action="store_true", default=True,
                        help="Enable story context enhancement (default: enabled)")
    parser.add_argument("--disable-story-flow", action="store_false", dest="enable_story_flow",
                        help="Disable story context enhancement")

    args = parser.parse_args()

    asyncio.run(run_multimodal_flow(
        args.video_path,
        args.analysis_out,
        args.prompts_out,
        transcript_path=args.transcript,
        video_duration=args.duration,
        preview_duration=args.preview_duration,
        clip_count=args.clip_count,
        script_path=args.script,
        enable_story_flow=args.enable_story_flow,
    ))
