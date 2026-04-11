# How to Fix Gemini Authentication Error

## The Problem
Your Gemini cookies have expired. The error message shows:
```
Account status: UNAUTHENTICATED - Session is not authenticated or cookies have expired.
```

## Solution: Get Fresh Cookies

### Step 1: Open Gemini in Your Browser
1. Go to https://gemini.google.com
2. **Log out completely** if you're already logged in
3. **Log in again** with your Google account
4. Make sure you can actually use Gemini (send a test message)

### Step 2: Extract the Cookies

#### Option A: Using Browser DevTools (Recommended)
1. While on https://gemini.google.com, press **F12** to open Developer Tools
2. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
3. In the left sidebar, expand **Cookies** → **https://gemini.google.com**
4. Find and copy these two cookie values:
   - `__Secure-1PSID` (starts with something like "g.a000...")
   - `__Secure-1PSIDTS` (a long string)

#### Option B: Using Network Tab
1. Press **F12** and go to the **Network** tab
2. Refresh the page (F5)
3. Click any request to gemini.google.com
4. Look in the **Request Headers** section
5. Find the `Cookie:` header and copy the values of:
   - `__Secure-1PSID`
   - `__Secure-1PSIDTS`

### Step 3: Add Cookies to Your .env File

Edit the `.env` file in your project root and add:

```bash
# Gemini Authentication Cookies
# Get these from https://gemini.google.com (F12 > Application > Cookies)
SECURE_1PSID=your_actual_cookie_value_here
SECURE_1PSIDTS=your_actual_cookie_value_here
```

**Important:** 
- Remove any quotes around the cookie values
- Make sure there are no extra spaces
- The values should be very long strings

### Step 4: Restart Your Pipeline

```bash
./init_and_run.sh
```

## Why This Happens

Google's `__Secure-1PSIDTS` cookie expires frequently (sometimes within hours). The `gemini-webapi` library tries to auto-refresh it, but if your initial cookies are already expired, it can't help.

## Alternative: Use Browser Auto-Extraction

If you don't want to manually set cookies, make sure:

1. You're logged into https://gemini.google.com in your **default browser**
2. Your browser cookies are **fresh** (log out and log back in)
3. Close the browser after logging in (this helps `browser-cookie3` read the cookies)
4. Run your script immediately after

The script will automatically try to extract cookies from your browser using `browser-cookie3`.

## Troubleshooting

### "Still getting UNAUTHENTICATED error"
- Make sure you copied the **entire** cookie value (they're very long)
- Try logging out of Gemini completely and logging back in
- Check that you're using the cookies from the **same Google account** that has Gemini access

### "Can't find the cookies in DevTools"
- Make sure you're on https://gemini.google.com (not aistudio.google.com)
- Try using Chrome or Firefox (better DevTools support)
- Make sure you're actually logged in and can use Gemini

### "Cookies expire too quickly"
- This is normal behavior from Google
- The `gemini-webapi` library will auto-refresh them once initialized successfully
- You only need to manually update them when they're completely expired
