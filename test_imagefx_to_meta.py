#!/usr/bin/env python3
"""
Targeted Test: ImageFX-to-Meta AI Pipeline.

1. Generate image using ImageFX CLI (Imagen 4).
2. Upload generated image to Meta AI.
3. Animate uploaded image using Meta AI.
"""

import os
import sys
import json
import time
import shutil
import subprocess
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

IMAGEFX_CLI = SCRIPT_DIR / "imageFX-api" / "dist" / "cli.js"
TEST_PROMPT = "A majestic lion standing on a rock at sunset, cinematic lighting, 8k, detailed fur, vibrant sky"
VIDEO_PROMPT = "Animate this majestic lion, making it slowly roar as the sun sets behind it."
TMP_DIR = SCRIPT_DIR / "tmp" / "test_imagefx_meta"

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
            "datr": c.get("datr", ""),
            "abra_sess": c.get("abra_sess", ""),
            "ecto_1_sess": c.get("ecto_1_sess", ""),
        }
    except Exception as e:
        print(f"Error loading meta cookies: {e}")
        return None

def load_imagefx_cookie():
    """Load cookie for ImageFX."""
    for cf in ["imagefx_cookie.txt", "whisk_cookie.txt"]:
        cookie_file = SCRIPT_DIR / cf
        if cookie_file.exists():
            return cookie_file.read_text().strip()
    return None

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Generate Image with ImageFX
    print("\n--- STEP 1: Generate Image with ImageFX ---")
    fx_cookie = load_imagefx_cookie()
    if not fx_cookie:
        print("Error: No ImageFX cookie found.")
        sys.exit(1)
        
    print(f"Prompt: {TEST_PROMPT}")
    fx_cmd = [
        "node", str(IMAGEFX_CLI),
        "--prompt", TEST_PROMPT,
        "--ratio", "IMAGE_ASPECT_RATIO_LANDSCAPE",
        "--dir", str(TMP_DIR),
        "--cookie", fx_cookie,
        "--count", "1"
    ]
    
    start = time.time()
    try:
        result = subprocess.run(fx_cmd, capture_output=True, text=True, timeout=180, cwd=str(SCRIPT_DIR / "imageFX-api"))
        print(result.stdout)
        if result.returncode != 0:
            print(f"✗ ImageFX failed: {result.stderr or result.stdout}")
        
        # Find the image
        images = sorted(TMP_DIR.glob("image_*.png"), key=lambda p: p.stat().st_mtime)
        if not images:
            print(f"✗ No image found in {TMP_DIR}.")
            sys.exit(1)
            
        img_path = images[-1]
        print(f"✓ Image generated in {time.time() - start:.1f}s: {img_path}")
    except Exception as e:
        print(f"✗ Exception during ImageFX generation: {e}")
        sys.exit(1)
        
    # 2. Upload and Animate with Meta AI
    print("\n--- STEP 2: Animate with Meta AI ---")
    meta_cookies = load_meta_cookies()
    if not meta_cookies:
        sys.exit(1)
        
    ai = MetaAI(cookies=meta_cookies)
    print("Initializing MetaAI...")
    
    print(f"Uploading image: {img_path.name}...")
    upload_res = ai.upload_image(str(img_path))
    if not upload_res.get("success") or not upload_res.get("media_id"):
        print(f"✗ Image upload failed: {upload_res.get('error')}")
        sys.exit(1)
        
    media_id = upload_res["media_id"]
    print(f"✓ Image uploaded (ID: {media_id})")
    
    print(f"Prompting animation: {VIDEO_PROMPT}")
    start = time.time()
    try:
        # Use generate_video which handles polling
        anim_res = ai.generate_video(
            prompt=VIDEO_PROMPT,
            media_ids=[media_id],
            attachment_metadata={
                "file_size": upload_res.get("file_size"),
                "mime_type": upload_res.get("mime_type")
            },
            wait_before_poll=15,
            max_attempts=40,
            wait_seconds=5,
            verbose=True
        )
        
        if not anim_res.get("success") or not anim_res.get("video_urls"):
            print(f"✗ Animation failed: {anim_res.get('error')}")
            sys.exit(1)
            
        video_url = anim_res["video_urls"][0]
        print(f"✓ Animation generated in {time.time() - start:.1f}s: {video_url[:80]}...")
        
        # Download video
        video_path = TMP_DIR / "final_animation.mp4"
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
        print(f"✗ Exception during Meta AI animation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
