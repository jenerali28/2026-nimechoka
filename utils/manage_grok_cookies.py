#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

TOKEN_FILE = Path("grok2api/data/token.json")

def load_tokens():
    if not TOKEN_FILE.exists():
        return {"ssoBasic": []}
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def save_tokens(data):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_cookies(cookie_strings):
    data = load_tokens()
    existing_tokens = {t["token"] for t in data["ssoBasic"]}
    
    new_count = 0
    for s in cookie_strings:
        s = s.strip()
        if not s: continue
        
        # Clean the string if it's a full cookie header
        token = s
        if "sso=" in s:
            import re
            match = re.search(r'sso=([^;]+)', s)
            if match:
                token = match.group(1)
        
        if token in existing_tokens:
            print(f"Skipping existing token: {token[:20]}...")
            continue
            
        new_token = {
            "token": token,
            "status": "active",
            "quota": 36,
            "created_at": int(time.time() * 1000),
            "last_used_at": None,
            "use_count": 0,
            "fail_count": 0,
            "last_fail_at": None,
            "last_fail_reason": None,
            "last_sync_at": None,
            "tags": [],
            "note": "Bulk added",
            "last_asset_clear_at": None
        }
        data["ssoBasic"].append(new_token)
        new_count += 1
        existing_tokens.add(token)
        
    save_tokens(data)
    print(f"Successfully added {new_count} new tokens to {TOKEN_FILE}")

def main():
    if len(sys.argv) > 1:
        # Pass tokens as arguments
        add_cookies(sys.argv[1:])
    else:
        print("--- Grok Cookie Manager ---")
        print("Paste your 'sso' cookie values here (one per line).")
        print("Press Ctrl+D (Unix) or Ctrl+Z (Windows) when finished:")
        try:
            input_data = sys.stdin.read()
            if input_data:
                add_cookies(input_data.splitlines())
        except EOFError:
            pass

if __name__ == "__main__":
    main()
