#!/usr/bin/env python3
"""
Title Generator — YouTube-Worthy Swahili Bible Video Titles.

Uses Gemini WebUI (G_3_0_PRO) to generate multiple title candidates,
then picks the best one for maximum CTR.
"""

import asyncio
import argparse
import re
import sys
from pathlib import Path

from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TITLE_PROMPT = """\
Unazalisha kichwa cha video kwa YouTube kwa Kiswahili.

MADA YA BIBLIA: {topic}

Tengeneza vichwa 5 tofauti vya video kwa mada hii. Kila kichwa lazima:
1. Kiwe katika Kiswahili fasaha (audience ya Tanzania)
2. Kiwe cha kuvutia sana — mtu lazima atake kubonyeza
3. Kitumie emoji 1-2 zinazofaa
4. Kisiwe zaidi ya herufi 60
5. Kionyeshe drama, siri, au hisia kali
6. Kisiwe na maneno ya kawaida kama "somo" au "mafunzo" — kiwe kama movie trailer

MIFANO YA VICHWA VYEMA:
- "Mungu Alimjaribu Abrahamu Kwa Njia Hii 😱🔥"
- "Siku Bahari Ilipasuka — Musa na Hali ya Kutisha ⚡"
- "Kijana Huyu Aliuzwa na Ndugu Zake... Lakini Hatima Yake 🤯"

Andika vichwa 5 tu, moja kwa kila mstari. Hakuna maelezo zaidi.
"""

SELECT_PROMPT = """\
Hivi ni vichwa 5 vya video kwa YouTube kuhusu mada ya Biblia.
Chagua kichwa KIMOJA bora zaidi — kile ambacho kitapata clicks nyingi zaidi.

{titles}

Jibu na kichwa kilichochaguliwa TU — mstari mmoja, bila maelezo.
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

client = GeminiClient()


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

async def generate_title(topic: str) -> str:
    """Generate a YouTube-worthy Swahili title for a Bible story topic."""
    await client.init(timeout=120, watchdog_timeout=60)

    MAX_RETRIES = 3

    # --- Step 1: Generate 5 candidates ---
    candidates = []
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  🏷️  Generating title candidates (attempt {attempt})...")
            chat = client.start_chat(model=Model.G_3_0_PRO)
            resp = await chat.send_message(TITLE_PROMPT.format(topic=topic))
            raw = resp.text.strip()

            # Parse lines — each non-empty line is a title candidate
            for line in raw.splitlines():
                line = line.strip()
                # Remove leading numbering (1., 2., -, etc)
                line = re.sub(r'^[\d]+[.)]\s*', '', line)
                line = re.sub(r'^[-•]\s*', '', line)
                line = line.strip('"\'').strip()
                if line and len(line) > 5:
                    candidates.append(line)

            if candidates:
                break
        except Exception as e:
            print(f"  ⚠ Title generation attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(5 * attempt)

    if not candidates:
        # Fallback: simple descriptive title
        fallback = f"Hadithi ya Biblia: {topic} 📖"
        print(f"  ⚠ No candidates generated, using fallback: {fallback}")
        return fallback

    print(f"  📝 Got {len(candidates)} title candidates")
    for i, c in enumerate(candidates, 1):
        print(f"     {i}. {c}")

    # --- Step 2: Pick the best ---
    if len(candidates) == 1:
        best = candidates[0]
    else:
        titles_text = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates, 1))
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                chat2 = client.start_chat(model=Model.G_3_0_PRO)
                resp2 = await chat2.send_message(SELECT_PROMPT.format(titles=titles_text))
                best = resp2.text.strip().strip('"\'').strip()
                # Verify the AI picked one of our candidates
                if best and len(best) > 5:
                    break
            except Exception as e:
                print(f"  ⚠ Title selection attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(5 * attempt)
                best = candidates[0]  # fallback to first

    print(f"  ✅ Selected title: {best}")
    return best


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate YouTube Swahili Bible Title")
    parser.add_argument("topic", help="Bible story topic")
    parser.add_argument("-o", "--output", help="Save title to file")

    args = parser.parse_args()

    print("=" * 60)
    print("  Bible Title Generator — Gemini G_3_0_PRO")
    print("=" * 60)

    title = asyncio.run(generate_title(args.topic))

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(title, encoding="utf-8")
        print(f"  Saved to: {out}")
