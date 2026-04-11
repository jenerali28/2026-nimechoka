#!/usr/bin/env python3
"""
Convert structured video prompts to plain text format with style anchor.

The original prompts have the style anchor embedded in every video_prompt as plain text.
This script converts structured JSON video prompts to that format.
"""

import yaml
from pathlib import Path

def convert_video_prompt_to_text(video_prompt_data: dict, style_anchor: str) -> str:
    """Convert structured video prompt to plain text with style anchor."""
    
    if isinstance(video_prompt_data, str):
        # Already a string, just ensure it has the style anchor
        if style_anchor.lower() not in video_prompt_data.lower():
            return f"{style_anchor}, {video_prompt_data}"
        return video_prompt_data
    
    # Extract components from structured format
    meta = video_prompt_data.get('meta', {})
    style = meta.get('style', '')
    
    global_ctx = video_prompt_data.get('global_context', {})
    scene_desc = global_ctx.get('scene_description', '')
    env_desc = global_ctx.get('environment_description', '')
    
    action_beats = video_prompt_data.get('action_beats', [])
    camera = video_prompt_data.get('camera_motion', {})
    camera_move = camera.get('primary_move', 'Static')
    
    negative = video_prompt_data.get('negative_prompt', 'photorealistic, 3D render, CGI, watermark, text, subtitle, blurry, low quality, multiple panels, split screen, collage, static image, same expression every scene')
    
    # Build plain text prompt
    parts = [style_anchor]
    
    if scene_desc:
        parts.append(scene_desc)
    
    # Add action beats with timestamps
    for beat in action_beats:
        time_range = beat.get('time_range', '')
        action = beat.get('action', '')
        cam = beat.get('camera', '')
        
        if time_range and action:
            beat_text = f"[{time_range}] {action}"
            if cam:
                beat_text += f" {cam}"
            parts.append(beat_text)
    
    # Add camera info if not in beats
    if camera_move and camera_move != 'Static':
        parts.append(f"Camera: {camera_move}.")
    
    # Add negative prompt
    parts.append(f"negative: {negative}")
    
    return " ".join(parts)


def fix_prompts_file(prompts_file: Path):
    """Fix all video prompts in the file to use plain text format with style anchor."""
    
    print(f"\n{'='*60}")
    print(f"  Fixing Video Prompt Format")
    print(f"{'='*60}")
    print(f"  File: {prompts_file}")
    
    with open(prompts_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    style_anchor = data.get('style_anchor', '')
    if not style_anchor:
        print("  ⚠ No style_anchor found in file!")
        return
    
    print(f"  Style: {style_anchor[:80]}...")
    
    scenes = data.get('scenes', [])
    fixed_count = 0
    
    for scene in scenes:
        scene_num = scene.get('scene_number', 0)
        video_prompt = scene.get('video_prompt')
        
        if video_prompt and isinstance(video_prompt, dict):
            # Convert structured to plain text
            text_prompt = convert_video_prompt_to_text(video_prompt, style_anchor)
            scene['video_prompt'] = text_prompt
            fixed_count += 1
            print(f"  ✓ Fixed scene {scene_num}")
        elif video_prompt and isinstance(video_prompt, str):
            # Already text, ensure it has style anchor
            if style_anchor.lower() not in video_prompt.lower():
                scene['video_prompt'] = f"{style_anchor}, {video_prompt}"
                fixed_count += 1
                print(f"  ✓ Added style to scene {scene_num}")
    
    # Create backup
    backup_file = prompts_file.with_suffix('.yaml.backup3')
    print(f"\n  💾 Creating backup: {backup_file}")
    with open(backup_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)
    
    # Save fixed version
    print(f"  💾 Saving fixed prompts: {prompts_file}")
    with open(prompts_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)
    
    print(f"\n{'='*60}")
    print(f"  ✅ Fixed {fixed_count} video prompts")
    print(f"  ✅ All prompts now have consistent MS Paint style")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fix video prompt format to include style anchor"
    )
    parser.add_argument(
        "--prompts-file",
        default="outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml",
        help="Path to prompts.yaml file"
    )
    
    args = parser.parse_args()
    prompts_file = Path(args.prompts_file)
    
    if not prompts_file.exists():
        print(f"Error: {prompts_file} not found")
        exit(1)
    
    fix_prompts_file(prompts_file)
