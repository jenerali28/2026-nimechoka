#!/usr/bin/env python3
"""
Simple unit tests for story_context module.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from story_context import (
    read_script,
    split_script_into_scenes,
    extract_location,
    extract_characters,
    extract_action,
    detect_emotional_tone,
    build_scene_context,
    track_story_context
)


def test_read_script():
    """Test reading script files."""
    print("Testing read_script...")
    
    # Test with non-existent file
    result = read_script("nonexistent.txt")
    assert result == "", "Should return empty string for missing file"
    
    # Test with real file
    result = read_script("outputs/Why it Sucks to Be an Egyptian Concubine/spanish_script.txt")
    assert len(result) > 0, "Should read real script file"
    assert "Siria" in result, "Should contain expected content"
    
    print("  ✅ read_script works")


def test_split_script_into_scenes():
    """Test splitting script into scenes."""
    print("Testing split_script_into_scenes...")
    
    test_script = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    
    # Test splitting into 3 scenes
    scenes = split_script_into_scenes(test_script, 3)
    assert len(scenes) == 3, "Should split into 3 scenes"
    
    # Test with empty script
    scenes = split_script_into_scenes("", 5)
    assert len(scenes) == 0, "Should return empty list for empty script"
    
    # Test with zero scenes
    scenes = split_script_into_scenes(test_script, 0)
    assert len(scenes) == 0, "Should return empty list for zero scenes"
    
    print("  ✅ split_script_into_scenes works")


def test_extract_location():
    """Test location extraction."""
    print("Testing extract_location...")
    
    # Test Spanish locations (known locations are prioritized)
    assert extract_location("en el palacio de Egipto") == "egipto"  # egipto found first
    assert extract_location("en Menfis bajo el sol") == "menfis"
    assert extract_location("dentro del harén real") == "harén"
    
    # Test English locations
    assert extract_location("in the desert") == "desert"
    assert extract_location("at the temple") == "temple"
    
    # Test with only palacio (no other known locations)
    assert extract_location("en el palacio solamente") == "palacio"
    
    # Test unknown location
    assert extract_location("something random") == "unknown location"
    
    print("  ✅ extract_location works")


def test_extract_characters():
    """Test character extraction."""
    print("Testing extract_characters...")
    
    characters = ["Protagonist", "Pharaoh", "Great Royal Wife"]
    
    # Test with protagonist mentioned
    scene = "The Protagonist stands in the palace"
    result = extract_characters(scene, characters)
    assert "Protagonist" in result, "Should find Protagonist"
    
    # Test with multiple characters
    scene = "The Pharaoh meets the Protagonist"
    result = extract_characters(scene, characters)
    assert "Pharaoh" in result and "Protagonist" in result, "Should find both characters"
    
    # Test with no characters (should default to first)
    scene = "A random scene with no one"
    result = extract_characters(scene, characters)
    assert len(result) > 0, "Should default to first character"
    
    print("  ✅ extract_characters works")


def test_extract_action():
    """Test action extraction."""
    print("Testing extract_action...")
    
    # Test simple sentence
    action = extract_action("The character walks slowly. Then runs fast.")
    assert "walks slowly" in action, "Should extract first sentence"
    
    # Test long sentence (should truncate)
    long_text = "A" * 200
    action = extract_action(long_text)
    assert len(action) <= 100, "Should truncate long actions"
    
    # Test empty text
    action = extract_action("")
    assert action == "scene continues", "Should return default for empty text"
    
    print("  ✅ extract_action works")


def test_detect_emotional_tone():
    """Test emotional tone detection."""
    print("Testing detect_emotional_tone...")
    
    # Test tense keywords
    assert detect_emotional_tone("pánico y terror en la noche") == "tense"
    assert detect_emotional_tone("fear and panic everywhere") == "tense"
    
    # Test dramatic keywords
    assert detect_emotional_tone("muerte y sangre en la batalla") == "dramatic"
    assert detect_emotional_tone("death and blood in war") == "dramatic"
    
    # Test action keywords
    assert detect_emotional_tone("irrumpe y arrastra con fuerza") == "action"
    assert detect_emotional_tone("burst in and drag away") == "action"
    
    # Test calm keywords
    assert detect_emotional_tone("tranquilo y sereno día") == "calm"
    assert detect_emotional_tone("normal peaceful scene") == "calm"  # "normal" is a calm keyword
    
    # Test neutral (no keywords)
    assert detect_emotional_tone("just a regular scene") == "neutral"
    
    print("  ✅ detect_emotional_tone works")


def test_build_scene_context():
    """Test building scene context."""
    print("Testing build_scene_context...")
    
    characters = ["Protagonist", "Pharaoh"]
    scene_text = "The Protagonist stands in the palace. There is tension in the air."
    
    # Test first scene (no previous context)
    context = build_scene_context(1, scene_text, characters, None)
    assert context['scene_number'] == 1
    assert context['context_string'] == "Opening scene"
    assert 'location' in context
    assert 'characters' in context
    assert 'action' in context
    assert 'tone' in context
    
    # Test second scene (with previous context)
    context2 = build_scene_context(2, "Next scene in the desert", characters, context)
    assert context2['scene_number'] == 2
    assert "Previous scene:" in context2['context_string']
    
    print("  ✅ build_scene_context works")


def test_track_story_context():
    """Test full story context tracking."""
    print("Testing track_story_context...")
    
    script_path = "outputs/Why it Sucks to Be an Egyptian Concubine/spanish_script.txt"
    characters = ["Protagonist", "Pharaoh", "Great Royal Wife"]
    
    # Test with real script
    contexts = track_story_context(script_path, 5, characters)
    assert len(contexts) == 5, "Should return 5 contexts"
    assert contexts[0]['context_string'] == "Opening scene", "First scene should be opening"
    assert "Previous scene:" in contexts[1]['context_string'], "Second scene should reference previous"
    
    # Test with missing script
    contexts = track_story_context("nonexistent.txt", 3, characters)
    assert len(contexts) == 3, "Should return 3 empty contexts"
    
    print("  ✅ track_story_context works")


def run_all_tests():
    """Run all tests."""
    print("\n🧪 Running story_context tests...\n")
    
    try:
        test_read_script()
        test_split_script_into_scenes()
        test_extract_location()
        test_extract_characters()
        test_extract_action()
        test_detect_emotional_tone()
        test_build_scene_context()
        test_track_story_context()
        
        print("\n✅ All tests passed!\n")
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
