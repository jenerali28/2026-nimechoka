#!/usr/bin/env python3
"""
Script Generator — Children's Bible Story Narration.

Uses Gemini WebUI (G_3_0_PRO) with a Gem (system prompt) loaded from
style_guide.json.  The Gem contains every writing rule; the user prompt
is simply the topic.

Flow:
  1. Ensure Gemini client is initialised
  2. Load style_guide.json → build system-prompt text
  3. Create or update a "BibleStoryWriter" Gem with that text
  4. Open a chat with the Gem attached
  5. Send the topic as the user message
  6. Return the generated script
"""

import asyncio
import argparse
import json
import sys
import time
from pathlib import Path

# Resolve style_guide.json relative to this file's parent (project root)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
STYLE_GUIDE_PATH = _PROJECT_ROOT / "style_guide.json"

# Ensure gemini_webapi can be imported
_GEMINI_API_SRC = _PROJECT_ROOT / "Gemini-API-New" / "src"
if str(_GEMINI_API_SRC) not in sys.path:
    sys.path.insert(0, str(_GEMINI_API_SRC))

from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
GEM_NAME = "BibleStoryWriter"
GEM_DESCRIPTION = "Scriptwriter for animated children's Bible story YouTube channel"

# Resolve style_guide.json relative to this file's parent (project root)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
STYLE_GUIDE_PATH = _PROJECT_ROOT / "style_guide.json"


# ---------------------------------------------------------------------------
# Build system prompt from style guide
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Load style_guide.json and wrap it in the system-prompt template."""
    if not STYLE_GUIDE_PATH.exists():
        raise FileNotFoundError(
            f"style_guide.json not found at {STYLE_GUIDE_PATH}. "
            "Please create it in the project root."
        )

    with open(STYLE_GUIDE_PATH, "r", encoding="utf-8") as f:
        style_guide = json.load(f)

    system_prompt = (
        "Wewe ni mwandishi wa hadithi za Biblia kwa Kiswahili kwa chaneli ya "
        "YouTube ya watoto inayolenga watazamaji wa Tanzania wanaozungumza Kiswahili.\n\n"
        "MUHIMU: Script nzima LAZIMA iandikwe kwa Kiswahili (Kiswahili fasaha). "
        "Andika kama Mtanzania anavyoweza kusimulia hadithi kwa asili.\n\n"
        "Lazima ufuate mwongozo huu wa mitindo (style guide) kwa usahihi kabisa. Kila sheria iliyomo ni ya lazima:\n\n"
        f"{json.dumps(style_guide, indent=2, ensure_ascii=False)}\n\n"
        "Unapopewa mada ya hadithi ya Biblia, tengeneza script ambayo:\n"
        "- Imeandikwa kikamilifu kwa Kiswahili\n"
        "- Inafuata kila sheria katika mwongozo wa mitindo hapo juu\n"
        "- Ni maandishi ya kawaida yanayoendelea bila muundo, lebo, alama, au mapumziko (single continuous plain text)\n"
        "- Iko tayari kupitishwa moja kwa moja kwenye mtambo wa kutoa sauti (TTS engine)\n"
        "- Haiongezi kitu chochote ambacho hakijaelezwa katika mwongozo wa mitindo\n"
        "- Ni mwaminifu kwa chanzo cha Biblia — usivumbue matukio yasiyokuwa kwenye Biblia"
    )
    return system_prompt


# ---------------------------------------------------------------------------
# Client — with auto-reinit on cookie expiry
# ---------------------------------------------------------------------------

client = GeminiClient()
_client_initialized = False


async def _ensure_client():
    """Initialize or re-initialize the Gemini client."""
    global _client_initialized
    try:
        await client.init(timeout=300, watchdog_timeout=120)
        _client_initialized = True
    except Exception as e:
        print(f"  ⚠ Client init failed: {e}")
        _client_initialized = False
        raise


async def _reinit_client():
    """Force re-initialization (e.g., after cookie expiry)."""
    global client, _client_initialized
    print("  🔄 Re-initializing Gemini client (cookies may have expired)...")
    _client_initialized = False
    client = GeminiClient()
    await _ensure_client()


def _is_cookie_error(error: Exception) -> bool:
    """Check if an error is due to expired cookies."""
    msg = str(error).lower()
    return any(kw in msg for kw in [
        "secure_1psidts", "cookie", "expired", "failed to initialize",
        "invalid", "authentication",
    ])


# ---------------------------------------------------------------------------
# Gem management
# ---------------------------------------------------------------------------

async def _ensure_gem(system_prompt: str):
    """Create or update the BibleStoryWriter Gem.

    Returns a Gem object ready to be passed to start_chat().
    """
    global client

    print("  🔍 Checking for existing Gem...")
    try:
        gems = await client.fetch_gems()
        existing = gems.get(name=GEM_NAME)
    except Exception as e:
        print(f"  ⚠ Could not fetch gems: {e}")
        existing = None

    try:
        if existing:
            # Update the Gem if the prompt has changed
            if existing.prompt != system_prompt:
                print(f"  ✏️  Updating Gem '{GEM_NAME}' with latest style guide...")
                gem = await client.update_gem(
                    existing, name=GEM_NAME,
                    prompt=system_prompt, description=GEM_DESCRIPTION,
                )
            else:
                print(f"  ✓ Gem '{GEM_NAME}' is up to date")
                gem = existing
        else:
            print(f"  ✨ Creating new Gem '{GEM_NAME}'...")
            gem = await client.create_gem(
                name=GEM_NAME,
                prompt=system_prompt,
                description=GEM_DESCRIPTION,
            )
        return gem
    except Exception as e:
        print(f"  ⚠ Gem management failed: {e}")
        print("  🔄 Falling back to direct prompt injection...")
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


# ---------------------------------------------------------------------------
# Core Generation
# ---------------------------------------------------------------------------

async def _send_message_with_gem(user_prompt: str, gem) -> str:
    """Send a message using the Gem as system prompt, with retry logic."""
    global _client_initialized
    reinit_done = False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if not _client_initialized:
                await _ensure_client()
            chat = client.start_chat(model=Model.G_3_0_FLASH, gem=gem)
            resp = await chat.send_message(user_prompt)
            return resp.text.strip()
        except Exception as e:
            if _is_cookie_error(e) and not reinit_done:
                print(f"    🔄 Cookie error detected, re-initializing client...")
                try:
                    await _reinit_client()
                    reinit_done = True
                    continue
                except Exception as reinit_err:
                    print(f"    ❌ Re-init also failed: {reinit_err}")
            if attempt < MAX_RETRIES:
                wait = 10 * attempt
                print(f"    ⚠ Attempt {attempt} failed: {e}, retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                raise
    # Should be unreachable, but satisfies type checker
    raise RuntimeError("All retry attempts exhausted")


async def generate_bible_script(topic: str) -> str:
    """Generate a children's Bible story script using a Gem-based system prompt.

    Returns the final script text.
    """
    await _ensure_client()

    print(f"\n{'='*60}")
    print(f"  📖 Bible Script Generator — {topic}")
    print(f"{'='*60}")

    # --- Step 1: Load style guide & prepare Gem ---
    print(f"\n[1/2] Setting up style-guide Gem...")
    system_prompt = _load_system_prompt()
    gem = await _ensure_gem(system_prompt)

    # --- Step 2: Generate script ---
    print(f"\n[2/2] Generating script...")
    user_prompt = f"Andika hadithi ya Biblia kuhusu: {topic}"
    
    # If Gem management failed, wrap the user prompt inside the system prompt
    if gem is None:
        full_prompt = f"{system_prompt}\n\n=== MADA (TOPIC) ===\n{user_prompt}"
        script = await _send_message_with_gem(full_prompt, gem=None)
    else:
        script = await _send_message_with_gem(user_prompt, gem)

    final_wc = _count_words(script)
    est_minutes = final_wc / 150  # ~150 words/min for narration
    print(f"\n  📊 Final script: {final_wc} words (~{est_minutes:.1f} min narration)")

    return script


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Bible Story Script")
    parser.add_argument("topic", help="Bible story topic")
    parser.add_argument("-o", "--output", default="outputs/script/bible_script.txt",
                        help="Output file path")

    args = parser.parse_args()
    output_path = Path(args.output)

    script = asyncio.run(generate_bible_script(args.topic))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(script, encoding="utf-8")

    print(f"\n✅ Script saved: {output_path}")
    print(f"   Words: {_count_words(script)}")
