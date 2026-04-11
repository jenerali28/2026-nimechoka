# Story Context Module

Simple module for tracking story progression across video scenes to create cinematic flow.

## Overview

The `story_context.py` module helps make video scenes flow together like a movie by:
- Reading script files to understand story progression
- Tracking location, characters, and actions for each scene
- Detecting basic emotional tone (tense, calm, dramatic, action)
- Building context strings that connect scenes together

## Features

### ✅ Simple and Focused
- No complex data structures - just dicts and lists
- No external dependencies - uses only standard library (re, pathlib)
- Easy to understand and modify

### ✅ Script Analysis
- Reads English or Spanish script files
- Splits script into scene segments automatically
- Extracts key information from each scene

### ✅ Context Tracking
- Tracks location changes between scenes
- Identifies which characters appear in each scene
- Detects emotional tone using keyword matching
- Builds context strings: "Previous scene: [location], [characters], [action]"

## Usage

### Basic Usage

```python
from story_context import track_story_context

# Track context for all scenes
contexts = track_story_context(
    script_path="outputs/project/spanish_script.txt",
    num_scenes=30,
    character_names=["Protagonist", "Pharaoh", "Great Royal Wife"]
)

# Access context for each scene
for ctx in contexts:
    print(f"Scene {ctx['scene_number']}:")
    print(f"  Location: {ctx['location']}")
    print(f"  Characters: {ctx['characters']}")
    print(f"  Tone: {ctx['tone']}")
    print(f"  Context: {ctx['context_string']}")
```

### Individual Functions

```python
from story_context import (
    read_script,
    split_script_into_scenes,
    extract_location,
    extract_characters,
    extract_action,
    detect_emotional_tone
)

# Read script
script_text = read_script("path/to/script.txt")

# Split into scenes
scenes = split_script_into_scenes(script_text, num_scenes=10)

# Extract information from a scene
location = extract_location(scenes[0])
characters = extract_characters(scenes[0], ["Protagonist", "Pharaoh"])
action = extract_action(scenes[0])
tone = detect_emotional_tone(scenes[0])
```

### Command Line

```bash
# Test the module
python3 utils/story_context.py "path/to/script.txt" 10

# Run tests
python3 utils/test_story_context.py

# See example usage
python3 utils/example_story_context_usage.py
```

## Context Dictionary Structure

Each scene context is a dictionary with:

```python
{
    'scene_number': 1,                    # Scene number (1-indexed)
    'location': 'palace',                 # Detected location
    'characters': ['Protagonist'],        # Characters present
    'action': 'Character walks...',       # Main action (first sentence)
    'tone': 'tense',                      # Emotional tone
    'context_string': 'Previous scene...' # Formatted context string
}
```

## Emotional Tone Detection

Simple keyword-based detection for:
- **tense**: panic, fear, terror, crying, desperation
- **calm**: tranquil, normal, soft, peace, relaxed
- **dramatic**: death, blood, war, murder, betrayal
- **action**: burst, drag, attack, run, fight, escape
- **neutral**: no keywords matched

Supports both Spanish and English keywords.

## Location Detection

Detects common locations:
- Spanish: siria, egipto, menfis, harén, palacio, calle, casa, desierto, templo
- English: syria, egypt, memphis, harem, palace, street, house, desert, temple

Falls back to pattern matching if no known location found.

## Integration with Pipeline

### With prompts.yaml

```python
import yaml
from story_context import track_story_context

# Load prompts
with open("prompts.yaml", 'r') as f:
    prompts_data = yaml.safe_load(f)

# Get character names
character_names = [
    char['name'] 
    for char in prompts_data['character_profile']['characters']
]

# Track context
contexts = track_story_context(
    script_path="spanish_script.txt",
    num_scenes=len(prompts_data['scenes']),
    character_names=character_names
)

# Enhance prompts with context
for i, scene in enumerate(prompts_data['scenes']):
    ctx = contexts[i]
    
    # Add context to prompt
    original_prompt = scene['image_prompt']
    enhanced_prompt = f"{ctx['context_string']}. {original_prompt}"
    
    scene['image_prompt'] = enhanced_prompt
```

## Files

- `story_context.py` - Main module with all functions
- `test_story_context.py` - Unit tests
- `example_story_context_usage.py` - Usage examples
- `STORY_CONTEXT_README.md` - This file

## Testing

Run the test suite:

```bash
python3 utils/test_story_context.py
```

All tests should pass:
- ✅ read_script works
- ✅ split_script_into_scenes works
- ✅ extract_location works
- ✅ extract_characters works
- ✅ extract_action works
- ✅ detect_emotional_tone works
- ✅ build_scene_context works
- ✅ track_story_context works

## Example Output

```
Scene 1:
  Location: siria
  Characters: Protagonist
  Tone: neutral
  Action: Siria. Siglo XIV antes de Cristo...
  Context: Opening scene

Scene 2:
  Location: egipto
  Characters: Protagonist
  Tone: tense
  Action: En un parpadeo, te encuentras hacinada en un barco...
  Context: Previous scene: siria, Protagonist, Siria. Siglo XIV...
```

## Next Steps

This module implements **Task 1.1** of the Cinematic Storytelling System spec.

Next tasks:
- **Task 2**: Create `enhance_prompts.py` to inject context into prompts.yaml
- **Task 3**: Integrate with `multimodal_orchestrator.py`
- **Task 4**: Add character consistency tracking
- **Task 5**: Add transition logic

## Design Philosophy

**Keep It Simple:**
- No complex graph structures - just track previous scene
- No over-analysis - just detect basic tone from keywords
- No new file formats - work with existing prompts.yaml
- No new dependencies - use existing libraries only

**Focus on Impact:**
- Visual continuity is the goal, not perfect story analysis
- Simple context injection makes a huge difference
- Character consistency is more important than complex transitions
- Test early and often with real examples

## License

Part of the Grok2API video generation pipeline.
