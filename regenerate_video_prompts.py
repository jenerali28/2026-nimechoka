#!/usr/bin/env python3
"""
Regenerate video prompts for scenes 33-200.

The original prompts were designed for static images with Ken Burns zoom.
This script regenerates them as proper video prompts with motion/animation.
"""

import asyncio
import json
import sys
import yaml
from pathlib import Path

# Import the visual prompt generator
sys.path.insert(0, str(Path(__file__).parent / "bible"))
from generate_visuals import (
    client,
    _generate_character_profile,
    _run_video_batch,
    _parse_json_block,
    split_script_into_segments,
    BATCH_SIZE,
)

async def regenerate_video_prompts_from_scene(
    prompts_file: Path,
    script_file: Path,
    start_scene: int = 33
):
    """Regenerate video prompts starting from a specific scene number."""
    
    # Load existing prompts
    print(f"\n{'='*60}")
    print(f"  Regenerating Video Prompts")
    print(f"{'='*60}")
    print(f"  Prompts file : {prompts_file}")
    print(f"  Script file  : {script_file}")
    print(f"  Start scene  : {start_scene}")
    
    with open(prompts_file, 'r', encoding='utf-8') as f:
        prompts_data = yaml.safe_load(f)
    
    with open(script_file, 'r', encoding='utf-8') as f:
        script_text = f.read().strip()
    
    scenes = prompts_data.get('scenes', [])
    total_scenes = len(scenes)
    
    print(f"  Total scenes : {total_scenes}")
    print(f"  Regenerating : {start_scene}-{total_scenes}")
    
    # Initialize Gemini client
    await client.init(timeout=300, watchdog_timeout=120)
    
    # Generate character profile from full script
    print(f"\n  👤 Generating character profile...")
    char_profile = await _generate_character_profile(script_text)
    
    # Get scenes that need regeneration
    scenes_to_regenerate = [s for s in scenes if s.get('scene_number', 0) >= start_scene]
    
    if not scenes_to_regenerate:
        print(f"\n  ⚠ No scenes found to regenerate!")
        return
    
    # Split script into segments for these scenes
    segments = split_script_into_segments(script_text, total_scenes)
    
    # Build scene tasks (scene_number, segment_text)
    scene_tasks = []
    for scene in scenes_to_regenerate:
        scene_num = scene.get('scene_number', 0)
        if scene_num > 0 and scene_num <= len(segments):
            seg_text = segments[scene_num - 1]
            scene_tasks.append((scene_num, seg_text))
    
    print(f"\n  Processing {len(scene_tasks)} scenes in batches of {BATCH_SIZE}...")
    
    # Process in batches
    num_batches = (len(scene_tasks) + BATCH_SIZE - 1) // BATCH_SIZE
    video_scenes_flat = []
    
    for batch_idx in range(num_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(scene_tasks))
        batch = scene_tasks[start_i:end_i]
        
        result = await _run_video_batch(batch, char_profile, batch_idx, num_batches)
        video_scenes_flat.extend(result)
        
        # Small delay between batches to avoid rate limiting
        if batch_idx < num_batches - 1:
            await asyncio.sleep(2)
    
    # Update the scenes with new video prompts
    video_map = {s['scene_number']: s.get('video_prompt') for s in video_scenes_flat}
    
    updated_count = 0
    for scene in scenes:
        scene_num = scene.get('scene_number', 0)
        if scene_num in video_map:
            scene['video_prompt'] = video_map[scene_num]
            updated_count += 1
    
    # Update character profile
    prompts_data['character_profile'] = char_profile
    
    # Save updated prompts
    backup_file = prompts_file.with_suffix('.yaml.backup')
    print(f"\n  💾 Creating backup: {backup_file}")
    with open(backup_file, 'w', encoding='utf-8') as f:
        yaml.dump(prompts_data, f, sort_keys=False, allow_unicode=True)
    
    print(f"  💾 Saving updated prompts: {prompts_file}")
    with open(prompts_file, 'w', encoding='utf-8') as f:
        yaml.dump(prompts_data, f, sort_keys=False, allow_unicode=True)
    
    print(f"\n{'='*60}")
    print(f"  ✅ Updated {updated_count} video prompts")
    print(f"  ✅ Scenes {start_scene}-{total_scenes} now have proper video prompts")
    print(f"{'='*60}")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Regenerate video prompts for scenes that were originally designed for images"
    )
    parser.add_argument(
        "--prompts-file",
        default="outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml",
        help="Path to prompts.yaml file"
    )
    parser.add_argument(
        "--script-file",
        default="outputs/Why it Sucks to Be an Egyptian Concubine/spanish_script.txt",
        help="Path to script file"
    )
    parser.add_argument(
        "--start-scene",
        type=int,
        default=33,
        help="First scene number to regenerate (default: 33)"
    )
    
    args = parser.parse_args()
    
    prompts_file = Path(args.prompts_file)
    script_file = Path(args.script_file)
    
    if not prompts_file.exists():
        print(f"Error: Prompts file not found: {prompts_file}")
        sys.exit(1)
    
    if not script_file.exists():
        print(f"Error: Script file not found: {script_file}")
        sys.exit(1)
    
    await regenerate_video_prompts_from_scene(
        prompts_file,
        script_file,
        args.start_scene
    )


if __name__ == "__main__":
    asyncio.run(main())
