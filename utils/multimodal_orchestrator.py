#!/usr/bin/env python3
"""
Gemini Multimodal Orchestrator — Adaptive Analysis + Batched Prompt Engineering.

Short videos (≤90s):
  Turn 1: Analyze the full video with SEALCaM → YAML
  Then: Batched prompt generation (segments of script → prompts)

Long videos (>90s):
  Turn 1: Analyze the PREVIEW clip (first 60s) with SEALCaM → YAML
  Turn 2: Reconstruct remaining scenes from transcript + visual patterns
  Then: Batched prompt generation (segments of script → prompts)

Key Design: Prompts are generated in batches of ~8 scenes, each in a
separate Gemini call with the full style context. This ensures ALL scenes
get generated reliably — no single call needs to produce 100+ scenes.
"""

import asyncio
import math
import os
import re
import sys
import json
import yaml
from pathlib import Path
from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model

# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

client = GeminiClient()


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """\
Analyze this video until the VERY LAST FRAME.
Break it down into distinct chronological scenes.
Describe ONLY the visual action and environment. Do NOT mention text overlays, subtitles, labels, or UI elements.

CRITICAL — VISUAL MEDIUM DETECTION:
First, determine the overall visual medium/style of this video. Be as specific as possible. Options include:
- "3D animation" (CGI, Blender/C4D style, stylized characters, smooth surfaces)
- "2D animation" (flat, cartoon, motion graphics, hand-drawn)
- "stick figure animation" (simple line-drawn characters, minimal detail)
- "motion graphics" (geometric shapes, kinetic typography, infographic-style)
- "screen recording" (software UI, desktop capture)
- "realistic" (live-action footage, real photography, documentary)
- "photorealistic CGI" (CGI that mimics real photography)
- "stop motion" (claymation, paper cutout, physical object animation)
- "mixed media" (combination of styles)
State this ONCE as the top-level `visual_style` field.

Also provide:
- `style_subcategory`: A more specific label (e.g. "cel-shaded anime", "Pixar-style CGI", "whiteboard animation", "gopro footage", "drone aerial", "2D explainer")
- `animation_complexity`: One of "simple" (stick figures, basic shapes, flat colors), "moderate" (stylized 3D, clean 2D with shading), or "complex" (photorealistic, high-detail textures, realistic lighting)

CRITICAL — PRECISION DESCRIPTIONS:
Your descriptions MUST be precise enough to recreate each frame exactly.
For each scene, describe:
- EXACT colors (not "blue" but "bright cerulean blue" or "deep navy")
- EXACT positions and compositions (what's on the left, right, center, foreground, background)
- EXACT shapes, sizes, and proportions of all objects
- EXACT textures and materials (smooth, rough, glossy, matte, translucent)
- The EXACT visual perspective and framing

Output the result as valid YAML with these top-level fields:
- visual_style: the detected medium
- style_subcategory: more specific label
- animation_complexity: "simple", "moderate", or "complex"
- color_palette: dominant colors and mood (e.g. "vibrant blues, clean whites, bright saturated colors")
- rendering_style: specific rendering details (e.g. "smooth plastic-like surfaces, soft shadows, stylized proportions")
- audio: brief audio mood description

And for each scene:
- scene_number, timestamp, duration
- description: HIGHLY detailed objective description — enough to perfectly recreate the frame
- subject: main element in focus (describe its exact appearance)
- environment: background/setting with exact colors and details
- action: specific movement occurring (describe simply and literally)
- lighting: lighting conditions only (e.g. "bright studio lighting", "warm golden hour")
- camera: camera perspective and movement
- key_colors: list of the 3-5 most prominent hex color codes visible in this scene

Also identify RECURRING CHARACTERS or subjects:
- recurring_characters: a top-level list of characters/subjects that appear in multiple scenes.
  For each, provide: name, visual_description (detailed enough to recreate consistently),
  and scenes_appeared_in (list of scene numbers).
"""

RECONSTRUCTION_PROMPT = """\
You previously analyzed the FIRST {preview_duration} seconds of a {total_duration:.0f}-second video.
That analysis captured {analyzed_scene_count} scenes covering timestamps 00:00 through ~{preview_end}.

Now I need you to RECONSTRUCT the remaining scenes (from ~{preview_end} to the end) using:

1. **The visual style and patterns** you observed in the first segment — the reconstructed scenes
   MUST follow the EXACT SAME:
   - Visual style: {visual_style}
   - Style subcategory: {style_subcategory}
   - Animation complexity: {animation_complexity}
   - Color palette: {color_palette}
   - Rendering style: {rendering_style}
   - Scene composition patterns (how subjects are framed, how backgrounds work, typical camera angles)
   - Scene transition flow (how scenes progress and connect to each other)

2. **The full transcript** of what the narrator says throughout the ENTIRE video:

---
{transcript}
---

CRITICAL RULES:
- Each reconstructed scene MUST look like it belongs in the same video as the analyzed scenes.
- Use the transcript to determine WHAT is being shown at each moment — the narrator describes
  or references what's on screen.
- Maintain the same pacing and scene duration patterns from the analyzed segment.
- Continue scene numbering from {next_scene_number}.
- Each scene should cover roughly the same duration as scenes in the analyzed segment.
- Describe subjects, environments, actions, lighting, and camera with the SAME level of
  precision and the SAME visual language as your original analysis.

Output ONLY the new scenes as valid YAML (a list under `scenes:`), continuing from scene {next_scene_number}.
Use the exact same field structure as the original analysis.
Do NOT repeat the global style fields — only output the new scenes.
"""

# Prompt for batched scene generation — given style context + script segments
# Generates RICH text-to-video prompts with TIMESTAMPED ACTION CHOREOGRAPHY
BATCH_PROMPT = """\
You are an expert Prompt Engineer for AI video generation. I'll give you:
1. A VIDEO STYLE CONTEXT describing the visual style of a video
2. A set of SCRIPT SEGMENTS — each segment is narration for one 6-second video clip

For EACH segment, generate a RICH text-to-video prompt with TIMESTAMPED ACTION CHOREOGRAPHY.
This is critical — a 6-second video needs specific actions choreographed across the full
duration, or the AI will fill empty time with random weird movements (waving, fidgeting, etc).

VIDEO STYLE CONTEXT:
- Visual style: {visual_style}
- Style subcategory: {style_subcategory}
- Animation complexity: {animation_complexity}
- Color palette: {color_palette}
- Rendering style: {rendering_style}
{character_context}

SCRIPT SEGMENTS (scenes {start_num} through {end_num}):
{segments_text}

For EACH segment above, generate:

**Video Prompt (MUST include timestamped choreography):**

Structure your prompt EXACTLY like this:

PART 1 — SCENE SETUP (1-2 sentences):
- Style: "{visual_style}, {style_subcategory}."
- Subject appearance (clothing, colors, features — be specific and consistent for recurring characters)
- Environment/setting (background, spatial layout, materials, atmosphere)
- Lighting and color mood

PART 2 — TIMESTAMPED ACTION CHOREOGRAPHY (2-3 beats covering FULL 6 seconds):
Break the 6 seconds into timed action beats. Each beat describes EXACTLY what happens
during that time window. This prevents the AI from inventing random filler movements.

Format each beat as: "[X.0s-Y.0s] description of action"

Example beats for a 6-second clip:
  "[0.0s-2.5s] The emperor stands still on his throne, gazing down with a stern expression. Camera: slow push-in from wide shot."
  "[2.5s-4.5s] He slowly raises his right hand and gestures dismissively. A servant in the background bows deeply."
  "[4.5s-6.0s] The emperor's expression softens slightly. He turns his head to the left. Camera holds steady, close-up."

Rules for action beats:
- COVER THE FULL 6 SECONDS — no gaps!
- Keep movements SLOW and DELIBERATE — AI handles subtle motion better than fast action
- Describe ONE specific action per beat (not multiple simultaneous actions)
- Include camera movement in at least one beat
- Movements should be physically plausible and natural
- Prefer: gazing, walking slowly, turning head, gesturing, leaning, reaching, nodding
- AVOID: waving, dancing, jumping, running, fighting (these create artifacts)

PART 3 — QUALITY TAG:
End with: "Cinematic quality, smooth natural motion, 24fps, hyper-detailed, no artifacts, no jitter."

**Negative Prompt:**
{negative_instructions}

OUTPUT: A single valid JSON object:
{{
  "scenes": [
    {{
      "scene_number": {start_num},
      "spanish_script": "(the script segment text)",
      "image_prompt": {{
         "prompt": "(same scene description without timestamps — kept for compatibility)",
         "negative_prompt": "...",
         "aspect_ratio": "16:9"
      }},
      "video_prompt": {{
         "prompt": "(FULL prompt: scene setup + [0.0s-2.5s] beat 1 + [2.5s-4.5s] beat 2 + [4.5s-6.0s] beat 3 + quality tag)",
         "duration": "6s",
         "camera_motion": "(primary camera movement used)"
      }}
    }}
  ]
}}

Generate EXACTLY {batch_size} scenes (one per segment). Return ONLY the JSON, no other text.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_yaml_block(text: str) -> str:
    """Extract YAML content, stripping markdown fences if present."""
    if "```yaml" in text:
        return text.split("```yaml")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def _parse_json_block(text: str) -> str:
    """Extract JSON content, stripping markdown fences if present."""
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def _load_transcript(transcript_path: str) -> str:
    """Load the English transcript, stripping headers and timestamp sections."""
    raw = Path(transcript_path).read_text(encoding="utf-8").strip()
    lines = raw.splitlines()
    text_lines = []
    skip_timestamps = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if "Timestamped" in stripped:
                skip_timestamps = True
            continue
        if skip_timestamps:
            if stripped:
                text_lines.append(stripped)
            continue
        if stripped:
            text_lines.append(stripped)

    return "\n".join(text_lines).strip() if text_lines else raw


def _merge_analysis_with_reconstructed(analysis_text: str, reconstructed_text: str) -> str:
    """Merge the original partial analysis YAML with reconstructed scenes."""
    try:
        original = yaml.safe_load(analysis_text)
        reconstructed = yaml.safe_load(reconstructed_text)

        if original is None:
            original = {}
        if reconstructed is None:
            reconstructed = {}

        original_scenes = original.get("scenes", [])
        new_scenes = reconstructed.get("scenes", [])

        # Append reconstructed scenes
        original["scenes"] = original_scenes + new_scenes

        return yaml.dump(original, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception as e:
        print(f"  ⚠ Could not merge YAML cleanly: {e}")
        return analysis_text + "\n" + reconstructed_text


def _split_script_into_segments(script_text: str, num_segments: int) -> list[str]:
    """Split a script into N roughly equal segments by paragraph.
    
    Merges small paragraphs and splits large ones to create balanced segments.
    Each segment becomes the narration for one 10-second video clip.
    """
    # Split into paragraphs
    paragraphs = re.split(r'\n\s*\n', script_text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if len(paragraphs) == 0:
        return [script_text] * num_segments

    # If fewer paragraphs than segments, further split by sentences
    if len(paragraphs) < num_segments:
        all_sentences = []
        for para in paragraphs:
            sents = re.split(r'(?<=[.!?…])\s+', para)
            all_sentences.extend([s.strip() for s in sents if s.strip()])
        units = all_sentences if len(all_sentences) >= num_segments else paragraphs
    else:
        units = paragraphs

    # Distribute units evenly across segments
    if len(units) <= num_segments:
        # Fewer units than segments — pad by repeating last
        segments = units[:]
        while len(segments) < num_segments:
            segments.append(segments[-1])
        return segments

    # More units than segments — merge groups
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


def _get_negative_instructions(visual_style: str) -> str:
    """Build negative prompt instructions based on detected style."""
    style_lower = visual_style.lower()
    if any(kw in style_lower for kw in ["3d", "cgi", "animation", "animated", "cartoon"]):
        return (
            '- Include: "photorealistic, live-action, photograph, DSLR, real skin texture, '
            'watermark, text, subtitle, blurry, low quality, text overlay, label, UI element"'
        )
    else:
        return (
            '- Include: "3D render, cartoon, anime, CGI, plastic texture, '
            'watermark, text, subtitle, blurry, low quality, text overlay, label, UI element"'
        )


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
):
    """Run the multimodal analysis + batched prompt engineering flow.

    For short videos (or when no transcript is provided), runs the original 2-turn flow.
    For long videos with a transcript, runs a 3-turn flow with scene reconstruction.
    
    If script_path is provided (Spanish script), prompts are generated in batches
    of ~8 scenes at a time, ensuring ALL clips get unique scene prompts.
    """
    is_long_video = transcript_path is not None and video_duration > 90

    if is_long_video:
        print(f"🚀 Long Video Mode — analyzing preview, then reconstructing {video_duration:.0f}s of content")
    else:
        print(f"🚀 Standard Mode — full video analysis")

    print(f"   Video/Preview: {video_path}")
    await client.init(timeout=600, watchdog_timeout=300)

    # Use non-thinking model for more reliable multimodal (video) processing
    MODELS_TO_TRY = [Model.G_3_0_FLASH, Model.G_3_0_PRO]
    MAX_RETRIES = 3
    BATCH_SIZE = 8  # Scenes per Gemini call for prompt generation

    # -----------------------------------------------------------------------
    # Turn 1: Visual Analysis (preview clip or full video)
    # -----------------------------------------------------------------------
    analysis_text = None
    chat = None

    for model in MODELS_TO_TRY:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"\n  Attempt {attempt}/{MAX_RETRIES} with {model}...")
                chat = client.start_chat(model=model)

                print("\n[Turn 1] Visual Analysis (with video)...")
                resp1 = await chat.send_message(ANALYSIS_PROMPT, files=[video_path])
                analysis_text = resp1.text
                break  # success
            except Exception as e:
                print(f"  ⚠ Attempt {attempt} failed: {e}")
                if attempt == MAX_RETRIES:
                    print(f"  All {MAX_RETRIES} attempts failed with {model}, trying next model...")
                    analysis_text = None
                else:
                    import time
                    wait = attempt * 10
                    print(f"  Waiting {wait}s before retry...")
                    await asyncio.sleep(wait)
        if analysis_text:
            break

    if not analysis_text:
        print("❌ All models and retries exhausted. Could not analyze the video.")
        sys.exit(1)

    analysis_text = _parse_yaml_block(analysis_text)
    print("✅ Analysis captured.")

    # -----------------------------------------------------------------------
    # Turn 2 (long videos only): Reconstruct remaining scenes
    # -----------------------------------------------------------------------
    if is_long_video:
        print("\n[Turn 2] Reconstructing remaining scenes from transcript + visual patterns...")

        try:
            analysis_data = yaml.safe_load(analysis_text)
        except Exception:
            analysis_data = {}

        analyzed_scenes = analysis_data.get("scenes", [])
        transcript_text = _load_transcript(transcript_path)

        preview_end_mm = preview_duration // 60
        preview_end_ss = preview_duration % 60
        preview_end = f"{preview_end_mm:02d}:{preview_end_ss:02d}"

        reconstruction_prompt = RECONSTRUCTION_PROMPT.format(
            preview_duration=preview_duration,
            total_duration=video_duration,
            analyzed_scene_count=len(analyzed_scenes),
            preview_end=preview_end,
            visual_style=analysis_data.get("visual_style", "unknown"),
            style_subcategory=analysis_data.get("style_subcategory", "unknown"),
            animation_complexity=analysis_data.get("animation_complexity", "moderate"),
            color_palette=analysis_data.get("color_palette", "unknown"),
            rendering_style=analysis_data.get("rendering_style", "unknown"),
            transcript=transcript_text,
            next_scene_number=len(analyzed_scenes) + 1,
        )

        try:
            resp2 = await chat.send_message(reconstruction_prompt)
            reconstructed_text = _parse_yaml_block(resp2.text)
            analysis_text = _merge_analysis_with_reconstructed(analysis_text, reconstructed_text)
            print(f"✅ Reconstructed scenes merged.")
        except Exception as e:
            print(f"  ⚠ Scene reconstruction failed: {e}")
            print("  Continuing with partial analysis only...")

    # Save analysis
    with open(analysis_out, "w", encoding="utf-8") as f:
        f.write(analysis_text)

    # -----------------------------------------------------------------------
    # Parse analysis for style context
    # -----------------------------------------------------------------------
    try:
        analysis_data = yaml.safe_load(analysis_text)
    except Exception:
        analysis_data = {}

    visual_style = analysis_data.get("visual_style", "3D animation")
    style_subcategory = analysis_data.get("style_subcategory", "stylized CGI")
    animation_complexity = analysis_data.get("animation_complexity", "moderate")
    color_palette = analysis_data.get("color_palette", "vibrant colors")
    rendering_style = analysis_data.get("rendering_style", "smooth surfaces, soft shadows")
    negative_instructions = _get_negative_instructions(visual_style)

    # -----------------------------------------------------------------------
    # Batched Prompt Generation
    # -----------------------------------------------------------------------
    if script_path and clip_count > 0 and Path(script_path).exists():
        # BATCHED MODE: Split script into segments, generate prompts in batches
        script_text = Path(script_path).read_text(encoding="utf-8").strip()
        segments = _split_script_into_segments(script_text, clip_count)

        print(f"\n[Batched Prompts] Generating {clip_count} scene prompts in batches of {BATCH_SIZE}...")
        print(f"  Style: {visual_style} / {style_subcategory}")

        all_scenes = []
        num_batches = math.ceil(clip_count / BATCH_SIZE)

        for batch_idx in range(num_batches):
            start_i = batch_idx * BATCH_SIZE
            end_i = min(start_i + BATCH_SIZE, clip_count)
            batch_segments = segments[start_i:end_i]
            batch_size = len(batch_segments)
            start_num = start_i + 1
            end_num = end_i

            # Format segments for the prompt
            segments_text = ""
            for j, seg in enumerate(batch_segments):
                scene_num = start_i + j + 1
                segments_text += f"\n--- SEGMENT {scene_num} ---\n{seg}\n"

            # Build character context from analysis if available
            character_context = ""
            recurring_chars = analysis_data.get("recurring_characters", [])
            if recurring_chars:
                char_lines = ["\nRECURRING CHARACTERS (maintain visual consistency):"]
                for ch in recurring_chars[:5]:
                    name = ch.get("name", "unknown")
                    desc = ch.get("visual_description", "")
                    if desc:
                        char_lines.append(f"  - {name}: {desc}")
                character_context = "\n".join(char_lines)

            prompt = BATCH_PROMPT.format(
                visual_style=visual_style,
                style_subcategory=style_subcategory,
                animation_complexity=animation_complexity,
                color_palette=color_palette,
                rendering_style=rendering_style,
                character_context=character_context,
                start_num=start_num,
                end_num=end_num,
                segments_text=segments_text,
                negative_instructions=negative_instructions,
                batch_size=batch_size,
            )

            print(f"\n  Batch {batch_idx + 1}/{num_batches}: scenes {start_num}-{end_num} ({batch_size} scenes)...")

            # Each batch gets a fresh chat for reliability
            batch_done = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    batch_chat = client.start_chat(model=MODELS_TO_TRY[0])
                    resp = await batch_chat.send_message(prompt)
                    json_text = _parse_json_block(resp.text)
                    batch_data = json.loads(json_text)
                    batch_scenes = batch_data.get("scenes", [])

                    if len(batch_scenes) > 0:
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
                print(f"    ❌ Batch {batch_idx + 1} failed after {MAX_RETRIES} attempts — skipping")

        # Combine all batches into final output
        final_data = {
            "visual_style": visual_style,
            "style_subcategory": style_subcategory,
            "animation_complexity": animation_complexity,
            "scenes": all_scenes,
        }

        with open(prompts_out, "w", encoding="utf-8") as f:
            yaml.dump(final_data, f, sort_keys=False, allow_unicode=True)

        print(f"\n✅ Batched prompt generation complete: {len(all_scenes)} scenes total.")

    else:
        # SINGLE-SHOT MODE (fallback when no script is provided)
        turn_label = "Turn 3" if is_long_video else "Turn 2"
        print(f"\n[{turn_label}] Single-shot prompts (no script provided)...")

        if clip_count > 0:
            clip_count_instruction = (
                f"Generate EXACTLY {clip_count} scenes. Each scene = 10-second video clip.\n"
                f"Distribute visual concepts evenly across all {clip_count} scenes."
            )
        else:
            clip_count_instruction = (
                "Generate one scene per visual concept from the analysis.\n"
                "Each scene will become a 10-second video clip."
            )

        # Build a simpler unified prompt for single-shot mode
        single_shot_prompt = f"""\
Now generate clone-quality image and video prompts for the scenes you analyzed.

{clip_count_instruction}

For each scene, generate:
1. Image Prompt — reproduce the exact frame from analysis, starting with the style prefix "{visual_style}, {style_subcategory}"
2. Video Prompt — simple animation starting with "Animate this exact image:"
3. Spanish script — viral Spanish narration for the scene

OUTPUT as valid JSON:
{{{{
  "visual_style": "{visual_style}",
  "style_subcategory": "{style_subcategory}",
  "animation_complexity": "{animation_complexity}",
  "scenes": [
    {{{{
      "scene_number": 1,
      "spanish_script": "...",
      "image_prompt": {{{{ "prompt": "...", "negative_prompt": "...", "aspect_ratio": "16:9" }}}},
      "video_prompt": {{{{ "prompt": "Animate this exact image: ...", "duration": "10s", "camera_motion": "..." }}}}
    }}}}
  ]
}}}}
"""

        try:
            resp_final = await chat.send_message(single_shot_prompt)
            prompts_text = _parse_json_block(resp_final.text)
            data = json.loads(prompts_text)
            with open(prompts_out, "w", encoding="utf-8") as f:
                yaml.dump(data, f, sort_keys=False, allow_unicode=True)
            scene_count = len(data.get("scenes", []))
            print(f"✅ Clone-quality prompts generated: {scene_count} scenes.")
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse Gemini's JSON response: {e}")
            print("Raw response:", resp_final.text[:2000])
            sys.exit(1)
        except Exception as e:
            print(f"❌ Prompt generation failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Gemini Multimodal Orchestrator — Adaptive Analysis + Batched Prompts."
    )
    parser.add_argument("video_path", help="Path to the video (or preview clip)")
    parser.add_argument("analysis_out", nargs="?", default="outputs/analysis.yaml",
                        help="Path for analysis YAML output")
    parser.add_argument("prompts_out", nargs="?", default="outputs/prompts.yaml",
                        help="Path for prompts YAML output")
    parser.add_argument("--transcript", default=None,
                        help="Path to English transcript (enables long-video reconstruction)")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Total video duration in seconds (for long-video mode)")
    parser.add_argument("--preview-duration", type=int, default=60,
                        help="How many seconds the preview clip covers (default: 60)")
    parser.add_argument("--clip-count", type=int, default=0,
                        help="Exact number of scene prompts to generate (0 = auto from analysis)")
    parser.add_argument("--script", default=None,
                        help="Path to Spanish script (enables batched prompt generation)")

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
    ))
