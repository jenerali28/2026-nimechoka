#!/usr/bin/env python3
"""
Print the full prompts that would be sent to the image/video generator.
Shows exactly what Gemini receives as instructions, and what the final
enhanced scene prompts look like — no truncation.
"""

import sys
import tempfile
import yaml
from pathlib import Path

# ── single paragraph script ──────────────────────────────────────────────────
SCRIPT = """
In the year 1644, a young woodcutter named Wei lived in a small village outside Beijing.
He spent his days chopping wood in the forest, dreaming of a better life.
One morning, a strange white carriage appeared at the edge of the village.
A palace recruiter stepped out, holding a steamed bun and an imperial scroll.
Wei had no idea his life was about to change forever.
"""

# ── minimal prompts.yaml that mirrors what the pipeline produces ──────────────
TEST_PROMPTS = {
    "visual_style": "2D Illustration",
    "style_subcategory": "Wojak/rage comic faces on stick-figure bodies",
    "style_anchor": None,   # filled below from STYLE_ANCHOR
    "character_profile": {
        "characters": [
            {
                "name": "Wei",
                "role": "Protagonist",
                "appearance_anchor": (
                    "pure black line stick figure (5 lines only, no body fill), "
                    "black topknot hair, "
                    "detached wojak-style pale face with sad heavy-lidded eyes, grey tunic floating"
                ),
            },
            {
                "name": "The Recruiter",
                "role": "Palace Scout",
                "appearance_anchor": (
                    "pure black line stick figure (5 lines only, no body fill), "
                    "official cap, "
                    "detached wojak-style pale face with sad heavy-lidded eyes, white tunic floating"
                ),
            },
        ]
    },
    "scenes": [
        {
            "scene_number": 1,
            "image_prompt": (
                "crude minimalist cartoon in the style of wojak and rage comics, "
                "snowy forest with tall brown tree trunks. "
                "Wei stands alone holding an axe, looking confused."
            ),
            "video_prompt": (
                "crude minimalist cartoon in the style of wojak and rage comics, "
                "forest clearing. Wei stands still. "
                "[0s-2s] Wei raises axe. [2s-4s] Axe comes down on log. [4s-6s] Wei pauses, looks around."
            ),
        },
        {
            "scene_number": 2,
            "image_prompt": (
                "crude minimalist cartoon in the style of wojak and rage comics, "
                "village road. A white carriage arrives. "
                "The Recruiter steps out holding a steamed bun."
            ),
            "video_prompt": (
                "crude minimalist cartoon in the style of wojak and rage comics, "
                "village road. White carriage rolls in. "
                "[0s-2s] Carriage bounces to a stop. [2s-4s] Door swings open. [4s-6s] Recruiter steps out."
            ),
        },
    ],
}


def sep(title=""):
    width = 72
    if title:
        pad = (width - len(title) - 2) // 2
        print("─" * pad + f" {title} " + "─" * pad)
    else:
        print("─" * width)


def main():
    from utils.multimodal_orchestrator import (
        STYLE_ANCHOR,
        IMAGE_NEGATIVE,
        VIDEO_NEGATIVE,
        IMAGE_BATCH_PROMPT,
        VIDEO_BATCH_PROMPT,
        _build_character_anchors,
    )
    from utils.enhance_prompts import enhance_prompts

    TEST_PROMPTS["style_anchor"] = STYLE_ANCHOR
    character_anchors = _build_character_anchors(TEST_PROMPTS["character_profile"])

    # ── 1. STYLE ANCHOR ───────────────────────────────────────────────────────
    print("\n")
    sep("STYLE ANCHOR (injected into every prompt)")
    print(STYLE_ANCHOR)

    # ── 2. CHARACTER ANCHORS ──────────────────────────────────────────────────
    print()
    sep("CHARACTER ANCHORS")
    print(character_anchors)

    # ── 3. FULL IMAGE BATCH PROMPT (what Gemini receives) ────────────────────
    segments_text = "\n--- SEGMENT 1 ---\n" + SCRIPT.strip() + "\n"
    full_image_prompt = IMAGE_BATCH_PROMPT.format(
        style_anchor=STYLE_ANCHOR,
        character_anchors=character_anchors,
        negative=IMAGE_NEGATIVE,
        start_num=1,
        end_num=1,
        segments_text=segments_text,
        batch_size=1,
    )
    print()
    sep("FULL IMAGE BATCH PROMPT  (sent to Gemini)")
    print(full_image_prompt)

    # ── 4. FULL VIDEO BATCH PROMPT (what Gemini receives) ────────────────────
    full_video_prompt = VIDEO_BATCH_PROMPT.format(
        style_anchor=STYLE_ANCHOR,
        character_anchors=character_anchors,
        negative=VIDEO_NEGATIVE,
        start_num=1,
        end_num=1,
        segments_text=segments_text,
        batch_size=1,
    )
    print()
    sep("FULL VIDEO BATCH PROMPT  (sent to Gemini)")
    print(full_video_prompt)

    # ── 5. ENHANCED SCENE PROMPTS (after enhance_prompts post-processing) ────
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        prompts_file = tmpdir / "prompts.yaml"
        script_file  = tmpdir / "script.txt"

        with open(prompts_file, "w", encoding="utf-8") as f:
            yaml.dump(TEST_PROMPTS, f, sort_keys=False, allow_unicode=True)
        script_file.write_text(SCRIPT.strip(), encoding="utf-8")

        enhance_prompts(str(prompts_file), str(script_file))

        with open(prompts_file, "r", encoding="utf-8") as f:
            enhanced = yaml.safe_load(f)

    print()
    sep("ENHANCED SCENE PROMPTS  (final output written to prompts.yaml)")
    for scene in enhanced.get("scenes", []):
        sn = scene["scene_number"]
        img = scene.get("image_prompt", "")
        vid = scene.get("video_prompt", "")
        print(f"\n┌─ Scene {sn} — IMAGE PROMPT ({len(img)} chars)")
        print(img)
        print(f"\n└─ Scene {sn} — VIDEO PROMPT ({len(vid)} chars)")
        print(vid)
        print()

    sep()


if __name__ == "__main__":
    main()
