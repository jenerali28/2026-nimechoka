# Gemini Authentication Fix - Summary

## What Was Fixed

### 1. **Authentication Issue (Status 405 Error)**
- **Problem**: The script was getting "Method Not Allowed" (405) errors when trying to use Gemini models
- **Root Cause**: 
  - Using `start_chat()` and `send_message()` was creating too many chat sessions
  - The `Model.G_3_0_FLASH` might not be available for all accounts
  - No fallback mechanism when a model fails

### 2. **Solution Implemented**
- ✅ Changed from `start_chat()` + `send_message()` to `generate_content()` (more reliable)
- ✅ Added model fallback logic - tries models in this order:
  1. `Model.UNSPECIFIED` (default model)
  2. `Model.G_3_0_FLASH` (Gemini 3.0 Flash)
  3. `Model.G_3_0_PRO` (Gemini 3.0 Pro)
- ✅ Added better error handling with retry logic
- ✅ Added environment variable support for manual cookie configuration
- ✅ Improved wait times between retries (10s, 20s, 30s)

### 3. **Files Modified**
1. **`utils/multimodal_orchestrator.py`**
   - Added dotenv support for manual cookies
   - Changed API calls from chat-based to direct content generation
   - Added model fallback logic for character profiles, image prompts, and video prompts
   - Improved error messages

2. **`utils/rewrite_script_gemini.py`**
   - Added dotenv support for manual cookies
   - Added fallback to browser cookies if env vars not set

3. **`requirements.txt`**
   - Added `python-dotenv>=1.0.0` for environment variable support

4. **`.env`** (created)
   - Template for manual cookie configuration (optional)

5. **`test_gemini_auth.py`** (created)
   - Diagnostic tool to test authentication

6. **`COOKIE_REFRESH_GUIDE.md`** (created)
   - Step-by-step guide for refreshing cookies manually

## Current Status

### ✅ Working
- Authentication is successful
- Client initialization works with Firefox browser cookies
- Model fallback mechanism is functioning
- No more "UNAUTHENTICATED" errors

### ⏳ In Progress
- Gemini API responses are slow (this is normal for large prompts)
- The script is currently running and waiting for responses
- With 212 clips in 27 batches, expect ~30-60 minutes total processing time

## How to Use

### Option 1: Automatic (Current Setup - Working)
Your Firefox browser cookies are being used automatically. Just make sure:
1. You're logged into https://gemini.google.com in Firefox
2. Your session is active (refresh the page occasionally)

### Option 2: Manual Cookies (If Automatic Fails)
1. Get fresh cookies from https://gemini.google.com:
   - Press F12 → Application tab → Cookies
   - Copy `__Secure-1PSID` and `__Secure-1PSIDTS`

2. Edit `.env` file:
   ```bash
   SECURE_1PSID=your_cookie_value_here
   SECURE_1PSIDTS=your_cookie_value_here
   ```

3. Run your pipeline again

## Testing

### Quick Authentication Test
```bash
source .venv/bin/activate
python test_gemini_auth.py
```

### Test with Small Batch
```bash
source .venv/bin/activate
python utils/multimodal_orchestrator.py \
  "outputs/Why it Sucks to Be an Egyptian Concubine/Why it Sucks to Be an Egyptian Concubine_preview.mp4" \
  "outputs/Why it Sucks to Be an Egyptian Concubine/analysis.yaml" \
  "outputs/Why it Sucks to Be an Egyptian Concubine/prompts.yaml" \
  --clip-count 8 \
  --script "outputs/Why it Sucks to Be an Egyptian Concubine/spanish_script.txt" \
  --transcript "outputs/Why it Sucks to Be an Egyptian Concubine/english_script.txt" \
  --duration 837.845624
```

### Run Full Pipeline
```bash
./init_and_run.sh
```

## Troubleshooting

### If you still get 405 errors:
1. Your account might have rate limits - wait 10-15 minutes
2. Try using manual cookies instead of browser auto-extraction
3. Check if you can use Gemini normally in your browser

### If responses are very slow:
- This is normal for large prompts (8 scenes per batch)
- Gemini free tier has rate limits
- Consider reducing batch size or clip count for testing

### If authentication fails:
1. Log out of https://gemini.google.com completely
2. Log back in
3. Close and reopen Firefox
4. Try the test script again

## Performance Notes

- **Character Profile**: ~30-60 seconds (1 API call)
- **Image Prompts**: ~5-10 seconds per batch of 8 scenes
- **Video Prompts**: ~5-10 seconds per batch of 8 scenes
- **Total for 212 clips**: ~30-60 minutes (27 batches × 2 passes)

The script will automatically retry failed batches up to 3 times with increasing wait times.
