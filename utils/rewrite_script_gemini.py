#!/usr/bin/env python3
"""
Script Rewriter — Rewrite English script to Spanish via Gemini WebUI.

Takes an English transcript and uses Gemini to rewrite it into a fresh Spanish script.
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add Gemini-API-New to path
sys.path.insert(0, str(Path(__file__).parent.parent / "Gemini-API-New" / "src"))
from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = "outputs/script/spanish_script.txt"

REWRITE_SYSTEM_PROMPT = """\
You are an expert bilingual copywriter specializing in viral social media content in Spanish.

Your task is to **rewrite** an English video script into Spanish. Follow these rules strictly:

1. **DO NOT translate literally.** Rewrite the entire script using genuinely different wording, \
phrasing, and sentence structures in Spanish. It should feel like a native Spanish scriptwriter \
wrote it from scratch.

2. **KEEP THE HOOK FAITHFUL.** The opening hook (the first 1-2 sentences) must preserve the \
same energy, surprise factor, and emotional impact as the English original. The hook phrasing \
should closely mirror the English — same rhythm, similar dramatic effect — but in natural \
Spanish.

3. **MATCH THE TONE AND PACING.** If the English script is punchy and fast-paced, the Spanish \
version must also be punchy and fast-paced. Match the vibe — hype, dramatic, casual, \
informative, etc.

4. **MOVIE TRAILER NARRATION STYLE.** The script should feel like it's being read by a deep \
male voice narrating a movie trailer — fast-paced, dramatic pauses indicated by "..." or em \
dashes, short punchy sentences, building intensity.

5. **SAME STRUCTURE AND LENGTH.** Keep the same number of segments/sections. Each segment should \
cover the same topic as the English counterpart but expressed differently. IMPORTANT: Maintain \
approximately the same length and level of detail as the English script. Do not compress or \
shorten the narrative — every scene, beat, and detail should be preserved in Spanish.

6. **OUTPUT ONLY THE SPANISH SCRIPT.** No explanations, no headers, no commentary. Just the \
raw Spanish script text, ready to be narrated.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_english_script(path: Path) -> str:
    """Load the English transcript file."""
    raw = path.read_text(encoding="utf-8").strip()
    lines = raw.splitlines()
    text_lines = []
    skip_timestamps = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if "Timestamped" in stripped:
                skip_timestamps = True
            continue
        if skip_timestamps:
            continue
        if stripped:
            text_lines.append(stripped)

    result = " ".join(text_lines).strip()
    if not result:
        result = raw
    return result


async def rewrite_to_spanish(english_text: str, client: GeminiClient) -> str:
    """Send the English script to Gemini for Spanish rewriting."""
    
    print(f"  Script size: {len(english_text)} chars (~{len(english_text)//4} tokens)")
    print("  Waiting for Spanish rewrite...")

    prompt = f"""{REWRITE_SYSTEM_PROMPT}

Here is the English video script to rewrite into Spanish:

---
{english_text}
---

Rewrite this script in Spanish following all the rules. Output ONLY the Spanish script text, nothing else."""

    # Retry up to 3 times
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            chat = client.start_chat(model=Model.G_3_0_FLASH)
            response = await chat.send_message(prompt)
            
            content = response.text.strip()
            
            # Clean up any markdown fences
            content = re.sub(r"^```\w*\s*\n?", "", content)
            content = re.sub(r"\n?```\s*$", "", content)
            
            print(f"  ✅ Response received")
            return content.strip()

        except Exception as e:
            print(f"\n  ⚠ Attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                wait = 10 * attempt
                print(f"  Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                print(f"\n❌ Error: Gemini API call failed after {max_retries} attempts.")
                sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main_async():
    parser = argparse.ArgumentParser(description="Rewrite English script to Spanish via Gemini.")
    parser.add_argument("english_script", type=str, help="Path to the English transcript file")
    parser.add_argument("-o", "--output", type=str, default=DEFAULT_OUTPUT, 
                        help=f"Path to save (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--api-base", help="Ignored (signature compatibility)")

    args = parser.parse_args()
    script_path = Path(args.english_script).resolve()
    output_path = Path(args.output).resolve()

    print("=" * 60)
    print("  Script Rewriter — Gemini WebUI")
    print("=" * 60)

    # Initialize Gemini client with cookies from environment if available
    secure_1psid = os.getenv("SECURE_1PSID")
    secure_1psidts = os.getenv("SECURE_1PSIDTS")
    
    if secure_1psid and secure_1psidts:
        client = GeminiClient(secure_1psid, secure_1psidts)
        print("  🔐 Using Gemini cookies from environment variables")
    else:
        client = GeminiClient()
        print("  🔐 Using Gemini cookies from browser (browser-cookie3)")
    
    await client.init(timeout=300, watchdog_timeout=120)

    english_text = load_english_script(script_path)
    spanish_text = await rewrite_to_spanish(english_text, client)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(spanish_text, encoding="utf-8")
    
    print(f"\n✅ Spanish script ready! ({len(spanish_text)} chars)")
    print(f"   Saved to: {output_path}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
