import sys
import os
import json
import logging
import time
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)

# Add the src directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'metaai-api/src')))

from metaai_api import VideoGenerator
from metaai_api.html_scraper import MetaAIHTMLScraper

# Provided cookies
cookie_string = "datr=bw-IaXiI_Pi1DIHlSMX3fa98;ecto_1_sess=fec0fa5b-e17a-4386-b1d8-c28a49871b15.v1%3ADb6pL9Uix23W1Ng9LMKG_qvjzpD7Xr8VsR6q-pFgdlrlu_qbBHL-SmiEYogk-BUYdYcP34ydkgpYeYYVVanK8ybk2uWVyx0Y8nON0yCe8QvdPEMEMj_Y1evzt-h53BoogZ74cdhK70y_K5tgHQv8z5s12bIqmEEczy17z_0uI6dWbE9N6E9stqHhgu5D8W-53TviKav1_WbjhMjg_2lCV5I3Xnfp_jMM92_w_zdrgIYgUfI6bOCts0-w6KdR0V6Ax_EAesv0r0dbJL2Zm-BX09MJ2hGuLi-pMXOHU_6_5v-cQwYsXiPD9mv3FjV2zqojYCK7J8-VKBDr40kmVdAybmBEVlnc3a1_t042N7aY-8L3HVxhf7rrhee-1RuyAcSeB2BZzUxb6rnSwF9fXvccsfqv9smWGRy7yx-qxFOCSFzPtwwgMJbeE9pCHZAfDyKAzbKxWF91ZQ4Ax6ruyS8Rayq0cXe4-qfOmy4HE9jHcUMd5N-ESxdpSren_TmWVo1d%3AlwtRJJj3geMYdtrA%3AagxWr4iAx-pHG_DCSQaozQ.FRCv5pQ-3NKwnv85mRXqcPuGWeWjq7hweS2vTT5npgI;ps_l=1;wd=1358x644;abra_sess=FrqF7evn5cwDFhIYDkxXVG5mbmlhWnptbFN3FuaWxZgNAA%3D%3D;dpr=1;ps_n=1;rd_challenge=Q_6hBQNY5mWo7vKO_VcYROgqz0jg6Ogdrya_1XMEBR3gvfMY_pUQcbO2-bNTTJmFu4RWuyVexBpDlnYCNKLqR5W3kEo"

# Parse cookies for session
cookies = {}
for item in cookie_string.split(';'):
    if '=' in item:
        key, value = item.strip().split('=', 1)
        cookies[key] = value

# Initialize VideoGenerator
generator = VideoGenerator(cookies_str=cookie_string)

# Test prompt
prompt = "A majestic lion walking through the African savanna at sunset"
print(f"Submitting video request with prompt: {prompt}")

# Step 1: Submit request
conversation_id = generator.create_video_generation_request(prompt_text=prompt)

if conversation_id:
    print(f"✅ Request submitted! Conversation ID: {conversation_id}")
    print(f"🔗 View progress at: https://www.meta.ai/prompt/{conversation_id}")
    
    # Step 2: Use HTML scraper to find the video URL
    print("Initializing HTML scraper for polling...")
    session = requests.Session()
    session.cookies.update(cookies)
    scraper = MetaAIHTMLScraper(session)
    
    print("Waiting 15 seconds for initial processing...")
    time.sleep(15)
    
    print("Polling conversation page for video URLs...")
    videos = scraper.fetch_video_urls_from_page(conversation_id, max_attempts=15, wait_seconds=10)
    
    if videos:
        print(f"✅ SUCCESS! Found {len(videos)} video(s):")
        for i, v in enumerate(videos, 1):
            print(f"   {i}. {v['url']}")
    else:
        print("❌ FAILED: No video URLs found via HTML scraping after polling.")
else:
    print("❌ FAILED: Could not submit video generation request.")
