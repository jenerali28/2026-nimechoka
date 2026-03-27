#!/usr/bin/env python3
"""
Script Rewriter — Rewrite English script to Spanish via NVIDIA NIM (DeepSeek V3.1).

Takes an English transcript and uses NVIDIA NIM's DeepSeek V3.1 model
to rewrite it into a fresh Spanish script.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from openai import OpenAI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NVIDIA_API_KEY = "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"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "deepseek-ai/deepseek-v3.1"
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

5. **SAME STRUCTURE.** Keep the same number of segments/sections. Each segment should cover \
the same topic as the English counterpart but expressed differently.

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

def rewrite_to_spanish(english_text: str, model: str) -> str:
    """Send the English script to NVIDIA NIM for Spanish rewriting using DeepSeek V3.1."""
    client = OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        timeout=300.0,  # 5 min timeout for large scripts
    )

    print(f"  Sending request to NVIDIA NIM ({model})...")
    print(f"  Script size: {len(english_text)} chars (~{len(english_text)//4} tokens)")
    print("  Waiting for Spanish rewrite...")

    messages = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Here is the English video script to rewrite into Spanish:\n\n---\n{english_text}\n---\n\nRewrite this script in Spanish following all the rules. Output ONLY the Spanish script text, nothing else."}
    ]

    # Retry up to 3 times with backoff
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        start = time.time()
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                top_p=0.7,
                max_tokens=16384,
                stream=False,
            )

            content = completion.choices[0].message.content
            elapsed = time.time() - start
            print(f"  Response received in {elapsed:.1f}s")

            # Clean up any markdown fences
            content = content.strip()
            content = re.sub(r"^```\w*\s*\n?", "", content)
            content = re.sub(r"\n?```\s*$", "", content)
            return content.strip()

        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  ⚠ Attempt {attempt}/{max_retries} failed after {elapsed:.1f}s: {e}")
            if attempt < max_retries:
                wait = 10 * attempt
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"\nError: NVIDIA API call failed after {max_retries} attempts.")
                sys.exit(1)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Rewrite English script to Spanish via NVIDIA NIM.")
    parser.add_argument("english_script", type=str, help="Path to the English transcript file")
    parser.add_argument("-o", "--output", type=str, default=DEFAULT_OUTPUT, help=f"Path to save (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})")
    parser.add_argument("--api-base", help="Ignored (signature compatibility)")

    args = parser.parse_args()
    script_path = Path(args.english_script).resolve()
    output_path = Path(args.output).resolve()

    print("=" * 60)
    print("  Script Rewriter — DeepSeek V3.1 @ NVIDIA NIM")
    print("=" * 60)

    english_text = load_english_script(script_path)
    spanish_text = rewrite_to_spanish(english_text, args.model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(spanish_text, encoding="utf-8")
    
    print(f"\n✅ Spanish script ready! ({len(spanish_text)} chars)")
    print(f"   Saved to: {output_path}")

if __name__ == "__main__":
    main()
