#!/usr/bin/env python3
"""
Quick test for the updated wojak/rage-comic style prompts.

Tests the style anchor, character profile prompt template, and
enhance_prompts pipeline with a single paragraph of script text.
No Gemini API needed — validates the prompt strings and enhancement logic.
"""

import sys
import tempfile
import yaml
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Validate the style anchor contains wojak keywords
# ---------------------------------------------------------------------------

def test_style_anchor_contains_wojak():
    from utils.multimodal_orchestrator import STYLE_ANCHOR
    required_phrases = [
        "wojak",
        "rage comic",
        "feels guy",
        "heavy eyelids",
        "no body fill",
        "vertical line for torso",
        "no clothing shape",
    ]
    missing = [p for p in required_phrases if p.lower() not in STYLE_ANCHOR.lower()]
    assert not missing, f"STYLE_ANCHOR missing phrases: {missing}\n\nActual:\n{STYLE_ANCHOR}"
    print(f"  ✓ STYLE_ANCHOR contains all required keywords (including line-body spec)")
    print(f"    Preview: {STYLE_ANCHOR[:140]}...")


# ---------------------------------------------------------------------------
# 2. Validate the character profile prompt template enforces wojak anchors
# ---------------------------------------------------------------------------

def test_character_profile_prompt_enforces_wojak():
    from utils.multimodal_orchestrator import CHARACTER_PROFILE_PROMPT
    required = [
        "wojak",
        "feels guy",
        "sad heavy-lidded eyes",
        "appearance_anchor",
        "detached wojak-style",
    ]
    missing = [p for p in required if p.lower() not in CHARACTER_PROFILE_PROMPT.lower()]
    assert not missing, f"CHARACTER_PROFILE_PROMPT missing: {missing}"
    print(f"  ✓ CHARACTER_PROFILE_PROMPT enforces wojak face style")


# ---------------------------------------------------------------------------
# 3. Validate the image batch prompt example uses wojak language
# ---------------------------------------------------------------------------

def test_image_batch_prompt_example_uses_wojak():
    from utils.multimodal_orchestrator import IMAGE_BATCH_PROMPT
    assert "wojak" in IMAGE_BATCH_PROMPT.lower(), "IMAGE_BATCH_PROMPT example missing 'wojak'"
    assert "sad heavy-lidded eyes" in IMAGE_BATCH_PROMPT.lower(), \
        "IMAGE_BATCH_PROMPT missing 'sad heavy-lidded eyes' rule"
    print(f"  ✓ IMAGE_BATCH_PROMPT example uses wojak language")


# ---------------------------------------------------------------------------
# 4. Validate the video batch prompt enforces wojak face description
# ---------------------------------------------------------------------------

def test_video_batch_prompt_enforces_wojak():
    from utils.multimodal_orchestrator import VIDEO_BATCH_PROMPT
    assert "wojak-style" in VIDEO_BATCH_PROMPT.lower(), \
        "VIDEO_BATCH_PROMPT missing wojak-style face rule"
    print(f"  ✓ VIDEO_BATCH_PROMPT enforces wojak-style face")


# ---------------------------------------------------------------------------
# 5. Validate _build_character_anchors fallback uses wojak language
# ---------------------------------------------------------------------------

def test_build_character_anchors_fallback_uses_wojak():
    from utils.multimodal_orchestrator import _build_character_anchors
    # Empty profile → fallback
    result = _build_character_anchors({"characters": []})
    assert "wojak" in result.lower(), f"Fallback anchor missing 'wojak': {result}"
    assert "no body fill" in result.lower() or "5 lines" in result.lower(), \
        f"Fallback anchor missing line-body spec: {result}"
    print(f"  ✓ _build_character_anchors fallback uses line-body + wojak language")


def test_build_character_anchors_with_profile():
    from utils.multimodal_orchestrator import _build_character_anchors
    profile = {
        "characters": [
            {
                "name": "The Protagonist",
                "appearance_anchor": "pure black line stick figure (5 lines only, no body fill), long brown hair, detached wojak-style white face with sad heavy-lidded eyes, black tunic floating"
            }
        ]
    }
    result = _build_character_anchors(profile)
    assert "The Protagonist" in result
    assert "wojak-style" in result.lower()
    assert "no body fill" in result.lower() or "5 lines" in result.lower()
    print(f"  ✓ _build_character_anchors with profile preserves line-body + wojak anchor")
    print(f"    Result: {result}")


# ---------------------------------------------------------------------------
# 6. Full enhance_prompts pipeline with a single paragraph
# ---------------------------------------------------------------------------

SINGLE_PARAGRAPH_SCRIPT = """
In the year 1644, a young woodcutter named Wei lived in a small village outside Beijing.
He spent his days chopping wood in the forest, dreaming of a better life.
One morning, a strange white carriage appeared at the edge of the village.
A palace recruiter stepped out, holding a steamed bun and an imperial scroll.
Wei had no idea his life was about to change forever.
"""

TEST_PROMPTS_WOJAK = {
    "visual_style": "2D Illustration",
    "style_subcategory": "Wojak/rage comic faces on stick-figure bodies",
    "style_anchor": (
        "crude minimalist cartoon in the style of wojak and rage comics, "
        "stick-figure bodies with detached oversized wojak-style faces, "
        "faces look like pale realistic human faces drawn crudely — the classic 'feels guy' / wojak meme face, "
        "simple sad or tired human-like face with realistic nose and heavy eyelids, "
        "flat colors, simple thick black outlines, MS Paint aesthetic"
    ),
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


def test_enhance_prompts_single_paragraph():
    """Run enhance_prompts on a single paragraph and verify wojak style is preserved."""
    from utils.enhance_prompts import enhance_prompts

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        prompts_file = tmpdir / "prompts.yaml"
        with open(prompts_file, "w", encoding="utf-8") as f:
            yaml.dump(TEST_PROMPTS_WOJAK, f, sort_keys=False, allow_unicode=True)

        script_file = tmpdir / "script.txt"
        script_file.write_text(SINGLE_PARAGRAPH_SCRIPT.strip(), encoding="utf-8")

        success = enhance_prompts(str(prompts_file), str(script_file))
        assert success, "enhance_prompts returned False"

        with open(prompts_file, "r", encoding="utf-8") as f:
            enhanced = yaml.safe_load(f)

        scenes = enhanced.get("scenes", [])
        assert len(scenes) == 2, f"Expected 2 scenes, got {len(scenes)}"

        print(f"\n  ✓ enhance_prompts ran successfully on single paragraph")

        for scene in scenes:
            sn = scene["scene_number"]
            for field in ("image_prompt", "video_prompt"):
                prompt = scene.get(field, "")
                if isinstance(prompt, dict):
                    prompt = prompt.get("prompt", "")

                # Must not exceed 950 chars
                assert len(prompt) <= 950, \
                    f"Scene {sn} {field} exceeds 950 chars: {len(prompt)}"

                # Style anchor must still be present (not stripped)
                assert "wojak" in prompt.lower(), \
                    f"Scene {sn} {field} lost 'wojak' keyword!\nPrompt: {prompt}"

                print(f"  ✓ Scene {sn} {field}: {len(prompt)} chars, wojak style preserved")

        # Show the enhanced prompts
        print("\n" + "=" * 70)
        print("ENHANCED PROMPTS OUTPUT")
        print("=" * 70)
        for scene in scenes:
            sn = scene["scene_number"]
            img = scene.get("image_prompt", "")
            vid = scene.get("video_prompt", "")
            print(f"\n--- Scene {sn} ---")
            print(f"IMAGE ({len(img)} chars):\n  {img}")
            print(f"\nVIDEO ({len(vid)} chars):\n  {vid}")

        return True


# ---------------------------------------------------------------------------
# 7. Verify location is appended (not prepended) so style anchor leads
# ---------------------------------------------------------------------------

def test_location_appended_not_prepended():
    from utils.enhance_prompts import ensure_location_in_prompt
    prompt = "crude minimalist cartoon in the style of wojak and rage comics, Wei stands alone."
    result = ensure_location_in_prompt(prompt, "palace")
    # Style anchor must still be at the start
    assert result.startswith("crude minimalist cartoon"), \
        f"Style anchor was displaced! Result starts with: {result[:60]}"
    # Location must be somewhere in the prompt
    assert "palace" in result.lower(), f"Location not added: {result}"
    # Location must NOT be at the very start
    assert not result.lower().startswith("setting:"), \
        f"Location was prepended (bad): {result[:60]}"
    print(f"  ✓ Location appended at end, style anchor leads")
    print(f"    Result: {result}")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

def main():
    tests = [
        ("Style anchor contains wojak keywords",        test_style_anchor_contains_wojak),
        ("Character profile prompt enforces wojak",     test_character_profile_prompt_enforces_wojak),
        ("Image batch prompt example uses wojak",       test_image_batch_prompt_example_uses_wojak),
        ("Video batch prompt enforces wojak face",      test_video_batch_prompt_enforces_wojak),
        ("_build_character_anchors fallback uses wojak",test_build_character_anchors_fallback_uses_wojak),
        ("_build_character_anchors with profile",       test_build_character_anchors_with_profile),
        ("Location appended, not prepended",            test_location_appended_not_prepended),
        ("enhance_prompts single paragraph",            test_enhance_prompts_single_paragraph),
    ]

    print("\n" + "=" * 70)
    print("  WOJAK STYLE PROMPT TEST SUITE")
    print("=" * 70)

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n▶ {name}")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    if failed == 0:
        print(f"  ✅ ALL {passed} TESTS PASSED")
    else:
        print(f"  ❌ {failed} FAILED / {passed} PASSED")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
