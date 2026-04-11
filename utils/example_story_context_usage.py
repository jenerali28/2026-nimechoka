#!/usr/bin/env python3
"""
Example usage of story_context module with prompts.yaml.

This demonstrates how to integrate story context tracking
with the existing video generation pipeline.
"""

import yaml
from pathlib import Path
from story_context import track_story_context


def example_usage():
    """
    Example: Track story context for the Egyptian Concubine video.
    """
    # Paths
    project_dir = Path("outputs/Why it Sucks to Be an Egyptian Concubine")
    script_path = project_dir / "spanish_script.txt"
    prompts_path = project_dir / "prompts.yaml"
    
    # Load prompts.yaml to get character names and scene count
    with open(prompts_path, 'r', encoding='utf-8') as f:
        prompts_data = yaml.safe_load(f)
    
    # Extract character names from character_profile
    character_names = [
        char['name'] 
        for char in prompts_data.get('character_profile', {}).get('characters', [])
    ]
    
    # Get number of scenes
    num_scenes = len(prompts_data.get('scenes', []))
    
    print(f"📖 Tracking story context for {num_scenes} scenes")
    print(f"👥 Characters: {', '.join(character_names)}\n")
    
    # Track story context
    contexts = track_story_context(str(script_path), num_scenes, character_names)
    
    # Display results
    print("Story Context Summary:")
    print("=" * 70)
    
    for ctx in contexts[:10]:  # Show first 10 scenes
        print(f"\nScene {ctx['scene_number']}:")
        print(f"  📍 Location: {ctx['location']}")
        print(f"  👤 Characters: {', '.join(ctx['characters']) if ctx['characters'] else 'none'}")
        print(f"  🎭 Tone: {ctx['tone']}")
        print(f"  🎬 Action: {ctx['action'][:60]}...")
        print(f"  🔗 Context: {ctx['context_string'][:80]}...")
    
    if num_scenes > 10:
        print(f"\n... and {num_scenes - 10} more scenes")
    
    print("\n" + "=" * 70)
    print("\n✅ Story context tracking complete!")
    print("\nNext steps:")
    print("  1. Use these contexts to enhance prompts in prompts.yaml")
    print("  2. Add context_string to each scene's prompt")
    print("  3. Maintain character consistency using character names")
    print("  4. Add location transitions based on location changes")


def example_context_enhancement():
    """
    Example: Show how to enhance a prompt with story context.
    """
    print("\n\n📝 Example: Enhancing a prompt with story context\n")
    print("=" * 70)
    
    # Example original prompt
    original_prompt = (
        "crude minimalist cartoon, desert landscape, "
        "The Protagonist stands alone looking confused"
    )
    
    # Example context from previous scene
    previous_context = {
        'location': 'siria',
        'characters': ['Protagonist'],
        'action': 'Protagonist is at home with family',
        'tone': 'calm'
    }
    
    # Enhanced prompt with context
    enhanced_prompt = (
        f"Continuing from {previous_context['location']} "
        f"where {', '.join(previous_context['characters'])} "
        f"was {previous_context['action']}. "
        f"{original_prompt}"
    )
    
    print("Original prompt:")
    print(f"  {original_prompt}\n")
    
    print("Enhanced prompt with context:")
    print(f"  {enhanced_prompt}\n")
    
    print("=" * 70)
    print("\nThe enhanced prompt now includes:")
    print("  ✅ Previous scene location")
    print("  ✅ Character continuity")
    print("  ✅ Action context")
    print("  ✅ Smooth transition between scenes")


if __name__ == "__main__":
    example_usage()
    example_context_enhancement()
