#!/usr/bin/env python3
"""
Example: Using enhance_prompts.py to add story context to prompts.

This example shows how to enhance existing prompts with story context
for better visual continuity between scenes.
"""

from pathlib import Path
from utils.enhance_prompts import enhance_prompts

# Example usage
def main():
    """
    Enhance prompts for an existing video project.
    """
    # Path to your video project
    project_name = "Why it Sucks to Be an Egyptian Concubine"
    project_dir = Path("outputs") / project_name
    
    # Input files
    prompts_file = project_dir / "prompts.yaml"
    script_file = project_dir / "spanish_script.txt"  # or english_script.txt
    
    # Check if files exist
    if not prompts_file.exists():
        print(f"❌ Prompts file not found: {prompts_file}")
        print("\nMake sure you've generated prompts first using:")
        print("  python3 utils/multimodal_orchestrator.py ...")
        return
    
    if not script_file.exists():
        print(f"❌ Script file not found: {script_file}")
        print("\nTrying english_script.txt instead...")
        script_file = project_dir / "english_script.txt"
        
        if not script_file.exists():
            print(f"❌ No script file found in {project_dir}")
            return
    
    print(f"📝 Enhancing prompts for: {project_name}")
    print(f"  Prompts: {prompts_file}")
    print(f"  Script: {script_file}")
    print()
    
    # Enhance prompts (overwrites prompts.yaml)
    success = enhance_prompts(
        prompts_path=str(prompts_file),
        script_path=str(script_file)
    )
    
    if success:
        print("\n✅ Success! Your prompts now have story context.")
        print("\nWhat was added:")
        print("  • Previous scene context for continuity")
        print("  • Character appearance consistency")
        print("  • Location transition hints")
        print("  • Emotional tone cues")
        print("\nNext steps:")
        print("  1. Review the enhanced prompts.yaml")
        print("  2. Generate videos with: python3 utils/generate_videos.py")
        print("  3. Watch the improved visual flow!")
    else:
        print("\n❌ Enhancement failed. Check the error messages above.")


if __name__ == "__main__":
    main()
