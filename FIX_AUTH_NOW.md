# 🔧 Quick Fix: Gemini Authentication Error

## What's Wrong?
Your Gemini cookies are **expired**. The error shows:
```
Account status: UNAUTHENTICATED - Session is not authenticated or cookies have expired.
```

## Quick Fix (5 minutes)

### Step 1: Test Current Status
```bash
python test_gemini_auth.py
```

This will show you exactly what's wrong with your cookies.

### Step 2: Get Fresh Cookies

1. **Open Chrome/Firefox** and go to https://gemini.google.com
2. **Log out completely** (click your profile → Sign out)
3. **Log back in** with your Google account
4. **Test Gemini** - send a message to make sure it works
5. **Press F12** to open Developer Tools
6. **Go to Application tab** (Chrome) or Storage tab (Firefox)
7. **Click Cookies** → **https://gemini.google.com**
8. **Find these two cookies:**
   - `__Secure-1PSID` 
   - `__Secure-1PSIDTS`
9. **Copy their values** (double-click the Value column, Ctrl+C)

### Step 3: Add to .env File

Edit `.env` in your project root:

```bash
# Gemini Authentication Cookies
SECURE_1PSID=paste_your_value_here
SECURE_1PSIDTS=paste_your_value_here
```

**Important:** 
- No quotes around the values
- No spaces before or after the `=`
- Copy the ENTIRE value (they're very long)

### Step 4: Test Again
```bash
python test_gemini_auth.py
```

You should see: `✅ Your Gemini authentication is working correctly!`

### Step 5: Run Your Pipeline
```bash
./init_and_run.sh
```

## Why Does This Happen?

Google's `__Secure-1PSIDTS` cookie expires frequently (sometimes within hours). The `browser-cookie3` library can extract cookies from your browser, but if those cookies are already expired, it won't help.

## Alternative: Skip Manual Cookie Setup

If you don't want to manually copy cookies:

1. Make sure you're logged into https://gemini.google.com in your **default browser**
2. **Close the browser completely** after logging in
3. Run your script **immediately**

The `browser-cookie3` library will try to extract fresh cookies automatically. But this only works if your browser cookies are fresh.

## Still Not Working?

See `COOKIE_REFRESH_GUIDE.md` for detailed troubleshooting steps.

## Quick Reference: Where to Find Cookies

### Chrome/Edge/Brave
1. F12 → Application tab
2. Cookies → https://gemini.google.com
3. Find `__Secure-1PSID` and `__Secure-1PSIDTS`

### Firefox
1. F12 → Storage tab
2. Cookies → https://gemini.google.com
3. Find `__Secure-1PSID` and `__Secure-1PSIDTS`

### Using Network Tab (Any Browser)
1. F12 → Network tab
2. Refresh page (F5)
3. Click any request
4. Look in Request Headers → Cookie
5. Find the two cookie values
