#!/usr/bin/env python3
"""
Targeted Test: Meta AI Pure Text-to-Video Pipeline.
"""

import os
import sys
import json
import time
from pathlib import Path
import requests

# Add metaai-api/src to path for MetaAI SDK
SCRIPT_DIR = Path(__file__).resolve().parent
METAAI_SRC = SCRIPT_DIR / "metaai-api" / "src"
if str(METAAI_SRC) not in sys.path:
    sys.path.insert(0, str(METAAI_SRC))

from metaai_api import MetaAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Optimized prompt for pure text-to-video (no image reference)
TEST_PROMPT = "Cinematic landscape shot of a majestic lion standing on a rock at sunset, slow camera push-in, golden hour lighting, 4k, hyper-realistic, high detail."
TMP_DIR = SCRIPT_DIR / "tmp" / "test_meta_text_video"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_meta_cookies():
    """Load required cookies for Meta AI."""
    cookies_file = SCRIPT_DIR / "meta_cookies.json"
    if not cookies_file.exists():
        print(f"Error: {cookies_file} not found")
        return None
    
    try:
        data = json.loads(cookies_file.read_text())
        c = data[0] if isinstance(data, list) and data else data
        return {
            "datr": "bw-IaXiI_Pi1DIHlSMX3fa98",
            "abra_sess": "FrqF7evn5cwDFhIYDkxXVG5mbmlhWnptbFN3FuaWxZgNAA%3D%3D",
            "ecto_1_sess": "fec0fa5b-e17a-4386-b1d8-c28a49871b15.v1%3AO0a9tcTrUVeT_HSaJ7e8-nMg_CDoFNYf2sb1DfIQ3jDHNdBKDfZajntlfjxNfeCUSa28ZTeQxn2SPHF6q3tFHXBwLRI9Hv3skzQETBEyU9GBmpmR6GoQxex2JoMPyZOxbBm9LNyNXjZ5CqKU_C8ww2Bl_jYVZlqa8mCxGlp0F3-ILNo5w_qfbX3i0BRHNqhfNsS7F5g6Na46h0lBqM3rd86Kq1QCkVkNOMf9Tc-mnyGSqM91iVSn2tPfxaeyLj5qmLkEq_0gU6rPrwcrKCK7McwJ-2T8YxAzW4AhvR26b93UYfrDSrJEBfL5UsakQ2az6vUVjiCfrxA_Vw6C1XzRdBIFPcHPOugao9BMkdXX3TpvP3bZozOQbfeeyBG-G_UlavJKULhne43PhyL8kkM1YXrlGIMiBK2ITiUC6jVEhCo9ftJVXHB8a54nEGKwp_dAu86opOeLnDF-QPS4x5G6FAjw4iwW43w3yWq3R8sYNg7aJ-5F_fnhz27RMlWya_fD%3AEWuI9U90cDsSML7p%3A3aR9kMh4cYxIv6ot53ntRw.kYF6ieLHUupxULvNuGO3h4RlwPRIcUx6mHpn5E7yPQY",
        }
    except Exception as e:
        print(f"Error loading meta cookies: {e}")
        return None

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n--- Meta AI Pure Text-to-Video Test ---")
    meta_cookies = load_meta_cookies()
    if not meta_cookies:
        sys.exit(1)
        
    ai = MetaAI(cookies=meta_cookies)
    print("Initializing MetaAI...")
    
    print(f"Prompt: {TEST_PROMPT}")
    start = time.time()
    try:
        # Use generate_video_new to submit the request
        result = ai.generate_video_new(
            prompt=TEST_PROMPT,
            auto_poll=False # We will poll ourselves to get direct URLs
        )
        
        if not result.get("success"):
            print(f"✗ Video generation failed: {result.get('error')}")
            sys.exit(1)
            
        conv_id = result.get("conversation_id")
        video_objects = result.get("response", {}).get("video_objects", [])
        video_ids = [v['id'] for v in video_objects if 'id' in v]
        
        if not video_ids:
            print("⚠ No video IDs found in initial response. Polling for them...")
            # Fallback to polling for IDs if not in initial SSE
            direct_links = ai.generation_api.poll_for_video_ids(conv_id, max_attempts=10)
            if direct_links:
                # Extract IDs from links like https://www.meta.ai/create/ID
                video_ids = [link.split('/')[-1] for link in direct_links]

        if not video_ids:
            print("✗ Could not retrieve video IDs.")
            sys.exit(1)

        print(f"✓ Found video ID(s): {video_ids}. Fetching direct mp4 URLs...")
        
        # Now fetch actual direct URLs
        videos = ai.generation_api.fetch_video_urls_by_media_id(
            video_ids=video_ids,
            conversation_id=conv_id,
            max_attempts=20,
            wait_seconds=5
        )
        
        if not videos:
            print("✗ Failed to retrieve direct mp4 URLs.")
            sys.exit(1)
            
        video_url = videos[0].get("url")
        print(f"✓ Direct video URL retrieved in {time.time() - start:.1f}s: {video_url[:80]}...")
        
        # Download video
        video_path = TMP_DIR / "text_to_video_test.mp4"
        print(f"Downloading video to {video_path}...")
        resp = requests.get(video_url, stream=True)
        if resp.status_code == 200:
            with open(video_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"✓ TEST SUCCESSFUL! Video saved to {video_path}")
        else:
            print(f"✗ Download failed (HTTP {resp.status_code})")
            
    except Exception as e:
        print(f"✗ Exception during Meta AI video generation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
