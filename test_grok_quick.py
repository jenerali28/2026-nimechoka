#!/usr/bin/env python3
"""Quick test for grok2api image and video generation."""

import json
import os
import re
import sys
import time
import requests
from pathlib import Path

API_BASE = "http://localhost:8000"
API_KEY = "grok2api"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
OUT_DIR = Path("test_outputs")
OUT_DIR.mkdir(exist_ok=True)


def test_image():
    print("\n" + "=" * 50)
    print("  TEST: Image Generation (grok-imagine-1.0)")
    print("=" * 50)

    payload = {
        "model": "grok-imagine-1.0",
        "prompt": "A lion standing on a rock at sunset, cinematic lighting, photorealistic",
        "n": 1,
        "size": "1280x720",
        "response_format": "url",
    }

    print(f"  Prompt: {payload['prompt']}")
    print("  Sending request...")
    t0 = time.time()

    try:
        resp = requests.post(f"{API_BASE}/v1/images/generations",
                             json=payload, headers=HEADERS, timeout=120)
        elapsed = time.time() - t0
        print(f"  Status: {resp.status_code} ({elapsed:.1f}s)")

        if resp.status_code != 200:
            print(f"  ERROR: {resp.text[:400]}")
            return False

        data = resp.json()
        img_entry = data.get("data", [{}])[0]
        img_url = img_entry.get("url", "")
        b64 = img_entry.get("b64_json", "")

        if img_url:
            print(f"  Got URL: {img_url[:80]}...")
            # Download it
            r = requests.get(img_url, timeout=60)
            if r.status_code == 200:
                out = OUT_DIR / "test_image.jpg"
                out.write_bytes(r.content)
                print(f"  Saved: {out} ({len(r.content)//1024} KB)")
                return True
            else:
                print(f"  Download failed: {r.status_code}")
                return False
        elif b64:
            import base64
            img_bytes = base64.b64decode(b64)
            out = OUT_DIR / "test_image.jpg"
            out.write_bytes(img_bytes)
            print(f"  Saved (b64): {out} ({len(img_bytes)//1024} KB)")
            return True
        else:
            print(f"  No image data in response: {json.dumps(data)[:300]}")
            return False

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


def test_video():
    print("\n" + "=" * 50)
    print("  TEST: Video Generation (aurora)")
    print("=" * 50)

    payload = {
        "model": "grok-imagine-1.0-video",
        "messages": [{"role": "user", "content": "A lion walking slowly through tall golden grass at sunset, cinematic, smooth motion"}],
        "stream": False,
        "video_config": {
            "aspect_ratio": "16:9",
            "video_length": 6,
            "resolution_name": "480p",
            "preset": "normal",
        },
    }

    print(f"  Prompt: {payload['messages'][0]['content']}")
    print("  Sending request (this may take 1-3 min)...")
    t0 = time.time()

    try:
        resp = requests.post(f"{API_BASE}/v1/chat/completions",
                             json=payload, headers=HEADERS, timeout=300)
        elapsed = time.time() - t0
        print(f"  Status: {resp.status_code} ({elapsed:.1f}s)")

        if resp.status_code != 200:
            print(f"  ERROR: {resp.text[:400]}")
            return False

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  Raw content: {content[:300]}")

        # Extract video URL
        video_url = None
        for pattern in [
            r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*',
            r'https?://assets\.grok\.com/[^\s"\'<>]+',
            r'src=["\']([^"\']+)["\']',
        ]:
            m = re.search(pattern, content)
            if m:
                video_url = m.group(1) if m.lastindex else m.group(0)
                break

        if not video_url:
            print(f"  Could not extract video URL from content")
            print(f"  Full response: {json.dumps(data)[:600]}")
            return False

        print(f"  Got URL: {video_url[:80]}...")
        r = requests.get(video_url, timeout=120, stream=True)
        if r.status_code == 200:
            out = OUT_DIR / "test_video.mp4"
            with open(out, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
            size_mb = out.stat().st_size / 1_048_576
            print(f"  Saved: {out} ({size_mb:.1f} MB)")
            return True
        else:
            print(f"  Download failed: {r.status_code}")
            return False

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


if __name__ == "__main__":
    print("Grok2API Quick Test")
    print(f"API: {API_BASE}")

    # Check server is up
    try:
        r = requests.get(f"{API_BASE}/v1/models", headers=HEADERS, timeout=5)
        models = [m["id"] for m in r.json().get("data", [])]
        print(f"Server OK — models: {models}")
    except Exception as e:
        print(f"Server not reachable: {e}")
        sys.exit(1)

    img_ok = test_image()
    vid_ok = test_video()

    print("\n" + "=" * 50)
    print(f"  Image: {'PASS' if img_ok else 'FAIL'}")
    print(f"  Video: {'PASS' if vid_ok else 'FAIL'}")
    print("=" * 50)
    sys.exit(0 if (img_ok and vid_ok) else 1)
