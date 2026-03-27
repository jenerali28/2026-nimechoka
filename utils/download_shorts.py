#!/usr/bin/env python3
import argparse
import os
import sys
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INPUT_DIR = Path("input_videos")
DEFAULT_LIMIT = 5

# ---------------------------------------------------------------------------
# Downloader Logic
# ---------------------------------------------------------------------------

def download_videos(urls, limit=DEFAULT_LIMIT):
    """Download YouTube videos using yt-dlp."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Base command
    # Use sys.executable -m yt_dlp to ensure we use the version in the venv
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--max-downloads", str(limit),
        "-o", f"{INPUT_DIR}/%(title)s.%(ext)s",
        "--no-playlist" if len(urls) > 1 else "",
        "--cookies-from-browser", "firefox"
    ]
    
    # Filter out empty strings
    cmd = [c for c in cmd if c]
    
    # Add URLs
    cmd.extend(urls)
    
    print(f"🚀 Starting bulk download into {INPUT_DIR}...")
    print(f"   Limit: {limit} videos")
    
    try:
        subprocess.run(cmd, check=True)
        print("\n✅ Download process complete.")
    except subprocess.CalledProcessError as e:
        if e.returncode == 101:
            print("\n✅ Download limit reached (expected).")
        else:
            print(f"\n❌ Error during download: {e}")
            sys.exit(1)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bulk YouTube Video Downloader")
    parser.add_argument("urls", nargs="+", help="YouTube URL(s) or Channel URL")
    parser.add_argument("-l", "--limit", type=int, default=DEFAULT_LIMIT, help=f"Max videos to download (default: {DEFAULT_LIMIT})")
    
    args = parser.parse_args()
    
    download_videos(args.urls, args.limit)

if __name__ == "__main__":
    main()
