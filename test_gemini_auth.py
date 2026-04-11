#!/usr/bin/env python3
"""
Test Gemini Authentication - Diagnose cookie issues
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add Gemini-API-New to path
sys.path.insert(0, str(Path(__file__).parent / "Gemini-API-New" / "src"))

from gemini_webapi import GeminiClient
from gemini_webapi.utils.load_browser_cookies import load_browser_cookies

load_dotenv()


def check_env_cookies():
    """Check if cookies are set in environment variables."""
    print("=" * 70)
    print("1. Checking Environment Variables (.env file)")
    print("=" * 70)
    
    secure_1psid = os.getenv("SECURE_1PSID")
    secure_1psidts = os.getenv("SECURE_1PSIDTS")
    
    if secure_1psid and secure_1psidts:
        print(f"✓ SECURE_1PSID found: {secure_1psid[:20]}...{secure_1psid[-20:]}")
        print(f"✓ SECURE_1PSIDTS found: {secure_1psidts[:20]}...{secure_1psidts[-20:]}")
        return True
    elif secure_1psid:
        print(f"✓ SECURE_1PSID found: {secure_1psid[:20]}...{secure_1psid[-20:]}")
        print("✗ SECURE_1PSIDTS not found")
        return False
    else:
        print("✗ No cookies found in environment variables")
        return False


def check_browser_cookies():
    """Check if cookies can be extracted from browser."""
    print("\n" + "=" * 70)
    print("2. Checking Browser Cookies (browser-cookie3)")
    print("=" * 70)
    
    try:
        cookies = load_browser_cookies(domain_name="google.com", verbose=True)
        
        if not cookies:
            print("✗ No cookies found in any browser")
            return False
        
        print(f"\n✓ Found cookies in {len(cookies)} browser(s):")
        
        has_valid = False
        for browser, cookie_dict in cookies.items():
            print(f"\n  Browser: {browser}")
            
            psid = cookie_dict.get("__Secure-1PSID")
            psidts = cookie_dict.get("__Secure-1PSIDTS")
            
            if psid:
                print(f"    ✓ __Secure-1PSID: {psid[:20]}...{psid[-20:]}")
                has_valid = True
            else:
                print(f"    ✗ __Secure-1PSID: Not found")
            
            if psidts:
                print(f"    ✓ __Secure-1PSIDTS: {psidts[:20]}...{psidts[-20:]}")
            else:
                print(f"    ✗ __Secure-1PSIDTS: Not found")
        
        return has_valid
    
    except Exception as e:
        print(f"✗ Error loading browser cookies: {e}")
        return False


async def test_authentication():
    """Test if authentication works with current cookies."""
    print("\n" + "=" * 70)
    print("3. Testing Gemini Authentication")
    print("=" * 70)
    
    secure_1psid = os.getenv("SECURE_1PSID")
    secure_1psidts = os.getenv("SECURE_1PSIDTS")
    
    PLACEHOLDERS = ["YOUR_SECURE_1PSID_VALUE_HERE", "YOUR_SECURE_1PSIDTS_VALUE_HERE"]
    
    try:
        if secure_1psid and secure_1psidts and secure_1psid not in PLACEHOLDERS and secure_1psidts not in PLACEHOLDERS:
            print("\n→ Using cookies from environment variables...")
            client = GeminiClient(secure_1psid, secure_1psidts)
        else:
            print("\n→ Using cookies from browser (auto-extraction)...")
            client = GeminiClient()
        
        print("→ Initializing client (this may take 10-30 seconds)...")
        await client.init(timeout=60, watchdog_timeout=30)
        
        print("✓ Client initialized successfully!")
        
        # Try a simple test message
        print("\n→ Sending test message to Gemini...")
        response = await client.generate_content("Reply with just 'OK' if you can read this.")
        
        print(f"✓ Authentication successful!")
        print(f"✓ Gemini response: {response.text[:100]}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Authentication failed: {e}")
        return False


async def main():
    print("\n" + "=" * 70)
    print("GEMINI AUTHENTICATION DIAGNOSTIC TOOL")
    print("=" * 70)
    
    env_ok = check_env_cookies()
    browser_ok = check_browser_cookies()
    
    if not env_ok and not browser_ok:
        print("\n" + "=" * 70)
        print("❌ NO VALID COOKIES FOUND")
        print("=" * 70)
        print("\nYou need to provide valid Gemini cookies. Options:")
        print("\n1. Set them in .env file:")
        print("   SECURE_1PSID=your_cookie_value")
        print("   SECURE_1PSIDTS=your_cookie_value")
        print("\n2. Log into https://gemini.google.com in your browser")
        print("   (cookies will be auto-extracted)")
        print("\nSee COOKIE_REFRESH_GUIDE.md for detailed instructions.")
        return
    
    # Test authentication
    auth_ok = await test_authentication()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Environment cookies: {'✓ Found' if env_ok else '✗ Not found'}")
    print(f"Browser cookies: {'✓ Found' if browser_ok else '✗ Not found'}")
    print(f"Authentication: {'✓ Working' if auth_ok else '✗ Failed'}")
    
    if auth_ok:
        print("\n✅ Your Gemini authentication is working correctly!")
    else:
        print("\n❌ Authentication failed. Your cookies are expired or invalid.")
        print("\nNext steps:")
        print("1. Log out of https://gemini.google.com completely")
        print("2. Log back in")
        print("3. Extract fresh cookies (see COOKIE_REFRESH_GUIDE.md)")
        print("4. Run this test again")


if __name__ == "__main__":
    asyncio.run(main())
