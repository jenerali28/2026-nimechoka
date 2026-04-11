#!/usr/bin/env python3
"""
Story Context Tracker for Cinematic Video Generation.

Simple module to track story progression across scenes:
- Reads script files to understand what happens in each scene
- Tracks location, characters, and actions
- Detects basic emotional tone using keyword matching
- Builds context strings for scene continuity
- Extracts character appearance from prompts.yaml for consistent descriptions

No complex data structures - just dicts and lists.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional


# Emotional tone keywords for simple detection
EMOTIONAL_KEYWORDS = {
    'tense': ['pánico', 'terror', 'miedo', 'gritar', 'llorar', 'desesperación', 
              'paralizada', 'estómago', 'encoge', 'alerta', 'peligrosa', 'conspirando',
              'panic', 'terror', 'fear', 'scream', 'cry', 'desperation', 'paralyzed',
              'stomach', 'alert', 'dangerous', 'conspiring'],
    'calm': ['tranquilo', 'normal', 'suave', 'paz', 'relajado', 'sereno',
             'calm', 'normal', 'soft', 'peace', 'relaxed', 'serene'],
    'dramatic': ['bomba', 'muerto', 'muerte', 'sangre', 'guerra', 'batalla', 'envenenado',
                 'asesinato', 'traición', 'jaque mate', 'fin', 'acabar',
                 'bomb', 'dead', 'death', 'blood', 'war', 'battle', 'poisoned',
                 'murder', 'betrayal', 'checkmate', 'end', 'finish'],
    'action': ['irrumpe', 'arrastra', 'golpea', 'ataca', 'corre', 'lucha', 'escapa',
               'persigue', 'destrozan', 'patadas', 'bofetadas',
               'burst', 'drag', 'hit', 'attack', 'run', 'fight', 'escape',
               'chase', 'destroy', 'kick', 'slap']
}


def read_script(script_path: str) -> str:
    """
    Read script file content.
    
    Args:
        script_path: Path to script file (english_script.txt or spanish_script.txt)
    
    Returns:
        Script text content, or empty string if file not found
    """
    try:
        path = Path(script_path)
        if not path.exists():
            return ""
        return path.read_text(encoding='utf-8').strip()
    except Exception:
        return ""


def split_script_into_scenes(script_text: str, num_scenes: int) -> List[str]:
    """
    Split script into roughly equal scene segments.
    
    Args:
        script_text: Full script content
        num_scenes: Number of scenes to split into
    
    Returns:
        List of scene text segments
    """
    if not script_text or num_scenes <= 0:
        return []
    
    # Split by paragraphs (double newline)
    paragraphs = re.split(r'\n\s*\n', script_text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if not paragraphs:
        return [script_text] * num_scenes
    
    # If fewer paragraphs than scenes, split by sentences
    if len(paragraphs) < num_scenes:
        all_sentences = []
        for para in paragraphs:
            # Split on sentence endings
            sents = re.split(r'(?<=[.!?…])\s+', para)
            all_sentences.extend([s.strip() for s in sents if s.strip()])
        units = all_sentences if len(all_sentences) >= num_scenes else paragraphs
    else:
        units = paragraphs
    
    # Distribute units across scenes
    scenes = []
    per_scene = len(units) / num_scenes
    
    for i in range(num_scenes):
        start = int(i * per_scene)
        end = int((i + 1) * per_scene)
        if i == num_scenes - 1:
            end = len(units)
        chunk = " ".join(units[start:end])
        scenes.append(chunk)
    
    return scenes


def extract_location(scene_text: str) -> str:
    """
    Extract location from scene text using simple pattern matching.
    
    Args:
        scene_text: Text content of the scene
    
    Returns:
        Location string, or "unknown location" if not found
    """
    # Known locations (Spanish and English)
    known_locations = [
        'siria', 'syria', 'egipto', 'egypt', 'menfis', 'memphis',
        'mediterráneo', 'mediterranean', 'barco', 'ship', 'boat',
        'calle', 'street', 'harén', 'harem', 'palacio', 'palace',
        'habitación', 'room', 'cuarto', 'chamber', 'courtyard', 'patio',
        'ciudad', 'city', 'desierto', 'desert', 'templo', 'temple',
        'festival', 'casa', 'house', 'home'
    ]
    
    scene_lower = scene_text.lower()
    
    # Check for known locations
    for location in known_locations:
        if location in scene_lower:
            return location
    
    # Try pattern matching as fallback
    location_patterns = [
        r'en (?:el|la|los|las|un|una) ([a-záéíóúñ]+)',  # Spanish: "en el/la..."
        r'in (?:the|a|an) ([a-z]+)',  # English: "in the/a..."
        r'at (?:the|a|an) ([a-z]+)',  # English: "at the/a..."
    ]
    
    for pattern in location_patterns:
        matches = re.findall(pattern, scene_lower)
        if matches:
            for match in matches:
                location = match.strip()
                # Skip very short or common words
                if len(location) > 4:
                    return location
    
    return "unknown location"


def extract_characters(scene_text: str, character_names: List[str]) -> List[str]:
    """
    Extract which characters appear in the scene.
    
    Args:
        scene_text: Text content of the scene
        character_names: List of known character names to look for
    
    Returns:
        List of character names found in the scene
    """
    present = []
    scene_lower = scene_text.lower()
    
    for name in character_names:
        # Check if character name appears in scene
        if name.lower() in scene_lower:
            present.append(name)
    
    # If no specific characters found, assume protagonist
    if not present and character_names:
        present.append(character_names[0])  # Default to first character (usually protagonist)
    
    return present


def extract_action(scene_text: str) -> str:
    """
    Extract main action from scene text.
    
    Args:
        scene_text: Text content of the scene
    
    Returns:
        Brief description of main action (first sentence or key phrase)
    """
    if not scene_text or not scene_text.strip():
        return "scene continues"
    
    # Get first sentence as main action
    sentences = re.split(r'[.!?…]\s+', scene_text.strip())
    if sentences and sentences[0]:
        action = sentences[0].strip()
        # Limit length
        if len(action) > 100:
            action = action[:97] + "..."
        return action
    
    return "scene continues"


def detect_emotional_tone(scene_text: str) -> str:
    """
    Detect emotional tone using simple keyword matching.
    
    Args:
        scene_text: Text content of the scene
    
    Returns:
        Emotional tone: 'tense', 'calm', 'dramatic', 'action', or 'neutral'
    """
    scene_lower = scene_text.lower()
    
    # Count keyword matches for each emotion
    tone_scores = {}
    for tone, keywords in EMOTIONAL_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in scene_lower)
        tone_scores[tone] = score
    
    # Return tone with highest score
    if tone_scores:
        max_tone = max(tone_scores, key=tone_scores.get)
        if tone_scores[max_tone] > 0:
            return max_tone
    
    return 'neutral'


def build_scene_context(
    scene_number: int,
    scene_text: str,
    character_names: List[str],
    previous_context: Optional[Dict] = None
) -> Dict:
    """
    Build context information for a single scene.
    
    Args:
        scene_number: Scene number (1-indexed)
        scene_text: Text content of the scene
        character_names: List of known character names
        previous_context: Context from previous scene (optional)
    
    Returns:
        Dictionary with scene context:
        {
            'scene_number': int,
            'location': str,
            'characters': List[str],
            'action': str,
            'tone': str,
            'context_string': str  # Formatted context for prompts
        }
    """
    location = extract_location(scene_text)
    characters = extract_characters(scene_text, character_names)
    action = extract_action(scene_text)
    tone = detect_emotional_tone(scene_text)
    
    # Build context string
    if previous_context:
        prev_location = previous_context.get('location', 'unknown')
        prev_characters = previous_context.get('characters', [])
        prev_action = previous_context.get('action', 'previous scene')
        
        context_string = (
            f"Previous scene: {prev_location}, "
            f"{', '.join(prev_characters) if prev_characters else 'characters'}, "
            f"{prev_action}"
        )
    else:
        context_string = "Opening scene"
    
    return {
        'scene_number': scene_number,
        'location': location,
        'characters': characters,
        'action': action,
        'tone': tone,
        'context_string': context_string
    }


def track_story_context(
    script_path: str,
    num_scenes: int,
    character_names: List[str]
) -> List[Dict]:
    """
    Track story context across all scenes.
    
    Args:
        script_path: Path to script file
        num_scenes: Number of scenes in the video
        character_names: List of character names to track
    
    Returns:
        List of context dictionaries, one per scene
    """
    # Read and split script
    script_text = read_script(script_path)
    if not script_text:
        # Return empty contexts if no script
        return [
            {
                'scene_number': i + 1,
                'location': 'unknown',
                'characters': [],
                'action': 'scene continues',
                'tone': 'neutral',
                'context_string': 'Opening scene' if i == 0 else 'Previous scene continues'
            }
            for i in range(num_scenes)
        ]
    
    scene_texts = split_script_into_scenes(script_text, num_scenes)
    
    # Build context for each scene
    contexts = []
    previous_context = None
    
    for i, scene_text in enumerate(scene_texts):
        context = build_scene_context(
            scene_number=i + 1,
            scene_text=scene_text,
            character_names=character_names,
            previous_context=previous_context
        )
        contexts.append(context)
        previous_context = context
    
    return contexts


def extract_character_profiles(prompts_yaml_path: str) -> Dict[str, str]:
    """
    Extract character appearance descriptions from prompts.yaml.

    Reads the character_profile section and returns a mapping of
    character name → appearance_anchor string.

    Args:
        prompts_yaml_path: Path to the prompts.yaml file

    Returns:
        Dict mapping character name to their appearance_anchor string.
        Returns empty dict if file not found or has no character_profile.

    Example:
        {
            "The Protagonist": "thin black stick figure, long dark hair, olive face, white dress",
            "The Pharaoh": "thin black stick figure, dark brown face, white kilt and pharaoh crown"
        }
    """
    try:
        path = Path(prompts_yaml_path)
        if not path.exists():
            return {}

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data or 'character_profile' not in data:
            return {}

        profile = data['character_profile']
        characters_list = profile.get('characters', [])

        profiles: Dict[str, str] = {}
        for char in characters_list:
            name = char.get('name', '').strip()
            anchor = char.get('appearance_anchor', '').strip()
            if name and anchor:
                profiles[name] = anchor

        return profiles

    except Exception:
        return {}


def format_character_description(character_name: str, character_profiles: Dict[str, str]) -> str:
    """
    Format a character's name with their consistent appearance description.

    Args:
        character_name: The character's name (e.g. "The Protagonist")
        character_profiles: Dict mapping character name → appearance_anchor

    Returns:
        Formatted string like:
        "The Protagonist (thin black stick figure, long dark hair, olive face, white dress)"
        or just the character name if no profile is found.
    """
    anchor = character_profiles.get(character_name, '').strip()
    if anchor:
        return f"{character_name} ({anchor})"
    return character_name


def inject_character_descriptions(
    characters_in_scene: List[str],
    character_profiles: Dict[str, str]
) -> str:
    """
    Build a character consistency string for all characters in a scene.

    For each character present in the scene, formats their name with their
    consistent appearance description so the AI model renders them consistently.

    Args:
        characters_in_scene: List of character names present in this scene
        character_profiles: Dict mapping character name → appearance_anchor

    Returns:
        A string describing all characters with their appearances, e.g.:
        "The Protagonist (thin black stick figure, long dark hair, olive face, white dress)"
        or multiple characters joined by "; ".
        Returns empty string if no characters or no profiles found.

    Example (FR2.2):
        "The Protagonist (thin black stick figure, long dark hair, olive face, white dress) continues..."
    """
    if not characters_in_scene or not character_profiles:
        return ""

    descriptions = []
    for name in characters_in_scene:
        desc = format_character_description(name, character_profiles)
        descriptions.append(desc)

    return "; ".join(descriptions)


if __name__ == "__main__":
    # Simple test
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python story_context.py <script_path> [num_scenes]")
        sys.exit(1)
    
    script_path = sys.argv[1]
    num_scenes = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    # Test with example characters
    test_characters = ["Protagonist", "Pharaoh", "Great Royal Wife"]
    
    contexts = track_story_context(script_path, num_scenes, test_characters)
    
    print(f"\n📖 Story Context Tracking: {num_scenes} scenes\n")
    for ctx in contexts:
        print(f"Scene {ctx['scene_number']}:")
        print(f"  Location: {ctx['location']}")
        print(f"  Characters: {', '.join(ctx['characters']) if ctx['characters'] else 'none'}")
        print(f"  Tone: {ctx['tone']}")
        print(f"  Action: {ctx['action'][:60]}...")
        print(f"  Context: {ctx['context_string']}")
        print()
