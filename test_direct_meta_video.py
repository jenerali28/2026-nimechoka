import sys
import os
import json
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)

# Add the src directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
metaai_src = str(PROJECT_ROOT / "metaai-api" / "src")
if metaai_src not in sys.path:
    sys.path.insert(0, metaai_src)

from metaai_api import MetaAI

def test_direct_urls():
    print("Initializing MetaAI...")
    ai = MetaAI() # Loads from metaai-api/.env
    
    prompt = "A cat swimming in a pool"
    print(f"Generating video with direct URL fetching for prompt: '{prompt}'...")
    
    try:
        # Call generation_api.generate_video directly with fetch_urls=True
        result = ai.generation_api.generate_video(prompt, fetch_urls=True)
        
        if result.get("videos"):
            print("\n✅ Successfully fetched direct video URLs!")
            for i, v in enumerate(result["videos"], 1):
                print(f"  {i}. {v.get('url')}")
        else:
            print("\n❌ Failed to fetch direct video URLs.")
            print(f"Result: {json.dumps(result, indent=2)}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_direct_urls()
