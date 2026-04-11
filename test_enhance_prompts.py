#!/usr/bin/env python3
"""
Test script for enhance_prompts.py module.

Creates a minimal test case with prompts and script to verify enhancement works.
"""

import tempfile
import yaml
from pathlib import Path
from utils.enhance_prompts import enhance_prompts

# Test data
TEST_PROMPTS = {
    'visual_style': 'Crude minimalist cartoon',
    'style_subcategory': 'MS Paint webcomic',
    'character_profile': {
        'characters': [
            {
                'name': 'Protagonist',
                'role': 'main character',
                'appearance_anchor': 'thin black stick figure, long dark hair, detached olive face, white dress'
            },
            {
                'name': 'Pharaoh',
                'role': 'antagonist',
                'appearance_anchor': 'thin black stick figure, shaved head, detached tan face, gold tunic'
            }
        ]
    },
    'scenes': [
        {
            'scene_number': 1,
            'image_prompt': 'A desert landscape. The Protagonist stands alone looking at the horizon.',
            'video_prompt': 'The Protagonist stands in the desert. [0s-2s] Wind blows sand. [2s-4s] Character looks around. [4s-6s] Scene holds.'
        },
        {
            'scene_number': 2,
            'image_prompt': 'Inside a palace courtyard. The Protagonist sweeps the floor while the Pharaoh watches.',
            'video_prompt': 'The Protagonist sweeps in the courtyard. [0s-2s] Sweeping motion. [2s-4s] Pharaoh enters. [4s-6s] Both characters present.'
        },
        {
            'scene_number': 3,
            'image_prompt': 'A dark chamber. The Protagonist sits alone, looking worried.',
            'video_prompt': 'The Protagonist sits in darkness. [0s-2s] Character shifts nervously. [2s-4s] Shadows move. [4s-6s] Scene holds.'
        }
    ]
}

TEST_SCRIPT = """
The Protagonist lived in ancient Egypt as a concubine. She spent her days in the desert, 
dreaming of freedom. The hot sun beat down on the sand as she stood alone.

One day, she was brought to the palace courtyard. The Pharaoh watched her closely as she 
performed her duties. The tension in the air was palpable. She swept the dusty floor 
while trying to avoid his gaze.

That night, she was locked in a dark chamber. Fear gripped her heart as she sat alone 
in the darkness. The walls seemed to close in around her. She wondered if she would 
ever see the light again.
"""


def test_enhance_prompts():
    """Test the enhance_prompts function."""
    print("\n🧪 Testing enhance_prompts module...\n")
    
    # Create temporary files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Write test prompts
        prompts_file = tmpdir / "prompts.yaml"
        with open(prompts_file, 'w', encoding='utf-8') as f:
            yaml.dump(TEST_PROMPTS, f, sort_keys=False, allow_unicode=True)
        
        print(f"✓ Created test prompts: {prompts_file}")
        
        # Write test script
        script_file = tmpdir / "script.txt"
        script_file.write_text(TEST_SCRIPT.strip(), encoding='utf-8')
        
        print(f"✓ Created test script: {script_file}")
        
        # Run enhancement
        print("\n📝 Running enhancement...\n")
        success = enhance_prompts(str(prompts_file), str(script_file))
        
        if not success:
            print("\n❌ Enhancement failed!")
            return False
        
        # Read enhanced prompts
        with open(prompts_file, 'r', encoding='utf-8') as f:
            enhanced_data = yaml.safe_load(f)
        
        print("\n✅ Enhancement complete!\n")
        print("=" * 70)
        print("ENHANCED PROMPTS SAMPLE")
        print("=" * 70)
        
        # Show first two scenes
        for i in range(min(2, len(enhanced_data['scenes']))):
            scene = enhanced_data['scenes'][i]
            print(f"\nScene {scene['scene_number']}:")
            print("-" * 70)
            
            # Get image prompt
            image_prompt = scene.get('image_prompt', '')
            if isinstance(image_prompt, dict):
                image_prompt = image_prompt.get('prompt', '')
            
            print(f"Image Prompt ({len(image_prompt)} chars):")
            print(f"  {image_prompt[:200]}...")
            
            # Get video prompt
            video_prompt = scene.get('video_prompt', '')
            if isinstance(video_prompt, dict):
                video_prompt = video_prompt.get('prompt', '')
            
            print(f"\nVideo Prompt ({len(video_prompt)} chars):")
            print(f"  {video_prompt[:200]}...")
        
        print("\n" + "=" * 70)
        
        # Verify enhancements
        print("\n🔍 Verification:")
        
        scene1 = enhanced_data['scenes'][0]
        scene2 = enhanced_data['scenes'][1]
        
        # Scene 1 should NOT have "Continuing from" (it's the first scene)
        image1 = scene1.get('image_prompt', '')
        if isinstance(image1, dict):
            image1 = image1.get('prompt', '')
        
        if "Continuing from" not in image1:
            print("  ✓ Scene 1 does not have 'Continuing from' (correct)")
        else:
            print("  ✗ Scene 1 has 'Continuing from' (should not)")
        
        # Scene 2 should have "Continuing from"
        image2 = scene2.get('image_prompt', '')
        if isinstance(image2, dict):
            image2 = image2.get('prompt', '')
        
        if "Continuing from" in image2:
            print("  ✓ Scene 2 has 'Continuing from' (correct)")
        else:
            print("  ✗ Scene 2 does not have 'Continuing from' (should have)")
        
        # Check character descriptions are injected
        if "thin black stick figure" in image1.lower():
            print("  ✓ Character descriptions injected (correct)")
        else:
            print("  ✗ Character descriptions not found (should be present)")
        
        # Check prompt lengths
        all_under_limit = True
        for scene in enhanced_data['scenes']:
            for prompt_key in ['image_prompt', 'video_prompt']:
                prompt = scene.get(prompt_key, '')
                if isinstance(prompt, dict):
                    prompt = prompt.get('prompt', '')
                
                if len(prompt) > 950:
                    print(f"  ✗ Scene {scene['scene_number']} {prompt_key} exceeds 950 chars: {len(prompt)}")
                    all_under_limit = False
        
        if all_under_limit:
            print("  ✓ All prompts under 950 characters (correct)")
        
        return True


if __name__ == "__main__":
    try:
        success = test_enhance_prompts()
        if success:
            print("\n✅ All tests passed!")
        else:
            print("\n❌ Tests failed!")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests for task 5.1 — transition logic and emotional visual cues
# ─────────────────────────────────────────────────────────────────────────────

from utils.enhance_prompts import (
    build_transition_hint,
    _is_dramatic_tone_shift,
    _get_visual_cue_for_tone,
)


def test_location_change_produces_scene_shifts():
    """5.1.1 — Location change adds 'Scene shifts to [new location]'."""
    hint = build_transition_hint(
        current_location="palace",
        prev_location="desert",
        current_tone="neutral",
        prev_tone="neutral",
    )
    assert "Scene shifts to palace" in hint, f"Expected 'Scene shifts to palace', got: {hint!r}"


def test_same_location_produces_still_in():
    """5.1.2 — Same location adds 'Still in [location]'."""
    hint = build_transition_hint(
        current_location="palace",
        prev_location="palace",
        current_tone="neutral",
        prev_tone="neutral",
    )
    assert "Still in palace" in hint, f"Expected 'Still in palace', got: {hint!r}"


def test_unknown_location_produces_no_location_hint():
    """Unknown location should not produce a location hint."""
    hint = build_transition_hint(
        current_location="unknown location",
        prev_location="desert",
        current_tone="neutral",
        prev_tone="neutral",
    )
    assert "Scene shifts" not in hint
    assert "Still in" not in hint


def test_dramatic_tone_shift_adds_visual_cue():
    """5.1.3 — Dramatic tone change adds a visual cue (lighting/camera)."""
    # calm (0) → tense (3): jump of 3, should be dramatic
    hint = build_transition_hint(
        current_location="palace",
        prev_location="palace",
        current_tone="tense",
        prev_tone="calm",
    )
    assert "Lighting shifts" in hint, f"Expected visual cue in hint, got: {hint!r}"
    assert "tight framing" in hint or "dark lighting" in hint, f"Expected tense visual cue, got: {hint!r}"


def test_minor_tone_shift_no_visual_cue():
    """Minor tone shift (adjacent levels) should NOT add a visual cue."""
    # neutral (1) → action (2): jump of 1, not dramatic
    hint = build_transition_hint(
        current_location="palace",
        prev_location="palace",
        current_tone="action",
        prev_tone="neutral",
    )
    assert "Lighting shifts" not in hint, f"Should not have visual cue for minor shift, got: {hint!r}"


def test_hint_is_at_most_two_sentences():
    """5.1.4 — Hint must be at most 2 sentences (1-2 sentences of context)."""
    # Location change + dramatic tone shift → 2 hints
    hint = build_transition_hint(
        current_location="temple",
        prev_location="desert",
        current_tone="dramatic",
        prev_tone="calm",
    )
    # Count sentences by splitting on ". "
    sentences = [s for s in hint.split(". ") if s.strip()]
    assert len(sentences) <= 2, f"Expected at most 2 sentences, got {len(sentences)}: {hint!r}"


def test_is_dramatic_tone_shift_large_jump():
    """Jumps of 2+ levels are dramatic."""
    assert _is_dramatic_tone_shift("calm", "tense") is True   # 0 → 3
    assert _is_dramatic_tone_shift("calm", "dramatic") is True  # 0 → 4
    assert _is_dramatic_tone_shift("tense", "calm") is True   # 3 → 0


def test_is_dramatic_tone_shift_small_jump():
    """Jumps of 1 level are not dramatic."""
    assert _is_dramatic_tone_shift("neutral", "action") is False  # 1 → 2
    assert _is_dramatic_tone_shift("action", "tense") is False    # 2 → 3
    assert _is_dramatic_tone_shift("calm", "neutral") is False    # 0 → 1


def test_is_dramatic_tone_shift_same_tone():
    """Same tone is not a dramatic shift."""
    assert _is_dramatic_tone_shift("tense", "tense") is False
    assert _is_dramatic_tone_shift("calm", "calm") is False


def test_get_visual_cue_for_known_tones():
    """Visual cues are returned for all known tones."""
    assert "tight framing" in _get_visual_cue_for_tone("tense")
    assert "dynamic camera" in _get_visual_cue_for_tone("dramatic")
    assert "dynamic framing" in _get_visual_cue_for_tone("action")
    assert "wide shot" in _get_visual_cue_for_tone("calm")
    assert "balanced framing" in _get_visual_cue_for_tone("neutral")


def test_get_visual_cue_unknown_tone_returns_default():
    """Unknown tone returns a sensible default."""
    cue = _get_visual_cue_for_tone("unknown_tone")
    assert cue  # non-empty
    assert "balanced framing" in cue


def test_location_change_with_dramatic_tone_shift():
    """Both location change and dramatic tone shift produce 2-sentence hint."""
    hint = build_transition_hint(
        current_location="temple",
        prev_location="desert",
        current_tone="dramatic",
        prev_tone="calm",
    )
    assert "Scene shifts to temple" in hint
    assert "Lighting shifts" in hint
    sentences = [s for s in hint.split(". ") if s.strip()]
    assert len(sentences) == 2


def run_unit_tests():
    """Run all unit tests for task 5.1."""
    tests = [
        test_location_change_produces_scene_shifts,
        test_same_location_produces_still_in,
        test_unknown_location_produces_no_location_hint,
        test_dramatic_tone_shift_adds_visual_cue,
        test_minor_tone_shift_no_visual_cue,
        test_hint_is_at_most_two_sentences,
        test_is_dramatic_tone_shift_large_jump,
        test_is_dramatic_tone_shift_small_jump,
        test_is_dramatic_tone_shift_same_tone,
        test_get_visual_cue_for_known_tones,
        test_get_visual_cue_unknown_tone_returns_default,
        test_location_change_with_dramatic_tone_shift,
    ]

    print("\n🧪 Running task 5.1 unit tests...\n")
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  ✓ {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test_fn.__name__} (error): {e}")
            failed += 1

    print(f"\n{'✅' if failed == 0 else '❌'} {passed}/{passed + failed} tests passed")
    return failed == 0
