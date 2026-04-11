# Gemini Authentication Fix

## Problem
The `gemini_webapi` client is failing with an authentication error:
```
AuthError: Failed to initialize client after 2 attempts. SECURE_1PSIDTS could get expired frequently, please make sure cookie values are up to date.
```

This happens because the Google Gemini cookies have expired.

## Solution

### Step 1: Get Fresh Cookies from Google Gemini

1. Open your browser and go to https://gemini.google.com
2. Log in with your Google account
3. Press **F12** to open Developer Tools
4. Go to the **Network** tab
5. Refresh the page (F5 or Ctrl+R)
6. Click on any request in the Network tab
7. Look for the **Cookies** section in the request headers
8. Find and copy these two cookie values:
   - `__Secure-1PSID`
   - `__Secure-1PSIDTS`

### Step 2: Update the .env File

Open the `.env` file in the root directory and replace the placeholder values:

```bash
# Gemini Authentication Cookies
# Get these from https://gemini.google.com (F12 > Network > Copy cookies)
SECURE_1PSID=your_actual_secure_1psid_value_here
SECURE_1PSIDTS=your_actual_secure_1psidts_value_here

# Grok2API Configuration
LOG_LEVEL=DEBUG
```

**Important:** 
- Copy the FULL cookie values (they're usually very long strings)
- Don't include quotes around the values
- Don't add spaces before or after the `=` sign

### Step 3: Install python-dotenv

The scripts now need `python-dotenv` to read the environment variables:

```bash
# If using uv (recommended):
uv pip install python-dotenv

# Or using regular pip:
pip install python-dotenv
```

Or install all requirements:
```bash
uv pip install -r requirements.txt
```

### Step 4: Run Your Pipeline Again

Now you can run your pipeline:

```bash
./init_and_run.sh
```

## Alternative: Use Browser Cookies Automatically

If you have `browser-cookie3` installed and you're logged into Gemini in your browser, the scripts will try to use those cookies automatically. However, this method is less reliable because:

1. Browser cookies expire frequently
2. Different browsers store cookies differently
3. It requires the browser to be on the same machine

**To use this method:**
```bash
pip install browser-cookie3
```

Then make sure you're logged into https://gemini.google.com in your browser before running the scripts.

## Troubleshooting

### "Cookies still expired after updating .env"

1. Make sure you copied the FULL cookie values (they're very long)
2. Check that there are no extra spaces or quotes in the .env file
3. Try getting fresh cookies again (they expire quickly)
4. Make sure the .env file is in the root directory of the project

### "ModuleNotFoundError: No module named 'dotenv'"

Install python-dotenv:
```bash
uv pip install python-dotenv
```

### "Still getting authentication errors"

The cookies expire frequently (sometimes within hours). You may need to:
1. Get fresh cookies again
2. Consider using a dedicated Google account for API access
3. Close your browser after copying cookies (this can extend their lifetime)

## What Changed

The following files were updated to support environment variable authentication:

1. **utils/multimodal_orchestrator.py** - Now reads cookies from environment variables
2. **utils/rewrite_script_gemini.py** - Now reads cookies from environment variables
3. **requirements.txt** - Added `python-dotenv>=1.0.0`
4. **.env** - Created with cookie placeholders

## Security Note

⚠️ **Never commit your .env file to git!** 

The `.env` file should already be in `.gitignore`. Your cookies are sensitive credentials that give access to your Google account.
